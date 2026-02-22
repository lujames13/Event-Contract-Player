# Task Spec G3.7 — Polymarket 模擬交易統計顯著性驗證 (3.3.3)

<!-- status: review -->
<!-- created: 2026-02-23 -->
<!-- architect: Antigravity -->

> **Gate:** 3.7 (對應 PROGRESS.md 3.3.3)
> **優先級:** 🔴 High — Blocker for Gate 4 (Live Trading)

---

## 目標

目前 Polymarket 模擬交易 (Paper Trading Pipeline) 已經成功上線並持續運行中，根據 `PROGRESS.md` 中 Gate 3 的通過條件，我們需要一個自動化的驗證腳本來進行「統計顯著性驗證」，確保我們累積的 `pm_orders` 通過了嚴格的機率門檻及獲利期望值檢查，才能安全放行進入 Gate 4 (真實資金交易)。
對應 PROGRESS.md: Phase 3 > Task 3.3.3

---

## 修改範圍

**需要新增/修改的檔案：**
- `scripts/polymarket/verify_significance.py` (新增) — 負責讀取 DB 中的預測與訂單，並進行統計檢驗 (Binomial Test for DA, t-test for PnL)。

**不可修改的檔案：**
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/infrastructure/store.py` (請避免無謂修改，可以透過原有的 `get_pm_strategy_detail` 或直接在腳本中寫 SQL 查詢完成)
- `src/btc_predictor/polymarket/pipeline.py` 等核心業務邏輯

---

## 實作要求

1. **資料讀取**：
   - 透過 `sqlite3` 連線到 `data/btc_predictor.db` (使用 Read-only 模式，避免鎖定 DB)。
   - 從 `prediction_signals` 與 `pm_orders` 撈取針對所有以 `pm_` 開頭策略且**已結算**（`o.pnl IS NOT NULL`）的模擬訂單數據。

2. **統計指標與檢定**：
   對每個「策略 × timeframe」(依據 `s.timeframe_minutes`) 的組合計算：
   - **Sample Size (N)**：總已結算筆數。如果 N < 200，在報告中明確標記為進度百分比 (例如 `[54/200] INSUFFICIENT_DATA`)，但不中斷分析。
   - **Directional Accuracy (DA)**：勝率。需計算 95% 信賴區間下限 (可使用 Normal Approximation)。
   - **Null Hypothesis (DA)**：H0: 真實勝率 <= 50% (Polymarket Maker 盈虧平衡點)。需計算 p-value (可以使用 `scipy.stats` 或 `math` / `numpy` 手算近似)。
   - **Total PnL & Avg PnL**：檢查總量與每筆期望值是否 > 0。
   - **Null Hypothesis (PnL)**：H0: 期望 PnL <= 0。需計算 p-value (t-test，依據每筆訂單 PnL 樣本計算 t-statistic)。

3. **報告產出**：
   - 將評估結果格式化並輸出到控制台 (stdout)。
   - 將完整的 Markdown 格式報告自動覆寫到 `reports/polymarket/PM-gate3-validation.md` 中。
   - 如果某一「策略 × timeframe」組合滿足：(1) N >= 200, (2) DA p-value < 0.05, (3) PnL p-value < 0.05，並標記為 `🟢 [GATE 3 PASSED]`。反之如果進行中標記為 `⏳ [WAITING]`。

---

## 不要做的事

- **不要**將這個分析邏輯混入即時交易的 pipeline 中，這是一個單純跑離線查詢的驗證腳本。
- **不要**任意修改已有 `pyproject.toml` 中的核心套件。如需使用 `scipy`，可以用 `uv add --dev scipy`，或盡量用 `numpy` / `math` 處理。

---

## 驗收標準

1. 執行 `uv run python scripts/polymarket/verify_significance.py` 能夠成功執行不報錯。
2. 腳本能正確輸出 각策略 / timeframe 之 N、DA、PnL 以及對應的統計檢驗 p-value 和信賴區間。
3. 成功於 `reports/polymarket/` 產生並格式化 `PM-gate3-validation.md`。

---

## Coding Agent 回報區

### 實作結果
- 成功新增 `scripts/polymarket/verify_significance.py`。
- 實作了從 `data/btc_predictor.db` 的唯讀查詢邏輯，利用 `scipy.stats` 計算勝率的精確信賴區間與 p-value (Binomial Test)，以及 PnL 的單尾 T-檢定 (1-Sample t-test)。
- 輸出的格式與邏輯均依照 task spec 制定的規範製作，成功產出 stdout 及 `reports/polymarket/PM-gate3-validation.md`。

### 驗收自檢
- [x] 1. 執行 `uv run python scripts/polymarket/verify_significance.py` 能夠成功執行不報錯。
- [x] 2. 腳本能正確輸出 각策略 / timeframe 之 N、DA、PnL 以及對應的統計檢驗 p-value 和信賴區間。
- [x] 3. 成功於 `reports/polymarket/` 產生並格式化 `PM-gate3-validation.md`。

### 遇到的問題
無。`scipy` 原先已經安裝於環境中，因此可以直接使用而無需額外修改依賴。

### PROGRESS.md 修改建議
無，這是單純的腳本開發與驗證邏輯實作。待未來該信號通過驗證時，再推動進度。

**Commit Hash:** `6915f4c`

---

## Review Agent 回報區

### 審核結果

### 驗收標準檢查

### 修改範圍檢查

### 發現的問題

### PROGRESS.md 修改建議
