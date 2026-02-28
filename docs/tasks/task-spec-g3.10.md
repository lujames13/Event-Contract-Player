# Task Spec G3.10 — Analytics 模組 4：Analyst Agent Skill (3.4.3)
<!-- status: draft -->
<!-- created: 2026-02-28 -->
<!-- architect: Antigravity -->

## 目標
建立分析系統的「模組 4：Analyst Agent Skill」。這是一個純文本形式的 Agent Workflow，用於指導模型（例如 Coding Agent）在使用者請求分析（例如呼叫 `/analyze` 指令）時，如何正確讀取報告，並產出專業的系統診斷（發生什麼事）與行動建議（推薦的後續改進）。

對應 PROGRESS.md: Gate 3 > Task 3.4.3 (Diagnostic skill & Recommendation skill)

## 修改範圍
需要新增或修改的檔案：
- `.agent/workflows/analyst.md` (新增) — 定義 Analyst Workflow。若資料夾 `.agent/workflows/` 不存在請建立。
- `docs/PROGRESS.md` (更新) — 將 3.4.3 區塊下的兩個項目（Diagnostic skill 與 Recommendation skill）標記為完成 `[x]`。

不可修改的檔案：
- 任何 `.py` 腳本（分析、萃取、報告產出等 Python 程式碼）
- `docs/DECISIONS.md`
- `config/project_constants.yaml`

## 實作要求
我們需要定義一個供 Agent 閱讀的 workflow，請在 `.agent/workflows/analyst.md` 內撰寫完整指令。要求如下：

1. **YAML Frontmatter**: 檔案頂部必須有標準格式：
   ```yaml
   ---
   description: 讀取並分析策略表現報告，執行統計診斷並給出下一步行動建議
   ---
   ```
2. **Trigger**: 觸發指令設定為 `/analyze`。
3. **Role (角色設定)**: 將 Agent 定位為「量化策略分析師（Quant Strategy Analyst）」。要求其保持冷靜、客觀，必須且只依賴 `metrics.json` 或 `metrics_report.md` 的數據說話，並遵循 `docs/DECISIONS.md` 的約束提供改進意見。
4. **Steps (分析步驟)**:
   - **Step 1 - 資料載入**: 讀取 `reports/polymarket/metrics_report.md` (或 `metrics.json`)，以及 `docs/DECISIONS.md`、`config/project_constants.yaml` 的相關區塊。
   - **Step 2 - 系統診斷 (Diagnosis)**:
     - 檢查整體 `gate3_status` 是否達標。
     - 解析 `directional_accuracy` 與 `pnl`，判斷模型的獲利能力是否具有顯著基礎，還是處於隨機波動。
     - 檢查 `drift` 和 `calibration`，判斷策略是否面臨嚴重的 Concept Drift，或是校準失真 (overconfident/underconfident)。
   - **Step 3 - 行動建議 (Recommendation)**:
     - 基於診斷結果給出 1 到 2 個具體的、可執行的下一步計畫（如：模型需要更多特徵 pm_v2、需要做 ensemble 加權、重新校準 threshold、還是繼續累積樣本紙上交易）。
     - 行動建議必須對應到 PROGRESS.md 後續的 TODO 項目。
5. **Constraints (限制)**:
   - 拒絕算命或猜測市場。
   - 所有優化建議不得違反 DECISIONS.md 的技術邊界（例如要求擴充到大 VRAM 的 LLM 或高頻做市策略）。

## 不要做的事
- 不要寫任何 Python 程式碼，這個任務單純只是一個建置 Agent Prompt/Workflow 文件的設計任務。
- 不要將特定的「盈虧平衡常數」寫死在 `analyst.md` 中，而是指示 Analyst 去參考 `metrics.json` 中的計算結果或查詢專案 YAML。
- 不要在本次 Task 中實際執行分析，產出文件即可。

## 驗收標準
1. `.agent/workflows/analyst.md` 以正確的文件格式被建立出來。
2. `.agent/workflows/analyst.md` 包含上述 YAML frontmatter 及所有必需的 Steps（資料載入、診斷、建議）。
3. `docs/PROGRESS.md` 中的 3.4.3 (`Diagnostic skill` 與 `Recommendation skill`) 皆已標記為主動完成 `[x]`。

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

### 審核結果
<!-- PASS / FAIL / PASS WITH NOTES -->

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->

### PROGRESS.md 修改建議
<!-- 如有 -->
