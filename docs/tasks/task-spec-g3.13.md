# Task Spec G3.13 — Polymarket 回歸模型第一輪 Baseline 實驗 (7 架構)
<!-- status: todo -->
<!-- created: 2026-03-03 -->
<!-- architect: Antigravity -->

## 目標

承接 G3.12 基礎設施的建置，本任務聚焦於執行原定的 G3.12.2 目標：完成第一輪 breadth-first baseline 實驗（7 個架構 × 2 個 timeframe）。
這將為 Polymarket 的模型迭代打下基礎，讓我們可以分辨哪種模型架構（Tree-based vs. Neural Networks）在預測價格變化幅度上更具優勢。

對應 PROGRESS.md: Gate 3 > Task 3.4.4（模型迭代改進）

---

## 修改範圍

**需要修改/新增的檔案：**

- `docs/PROGRESS.md`
  - 更新任務進度。

- 共用特徵模組（新增）：
  - `src/btc_predictor/strategies/pm_common/features_short.py` (Feature Set A)
  - `src/btc_predictor/strategies/pm_common/features_window.py` (Feature Set B)

- 7 個模型架構目錄與實作（新增）：
  - `src/btc_predictor/strategies/pm_xgb_reg_v1/`
  - `src/btc_predictor/strategies/pm_lgbm_reg_v1/`
  - `src/btc_predictor/strategies/pm_cb_reg_v1/`
  - `src/btc_predictor/strategies/pm_mlp_reg_v1/`
  - `src/btc_predictor/strategies/pm_tabnet_reg_v1/`
  - `src/btc_predictor/strategies/pm_cnn_reg_v1/`
  - `src/btc_predictor/strategies/pm_lstm_reg_v1/`
  - 每個目錄內需包含 `__init__.py`, `strategy.py`, `model.py`。特徵請直接 import `pm_common` 中的寫法。

- 測試腳本（新增）：
  - 至少針對 `pm_common` 內的特徵產生邏輯建立 unit tests：`tests/strategies/test_pm_common_features.py`
  - 為這 7 個策略架構新增基礎功能測試，例如預測輸出格式是否正確：`tests/strategies/test_pm_reg_baselines.py`

- 實驗紀錄（修改）：
  - `docs/PM_MODEL_ITERATIONS.md` （更新 Scoreboard 和 Experiment 紀錄）。

**依賴更新：**
- `pyproject.toml` / `uv.lock`
  - 需執行 `uv add pytorch-tabnet`。

**不可修改的檔案：**
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/strategies/base.py` （不可修改基底架構）
- `src/btc_predictor/models.py` （PredictionSignal 不可修改）
- 原有的所有 `pm_v1/`, `xgboost_v1/`, `lgbm_v2/`, `catboost_v1/` 等策略，以及與分類模型相關的機制。
- `src/btc_predictor/analytics/`

---

## 實作要求

### 1. 共用特徵抽取 (Feature Sets)

**Feature Set A (`features_short.py`)：**
- 供 XGBoost, LightGBM, CatBoost, MLP, TabNet 使用。
- 需要標準的技術指標特徵、時間編碼等。
- 確保所有模型 import 這個統一個 generator，不要各自複製程式碼。

**Feature Set B (`features_window.py`)：**
- 供 CNN, LSTM 使用。
- 負責產生 normalized raw window input (例如過去 30 分鐘或 60 分鐘的 OHLCV time-series 矩陣)。
- 注意：Window 的最後一筆應為 $t$ 當時的收盤狀態，不可以包含 $t+1$ 的數據以防止前視偏差。

### 2. 7 架構策略實作

| # | 策略名稱 | 架構 | Feature Set | 特殊依賴 |
|---|---------|------|-------------|---------|
| 1 | `pm_xgb_reg_v1` | XGBoost Regressor | A | xgboost |
| 2 | `pm_lgbm_reg_v1` | LightGBM Regressor | A | lightgbm |
| 3 | `pm_cb_reg_v1` | CatBoost Regressor | A | catboost |
| 4 | `pm_mlp_reg_v1` | MLP (3-layer, h=128) | A | torch |
| 5 | `pm_tabnet_reg_v1` | TabNet | A | pytorch-tabnet |
| 6 | `pm_cnn_reg_v1` | 1D-CNN | B | torch |
| 7 | `pm_lstm_reg_v1` | LSTM (2-layer, h=64) | B | torch |

- **統一設定**（第一輪 default）：
  * Train window = 60 天
  * 損失函數：Huber loss 或 Pseudo-Huber（依套件支援度選擇）
  * 無 feature selection, 無 purged gap
  * Neural Networks 需包含 validation set (train window 最後 20%) 作為 early stopping 機制。

### 3. Baseline 回測執行與記錄

- 對上述 7 個策略，各跑 5m 以及 15m timeframe 的 walk-forward backtest。
- 使用 `scripts/backtest.py`。預期將在 `reports/` 下產出 14 份報告。
- 將 `regression_stats` 的重點指標（MAE, direction_da, 等）登記至 `docs/PM_MODEL_ITERATIONS.md` 的 Scoreboard。

---

## 不要做的事

- **絕對不可以**將 Polymarket 的價格資料（market price）放入 Feature Layer 中訓練。特徵必須僅依賴 Binance OHLCV。
- **不要**在第一次 baseline 裡就進行 Hyperparameter Tuning。這輪目的是測量 default 設定下的表現，確保管道跑得動且數據合理。請花最多時間在實作與確保特徵不漏水上，不要花在那微調模型參數。
- **注意記憶體限制**：神經網路（CNN/LSTM/TabNet）的隱藏層大小（h）、batch size 必須在合理的範圍，以確保不超過 8GB VRAM。

---

## 驗收標準

1. 獨立建立 `pm_common` 特徵模組，並成功撰寫對應的單元測試且 `uv run pytest tests/strategies/test_pm_common_features.py` 通過。
2. `uv add pytorch-tabnet` 成功且無環境衝突。
3. 7 種模型策略完整實作，且對應的載入/預測測試皆通過。
4. 成功執行並產出 14 份 backtest JSON 報告（7 模型 × 2 timeframe）。
5. `docs/PM_MODEL_ITERATIONS.md` 包含所有 14 筆 baseline 測試的分數，且 Experiment 區塊對該輪測試有簡短觀察。

---

## Coding Agent 回報區

### 實作結果
- 

### 驗收自檢
- [ ] 1. 通過 `test_pm_common_features.py` 測試。
- [ ] 2. 成功新增並安裝 pytorch-tabnet。
- [ ] 3. 7 種模型實作完畢且通過簡單測試。
- [ ] 4. 14 份報告產出完成。
- [ ] 5. PM_MODEL_ITERATIONS.md 已更新。

### 遇到的問題
- 

### PROGRESS.md 修改建議
- 

---

## Review Agent 回報區

### 審核結果
- [ ] PASS
- [ ] FAIL
- [ ] PASS WITH NOTES

### 驗收標準檢查
- [ ] ...

### 發現的問題
- ...
