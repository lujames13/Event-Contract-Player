# Task Spec G3.8 — Paper Trading 績效儀表板 (3.4.1)
<!-- status: todo -->
<!-- created: 2026-02-28 -->
<!-- architect: Antigravity -->

## 目標
建立一個完整的 Paper Trading 績效分析腳本，從 SQLite 中讀取累積的 `prediction_signals`、`pm_orders`、`simulated_trades` 數據，產出可操作的績效報告（Markdown + terminal 輸出）。讓人類能在進入實盤之前，對模型表現有全面的理解。
對應 PROGRESS.md: Gate 3 > Task 3.4.1

## 修改範圍
需要新增/修改的檔案：
- `scripts/polymarket/analyze_performance.py` (新增) — 主分析腳本
- `reports/polymarket/paper-trading-report.md` (新增，腳本自動產出) — Markdown 格式績效報告
- `tests/polymarket/test_analyze_performance.py` (新增) — 測試分析邏輯的核心計算函數

不可修改的檔案：
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/polymarket/pipeline.py`
- `src/btc_predictor/infrastructure/store.py`（不新增方法，利用現有介面）

## 實作要求

### 1. 報告區塊

腳本應產出以下區塊，每個區塊均為獨立函數，方便單元測試：

**A. Executive Summary**
- 報告時間範圍（首筆 signal 至今）
- 各策略 × timeframe 的已結算 signal 總數、traded signal 數
- 當前是否達到 Gate 3 通過條件（200+ trades, DA > 52%, positive PnL）

**B. Directional Accuracy (DA) 分析**
- 整體 DA（所有已結算 signals，不論是否 traded）
- 分 timeframe DA
- 分 traded/non-traded DA（觀察 alpha threshold 是否有效篩選）
- 每日 DA 趨勢（rolling 7-day MA）— 偵測 concept drift
- DA 的 95% Binomial Confidence Interval

**C. PnL 分析（僅 traded signals）**
- Cumulative PnL 曲線數據（每筆交易的累積 PnL）
- 每日 PnL
- 每週 PnL
- Max drawdown（金額 + 百分比）
- Win rate vs breakeven win rate
- Average win / average loss / profit factor
- Sharpe-like ratio（daily PnL mean / daily PnL std）

**D. Alpha 分析**
- Alpha 分佈統計（mean, median, std, min, max）
- Alpha vs 實際勝率的散點分析（分桶：alpha < 0.02, 0.02-0.05, 0.05-0.10, > 0.10）
- 不同 alpha threshold 下的預期 PnL 模擬（供閾值調整參考）

**E. 時間維度分析**
- 按 UTC 小時分佈的 DA（哪些時段模型表現最好/最差）
- 按星期幾分佈的 DA
- 最近 N 天 vs 全期的 DA 比較（偵測近期 drift）

### 2. 技術要求

- 使用 `DataStore.get_settled_signals()` 和 `DataStore.get_pm_strategy_detail()` 等現有方法取得數據
- 如果現有 Store 方法不足以拿到所有需要的數據，可以直接用 `sqlite3` 讀取（read-only），但不要修改 `store.py`
- 所有計算函數應為純函數（輸入 DataFrame，輸出 dict/DataFrame），便於測試
- 報告輸出為 Markdown 格式，存入 `reports/polymarket/paper-trading-report.md`
- 同時在 terminal 輸出摘要版本

### 3. CLI 介面

```bash
# 基本用法：分析所有策略
PYTHONPATH=src uv run python scripts/polymarket/analyze_performance.py

# 指定策略
PYTHONPATH=src uv run python scripts/polymarket/analyze_performance.py --strategy pm_v1

# 指定 timeframe
PYTHONPATH=src uv run python scripts/polymarket/analyze_performance.py --timeframe 5

# 指定時間範圍
PYTHONPATH=src uv run python scripts/polymarket/analyze_performance.py --days 7
```

## 不要做的事
- 不要修改 `store.py` 新增查詢方法 — 用現有方法或直接 read-only SQL
- 不要在分析腳本中寫入任何數據到資料庫
- 不要引入重型視覺化依賴（如 matplotlib, plotly）— 報告用純 Markdown 表格即可
- 不要做模型訓練或預測 — 這是純分析腳本
- 不要硬編碼 breakeven winrate — 從 `project_constants.yaml` 讀取

## 介面契約
- 輸入：SQLite DB 中的 `prediction_signals`、`pm_orders`、`simulated_trades` 表
- 輸出：`reports/polymarket/paper-trading-report.md` + terminal stdout
- 依賴介面：`DataStore.get_settled_signals()`, `DataStore.get_pm_strategy_detail()`, `load_constants()`

## 驗收標準
1. `uv run pytest tests/polymarket/test_analyze_performance.py -v` 全部通過
   - 測試須覆蓋：DA 計算、PnL 計算（含 drawdown）、alpha 分桶、confidence interval 計算
   - 使用合成 DataFrame 測試，不依賴真實 DB
2. `PYTHONPATH=src uv run python scripts/polymarket/analyze_performance.py` 可正常執行
   - 若 DB 中無數據，應優雅處理並輸出「Insufficient data」而非 crash
   - 若有數據，應產出 `reports/polymarket/paper-trading-report.md`
3. 產出的 Markdown 報告應包含上述 A-E 所有區塊（若該區塊數據不足則標注 N/A）

---

## Coding Agent 回報區

### 實作結果
<!-- 完成了什麼，修改了哪些檔案 -->

### 驗收自檢
<!-- 逐條列出驗收標準的 pass/fail -->

### 遇到的問題
<!-- 技術障礙、設計疑慮 -->

### PROGRESS.md 修改建議
<!-- 如果實作過程中發現規劃需要調整，在此說明 -->

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
