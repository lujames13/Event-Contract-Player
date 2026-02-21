# Task Spec G3.0 — Polymarket 遷移 Phase 1: 文件遷移與目錄重組

<!-- status: review -->
<!-- created: 2026-02-22 -->
<!-- architect: Antigravity -->

> **Gate:** 3.0
> **優先級:** 🔴 High — Polymarket MVP 開發的先決基礎
> **前置條件:** Gate 2.5 (Polymarket Feasibility Study) 已完成

---

## 目標

依據 `docs/polymarket-migration-plan.md` 的規劃，執行 **Phase 1：文件遷移與結構重組**。
本任務旨在整理程式碼庫結構，為後續 Polymarket 開發準備乾淨的基礎設施：
1. 更新四份核心文件 (DECISIONS.md, ARCHITECTURE.md, PROGRESS.md, project_constants.yaml)。
2. 建立 `binance/` 子目錄以收攏舊有 Binance 程式碼。
3. 調整 import 與目錄結構，確保所有測試依然能通過。

**注意：本任務純粹是檔案移動與 import 修正，嚴禁修改任何 runtime logic（執行時邏輯）。**

---

## 修改範圍

**修改的文件：**
- `docs/DECISIONS.md` — 依據 migration plan 修改
- `docs/ARCHITECTURE.md` — 重寫為 Polymarket 主線，舊版快照至 `docs/binance/`
- `docs/PROGRESS.md` — 重寫為新的 Gate 結構
- `config/project_constants.yaml` — 擴展 PM 配置，Binance 改為 SUSPENDED

**移動 / 建立的檔案與目錄：**
- 建立 `docs/binance/`，並加入 `ARCHITECTURE-binance.md` (前版快照)
- 建立 `src/btc_predictor/binance/`、`src/btc_predictor/polymarket/`
- 建立 `scripts/binance/`、`scripts/polymarket/`
- 建立 `reports/binance/`
- 建立 `tests/test_binance/`、`tests/test_polymarket/`
- **具體移動對象（依照 migration plan 3.3 執行）：**
  - 將目前 `scripts/` 中與 Binance 強綁定的腳本（如 `fetch_history.py`, `run_live_supervised.sh`, `train_xgboost_model.py`）移至 `scripts/binance/`
  - 將 `reports/*.json` 等 Binance 報告移入 `reports/binance/`
  - 如果當前 `src/` 內有高度耦合 Binance 的檔案，僅做必要的 import 修正重構以收攏到 `binance/` 中（但不影響 feed 正常運作，詳見 migration plan 中對於 pipeline 的說明。如果難以在本任務拆分，本任務僅限移動腳本並改 import）
  - 移動相關 tests 至 `tests/test_binance/`。

**不可修改的檔案：**
- 既有的策略如 `strategies/catboost_v1/`, `strategies/lgbm_v2/` 內部邏輯
- `backtest/engine.py` 核心邏輯
- `infrastructure/store.py` (本任務只做 migration plan 規定的移動，Schema 和 DataStore 的擴充留待 G3.1)

---

## 實作要求

1. **核心文件更新**：
   - 將 `docs/polymarket-migration-plan.md` 第 2 節定義的內容，原封不動地套入 `DECISIONS.md`、`ARCHITECTURE.md`、`PROGRESS.md` 以及 `config/project_constants.yaml`。
   - 保留 Binance 歷史，標上 `[SUSPENDED]`。
2. **目錄重組與 Import 修正**：
   - 移動檔案後，使用 IDE / 腳本全域尋找並替換被打破的 import 路徑。
   - 確保所有測試檔的 import 路徑正確。
3. **保持測試綠燈**：
   - 儘量不要改動 production code 或 test 的實際邏輯驗證，只要 test discovery 找得到、import 不報錯即可。
4. **準備空目錄**：
   - 為即將到來的 Polymarket 開發（G3.1）建立好模組結構：
     - `src/btc_predictor/polymarket/` (加 `__init__.py`)
     - `src/btc_predictor/strategies/pm_v1/`
     - `tests/test_polymarket/`

---

## 不要做的事

- **不要修改任何系統的執行時邏輯（runtime logic）。** 包含 `pipeline.py`、`engine.py` 等的內部行為。如果有拆分困難，寧可保持現狀只改 import 或留待下一個任務處理。
- **不要重命名套件庫 `btc_predictor`。**
- **不要刪除任何 Binance 程式碼，僅做收攏。**
- **不要在程式碼中實作 Polymarket API (Gamma / CLOB)，那是 G3.1 的工作。**

---

## 介面契約

參考 `ARCHITECTURE.md` 最新定義：
- `PredictionSignal`: 新增 Polymarket 專屬擴充欄位（可為 Optional，以保證向後相容）。
- `PolymarketOrder`: 新增的 dataclass，可於 `models.py` 中先行定義。

---

## 驗收標準

1. 核心文件 (`DECISIONS.md`, `ARCHITECTURE.md`, `PROGRESS.md`, `config/project_constants.yaml`) 皆已依照 migration plan 完成更新。
2. `src/btc_predictor/binance/` 與 `src/btc_predictor/polymarket/` 等新目錄皆已建立，且相關檔案成功移入。
3. 執行 `uv run pytest -v`，全部測試通過（無 import errors, 無 test regressions）。

---

## Coding Agent 回報區

### 實作結果
- 檢查前置 agent 的各項修改是否確實完成。發現先前實作中遺漏將 `src/btc_predictor/simulation/settler.py` 移動至 `src/btc_predictor/binance/settler.py`，已進行移動並完成相應的 import 修正。
- 建立並補齊缺失的目錄與 `__init__.py`：`src/btc_predictor/strategies/pm_v1/`, `tests/test_polymarket/`, `src/btc_predictor/binance/`, `src/btc_predictor/polymarket/`。
- 修復 `scripts/binance/` 底下的腳本 (`fetch_history.py`, `run_live_binance.py`, `train_xgboost_model.py`, `run_live_supervised.sh`) 中的相對匯入路徑（`sys.path.append` 與 `PROJECT_DIR`），確保目錄往下一層後能正確指回 `src/` 與專案根目錄。
- 修改所有舊的 `btc_predictor.simulation.settler` import 為 `btc_predictor.binance.settler`，確保測試綠燈。

### 驗收自檢
- [x] 1. 核心文件皆已更新。
- [x] 2. `src/btc_predictor/binance/` 與 `src/btc_predictor/polymarket/` 等新目錄皆已建立，且相關檔案 (`settler.py` 及對應 docs/scripts/tests) 成功移入並修正。
- [x] 3. 執行 `uv run pytest -v`，全部測試通過（無 import errors, 無 test regressions），83 passing。

### 遇到的問題
無重大技術障礙。先前發現 `settler.py` 遺漏移動，且 `run_live_supervised.sh` 裡面的 `PROJECT_DIR` 路徑沒有因為挪動到 `scripts/binance/` 而往下調整，已一併順利修復。`pipeline.py` 尚未拆分（符合 task spec 中對於有拆分困難的檔案留待 G3.1 的期待）。

### PROGRESS.md 修改建議
無。

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
