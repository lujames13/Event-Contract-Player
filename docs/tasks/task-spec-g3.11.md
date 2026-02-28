# Task Spec G3.11 — 模型迭代與信心度校準 (pm_v2) (3.4.4 & 3.4.6) (廢棄，已改進為 Task 3.12)
<!-- status: todo -->
<!-- created: 2026-03-01 -->
<!-- architect: Antigravity -->

## 目標

根據 Analyst Agent 的分析，目前的 `pm_v1` 模型在近期 50 筆預測中 DA 暴跌至 0.26（極度嚴重的 Concept Drift），且信心度存在極端的過度自信（Brier Score 0.285，大於隨機猜測的 0.249，表示校準極差）。
為了修復這兩個阻礙進入 Gate 4 (Live Trading) 的致命問題，本任務將建立新一代策略 `pm_v2`：
1. **模型迭代改進任務 (3.4.4)**：重新檢視特徵工程，由於 `pm_v1` 僅是過渡產物，請拋棄對原有 Binance 慣用參數的依賴。大幅調整特徵（如：對近期波動率更敏感的短期 EMA / MACD、更短的 Lookback window、更能捕捉 Polymarket `>=` 規則邊緣情況的特徵）。
2. **信心度校準重新分析 (3.4.6)**：在模型預測輸出前，導入機率校準機制（Platt Scaling 或 Isotonic Regression 等方法），修正模型的輸出機率與實際勝率的偏差。

對應 PROGRESS.md: Gate 3 > Task 3.4.4 & 3.4.6

## 修改範圍

**需要新增的檔案：**
- `src/btc_predictor/strategies/pm_v2/__init__.py`
- `src/btc_predictor/strategies/pm_v2/strategy.py` (實作 `BaseStrategy`，並在 Inference 階段整合機率校準器)
- `src/btc_predictor/strategies/pm_v2/features.py` (針對 `pm_v1` 的特徵及近期漂移作調整優化)
- `src/btc_predictor/strategies/pm_v2/model.py` (CatBoost 或 LGBM 等架構加上 `sklearn.calibration.CalibratedClassifierCV` 進行包裹訓練)
- `tests/strategies/test_pm_v2.py` (確認 Output Signal 屬性一致且信心度不超出合理範圍)

**需要修改的檔案：**
- `docs/PROGRESS.md` (標記 3.4.4 與 3.4.6 為處理中與完成狀態)
- `scripts/train_model.py` (確保 `pm_v2` 可以被正常呼叫訓練，若需要可針對 Calibration 調整)

**不可修改的檔案：**
- `src/btc_predictor/strategies/pm_v1/` 及之前的舊策略 (作為對照組 Baseline)。
- `docs/DECISIONS.md` 和 `config/project_constants.yaml` (如有參數設定可直接借用)。
- `src/btc_predictor/analytics/` 系統純粹提供測量工具，不負責修復。

## 實作要求

1. **建立 `pm_v2` 策略結構**
   - 不再盲目繼承或複製 `pm_v1` 或 `catboost_v1` 邏輯。這是一個針對 Polymarket 重新思考的大改版。
   - `strategy.py`：必須傳入 `settlement_condition=">="`，回傳格式完全符合 `PredictionSignal` 需求 (含有 `market_slug`, `alpha` 等 polymarket 專屬結構與型別)。

2. **特徵優化 (針對 Concept Drift 與 Polymarket 玩法)**
   - 修改 `features.py`：完全針對短 timeframe（5m/15m）以及 Polymarket Maker `>`/`=` 的特色設計。
   - 移除不必要或會造成嚴重 Overfitting 的長天期雜訊特徵。加入對近期市場結構極度敏感的設計。
   
3. **訓練與校準流程 (針對 Overconfidence)**
   - 在 `model.py` 中，不直接回傳單純的 Classifier。要使用 `CalibratedClassifierCV(method='sigmoid' 或 'isotonic', cv=3)` (Platt Scaling 或 Isotonic) 將原本訓練的模型包裹一層再回傳。確保 `predict_proba` 輸出的 confidence 受過良好校準。
   - 保障 Walk-forward Validation 的前提，校準集不能偷看未來測試集。

4. **全面訓練與比較分析**
   - 新模型建立完成後，執行 `uv run python scripts/train_model.py --strategy pm_v2 --all`。
   - 執行 `uv run python scripts/backtest.py --strategy pm_v2 --all --platform polymarket`。
   - 執行 `PYTHONPATH=src uv run python scripts/polymarket/compute_metrics.py --strategy pm_v2`。
   - 將新建立模型的 `metrics.json` 與先前的診斷比較，檢查 `brier_score` 是否低於 `pm_v1` 且預防了極端的 Confidence 值產生。

## 不要做的事

- 不要在 `analytics/*` 中硬塞寫特例來修飾 `brier_score`，而是要從模型端的 `pm_v2` 老老實實做機率校準。
- 不要動 `pm_v1` 的程式碼與回測資料，留下它才能進行 A/B 比對。

## 驗收標準

1. 成功建立 `pm_v2` 並確保它包含機率校準流程 (`CalibratedClassifierCV` 等)。
2. `uv run python scripts/train_model.py --strategy pm_v2 --timeframe 5` 和 `backtest.py` 能成功跑出新的一輪信號。
3. `compute_metrics.py` 的 Calibration 分析顯示 `brier_score` 低於 `0.285` (或至少低於 Baseline Random Prediction 的 `0.249`)，預期的勝率跟實際勝率對齊更緊密。
4. `uv run pytest tests/strategies/test_pm_v2.py -v` 測試通過（若需造假 Dummy 資料，需確保輸出 `alpha`, `direction`, `confidence` 在合理範疇）。

---

## Coding Agent 回報區

### 實作結果
<!-- 請填寫 -->

### 驗收自檢
<!-- 請逐條確認 -->

### 遇到的問題
<!-- 請填寫 -->

### PROGRESS.md 修改建議
<!-- 請填寫 -->

---

## Review Agent 回報區

### 審核結果
<!-- PASS / FAIL / PASS WITH NOTES -->

### 驗收標準檢查
<!-- 請逐條確認 -->

### 修改範圍檢查
<!-- 請確認有沒有動到不該動的檔案 -->

### 發現的問題
<!-- 請填寫 -->

### PROGRESS.md 修改建議
<!-- 請填寫 -->
