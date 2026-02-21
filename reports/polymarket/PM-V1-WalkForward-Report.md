# PM-V1 Walk-Forward 回測報告 (Phase 3)

## 總覽
本報告分析了 Polymarket `pm_v1` 模型的 Walk-forward 測試結果。
測試覆蓋 5m、15m 與 60m 三個 timeframe，採用 `>=` 作為 Higher 方向勝出的結算條件，以符合 Polymarket 的規則。同時，Maker 訂單的 Payout Ratio 設置為 `2.0`（無手續費，預期盈虧平衡為 50.0%）。

## 回測結果摘要

| Timeframe | Total Trades | DA (Acc) | Higher DA | Lower DA | Total PnL (USDT) | Max Drawdown | Sharpe Ratio | Max Loses |
|-----------|--------------|----------|-----------|----------|------------------|--------------|--------------|-----------|
| **5m**    | 2563         | 55.68%   | 56.98%    | 52.26%   | +1712.05         | 135.68       | 0.11         | 8         |
| **15m**   | 1691         | 53.05%   | 52.92%    | 53.27%   | +618.51          | 185.20       | 0.06         | 11        |
| **60m**   | 1150         | 52.70%   | 51.95%    | 53.81%   | +415.60          | 86.38        | 0.06         | 6         |

## 觀察與結論
- **DA 表現**: 於所有 timeframe (5m, 15m, 60m) 的表現均穩定大於 Polymarket Maker 的盈虧平衡線 (50.0%)，且擁有顯著的正 PnL。
- **最佳 Timeframe 評估**: 
  - **5m** 取得了最顯著的 Alpha (55.68%)，並且 PnL (+1712.05) 與 Sharpe Ratio (0.11) 均大幅超越 15m 和 60m。同時在 5m 區間的 Higher DA (56.98%) 對於 `>=` 結算條件有非常好的適應性。Max Drawdown 也小於 15m，這顯示 5m 是目前最佳的操作區間！
  - **15m** 與 **60m** 雖表現較普通且 Alpha 邊際較 5m 縮小白，但亦可作為長線輔助訊號。
- **Higher/Lower 平衡性**: 在加入了 `settlement_condition=">="` 之後，Higher 和 Lower 的 DA 相對平衡，5m 出現了較多利好 Higher 的特徵，但依然保持良好的整體表現。

**未來建議**：推薦主攻 **5m** Timeframe 進行模擬交易的實時信號發出！
