# Task Spec G3.12 — Polymarket 回歸模型探索基礎設施 + 第一輪 Baseline
<!-- status: todo -->
<!-- created: 2026-03-01 -->
<!-- architect: Antigravity -->

## 目標

建立回歸預測模型的基礎設施（labeling、回測引擎擴展、評估指標），並啟動第一輪 breadth-first baseline 實驗（7 個架構 × 2 個 timeframe）。

本任務分兩階段：
1. **G3.12.1（基礎設施）**：修改 labeling、回測引擎、stats 模組以支援回歸模型。
2. **G3.12.2（自主迭代）**：依照 `docs/PM_MODEL_ITERATIONS.md` 的規則，完成第一輪 7 架構 baseline 比較，並根據結果進入第二輪深入調整。

對應 PROGRESS.md: Gate 3 > Task 3.4.4（模型迭代改進）

---

## 階段一：G3.12.1 — 回歸基礎設施

### 修改範圍

**需要修改的檔案：**

- `src/btc_predictor/infrastructure/labeling.py`
  - 新增函數 `add_regression_labels(df, timeframe_minutes)` → 加入 `price_change_pct` 欄位
  - 公式：`(close[t+N] - close[t]) / close[t] * 100`
  - 既有的 `add_direction_labels()` 不可修改（分類模型仍需使用）

- `src/btc_predictor/backtest/engine.py`
  - `_process_fold()` 需支援回歸策略：當策略的 `predict()` 回傳的 `PredictionSignal` 是由回歸模型產生時（direction 和 confidence 由回歸輸出轉換而來），引擎的 PnL 計算邏輯不變（仍然是二元結算：win/lose × payout_ratio），因為 Polymarket 的實際結算就是二元的。
  - **關鍵：回歸策略的 `strategy.predict()` 仍然回傳標準 `PredictionSignal`。** 回歸 → 二元的轉換發生在策略內部，引擎不需要知道策略用的是回歸還是分類。
  - 需要新增：在 backtest report 中記錄額外的回歸指標（見下方 stats 擴展）。

- `src/btc_predictor/backtest/stats.py`
  - 新增函數 `compute_regression_stats(trades, predictions)` 計算：
    - `mae`：Mean Absolute Error of predicted vs actual price change
    - `rmse`：Root Mean Squared Error
    - `direction_da`：sign accuracy（= 現有 DA，但從回歸輸出推導）
    - `magnitude_da_correlation`：Spearman(abs(predicted_change), is_direction_correct)
    - `top_quartile_da`：top 25% magnitude 的方向準確率
    - `top_quartile_pnl`：top 25% magnitude 的 PnL
    - `alpha_curve`：按 abs(predicted_change) 分 4 桶，每桶的 DA 和 PnL
  - 此函數接收的 `predictions` 是一個 list of `(predicted_change_pct, actual_change_pct)` tuples，需要在 `_process_fold` 或回測後處理中收集。

- `scripts/train_model.py`
  - 確保支援新的 `pm_*_reg_*` 策略名稱。回歸策略的 `fit()` 接收 OHLCV + timeframe，內部自行呼叫 `add_regression_labels()` 產生回歸 label。

- `scripts/backtest.py`
  - 確保回測結果 JSON 包含回歸指標（mae, rmse, direction_da, magnitude_da_correlation, top_quartile_da, alpha_curve）。

**需要新增的檔案：**

- `tests/infrastructure/test_regression_labeling.py`
  - 測試 `add_regression_labels()` 的正確性
  - 驗證 5m 和 15m 的 label 計算
  - 驗證邊界情況（NaN handling, 資料不足時）

- `tests/backtest/test_regression_stats.py`
  - 測試 `compute_regression_stats()` 的計算正確性
  - 用已知數據驗證 MAE、direction DA、Spearman 相關性、top-quartile 計算

**不可修改的檔案：**
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/strategies/pm_v1/` 及所有既有策略（作為對照）
- `src/btc_predictor/strategies/base.py`（BaseStrategy 介面不變）
- `src/btc_predictor/models.py`（PredictionSignal 結構不變）
- `src/btc_predictor/analytics/` 系統

### 實作要求

1. **回歸 Label 函數**

```python
def add_regression_labels(
    df: pd.DataFrame, 
    timeframe_minutes: int
) -> pd.DataFrame:
    """
    Add regression labels: future price change percentage.
    
    Label = (close[t + timeframe] - close[t]) / close[t] * 100
    
    Args:
        df: OHLCV DataFrame with DatetimeIndex (1m frequency)
        timeframe_minutes: prediction horizon in minutes
    
    Returns:
        DataFrame with added 'price_change_pct' column.
        Rows where future close is unavailable will have NaN.
    """
```

- 不做 winsorize / clip（讓模型學習完整分布）
- 必須正確處理 off-by-one：`close[t]` 是預測時刻的收盤價，`close[t + timeframe_minutes]` 是結算時刻的收盤價
- 不得引入前視偏差：label 只依賴未來數據，不能洩漏到特徵中

2. **回歸策略的 BaseStrategy 適配**

回歸策略仍然繼承 `BaseStrategy`，`predict()` 仍然回傳 `PredictionSignal`。轉換邏輯在策略內部：

```python
# 策略內部虛擬碼
class PMXGBRegV1Strategy(BaseStrategy):
    def predict(self, ohlcv, timeframe_minutes) -> PredictionSignal:
        features = generate_features(ohlcv)
        predicted_change_pct = self.model.predict(features)  # 回歸輸出
        
        direction = "higher" if predicted_change_pct > 0 else "lower"
        confidence = min(abs(predicted_change_pct) / SCALE_FACTOR, 0.99)
        # SCALE_FACTOR 可用訓練集的 abs(label).quantile(0.95) 作為 normalize 基準
        
        return PredictionSignal(
            strategy_name=self.name,
            direction=direction,
            confidence=confidence,
            # ... 其他欄位
        )
```

**注意：** `confidence` 欄位的語義在回歸策略中代表「預測幅度的 normalized magnitude」，不再是機率。但 PredictionSignal 的型別不變。回測引擎仍用 `confidence` 來決定是否交易（目前 min_threshold = 0，全部交易）。

3. **回歸指標收集機制**

在 walk-forward 回測過程中，需要額外收集每筆交易的 `(predicted_change_pct, actual_change_pct)` pair。建議的做法：

- 在 `PredictionSignal` 的現有欄位中暫存 `predicted_change_pct`（可使用 `alpha` 欄位，因為在純回測環境中 alpha 未被使用）
- 或者：在 `_process_fold` 中額外計算 actual_change_pct 並記錄
- **選擇哪種做法由 coding agent 自行決定**，只要 `compute_regression_stats()` 能拿到正確的 predicted/actual pairs 即可

4. **回測報告 JSON 擴展**

現有的 backtest report JSON 包含 `total_da`, `higher_da`, `lower_da`, `total_pnl`, `sharpe_ratio` 等。新增：

```json
{
  "regression_stats": {
    "mae": 0.045,
    "rmse": 0.089,
    "direction_da": 0.534,
    "magnitude_da_correlation": {
      "spearman_rho": 0.12,
      "p_value": 0.003
    },
    "top_quartile_da": 0.571,
    "top_quartile_pnl": 45.2,
    "alpha_curve": [
      {"bucket": "Q4_lowest", "da": 0.502, "pnl": -12.3, "n": 150},
      {"bucket": "Q3", "da": 0.518, "pnl": 5.1, "n": 150},
      {"bucket": "Q2", "da": 0.541, "pnl": 23.7, "n": 150},
      {"bucket": "Q1_highest", "da": 0.571, "pnl": 45.2, "n": 150}
    ]
  }
}
```

### 驗收標準（G3.12.1）

1. `uv run pytest tests/infrastructure/test_regression_labeling.py -v` 通過
2. `uv run pytest tests/backtest/test_regression_stats.py -v` 通過
3. `uv run pytest` 全部既有測試仍通過（不能 break 現有功能）
4. 可以用一個簡單的 dummy 回歸策略跑完 backtest 且產出包含 `regression_stats` 的 JSON report

---

## 階段二：G3.12.2 — 自主迭代（第一輪 + 後續）

### 前置條件

G3.12.1 完成且所有測試通過。

### 工作模式

進入自主迭代模式，依照 `docs/PM_MODEL_ITERATIONS.md` 的規則執行。

### 第一輪任務：7 架構 Baseline

為以下每個架構建立策略目錄並跑 5m + 15m 回測：

| # | 策略名稱 | 架構 | Feature Set | 特殊依賴 |
|---|---------|------|-------------|---------|
| 1 | `pm_xgb_reg_v1` | XGBoost Regressor | A | xgboost（已安裝） |
| 2 | `pm_lgbm_reg_v1` | LightGBM Regressor | A | lightgbm（已安裝） |
| 3 | `pm_cb_reg_v1` | CatBoost Regressor | A | catboost（已安裝） |
| 4 | `pm_mlp_reg_v1` | MLP (3-layer, h=128) | A | torch（已安裝） |
| 5 | `pm_tabnet_reg_v1` | TabNet | A | pytorch-tabnet（需安裝） |
| 6 | `pm_cnn_reg_v1` | 1D-CNN | B | torch（已安裝） |
| 7 | `pm_lstm_reg_v1` | LSTM (2-layer, h=64) | B | torch（已安裝） |

**每個策略的目錄結構：**
```
src/btc_predictor/strategies/pm_xgb_reg_v1/
  ├── __init__.py
  ├── strategy.py    # 繼承 BaseStrategy
  ├── features.py    # Feature Set A 或 B
  └── model.py       # 模型訓練、儲存、載入
```

**Feature Set A 實作：**
- 新建一個共用的 `src/btc_predictor/strategies/pm_common/features_short.py`
- 所有使用 Feature Set A 的策略 import 此模組
- 避免每個策略各自複製一份特徵程式碼

**Feature Set B 實作：**
- 新建 `src/btc_predictor/strategies/pm_common/features_window.py`
- 負責產生 normalized raw window input
- CNN 和 LSTM 策略 import 此模組

**統一設定（第一輪 default）：**
- Train window = 60 天
- Huber loss / pseudo-huber（各架構的對應版本）
- 無 feature selection
- 無 purged gap
- Early stopping 有 validation set（train window 最後 20%）

**每個架構跑完後的 checklist：**
1. `uv run pytest tests/strategies/test_{策略名}.py -v` 通過
2. 5m + 15m 回測 report JSON 產出在 `reports/`
3. `docs/PM_MODEL_ITERATIONS.md` Scoreboard 更新
4. Experiment 區塊記錄假設、結果、分析

### 第一輪完成後

比較 Scoreboard，取 top 3 進入第二輪。第二輪方向由 `PM_MODEL_ITERATIONS.md` 的「改進方向清單」引導。

如果第一輪所有架構的 Dir DA 都 < 50.5%（接近隨機），先在 Discussion 區分析原因再繼續，不要盲目進入第二輪。

### 修改範圍（G3.12.2）

**開放範圍，但有邊界：**

- ✅ 可以新增：`src/btc_predictor/strategies/pm_*/` 下的新策略目錄
- ✅ 可以新增：`src/btc_predictor/strategies/pm_common/` 共用特徵模組
- ✅ 可以新增：`tests/strategies/test_pm_*.py` 新測試
- ✅ 必須更新：`docs/PM_MODEL_ITERATIONS.md`、`docs/PROGRESS.md`
- ✅ 可以安裝新依賴：`uv add pytorch-tabnet`（TabNet 需要）
- ❌ 不可修改：`src/btc_predictor/strategies/base.py`（BaseStrategy 介面）
- ❌ 不可修改：`src/btc_predictor/models.py`（PredictionSignal 結構）
- ❌ 不可修改：`docs/DECISIONS.md`、`config/project_constants.yaml`
- ❌ 不可修改：既有策略（`pm_v1/`, `xgboost_v1/`, `lgbm_v2/`, `catboost_v1/` 等）
- ❌ 不可修改：`src/btc_predictor/analytics/`

### 不要做的事

- 不要把 Polymarket market price 作為特徵或 label 的一部分。模型訓練只用 Binance OHLCV。
- 不要修改既有的二元分類回測流程。回歸基礎設施是新增，不是替換。
- 不要在單次實驗中同時改多個變數（第一輪 baseline 除外，因為是全新架構的初始化）。
- 不要嘗試需要 > 8GB VRAM 的模型配置。LSTM/CNN 的 hidden size 和 batch size 需注意。
- 不要引入需要新數據源的特徵（Fear & Greed, DXY, 鏈上數據等），只用 Binance OHLCV。
- 不要花超過 30 分鐘在單個架構的超參數調優上（第一輪是 baseline，用 reasonable default）。

---

## 驗收標準（整體）

### G3.12.1 驗收
1. `uv run pytest tests/infrastructure/test_regression_labeling.py -v` 通過
2. `uv run pytest tests/backtest/test_regression_stats.py -v` 通過
3. `uv run pytest` 全部既有測試通過
4. Dummy 回歸策略可跑完 backtest 並產出含 `regression_stats` 的 JSON

### G3.12.2 驗收（第一輪完成時）
1. `docs/PM_MODEL_ITERATIONS.md` 的 Scoreboard 有 ≥ 7 行（每個架構至少一個 5m 結果）
2. 每個架構有對應的 `tests/strategies/test_pm_*.py` 且通過
3. `reports/` 目錄下有 ≥ 14 個回測報告 JSON（7 架構 × 2 timeframe）
4. `docs/PM_MODEL_ITERATIONS.md` 有 Experiment 區塊記錄每個架構的實驗過程
5. `docs/PROGRESS.md` 已更新 3.4.4 的狀態

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