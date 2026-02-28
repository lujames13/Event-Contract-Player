# PM Model Iterations — Polymarket 回歸模型實驗追蹤

> 🔬 **Polymarket 模型實驗獨立追蹤文件**
>
> 此文件是 coding agent 在 Polymarket 模型探索階段的主要工作場域。
> Agent 依照下方規則自主迭代，架構師定期 review。
>
> **與 Gate 1 `MODEL_ITERATIONS.md` 的差異：**
> - 模型目標從**二元分類**改為**回歸預測**（price change %）
> - 評估指標新增 MAE、幅度-DA 相關性、Top-quartile DA、Alpha curve
> - Timeframe 改為 Polymarket 的 5m / 15m
> - Breakeven 從 Binance 的 54-56% 降至 Polymarket Maker 的 ~50%

---

## 核心設計：回歸驅動的交易框架

```
訓練階段：
  OHLCV features → 回歸模型 → E[price_change_%]
  Label: (close[t+N] - close[t]) / close[t] × 100

推理 → 交易決策：
  predicted_change = model.predict(features)
  direction = "higher" if predicted_change > 0 else "lower"
  magnitude = abs(predicted_change)  # 信心度 proxy
  
  # Live 交易（未來）：
  # alpha = model_implied_prob - polymarket_market_price
  # 若 alpha > threshold → 下單
```

**模型訓練完全不依賴 Polymarket 資料。** 訓練只用 Binance 1m OHLCV。
Polymarket market price 僅在 live 交易決策層使用。

---

## 收斂標準

| 指標 | 門檻 | 說明 |
|------|------|------|
| 方向 DA（sign accuracy） | > 52% | 回歸模型的方向判斷準確率 |
| 幅度-DA 正相關 | Spearman ρ > 0, p < 0.05 | 預測幅度越大 → 方向越準（回歸框架核心價值） |
| Top-quartile DA | > 55% | 預測幅度最大的 25% 交易的方向準確率 |
| OOS PnL > 0 | payout_ratio = 2.0 | 模擬 Polymarket maker 交易 |
| 最低 OOS 樣本數 | ≥ 500 | 每個 timeframe |

**PnL 計算方式：** 所有交易使用 `min_threshold = 0`（不過濾），payout_ratio = 2.0（Polymarket maker），settlement_condition = `>=`。

**達標定義：** 上述 5 項全部滿足。

---

## Label 定義

```python
# 回歸 label：未來 N 分鐘的百分比價格變動
label = (close[t + timeframe_minutes] - close[t]) / close[t] * 100

# 範例：
# close[t] = 100000, close[t+5] = 100150
# label = (100150 - 100000) / 100000 * 100 = 0.15 (%)
```

- 對 5m timeframe：`close[t+5] - close[t]` 的百分比
- 對 15m timeframe：`close[t+15] - close[t]` 的百分比
- **不做 winsorize / clip**：讓模型學習完整分布（但使用 Huber loss 降低極端值影響）

---

## 評估指標定義

回測完成後，對每個「策略 × timeframe」計算以下指標：

### 回歸品質指標
| 指標 | 計算方式 | 用途 |
|------|---------|------|
| **MAE** | mean(\|predicted - actual\|) | 預測精確度 |
| **RMSE** | sqrt(mean((predicted - actual)²)) | 對大誤差敏感 |
| **Direction DA** | mean(sign(predicted) == sign(actual)) | 方向準確率（= 二元分類的 DA） |

### 交易品質指標（核心）
| 指標 | 計算方式 | 用途 |
|------|---------|------|
| **幅度-DA 相關性** | Spearman(abs(predicted), is_direction_correct) | 預測越有信心 → 方向越準？ |
| **Top-Q1 DA** | DA of top 25% by abs(predicted) | 高信心交易的勝率 |
| **Top-Q1 PnL** | PnL of top 25% by abs(predicted) | 高信心交易的盈虧 |
| **Alpha Curve** | 按 abs(predicted) 分 4 桶，每桶的 DA 和 PnL | 信心度 vs 獲利的完整關係 |
| **Total PnL** | Σ(payout if win, -bet if lose), payout=2.0 | 整體盈虧 |
| **Sharpe Ratio** | mean(daily_pnl) / std(daily_pnl) | 風險調整後收益 |

### Scoreboard 欄位

| 欄位 | 說明 |
|------|------|
| 策略 | 策略名稱（如 `pm_xgb_reg_v1`） |
| TF | Timeframe（5m / 15m） |
| MAE | Mean Absolute Error (%) |
| Dir DA | 方向準確率 |
| ρ(mag,DA) | 幅度-DA Spearman 相關係數 |
| Q1 DA | Top-quartile DA |
| Sharpe | Sharpe Ratio |
| PnL | 總 PnL（USDT，假設每筆 $10） |
| 樣本 | OOS 交易筆數 |
| PnL ✓ | 是否 > 0 |
| Train Win | 訓練窗口天數 |

---

## Agent 自主迭代規則

### 工作流程

1. **選擇改進方向**：從下方「改進方向清單」中選擇，或根據上一輪結果提出新假設
2. **記錄實驗計畫**：在下方新增 Experiment 區塊，寫下假設、修改內容、預期影響
3. **實作修改**：建立新策略，必須繼承 `BaseStrategy`（回歸策略的 `predict()` 內部做回歸，但仍回傳 `PredictionSignal` 格式）
4. **跑 walk-forward 回測**：5m + 15m 全跑，記錄結果
5. **分析與比較**：與上一輪和 baseline 比較，判斷改善方向
6. **更新此文件**：填入結果，更新 Scoreboard
7. **更新 PROGRESS.md**：將最新結果同步

### 回測指令

```bash
# 訓練模型
uv run python scripts/train_model.py --strategy <strategy_name> --timeframe <5|15>

# 跑回測
uv run python scripts/backtest.py --strategy <strategy_name> --timeframe <5|15> --platform polymarket

# 批量
for tf in 5 15; do
  uv run python scripts/train_model.py --strategy <strategy_name> --timeframe $tf
  uv run python scripts/backtest.py --strategy <strategy_name> --timeframe $tf --platform polymarket
done
```

### 策略命名規則

- 格式：`pm_{架構}_reg_{版本}` — 例如 `pm_xgb_reg_v1`, `pm_lgbm_reg_v1`, `pm_cnn_reg_v1`
- `pm_` 前綴：區分 Polymarket 策略與 Binance 時代策略
- `_reg_`：標記為回歸模型（區分於 `pm_v1` 等分類模型）
- 每個策略對應 `src/btc_predictor/strategies/{策略名}/` 目錄

### 停止條件

- **任何 timeframe 達到收斂標準** → 在 PROGRESS.md 標記為候選，繼續優化
- **連續 3 輪實驗無改善**（所有 timeframe 的 Dir DA 和 Top-Q1 DA 都沒有提升）→ 停下，在 Discussion 區記錄瓶頸，等架構師 review
- **發現基礎設施問題**（如回歸 label 計算 bug、回測引擎問題）→ 停止模型實驗，在 PROGRESS.md Known Issues 記錄

---

## 模型架構候選人

| # | 策略名稱 | 架構 | Loss Function | 備註 |
|---|---------|------|--------------|------|
| 1 | `pm_xgb_reg_v1` | XGBoost | `reg:pseudohubererror` | Tree-based baseline |
| 2 | `pm_lgbm_reg_v1` | LightGBM | `huber` | Gate 1 最佳來源 |
| 3 | `pm_cb_reg_v1` | CatBoost | `Huber:delta=0.5` | Gate 1 10m 最佳 DA |
| 4 | `pm_mlp_reg_v1` | MLP (3-layer) | Huber loss (PyTorch) | Neural baseline |
| 5 | `pm_tabnet_reg_v1` | TabNet | Huber loss | 注意力機制，自動特徵選擇 |
| 6 | `pm_cnn_reg_v1` | 1D-CNN | Huber loss (PyTorch) | 直接吃 raw window，Feature Set B |
| 7 | `pm_lstm_reg_v1` | LSTM/GRU (2-layer, h=64) | Huber loss (PyTorch) | 時序記憶，Feature Set B |

所有模型統一使用 Huber loss（或等效 robust regression loss）。

---

## 特徵設計

### Feature Set A — Short-term TA（tree-based + MLP + TabNet 共用）

> 為 5m/15m 短 timeframe 重新設計。移除長週期雜訊，聚焦近期微結構。

| 類別 | 特徵 | 參數 | 說明 |
|------|------|------|------|
| **短期動量** | ret_1m, ret_2m, ret_3m, ret_5m | — | 最近 1-5 分鐘的 return |
| **短期波動** | vol_3m, vol_5m, vol_10m | rolling std of ret_1m | 近期波動率 |
| **短週期 RSI** | rsi_7 | period=7 | 比 RSI-14 更靈敏 |
| **短週期 EMA** | ema_3, ema_8, ema_13 | — | 取代 MACD(12,26,9) |
| **EMA 交叉** | ema_3_8_diff, ema_8_13_diff | ema_fast - ema_slow | 動量方向信號 |
| **短週期 BB** | bb_upper_10, bb_middle_10, bb_lower_10 | period=10 | 短期布林帶 |
| **BB 衍生** | bb_pct_b_10, bb_dist_10 | — | 價格在帶內位置 |
| **短週期 ATR** | atr_7 | period=7 | 短期波動幅度 |
| **成交量脈衝** | vol_ratio_3m, vol_ratio_5m | volume / rolling_mean(volume, N) | 異常成交量偵測 |
| **K 線形態** | candle_body_ratio, candle_range_pct | body/range, (high-low)/close | 微結構信號 |
| **OBV 動量** | obv, obv_ret_3m | OBV pct_change(3) | 成交量確認 |
| **時間** | hour_sin, hour_cos, day_sin, day_cos | — | 保留 |

**總特徵數：** ~25 個（比 Gate 1 的 ~40 個精簡）

### Feature Set B — Raw Window（1D-CNN / LSTM 專用）

| 輸入 | Shape | 說明 |
|------|-------|------|
| 最近 N 根 K 線的 [O, H, L, C, V] | (N, 5) | N ∈ {10, 20, 30}（作為超參數） |
| Normalization | 每根除以 window 第一根的 close | 消除 price level 依賴 |

Neural 模型可同時嘗試 Feature Set A（tabular input）和 Feature Set B（sequence input）。

---

## 實驗變數空間

> 除了模型架構和特徵集，以下也是 coding agent 可以探索的實驗軸：

| 變數 | 候選值 | 說明 |
|------|--------|------|
| Train window | 30, 60, 90 天 | 歷史窗口長度 |
| Huber delta | 0.1, 0.5, 1.0, 1.5 | 控制 Huber loss 對極端值的容忍度 |
| Feature selection | 全量 / Boruta / SHAP top-K | 特徵篩選方式 |
| Purged gap | 0, 5, 15 分鐘 | Walk-forward train/test 間隔，避免 label leakage |
| Early stopping | 有 / 無 | 用 validation set 做 early stopping |

**重要：一次只改一個變數，才能歸因效果。** 例外：第一輪 baseline 可以同時設定多個 reasonable default。

---

## 改進方向清單

> Agent 可以從這裡選擇下一步，也可以根據實驗結果自行提出新方向。
> 完成某個方向後在前面標 ✅。

### 特徵工程
- [ ] **Boruta 特徵選擇**：從 Feature Set A 中移除噪音特徵
- [ ] **SHAP 分析**：理解哪些特徵驅動預測
- [ ] **Feature Set A 的短週期變體**：嘗試更短的 lookback（如 RSI-5, BB-7）
- [ ] **微結構特徵擴展**：tick direction, volume profile, VWAP deviation
- [ ] **多尺度特徵**：同時用 Feature Set A + 少量長期特徵（如 ret_30m 作為 trend context）

### 訓練方式
- [ ] **Huber delta 調優**：不同 delta 值對回歸品質的影響
- [ ] **Quantile regression**：預測 p10/p50/p90 而非點估計
- [ ] **Sample weight 時間衰減**：近期數據權重更高
- [ ] **Purged walk-forward**：train/test gap 防止 leakage
- [ ] **超參數調優**：Optuna 搜索
- [ ] **不同 train window**：30 / 60 / 90 天

### 模型架構
- [ ] **所有 7 個架構的 baseline 比較**：Feature Set A，default 超參數
- [ ] **Neural 模型的 Feature Set B 實驗**：raw window input
- [ ] **Ensemble / Stacking**：多個模型的加權組合

### 後處理
- [ ] **幅度 → 機率映射**：用回測數據擬合 `abs(predicted_change)` → `P(direction_correct)` 的校準函數
- [ ] **最佳 min_threshold 搜索**：在回測中找 PnL 最大化的最低交易幅度門檻
- [ ] **Per-timeframe 獨立校準**：5m 和 15m 的最佳參數可能不同

---

## 建議的實驗順序

### 第一輪：Breadth-first Baseline（所有 7 個架構）

所有架構使用以下統一設定：
- Feature Set A（tree-based + MLP + TabNet）/ Feature Set B（CNN + LSTM）
- Train window = 60 天
- Huber loss with default delta
- 無 feature selection
- 無 purged gap
- 5m + 15m 全跑

**目標：** 建立跨架構的完整 scoreboard，識別 top 3。

### 第二輪：Top 3 深入調整

對第一輪的 top 3 做：
- Feature selection（Boruta / SHAP）
- Train window 實驗（30 / 60 / 90）
- 超參數 Optuna 調優
- Huber delta 調優

### 第三輪起：冠軍深入 + Ensemble

- 最佳架構的進一步特徵工程
- 嘗試 2-3 個模型的加權 ensemble
- 幅度 → 機率校準函數擬合

---

## Scoreboard

> 按 Top-Q1 DA 降序排列。**粗體** = 達到收斂標準。

### 5m

| 排名 | 實驗 | 策略 | MAE(%) | Dir DA | ρ(mag,DA) | Q1 DA | Sharpe | PnL | 樣本 | PnL ✓ | Train Win | 日期 |
|------|------|------|--------|--------|-----------|-------|--------|-----|------|------|-----------|------|
| — | — | — | — | — | — | — | — | — | — | — | — | — |

### 15m

| 排名 | 實驗 | 策略 | MAE(%) | Dir DA | ρ(mag,DA) | Q1 DA | Sharpe | PnL | 樣本 | PnL ✓ | Train Win | 日期 |
|------|------|------|--------|--------|-----------|-------|--------|-----|------|------|-----------|------|
| — | — | — | — | — | — | — | — | — | — | — | — | — |

---

## Experiments

> 由 coding agent 在迭代中新增。

（待第一輪實驗填入）

---

## Discussion

> 記錄瓶頸分析、架構師 review 結論、重大決策變更。

（待實驗開始後填入）