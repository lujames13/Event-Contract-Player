# PM-3-lite: Order Book Spread Snapshot 分析

## 1. Spread 統計表

| 指標 | 5m Market | 15m Market |
|------|-----------|------------|
| Median Spread | 0.0100 | 0.0100 |
| Mean Spread | 0.0115 | 0.0102 |
| P25 / P75 Spread | 0.0100 / 0.0100 | 0.0100 / 0.0100 |
| Spread at 0-60s | 0.0100 | - |
| Spread at 60-180s | 0.0100 | - |
| Spread at 180-240s | nan | - |
| Spread at last 60s | nan | - |

## 2. Depth 統計 (Slippage)
- **$50 Order Size**: 
  - 5m: 1.34%
  - 15m: 0.99%
- **$100 Order Size**:
  - 5m: 1.44%
  - 15m: 1.06%

## 3. 結論
- **Typical Spread**: 0.0100
- **Total Cost (Spread + Taker Fee)**: 在 $50 order size 下約 4.12% (含 3.12% fee)

## 4. Binance Price Lead 觀測 (PM-6.5)
- **Lag 分析**: Binance price lead 可能可行 (Lag ~20s > 2s E2E)
- **結論**: 在 5s 採樣精度下，Lag 觀測受限。

