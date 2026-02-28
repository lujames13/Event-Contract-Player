#!/usr/bin/env python3
"""
Analyst Agent 專用快查工具

用法：PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py <subcommand> [options]

子命令：
  da           - 方向準確率快查
  pnl          - PnL 摘要
  drift        - Concept Drift 檢查
  calibration  - 校準檢查
  gate3        - Gate 3 通過狀態快照
  full-refresh - 產生完整報告
"""

import argparse
import json
import sys
import subprocess
from pathlib import Path
from typing import Optional

try:
    import yaml
    from btc_predictor.analytics.extractors import get_signal_dataframe, get_trade_dataframe
    from btc_predictor.analytics.metrics import (
        compute_directional_accuracy,
        compute_pnl_metrics,
        compute_drift_detection,
        compute_confidence_calibration,
    )
except ImportError as e:
    print(json.dumps({"error": f"Import error: {e}. Make sure PYTHONPATH=src is set."}), file=sys.stderr)
    sys.exit(1)


def load_project_constants() -> dict:
    """載入 project_constants.yaml"""
    try:
        config_path = Path("config/project_constants.yaml")
        if not config_path.exists():
            return {}
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        return {}


def handle_da(args) -> dict:
    """方向準確率快查"""
    try:
        df = get_signal_dataframe(
            db_path=args.db_path,
            strategy_name=args.strategy,
            timeframe_minutes=args.timeframe,
            settled_only=True,
            days=args.days,
        )

        if df.empty:
            return {"error": "No settled signals found"}

        # 如果有 --last 參數，只取最近 N 筆
        last = getattr(args, 'last', None)
        if last and last > 0:
            df = df.tail(last)

        # 計算整體 DA
        result = compute_directional_accuracy(df)
        overall = result.get("overall", {})

        # 按 timeframe 分組計算（如果沒有指定 timeframe）
        by_timeframe = {}
        if not args.timeframe and "timeframe_minutes" in df.columns:
            tf_result = compute_directional_accuracy(df, groupby=["timeframe_minutes"])
            by_timeframe = tf_result.get("by_group", {})

        return {
            "overall_da": overall.get("da", 0.0),
            "total": overall.get("total", 0),
            "correct": overall.get("correct", 0),
            "ci_95": overall.get("ci_95", 0.0),
            "by_timeframe": by_timeframe,
        }

    except Exception as e:
        return {"error": str(e)}


def handle_pnl(args) -> dict:
    """PnL 摘要"""
    try:
        df = get_trade_dataframe(
            db_path=args.db_path,
            strategy_name=args.strategy,
            days=args.days,
        )

        if df.empty:
            return {"error": "No trades found"}

        result = compute_pnl_metrics(df)

        # 裁剪掉 daily_pnl 和 cumulative_pnl 陣列以節省 token
        return {
            "total_pnl": result.get("total_pnl", 0.0),
            "total_trades": result.get("total_trades", 0),
            "win_rate": result.get("win_rate", 0.0),
            "avg_win": result.get("avg_win", 0.0),
            "avg_loss": result.get("avg_loss", 0.0),
            "profit_factor": result.get("profit_factor", 0.0),
            "max_drawdown": result.get("max_drawdown", 0.0),
        }

    except Exception as e:
        return {"error": str(e)}


def handle_drift(args) -> dict:
    """Concept Drift 檢查"""
    try:
        df = get_signal_dataframe(
            db_path=args.db_path,
            strategy_name=args.strategy,
            timeframe_minutes=args.timeframe,
            settled_only=True,
            days=args.days,
        )

        if df.empty:
            return {"error": "No settled signals found"}

        window_size = args.window if args.window else 50
        result = compute_drift_detection(df, window_size=window_size)

        # 裁剪掉 rolling_da 陣列，只保留關鍵資訊
        return {
            "is_degrading": result.get("is_degrading", False),
            "trend_slope": result.get("trend_slope", 0.0),
            "best_window": result.get("best_window", {}),
            "worst_window": result.get("worst_window", {}),
        }

    except Exception as e:
        return {"error": str(e)}


def handle_calibration(args) -> dict:
    """校準檢查"""
    try:
        df = get_signal_dataframe(
            db_path=args.db_path,
            strategy_name=args.strategy,
            timeframe_minutes=args.timeframe,
            settled_only=True,
            days=args.days,
        )

        if df.empty:
            return {"error": "No settled signals found"}

        result = compute_confidence_calibration(df)

        return {
            "brier_score": result.get("brier_score", 0.0),
            "baseline_brier": result.get("baseline_brier", 0.0),
            "reliability_buckets": result.get("buckets", []),
        }

    except Exception as e:
        return {"error": str(e)}


def handle_gate3(args) -> dict:
    """Gate 3 通過狀態快照"""
    try:
        # 取得 DA
        da_result = handle_da(args)
        if "error" in da_result:
            return da_result

        # 取得 PnL
        pnl_result = handle_pnl(args)
        if "error" in pnl_result:
            return pnl_result

        # 從 project_constants.yaml 取得 breakeven_winrate
        constants = load_project_constants()
        polymarket_config = constants.get("polymarket", {})
        breakeven_config = polymarket_config.get("breakeven_winrate", {})

        # 預設使用 taker_at_p50 的 breakeven（最保守估計）
        breakeven_winrate = breakeven_config.get("taker_at_p50", 0.5156)

        # 檢查各項條件
        da_value = da_result.get("overall_da", 0.0)
        total_trades = pnl_result.get("total_trades", 0)
        total_pnl = pnl_result.get("total_pnl", 0.0)

        da_above_breakeven = da_value > breakeven_winrate
        trades_above_200 = total_trades >= 200
        pnl_positive = total_pnl > 0

        # 判斷整體狀態
        if da_above_breakeven and trades_above_200 and pnl_positive:
            overall_status = "PASS"
        elif not trades_above_200:
            overall_status = "INSUFFICIENT_DATA"
        elif da_above_breakeven or pnl_positive:
            overall_status = "PARTIAL"
        else:
            overall_status = "FAIL"

        return {
            "da_above_breakeven": da_above_breakeven,
            "trades_above_200": trades_above_200,
            "pnl_positive": pnl_positive,
            "overall": overall_status,
            "da_value": da_value,
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "breakeven_winrate": breakeven_winrate,
        }

    except Exception as e:
        return {"error": str(e)}


def handle_full_refresh(args) -> dict:
    """產生完整報告（會寫入檔案）"""
    try:
        # 建立參數列表
        compute_metrics_args = ["python", "scripts/polymarket/compute_metrics.py"]

        if args.strategy:
            compute_metrics_args.extend(["--strategy", args.strategy])
        if args.timeframe:
            compute_metrics_args.extend(["--timeframe", str(args.timeframe)])
        if args.days:
            compute_metrics_args.extend(["--days", str(args.days)])
        if args.db_path != "data/btc_predictor.db":
            compute_metrics_args.extend(["--db-path", args.db_path])

        # 執行 compute_metrics.py
        result1 = subprocess.run(
            compute_metrics_args,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src"}
        )

        if result1.returncode != 0:
            return {"error": f"compute_metrics.py failed: {result1.stderr}"}

        # 執行 generate_report.py
        result2 = subprocess.run(
            ["python", "scripts/polymarket/generate_report.py"],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src"}
        )

        if result2.returncode != 0:
            return {"error": f"generate_report.py failed: {result2.stderr}"}

        return {
            "status": "ok",
            "metrics_json": "reports/polymarket/metrics.json",
            "report_md": "reports/polymarket/metrics_report.md",
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Analyst Agent 專用快查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")
    subparsers.required = True

    # 通用參數函數
    def add_common_args(p):
        p.add_argument("--db-path", default="data/btc_predictor.db", help="DB 路徑")
        p.add_argument("--strategy", help="策略名稱篩選")
        p.add_argument("--timeframe", type=int, help="Timeframe 篩選（分鐘）")
        p.add_argument("--days", type=int, help="回看天數")

    # da 子命令
    p_da = subparsers.add_parser("da", help="方向準確率快查")
    add_common_args(p_da)
    p_da.add_argument("--last", type=int, help="只看最近 N 筆 settled signals")

    # pnl 子命令
    p_pnl = subparsers.add_parser("pnl", help="PnL 摘要")
    add_common_args(p_pnl)

    # drift 子命令
    p_drift = subparsers.add_parser("drift", help="Concept Drift 檢查")
    add_common_args(p_drift)
    p_drift.add_argument("--window", type=int, default=50, help="滾動窗口大小")

    # calibration 子命令
    p_cal = subparsers.add_parser("calibration", help="校準檢查")
    add_common_args(p_cal)

    # gate3 子命令
    p_gate3 = subparsers.add_parser("gate3", help="Gate 3 通過狀態快照")
    add_common_args(p_gate3)

    # full-refresh 子命令
    p_full = subparsers.add_parser("full-refresh", help="產生完整報告")
    add_common_args(p_full)

    args = parser.parse_args()

    # 路由到對應的 handler
    handlers = {
        "da": handle_da,
        "pnl": handle_pnl,
        "drift": handle_drift,
        "calibration": handle_calibration,
        "gate3": handle_gate3,
        "full-refresh": handle_full_refresh,
    }

    handler = handlers.get(args.subcommand)
    if not handler:
        print(json.dumps({"error": f"Unknown subcommand: {args.subcommand}"}))
        sys.exit(1)

    result = handler(args)

    # 輸出 JSON
    print(json.dumps(result, indent=2))

    # 如果有錯誤，返回非零 exit code
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
