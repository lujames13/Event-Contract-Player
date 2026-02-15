# Model Iterations

> 🔬 **模型實驗獨立追蹤文件**
>
> 此文件是 coding agent 在 Gate 1 階段的主要工作場域。
> Agent 依照下方規則自主迭代，架構師定期 review。

---

## 收斂標準（來自 DECISIONS.md）

| Timeframe | Breakeven DA | 目標 DA (breakeven + 5%) | Payout Ratio |
|-----------|-------------|------------------------|--------------|
| 10m | 55.56% | 60.6% | 1.80 |
| 30m | 54.05% | 59.1% | 1.85 |
| 60m | 54.05% | 59.1% | 1.85 |
| 1440m | 54.05% | 59.1% | 1.85 |

**信心度校準要求：** 高 confidence bucket 的實際勝率必須 ≥ 低 confidence bucket。
若校準反轉（高 confidence = 低勝率），該模型不合格。

**最低 OOS 樣本數：** ≥ 500 筆交易（每個 timeframe）。

---

## Agent 自主迭代規則

### 工作流程

1. **選擇改進方向**：從下方「改進方向清單」中選擇，或根據上一輪結果提出新假設
2. **記錄實驗計畫**：在下方新增 Experiment 區塊，寫下假設、修改內容、預期影響
3. **實作修改**：建立新策略或修改現有策略，必須繼承 BaseStrategy
4. **跑 walk-forward 回測**：4 個 timeframe 全跑，記錄結果
5. **分析與比較**：與上一輪和 baseline 比較，判斷改善方向
6. **更新此文件**：填入結果，更新 Scoreboard
7. **更新 PROGRESS.md**：將最新結果同步到 Gate 1 的回測結果摘要表

### 停止條件

- **任何 timeframe 達到收斂標準** → 在 PROGRESS.md 標記為 Gate 1 候選，繼續優化其他 timeframe
- **連續 3 輪實驗無改善**（所有 timeframe 的 DA 都沒有提升）→ 停下來，在 Discussion 區記錄瓶頸，等架構師 review
- **發現基礎設施問題**（如回測引擎 bug、label 錯誤）→ 停止模型實驗，在 PROGRESS.md Known Issues 記錄，等修復後再繼續

### 策略命名規則

- 格式：`{架構}_{版本}` — 例如 `xgboost_v1`, `xgboost_v2`, `lgbm_v1`, `mlp_v1`
- 同架構的不同版本遞增版號
- 不同架構使用不同前綴
- 每個策略對應 `src/btc_predictor/strategies/{策略名}/` 目錄

### 回測指令

```bash
# 訓練模型（如果策略需要）
uv run python scripts/train_model.py --strategy <strategy_name> --timeframe <10|30|60|1440>

# 跑回測
uv run python scripts/backtest.py --strategy <strategy_name> --timeframe <10|30|60|1440>

# 批量跑所有 timeframe
for tf in 10 30 60 1440; do
  uv run python scripts/backtest.py --strategy <strategy_name> --timeframe $tf
done
```

---

## 改進方向清單

> Agent 可以從這裡選擇下一步，也可以根據實驗結果自行提出新方向。
> 完成某個方向後在前面標 ✅。

### 特徵工程改進
- [ ] **Boruta 特徵選擇**：移除噪音特徵，可能比全特徵效果更好
- [ ] **SHAP 分析**：理解目前哪些特徵在驅動預測，哪些是噪音
- [ ] **不同 rolling window 組合**：目前固定用 [1,3,5,10,30,60] 週期，嘗試更多變體
- [ ] **微結構特徵**：bid-ask spread proxy、成交量突變、price momentum 分散度
- [ ] **多尺度特徵**：同時用 1m 和 5m/15m K 線的特徵（需注意不引入前視偏差）
- [ ] **移除冗餘特徵**：ret_Nm 和 log_ret_Nm 高度相關，可能只需保留一組

### 訓練方式改進
- [ ] **信心度校準**：Platt scaling 或 isotonic regression 校準 predict_proba 輸出
- [ ] **Early stopping 用 validation set**：目前 train_model 沒有用 val_data，可能過擬合
- [ ] **樣本權重**：近期數據權重更高（時間衰減加權）
- [ ] **Purged walk-forward**：train/test 之間加 gap 避免 label leakage
- [ ] **超參數調優**：Optuna 搜索 max_depth, n_estimators, learning_rate 等
- [ ] **Class balancing 策略**：目前用 scale_pos_weight，嘗試 SMOTE 或 undersampling
- [ ] **不同 train window 大小**：目前固定 60 天，嘗試 30/90/120 天

### 模型架構擴展
- [ ] **LightGBM**：通常比 XGBoost 更快，可能在同樣特徵上表現不同
- [ ] **CatBoost**：對 categorical 特徵有原生支援，且自帶 ordered boosting 防過擬合
- [ ] **簡單 MLP**：2-3 層全連接網路，看 neural 方法是否有優勢
- [ ] **N-BEATS**：時序專用架構，可直接對 OHLCV 序列建模
- [ ] **Ensemble / Stacking**：多個弱模型的投票或加權組合

### 後處理改進
- [ ] **Threshold 優化**：不用 0.5 作為 higher/lower 分界，用 ROC 曲線找最佳閾值
- [ ] **Per-timeframe 獨立校準**：不同 timeframe 的最佳閾值可能不同
- [ ] **Confidence bucketing 策略**：不同 confidence 區間用不同下注策略

---

## Scoreboard（所有實驗結果總覽）

> 按 OOS DA 降序排列。**粗體** = 達到 breakeven。

### 10m (Breakeven: 55.56%)

| 排名 | 實驗 | 策略 | OOS DA | Sharpe | 樣本 | 校準 | 日期 |
|------|------|------|--------|--------|------|------|------|
| 1 | 001 | xgboost_v1 | 51.17% | -0.08 | 57457 | ⚠️ 停滯 | 2026-02-15 |

### 30m (Breakeven: 54.05%)

| 排名 | 實驗 | 策略 | OOS DA | Sharpe | 樣本 | 校準 | 日期 |
|------|------|------|--------|--------|------|------|------|
| 1 | 001 | xgboost_v1 | 51.24% | -0.05 | 25863 | ❌ 反轉 | 2026-02-15 |

### 60m (Breakeven: 54.05%)

| 排名 | 實驗 | 策略 | OOS DA | Sharpe | 樣本 | 校準 | 日期 |
|------|------|------|--------|--------|------|------|------|
| 1 | 001 | xgboost_v1 | 50.78% | -0.06 | 13979 | ⚠️ 停滯 | 2026-02-15 |

### 1440m (Breakeven: 54.05%)

| 排名 | 實驗 | 策略 | OOS DA | Sharpe | 樣本 | 校準 | 日期 |
|------|------|------|--------|--------|------|------|------|
| 1 | 001 | xgboost_v1 | 51.91% | -0.06 | 366 | ⚠️ 停滯 | 2026-02-15 |

---

## 實驗記錄

### Experiment 001: XGBoost Baseline

- **日期**：2026-02-14
- **策略名**：`xgboost_v1`
- **假設**：基礎 TA 特徵 + XGBoost 方向分類可以 beat random（DA > 50%）
- **修改內容**：初始實作，無前一輪可比較
  - 特徵：returns (多週期), log returns, volatility, RSI(14), MACD(12,26,9), BB(20,2), ATR(14), 時間編碼 (sin/cos), volume ratio, OBV
  - 模型：XGBoost, max_depth=6, n_estimators=500, lr=0.05, early_stopping=50
  - 訓練：walk-forward, train_days=60, test_days=7
- **預期影響**：建立 baseline，預期 DA 55%+

**結果：**

| TF | OOS DA | Sharpe | Trades | PnL | MDD | Max Consec Loss | 校準 |
|----|--------|--------|--------|-----|-----|-----------------|------|
| 10m | 51.17% | -0.08 | 57457 | -43163 | 43238 | 14 | ⚠️ 停滯 |
| 30m | 51.24% | -0.05 | 25863 | -14458 | 14577 | 12 | ❌ 反轉 |
| 60m | 50.78% | -0.06 | 13979 | -9823 | 9866 | 12 | ⚠️ 停滯 |
| 1440m | 51.91% | -0.06 | 366 | -309 | 333 | 7 | ⚠️ 停滯 |

**信心度校準明細 (10m)：**

| Confidence Bucket | 實際勝率 (10m) | 實際勝率 (30m) | 判定 |
|-------------------|---------------|---------------|------|
| 0.6 - 0.7 | 50.89% | 50.88% | — |
| 0.7 - 0.8 | 51.25% | 50.87% | ⚠️ 停滯/下降 |
| 0.8 - 0.9 | 51.94% | 51.91% | ⚠️ 緩升 |
| 0.9 - 1.0 | 50.80% | 51.53% | ❌ 反轉 |

**分析：**
- DA 50.8% 與隨機猜測接近，模型幾乎沒有預測能力
- 信心度嚴重反轉：模型越「自信」的預測越不準，典型的過擬合特徵
- cumulative PnL 幾乎單調下降，沒有任何盈利階段
- higher DA (49.2%) < lower DA (53.9%)，模型對方向判斷有偏差

**可能原因：**
1. 訓練時沒有 validation set 做 early stopping → 過擬合訓練集
2. 特徵中可能有冗餘/噪音特徵（ret 和 log_ret 高度相關）
3. walk-forward train/test 之間沒有 gap → 潛在 label leakage
4. 所有 timeframe 用同一套特徵，但不同 timeframe 的有效特徵可能不同

**下一步建議：**
1. 首先補跑 30m/60m/1440m 的回測，確認問題是否在所有 timeframe 上一致
2. 加入 early stopping with validation set
3. 信心度校準（Platt scaling）
4. Boruta 特徵選擇去除噪音

---

### Experiment 002: 修復 XGBoost 過擬合 (Validation + Purged Gap)

- **日期**：2026-02-15
- **策略名**：`xgboost_v2`
- **假設**：目前訓練沒用 validation set 做 early stopping，導致過擬合。加入 validation set 並在 train/val 之間留出 `timeframe_minutes` 的 purged gap 可以有效減少過擬合。
- **修改內容**：
  - 實作新的策略 `xgboost_v2`。
  - 在 `fit` 方法中，將訓練數據切出最後 20% 作為 validation set。
  - 在 train 和 validation 數據之間留下 `timeframe_minutes` 行的 gap 以防止標籤洩漏。
  - 使用 XGBoost 的 `early_stopping_rounds=50`。
- **預期影響**：信心度校準改善，高 confidence bucket 的勝率不再反轉，OOS DA 可能微升。

**結果：**

| TF | OOS DA | Sharpe | Trades | PnL | MDD | Max Consec Loss | 校準 |
|----|--------|--------|--------|-----|-----|-----------------|------|
| 10m | — | — | — | — | — | — | 待跑 |
| 30m | — | — | — | — | — | — | 待跑 |
| 60m | — | — | — | — | — | — | 待跑 |
| 1440m | — | — | — | — | — | — | 待跑 |

---

---

## Discussion（瓶頸與待 review 的問題）

_（Agent 連續 3 輪無改善時在此記錄，由架構師 review）_

- **[2026-02-15] 架構師備註**：backtest engine 中 `lower` 方向的勝負判定可能有 bug。
  目前 `is_win = close_price <= open_price`，但平盤對 lower 也應該是 lose。
  在開始新一輪實驗前，應先修正此問題並重跑 Experiment 001 確認影響。