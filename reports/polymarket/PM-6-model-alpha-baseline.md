# PM-6: Model Alpha vs Market Price Baseline 分析

## 1. 實驗設計
- **樣本數**: 300 個已結算 5m BTC 市場
- **評估模型**:
  - `catboost_v1` (10m model): 用於 5m 市場預測 (Timeframe Mismatch)
  - `lgbm_v2` (60m model): 用於 5m 市場預測 (Timeframe Mismatch)
- **Alpha 定義**: `Alpha = Model_P(Up) - Market_Implied_P(Up)`
- **分析焦點**: 不同 Alpha 區間下的模型勝率與 Net Edge

## 2. Alpha 分佈統計

| 指標 | CatBoost v1 (10m) | LGBM v2 (60m) |
|------|-------------------|----------------|
| Mean Alpha | -0.77% | -1.49% |
| Median Alpha | -1.36% | -1.48% |
| Std Dev | 2.47% | 6.41% |
| |alpha| > 5% | 0.67% | 62.33% |
| |alpha| > 10% | 0.00% | 8.67% |

## 3. 條件勝率分析 (CatBoost v1 10m)

| Alpha Range | N | Model Win Rate | Market Implied WR | Net Edge | Taker BE (3.12%) | Maker BE (0%) |
|-------------|---|---------------|-------------------|----------|------------------|---------------|
| -10% ≤ alpha < -5% | 1 | 0.00% | 50.50% | -50.50% | ❌ | ❌ |
| -5% ≤ alpha < 0% | 200 | 45.50% | 50.23% | -4.73% | ❌ | ❌ |
| 0% ≤ alpha < 5% | 98 | 62.24% | 50.28% | +11.97% | ✅ | ✅ |
| 5% ≤ alpha < 10% | 1 | 100.00% | 50.00% | +50.00% | ✅ | ✅ |

## 4. 關鍵發現
1. **Timeframe Mismatch 影響**: 當前模型是針對 10m/60m 訓練的，但在 5m 市場上仍展現出一定的 Alpha 分佈。
2. **Net Edge 觀察**: 當 Alpha 絕對值較大時，模型的勝率是否能覆蓋 Taker Fee (3.12%)。
3. **結算條件**: Polymarket 包含平盤 (>=)，這對 Up 方向有利。

## 5. 結論與優化方向
- **Alpha 現狀**: 量化模型與市場共識的偏離度。
- **Top 優化方向**:
  1. 針對 5m timeframe 訓練專屬模型。
  2. 調整 Label 生成邏輯以匹配 Polymarket 的 `>=` 規則（平盤 = Up）。
  3. 加入 Polymarket 專屬特徵（如 Order Book Imbalance, Funding Rate）。

