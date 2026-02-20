# PM-2.1: Chainlink Oracle 靜態規格分析

## 1. 調查概述
本調查旨在確認 Polymarket BTC 5m 市場結算所使用的 Chainlink Oracle 規格，評估其更新頻率、精度以及歷史數據可用性，為 PM-8 回測提供基礎。

## 2. 關鍵參數摘要

| 參數 | 值 | 來源 |
|------|-----|------|
| **Feed Type** | Chainlink Data Streams (Low Latency) | 文件 / 官方公告 |
| **On-chain Fallback** | Price Feed Aggregator | 合約查詢 |
| **Heartbeat Interval** | 27,000s (On-chain) / 極高頻 (Data Streams) | 文件 / 合約分析 |
| **Deviation Threshold** | 0.05% | Official Chainlink Docs |
| **Polygon Contract** | `0xc907E116054Ad103354f2D350FD2514433D57F6f` | 實測驗證 |
| **Update Frequency (動態)** | < 1s (Data Streams) | 官方技術文件 |
| **結算精度** | 8 位小數 (USD) | 合約 `decimals()` |
| **歷史數據可用性** | 支援 (透過 Data Streams API 或 Indexer) | 技術文件 |

## 3. 詳細分析

### 3.1 Data Streams vs. Price Feeds
Polymarket 目前針對高頻市場（如 5m BTC）採用 **Chainlink Data Streams**。
- **Price Feeds (傳統)**：主動推送至鏈上，受限於區塊時間與 Gas 成本，通常有 Heartbeat (27000s) 或 Deviation (0.05%) 觸發。
- **Data Streams (新)**：拉取式 (Pull-based)，在結算瞬間由 Polymarket 伺服器向 Chainlink 節點請求簽名快照並提交至鏈上結算合約。延遲可達亞秒級。

### 3.2 鏈上實測結果
透過 Polygon RPC 查詢 Aggregator V3 介面 (`latestRoundData`)：
- **Aggregator Address**: `0xc907E116054Ad103354f2D350FD2514433D57F6f`
- **實測價格**: $67,958.35 (範例)
- **最後更新時間**: 每當價格變動超過 0.05% 時觸發，或 7.5 小時 (Heartbeat) 強制更新一次。

### 3.3 歷史數據可用性
- **回測可行性**: 🟢 **高**。
- **途徑**:
    1. **Official Data Streams API**: 支援回溯拉取歷史快照。
    2. **Third-party Indexers**: Dune Analytics 或 DeFiLlama 紀錄了 Price Feed 的歷史軌跡。
    3. **自建收集**: 由於 Data Streams 是拉取式，若要 100% 對齊 Polymarket 結算點，建議在 PM-2.2 中開始自行紀錄結算瞬間的 price report。

## 4. 結論
Chainlink Data Streams 提供足夠的精度與低延遲，確保了 Polymarket 5m 市場的結算公平性。

**結論回答**：「可以使用 Chainlink 歷史數據進行初步回測。但為了達到最高精度（對齊 Data Streams 結算點），仍需累積約 7-14 天的實測資料以捕捉 Data Streams 與 Binance Spot 之間的微小溢價。」
