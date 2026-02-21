# Task Spec G3.2 — Polymarket 多 Timeframe 模型訓練與回測

<!-- status: review -->
<!-- created: 2026-02-22 -->
<!-- architect: Antigravity -->

> **Gate:** 3.2
> **優先級:** 🔴 High — 核心 Alpha 驗證
> **前置條件:** G3.1 (Part 1 Pipeline 解耦合) 已完成

---

## 目標

依據 `docs/polymarket-migration-plan.md`，本任務將專注於「多 timeframe 模型訓練 + 回測 (Phase 3)」。

Polymarket 的結算條件 (`>=`) 以及 Maker 零手續費機制，大幅改變了模型的盈虧平衡點。此任務將：
1. 參數化 `labeling.py` 支援 `>=` 的結算條件。
2. 擴充回測引擎支援 Polymarket Fee 模型（Maker order proxy: breakeven 50% = payout_ratio 2.0）。
3. 基於 CatBoost 架構建立 Polymarket 專屬策略 `pm_v1`。
4. 執行 5m, 15m, 60m 的 Walk-forward 回測，驗證 Alpha 並找出最佳 timeframe 組合。

---

## 修改範圍

**新增檔案：**
- `src/btc_predictor/strategies/pm_v1/__init__.py`
- `src/btc_predictor/strategies/pm_v1/strategy.py`
- `src/btc_predictor/strategies/pm_v1/model.py`
- `src/btc_predictor/strategies/pm_v1/features.py` (可復用/繼承原有 `catboost_v1` 的特徵)
- `reports/polymarket/PM-V1-WalkForward-Report.md` (回測結果分析報告)

**被修改檔案：**
- `src/btc_predictor/infrastructure/labeling.py` (新增 `settlement_condition` 參數)
- `src/btc_predictor/backtest/engine.py` (支援 Polymarket payout/fee 模型)
- `scripts/train_model.py` (支援載入與訓練 `pm_v1`)
- `scripts/backtest.py` (支援 Polymarket 回測參數與輸出)
- `docs/PROGRESS.md` (更新 Gate 3 進度)

**不可動的檔案：**
- 任何 `binance/` 下的檔案。
- 既有的 `xgboost_v1`, `catboost_v1`, `lgbm_v2` 等 Binance 策略模組 (應保持歷史相容)。
- `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `config/project_constants.yaml` (如有需要修正設定，請保留原有結構並依循 `[SUSPENDED]` 標記原則)。

---

## 實作要求

1. **結算邏輯參數化 (`labeling.py`)**
   - 修改 `add_direction_labels` 與 `calculate_single_label`，加入 `settlement_condition: str = ">"` 參數。
   - 當 `settlement_condition == ">="` 時，`close_price >= open_price` 標記為 `1` (Higher/Up)，小於則為 `0` (Lower/Down)。
   - 預設值必須保持 `">"`，防止破壞其他 Binance 舊有策略的訓練或回測邏輯。

2. **回測引擎升級 (`backtest/engine.py` & `scripts/backtest.py`)**
   - 在 `run_backtest` 加入參數 `platform="binance"`，當傳入 `platform="polymarket"` 時：
     - 若為 Polymarket Maker，其假定盈虧平衡約 50.0%，在固定下注模擬中可視為 `payout_ratio = 2.0` (下注 $bet，贏得 $+bet，輸得 $-bet)。
     - 結算判斷必須對應 `>=` (與 `labeling.py` 一致)。

3. **實作 `pm_v1` 策略**
   - 於 `src/btc_predictor/strategies/pm_v1` 建立新策略。
   - 繼承 `BaseStrategy`，`name` 設為 `"pm_v1"`。
   - 在 `fit()` 內呼叫 `labeling.py` 時，必須明確傳入 `settlement_condition=">="`。
   - 模型架構使用 `CatBoostClassifier`。

4. **大規模 Walk-forward 回測與報告**
   - 使用 `scripts/train_model.py` 與 `scripts/backtest.py` 對 `pm_v1` 在 5m, 15m, 60m 三個 timeframe 進行 Walk-forward 回測（可使用 `-n_jobs -2` 啟動平行運算）。
   - 將每個 timeframe 的 **Directional Accuracy (DA)**、**Trades Count**、**Expected PnL** 彙整進新建立的報告 `reports/polymarket/PM-V1-WalkForward-Report.md`。
   - 在報告中，基於 `Alpha > 5%` (或合適閾值) 來進行 Alpha 分析，結論需推薦哪個 timeframe 表現最好。

---

## 不要做的事

- **不要**在 `pm_v1` 中實作 Polymarket CLOB 交易下單邏輯，API Clients 是接下來另一個 task 的範圍。
- **不要**修改 Binance EC 策略的歷史驗證碼與回測邏輯，所有 `pm_v1` 以外的模型都必須維持原本 `>` 結算條件與 `1.85` payout_ratio。
- **不要**手動硬改 DB schema，如果回測產生 SimulatedTrades 報錯，請利用 CLI 參數或記憶體層面的 mock 回避，不要影響已存在的 `simulated_trades` 表（本 Task 不包含 DB 遷移）。

---

## 驗收標準

1. 執行 `uv run pytest -v`，所有既有的 backtest 與 labeling 相關的測試必須維持通過 (No regressions)。
2. 能成功透過以下指令跑完 5m 訓練與回測 (不崩潰)：
   ```bash
   uv run python scripts/train_model.py --strategy pm_v1 --timeframe 5
   uv run python scripts/backtest.py --strategy pm_v1 --timeframe 5 --platform polymarket
   ```
3. 在 `reports/polymarket/PM-V1-WalkForward-Report.md` 中可以看到明確的 5m, 15m, 60m 的比較數據（DA、Trades、PnL）。

---

## Coding Agent 回報區

### 實作結果
- 實作了 `labeling.py` 與 `engine.py` / `backtest.py` 的參數化邏輯，新增了 `platform="polymarket"` 與 `settlement_condition=">="` 支援。
- 創建了 `pm_v1` 模型，完整復用 `catboost_v1` 的特徵生成與模型訓練邏輯，並直接使用 `>=` 作為訓練目標。
- 成功執行 5m, 15m, 60m 的並行回測，生成 `reports/polymarket/PM-V1-WalkForward-Report.md`。分析指出 5m Timeframe 表現最為優良 (DA 55.68%)。
- **PROGRESS.md 修改建議**：建議在 Gate 3.2 下將「3.2.1」至「3.2.4」項目全數打鉤。並標註 5m 模型跑出了 DA 55.68% 的亮眼成績，後續可基於 5m 作主力投入資源。

### 驗收自檢
- ✅ 1. 執行 `uv run pytest -v`，所有既有的 backtest 與 labeling 相關的測試必須維持通過：89 個 tests 均順利通過（1 warning 為原先就存在的 deprecation）。
- ✅ 2. 成功執行 `uv run python scripts/train_model.py` 與 `backtest.py` 進行 5m 訓練與回測，並且未崩潰。
- ✅ 3. 在 `reports/polymarket/PM-V1-WalkForward-Report.md` 中成功彙整 5m, 15m, 60m 的比較數據並提出最終結論（5m 表現最好）。

### 遇到的問題
- 執行 5m Walk-forward 回測時，由於 5 分鐘間距在測試區間中相當密集（高達三十多萬筆資料點推理），需要大約 10 分鐘左右才能順利跑完。這是正常之硬體效能瓶頸，無需更動架構。

**Commit Hash:** `aba4ab4`

---

## Review Agent 回報區

### 審核結果：[待填寫]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->
