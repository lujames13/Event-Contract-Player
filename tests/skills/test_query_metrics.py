import pytest
import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 將專案根目錄加入 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / ".claude" / "skills" / "analyst" / "scripts"))

from query_metrics import handle_da, handle_pnl, handle_drift, handle_calibration, handle_gate3


@pytest.fixture
def temp_db(tmp_path):
    """建立測試用的 SQLite DB"""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)

    # 建立 prediction_signals 表
    conn.execute("""
        CREATE TABLE prediction_signals (
            id TEXT, strategy_name TEXT, timestamp TEXT, timeframe_minutes INTEGER,
            direction TEXT, confidence FLOAT, current_price FLOAT, expiry_time TEXT,
            actual_direction TEXT, close_price FLOAT, is_correct BOOLEAN,
            traded BOOLEAN, trade_id TEXT, alpha FLOAT, created_at TEXT
        )
    """)

    # 建立 pm_orders 表
    conn.execute("""
        CREATE TABLE pm_orders (
            order_id TEXT, signal_id TEXT, placed_at TEXT,
            pnl FLOAT, strategy_name TEXT, timeframe_minutes INTEGER
        )
    """)

    # 插入測試數據（100 筆 signals，60% 正確）
    now = datetime.now(timezone.utc)
    signals = []
    trades = []

    for i in range(100):
        t = now - timedelta(hours=100 - i)
        is_correct = i < 60  # 前 60 筆正確
        confidence = 0.55 + (0.2 * (i / 100))  # 0.55 到 0.75
        pnl = 10.0 if is_correct else -9.0

        signal_id = f"s{i}"
        trade_id = f"t{i}"

        signals.append((
            signal_id, "pm_v1", t.isoformat(), 5, "higher",
            confidence, 50000, (t + timedelta(minutes=5)).isoformat(),
            "higher" if is_correct else "lower", 50100 if is_correct else 49900,
            is_correct, True, trade_id, 0.03, t.isoformat()
        ))

        trades.append((
            trade_id, signal_id, t.isoformat(), pnl, "pm_v1", 5
        ))

    conn.executemany("INSERT INTO prediction_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", signals)
    conn.executemany("INSERT INTO pm_orders VALUES (?, ?, ?, ?, ?, ?)", trades)

    conn.commit()
    conn.close()

    return str(db_path)


@pytest.fixture
def args_base(temp_db):
    """基礎參數物件"""
    class Args:
        def __init__(self):
            self.db_path = temp_db
            self.strategy = None
            self.timeframe = None
            self.days = None
            self.last = None
            self.window = 50

    return Args()


def test_handle_da_basic(args_base):
    """測試 DA 子命令基本功能"""
    result = handle_da(args_base)

    assert "error" not in result
    assert "overall_da" in result
    assert "total" in result
    assert "correct" in result
    assert "ci_95" in result
    assert "by_timeframe" in result

    # 驗證數值範圍
    assert result["total"] == 100
    assert result["correct"] == 60
    assert 0.0 <= result["overall_da"] <= 1.0
    assert result["ci_95"] >= 0.0


def test_handle_da_with_last(args_base):
    """測試 DA 的 --last N 參數"""
    args_base.last = 20

    result = handle_da(args_base)

    assert "error" not in result
    assert result["total"] == 20  # 只取最後 20 筆


def test_handle_da_with_strategy_filter(args_base):
    """測試策略篩選"""
    args_base.strategy = "pm_v1"

    result = handle_da(args_base)

    assert "error" not in result
    assert result["total"] == 100


def test_handle_da_nonexistent_strategy(args_base):
    """測試不存在的策略"""
    args_base.strategy = "nonexistent"

    result = handle_da(args_base)

    assert "error" in result


def test_handle_pnl_basic(args_base):
    """測試 PnL 子命令基本功能"""
    result = handle_pnl(args_base)

    assert "error" not in result
    assert "total_pnl" in result
    assert "total_trades" in result
    assert "win_rate" in result
    assert "avg_win" in result
    assert "avg_loss" in result
    assert "profit_factor" in result
    assert "max_drawdown" in result

    # 驗證基本邏輯
    assert result["total_trades"] == 100
    assert result["win_rate"] == 0.6  # 60% 勝率

    # 確保裁剪掉了 daily_pnl 和 cumulative_pnl
    assert "daily_pnl" not in result
    assert "cumulative_pnl" not in result


def test_handle_drift_basic(args_base):
    """測試 Drift 子命令基本功能"""
    result = handle_drift(args_base)

    assert "error" not in result
    assert "is_degrading" in result
    assert "trend_slope" in result
    assert "best_window" in result
    assert "worst_window" in result

    # 驗證 window 結構
    assert "start_idx" in result["best_window"]
    assert "end_idx" in result["best_window"]
    assert "da" in result["best_window"]

    # 確保裁剪掉了 rolling_da 陣列
    assert "rolling_da" not in result


def test_handle_drift_custom_window(args_base):
    """測試自定義 window size"""
    args_base.window = 30

    result = handle_drift(args_base)

    assert "error" not in result
    # 驗證 window 結束索引的間距
    assert result["best_window"]["end_idx"] - result["best_window"]["start_idx"] == 30


def test_handle_calibration_basic(args_base):
    """測試 Calibration 子命令基本功能"""
    result = handle_calibration(args_base)

    assert "error" not in result
    assert "brier_score" in result
    assert "baseline_brier" in result
    assert "reliability_buckets" in result

    # 驗證 Brier Score 範圍
    assert 0.0 <= result["brier_score"] <= 1.0
    assert 0.0 <= result["baseline_brier"] <= 1.0

    # 驗證 buckets 結構
    if len(result["reliability_buckets"]) > 0:
        bucket = result["reliability_buckets"][0]
        assert "expected" in bucket
        assert "actual" in bucket
        assert "count" in bucket
        assert "deviation" in bucket


def test_handle_gate3_basic(args_base):
    """測試 Gate3 子命令基本功能"""
    result = handle_gate3(args_base)

    assert "error" not in result
    assert "da_above_breakeven" in result
    assert "trades_above_200" in result
    assert "pnl_positive" in result
    assert "overall" in result
    assert "da_value" in result
    assert "total_trades" in result
    assert "total_pnl" in result
    assert "breakeven_winrate" in result

    # 驗證布林值
    assert isinstance(result["da_above_breakeven"], bool)
    assert isinstance(result["trades_above_200"], bool)
    assert isinstance(result["pnl_positive"], bool)

    # 驗證 overall 狀態
    assert result["overall"] in ["PASS", "FAIL", "PARTIAL", "INSUFFICIENT_DATA"]

    # 驗證數值
    assert result["total_trades"] == 100
    assert result["breakeven_winrate"] > 0.0


def test_db_not_exist():
    """測試 DB 不存在的錯誤處理"""
    class Args:
        def __init__(self):
            self.db_path = "nonexistent_db.db"
            self.strategy = None
            self.timeframe = None
            self.days = None
            self.last = None
            self.window = 50

    args = Args()

    # 所有子命令都應該返回錯誤而非 crash
    da_result = handle_da(args)
    assert "error" in da_result

    pnl_result = handle_pnl(args)
    assert "error" in pnl_result

    drift_result = handle_drift(args)
    assert "error" in drift_result

    cal_result = handle_calibration(args)
    assert "error" in cal_result

    gate3_result = handle_gate3(args)
    assert "error" in gate3_result


def test_json_serializable(args_base):
    """測試所有輸出都可以被序列化為 JSON"""
    results = [
        handle_da(args_base),
        handle_pnl(args_base),
        handle_drift(args_base),
        handle_calibration(args_base),
        handle_gate3(args_base),
    ]

    for result in results:
        try:
            json_str = json.dumps(result)
            # 確保可以反序列化
            json.loads(json_str)
        except (TypeError, ValueError) as e:
            pytest.fail(f"Result is not JSON serializable: {e}")


def test_da_last_exceeds_total(args_base):
    """測試 --last 大於總數的情況"""
    args_base.last = 200  # 大於實際的 100 筆

    result = handle_da(args_base)

    assert "error" not in result
    assert result["total"] == 100  # 應該返回所有數據
