# Task Spec G3.8 — Analytics 模組 1+2：Data Extraction + Metrics Engine (3.4.1)
<!-- status: review -->
<!-- created: 2026-02-28 -->
<!-- architect: Antigravity -->

## 目標
建立分析系統的底層基礎設施：**Data Extraction Layer**（從 SQLite 拉數據轉 DataFrame）和 **Metrics Engine**（計算 DA、PnL、drawdown、alpha 等指標）。兩者均為純函數庫，加上一個 CLI 腳本將全部指標輸出為 `metrics.json`。

這是四模組分析架構的地基。`metrics.json` 作為全系統的數據合約，上游（本 task 的計算層）和下游（報告產出器 + Analyst Agent Skill）都通過它解耦。

對應 PROGRESS.md: Gate 3 > Task 3.4.1

## 設計原則
- **固定計算歸固定腳本**：DA = correct/total 是公式，不需要 AI 推理
- **純函數設計**：每個函數 DataFrame in → dict out，便於測試和組合
- **結構化輸出**：`metrics.json` schema 嚴格定義，因為下游 agent 和報告都依賴它
- **不修改現有模組**：這是新增的 analytics 層，不動 store.py / pipeline.py

## 修改範圍
需要新增的檔案：
- `src/btc_predictor/analytics/__init__.py` (新增)
- `src/btc_predictor/analytics/extractors.py` (新增) — 模組 1：數據萃取
- `src/btc_predictor/analytics/metrics.py` (新增) — 模組 2：指標計算引擎
- `scripts/polymarket/compute_metrics.py` (新增) — CLI 腳本，跑全部計算，輸出 JSON
- `tests/analytics/test_extractors.py` (新增)
- `tests/analytics/test_metrics.py` (新增)

腳本產出物（不納入 git 追蹤）：
- `reports/polymarket/metrics.json` — 結構化指標輸出

不可修改的檔案：
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/infrastructure/store.py`
- `src/btc_predictor/polymarket/pipeline.py`

## 實作要求

### 模組 1：Data Extraction Layer (`extractors.py`)

提供乾淨的 DataFrame 萃取函數。每個函數接受 `db_path` 參數（預設 `data/btc_predictor.db`），用 read-only connection 讀取。

```python
# src/btc_predictor/analytics/extractors.py

def get_signal_dataframe(
    db_path: str = "data/btc_predictor.db",
    strategy_name: str | None = None,
    timeframe_minutes: int | None = None,
    settled_only: bool = True,
    days: int | None = None,
) -> pd.DataFrame:
    """
    從 prediction_signals 表萃取數據。
    回傳 DataFrame：columns 至少含 id, strategy_name, timestamp, timeframe_minutes,
    direction, confidence, current_price, expiry_time, actual_direction,
    close_price, is_correct, traded, trade_id
    """

def get_trade_dataframe(
    db_path: str = "data/btc_predictor.db",
    strategy_name: str | None = None,
    days: int | None = None,
) -> pd.DataFrame:
    """
    從 pm_orders JOIN prediction_signals 萃取交易數據。
    回傳 DataFrame：columns 含 order info + signal info + pnl
    """

def get_market_context(
    db_path: str = "data/btc_predictor.db",
    timestamps: list[datetime] | None = None,
) -> pd.DataFrame:
    """
    從 ohlcv 表取得每個 timestamp 附近的市場狀態。
    columns: timestamp, volatility_5m, volume_5m, price_change_1h
    用於分析模型在不同市場條件下的表現。
    """

def join_signals_with_context(
    signals_df: pd.DataFrame,
    context_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    將 signal DataFrame 與市場 context join 起來。
    純函數，不讀 DB。
    """
```

**重要：**
- 所有 DB 操作用 `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` 確保 read-only
- 讀完即關 connection，不持有（遵守 code-style-guide 的 SQLite 規則）
- timestamp 欄位統一轉為 `datetime` (UTC)
- 若 DB 不存在或表為空，回傳 empty DataFrame（不 crash）

### 模組 2：Metrics Engine (`metrics.py`)

所有函數為純函數：DataFrame in → dict out。不讀 DB、不讀 config、不產生 side effect。

```python
# src/btc_predictor/analytics/metrics.py

def compute_directional_accuracy(
    df: pd.DataFrame,
    groupby: list[str] | None = None,
) -> dict:
    """
    計算方向準確率。
    Output: {
        "overall": {"total": int, "correct": int, "da": float, "ci_95": float},
        "by_group": {group_key: {"total": ..., "da": ..., "ci_95": ...}, ...}  # if groupby
    }
    ci_95 用 Binomial CI: 1.96 * sqrt(p*(1-p)/n)
    """

def compute_pnl_metrics(df: pd.DataFrame) -> dict:
    """
    PnL 相關指標（需要 df 含 pnl 欄位）。
    Output: {
        "total_pnl": float,
        "total_trades": int,
        "win_rate": float,
        "avg_win": float,
        "avg_loss": float,
        "profit_factor": float,      # sum(wins) / abs(sum(losses))
        "max_drawdown": float,        # 金額
        "max_drawdown_pct": float,    # 百分比
        "sharpe_like": float,         # daily_pnl_mean / daily_pnl_std
        "daily_pnl": [{"date": str, "pnl": float}, ...],
        "cumulative_pnl": [{"trade_idx": int, "cum_pnl": float}, ...],
    }
    """

def compute_alpha_analysis(
    df: pd.DataFrame,
    buckets: list[float] | None = None,
) -> dict:
    """
    Alpha 分析（需要 df 含 alpha 和 is_correct 欄位）。
    預設 buckets: [0, 0.02, 0.05, 0.10, 1.0]
    Output: {
        "distribution": {"mean": float, "median": float, "std": float, "min": float, "max": float},
        "by_bucket": [
            {"range": "0.00-0.02", "count": int, "win_rate": float, "avg_pnl": float},
            ...
        ],
        "threshold_simulation": [
            {"threshold": float, "trades": int, "win_rate": float, "total_pnl": float},
            ...
        ]
    }
    threshold_simulation: 模擬 alpha threshold 從 0.00 到 0.15 每 0.01，看各閾值下的表現。
    """

def compute_temporal_patterns(df: pd.DataFrame) -> dict:
    """
    時間維度分析（需要 df 含 timestamp 和 is_correct 欄位）。
    Output: {
        "by_hour": [{"hour": int, "total": int, "da": float}, ...],   # UTC hour 0-23
        "by_weekday": [{"weekday": str, "total": int, "da": float}, ...],
        "recent_vs_all": {
            "last_7d": {"total": int, "da": float},
            "last_30d": {"total": int, "da": float},
            "all_time": {"total": int, "da": float},
        }
    }
    """

def compute_confidence_calibration(df: pd.DataFrame) -> dict:
    """
    信心度校準分析（需要 df 含 confidence 和 is_correct 欄位）。
    Output: {
        "buckets": [
            {"expected": float, "actual": float, "count": int, "deviation": float},
            ...
        ],
        "brier_score": float,
        "baseline_brier": float,
    }
    分桶：[0.50, 0.55), [0.55, 0.60), ..., [0.95, 1.00]
    """

def compute_drift_detection(df: pd.DataFrame, window_size: int = 50) -> dict:
    """
    Concept drift 偵測（滾動窗口 DA）。
    Output: {
        "rolling_da": [{"window_end_idx": int, "da": float}, ...],
        "trend_slope": float,          # 線性回歸斜率
        "is_degrading": bool,          # slope < -0.5% per window
        "worst_window": {"start_idx": int, "end_idx": int, "da": float},
        "best_window": {"start_idx": int, "end_idx": int, "da": float},
    }
    """
```

### CLI 腳本：`compute_metrics.py`

```bash
# 基本用法：計算所有策略
PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py

# 指定策略
PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py --strategy pm_v1

# 指定 timeframe
PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py --timeframe 5

# 指定時間範圍
PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py --days 7

# 輸出路徑（預設 reports/polymarket/metrics.json）
PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py -o custom_output.json
```

**`metrics.json` 頂層 schema：**

```json
{
  "meta": {
    "generated_at": "2026-02-28T03:00:00Z",
    "db_path": "data/btc_predictor.db",
    "filters": {"strategy": null, "timeframe": null, "days": null},
    "data_range": {"first_signal": "...", "last_signal": "...", "total_signals": 0, "settled_signals": 0}
  },
  "directional_accuracy": { ... },
  "pnl": { ... },
  "alpha": { ... },
  "temporal": { ... },
  "calibration": { ... },
  "drift": { ... },
  "gate3_status": {
    "da_above_52pct": false,
    "trades_above_200": false,
    "pnl_positive": false,
    "pipeline_72h_stable": null,
    "overall": "NOT_PASSED"
  }
}
```

CLI 同時在 terminal 印出精簡摘要（gate3 status + DA + PnL 一行摘要）。

## 不要做的事
- 不要修改 `store.py` — 用 read-only sqlite3 直接讀取
- 不要在 analytics 模組中寫入任何數據到資料庫
- 不要產出 Markdown 報告 — 那是模組 3 (task 3.4.2) 的職責
- 不要建立 agent skill — 那是模組 4 (task 3.4.3) 的職責
- 不要引入重型視覺化依賴（matplotlib, plotly 等）
- 不要硬編碼 breakeven winrate — 從 `project_constants.yaml` 讀取（只有 `compute_metrics.py` 讀 config，`metrics.py` 的純函數不讀）
- 不要在純函數中做 I/O（DB、file、network）— extractors 負責 I/O，metrics 只做計算

## 介面契約
- **模組 1 輸出**：`pd.DataFrame`（標準化欄位名稱）
- **模組 2 輸出**：`dict`（可直接 `json.dumps()` 序列化）
- **CLI 輸出**：`reports/polymarket/metrics.json`（嚴格遵守上述 schema）
- **依賴**：`DataStore` 的 SQLite schema（prediction_signals, pm_orders, simulated_trades, ohlcv 表結構）
- **config 依賴**：`load_constants()` 中的 `polymarket.breakeven_winrate`（僅在 CLI 腳本中讀取，不在純函數中）

## 驗收標準

1. **`uv run pytest tests/analytics/test_extractors.py -v` 全部通過**
   - 使用 in-memory SQLite 建立測試表，插入合成數據
   - 測試覆蓋：空表處理、篩選條件（strategy, timeframe, days）、timestamp 轉換
   - 測試 DB 不存在時回傳 empty DataFrame

2. **`uv run pytest tests/analytics/test_metrics.py -v` 全部通過**
   - 使用合成 DataFrame，不依賴真實 DB
   - 每個 `compute_*` 函數至少 2 個測試案例（正常 + 邊界）
   - 數值比較用 `pytest.approx()`
   - 測試覆蓋：空 DataFrame、只有 1 筆數據、全贏/全敗

3. **`PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py` 可正常執行**
   - 若 DB 中無數據 → 輸出 "Insufficient data" + 產出含 `meta` 的最小 metrics.json（不 crash）
   - 若有數據 → 產出完整 `reports/polymarket/metrics.json`，可用 `python -m json.tool` 驗證格式

4. **`metrics.json` 可被 `json.load()` 正確解析，且頂層 keys 與 schema 一致**

---

## Coding Agent 回報區

### 實作結果
✅ 新增 `src/btc_predictor/analytics/__init__.py`
✅ 新增 `src/btc_predictor/analytics/extractors.py` 處理 pure-function DataFrame extraction，使用 in-memory AS OF merge 處理 timestamps。
✅ 新增 `src/btc_predictor/analytics/metrics.py` 處理 DA, PnL, Alpha 等計算，輸出 JSON compatible dicts。
✅ 新增 `scripts/polymarket/compute_metrics.py` 提供 CLI 呼叫所有 function，依賴於 config yaml 讀取 winrate，無其餘 side-effect。
✅ 新增 `tests/analytics/test_extractors.py` (Pass)
✅ 新增 `tests/analytics/test_metrics.py` (Pass)
產出可自動忽略 untracked `reports/polymarket/metrics.json`。

### 驗收自檢
✅ 1. `uv run pytest tests/analytics/test_extractors.py -v` 全部通過
✅ 2. `uv run pytest tests/analytics/test_metrics.py -v` 全部通過
✅ 3. `PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py` 可正常執行，即使空標也回傳 valid schema。
✅ 4. `metrics.json` 可被 `json.load()` 正確解析，且頂層 keys 與 schema 一致。

### 遇到的問題
發現在 `extractors.py` 實作中，取得的 signals df 透過 parse datetime string (ISO 8601) 自動被轉為 `datetime64[ns, UTC]` 或微秒 (`us`)，但如果我們對 `ohlcv.close_time` 做同樣的事會產生 `datetime64[ms, UTC]` (milli)，使用 `merge_asof` 當 timestamps 的 resolutions 不同時會報錯，已直接透過 `astype('datetime64[ns, UTC]')` 強制型別對齊來解決。

### PROGRESS.md 修改建議
無（任務要求內不修改，且順利完成目前架構）。
Commit hash: 9cbdae02a608c450b07fbadce4d181651d04616f

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->

### PROGRESS.md 修改建議
<!-- 如有 -->
