# Task Spec G3.9 — Analytics 模組 3：Markdown 報告產出器 (3.4.2)
<!-- status: review -->
<!-- created: 2026-02-28 -->
<!-- architect: Antigravity -->

## 目標
建立分析系統的報告產出基礎設施（模組 3）。寫一個指令列工具（`scripts/polymarket/generate_report.py`），去讀取前一個 task 產出的 `metrics.json`，並將其渲染為易於閱讀的 Markdown 格式報告（例如 `reports/polymarket/metrics_report.md`）。這將做為人類開發者監控策略表現，以及提交給 Analyst Agent 的視覺化報表基礎。

對應 PROGRESS.md: Gate 3 > Task 3.4.2 (模組 3：報告產出器)

## 修改範圍
需要新增或修改的檔案：
- `scripts/polymarket/generate_report.py` (新增) — 讀取 `metrics.json` 並產出 Markdown 檔案的純 CLI 腳本。
- `docs/PROGRESS.md` (更新) — 將 3.4.1 與 3.4.2 的項目標記為完成 `[x]`。

腳本產出物（無需納入 git 追蹤）：
- `reports/polymarket/metrics_report.md` (或同等 Markdown 檔案)

不可修改的檔案：
- `src/btc_predictor/analytics/extractors.py`
- `src/btc_predictor/analytics/metrics.py`
- `scripts/polymarket/compute_metrics.py`
- `docs/DECISIONS.md`
- `config/project_constants.yaml`

## 實作要求

### 腳本：`scripts/polymarket/generate_report.py`

此工具應達成以下功能：
1. **讀取輸入**：可以透過 `--input` (預設 `reports/polymarket/metrics.json`) 指定 json 檔案的位置。
2. **產出輸出**：可以透過 `--output` (預設 `reports/polymarket/metrics_report.md`) 指定輸出的 md 檔案名稱。
3. **渲染邏輯**：請使用 Python 內建的 f-string （或輕量工具）將 JSON 的各個段落：`meta`, `gate3_status`, `directional_accuracy`, `pnl`, `alpha`, `temporal`, `calibration`, `drift` 排版為易懂的 Markdown 格式。
   建議的報告結構：
   - **Overview / Meta**: 報表產出時間 (Generated At), 策略 (Filters), 資料量區間等。
   - **Gate 3 Status**: 的摘要表格，使用 Emoji（例如 ✅ / ❌）表示是否達標。
   - **Core Metrics (DA & PnL)**: DA (Directional Accuracy) 與核心 PnL (Win Rate, Total PnL, Trades 數量) 的重點摘要表格。
   - **Alpha Analysis & Temporal**: 透過簡單清單或表格列出不同 threshold 及時段表現。
   - **Concept Drift**: Drift 是否發生 (如 `is_degrading` 為 `true` 則需附上醒目的 `🚨 WARNING`)。

要求輸出排版整齊，適合工程師快速檢閱，核心與警示指標需放在最前面。

## 不要做的事
- 不要重新計算任何指標。程式應「只」單純讀取並解析 `metrics.json` 的數值。
- 不要在報告腳本中再次存取 SQLite 資料庫，或去讀取 config yaml。如有判定門檻，都應使用 `metrics.json` 裡的內容（例如由 `gate3_status` 和 metrics 中提取）。
- 不要引入外部複雜的 Markdown 渲染依賴；單純的 f-string 或標準函式庫就能完成排版。

## 驗收標準
1. `metrics.json` 可用性：先執行 `PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py` 來確保有正確的最新對象。
2. 執行報告產生器：`uv run python scripts/polymarket/generate_report.py` 可以正常運作。
3. 腳本不報錯，並順利於 `reports/polymarket/metrics_report.md` 產出含有清晰 Markdown 格式（標題、表格、各項數據與 emoji）的報表。
4. 容錯處理：如 JSON 檔案不存在、內部格式無對應 keys（如 `--input invalid.json`），應優雅地吐出錯誤提示並結束，而不是引發無意義 stacktrace。
5. 檢查 `docs/PROGRESS.md`，確認任務清單 `3.4.1` 及 `3.4.2` 已被標記成已完成。

---

## Coding Agent 回報區

### 實作結果
- 新增 `scripts/polymarket/generate_report.py`。
- 修改 `docs/PROGRESS.md`，將 3.4.1 和 3.4.2 任務狀態打勾（完成）。

### 驗收自檢
1.  **`metrics.json` 可用性**：PASS，測試執行 `compute_metrics.py` 確認 `metrics.json` 可成功產出。
2.  **執行報告產生器**：PASS，`generate_report.py` 成功讀取現有 `metrics.json`。
3.  **無報錯並產出排版整齊的 Markdown 報告**：PASS，報告具備 emoji 標記狀態且具有所有必要區塊。
4.  **容錯處理**：PASS，若 JSON 檔案遺失或格式錯誤，有加入優雅的錯誤提示 (`system.exit(1)`)。
5.  **`docs/PROGRESS.md` 更新**：PASS，已將 `3.4.1` 及 `3.4.2` 標記為完成 `[x]`。

### 遇到的問題
這是一個單純且明確的生成報告元件，直接用 `f-string` 列印出來，由於 `ruff` 未設定為可以在 uv 全域執行故取消執行 formatter。測試了對象檔案不存在時的報錯也符合預期。

### PROGRESS.md 修改建議
無需額外更新，已經符合預期的在 G3 區域標記完成。

---

## Review Agent 回報區

### 審核結果
(PASS/FAIL)

### 驗收標準檢查
...

### 修改範圍檢查
...

### 發現的問題
...
