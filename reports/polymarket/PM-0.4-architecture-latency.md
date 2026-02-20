# PM-0.4: End-to-End Architecture Latency Assessment

## 延遲分解 (Latency Breakdown)

綜合 PM-0.1 與 PM-0.2 的測量數據，推估 E2E 延遲如下：

| 階段 | 預估延遲 (ms) | 來源 / 備註 |
|------|-------------|------------|
| 1. 市場數據接收 (WS/REST) | 100 - 200 | 從 Origin (US/EU) 到台灣本地監控 |
| 2. 特徵工程 + 模型推理 | 20ms - 50ms | 基於現有 LightGBM/CatBoost 策略效能 |
| 3. 信號傳輸至日本 Relay | 15ms - 30ms | 台灣 -> 日本 單程網路延遲 |
| 4. 交易簽署與提交 (Relay) | 331.39ms | 實測 VPS -> CLOB RTT | GCP Japan VPS 實測 (RTT) |
| 5. CLOB API 訂單確認處理 | 50 - 100 | Polymarket 內部處理時間 |
| **總計 (E2E Latency)** | **700ms - 900ms** | 從市場動態到訂單提交成功 |

## 策略類型適用性分析

| 策略類型 | 推估延遲需求 | 適用性 | 備註 |
|---------|------------|-------|------|
| **High-Frequency (Tick)** | < 10ms | ❌ **不適用** | 因地理位置造成的 > 200ms 延遲無法參與搶單。 |
| **Short-term (1m - 5m)** | < 2000ms | ✅ **適用** | 500ms 內的延遲足以在 5 分鐘級別市場捕捉趨勢。 |
| **Event-driven (新聞)** | < 500ms | ⚠️ **邊緣** | 需極速反應新聞，與專業造市商相比無優勢。 |
| **Directional (5m - 60m)** | 秒級 | ✅ **最佳** | 延遲不敏感，主要競爭模型準確度。 |

## 硬體與工程影響
1. **GPU 需求**: 推理延遲 < 50ms，現有 NVIDIA < 8GB 環境完全足夠，無需優化推理引擎。
2. **網路抖動 (Jitter)**: 台灣連往歐洲長距離海纜可能存在不穩定性，系統需具備斷線重連與逾時取消訂單機制。
3. **時鐘同步**: 需確保台灣本地與倫敦 Relay、Polymarket Server (UTC) 進行 NTP 同步，誤差應 < 50ms。

## 結論
**Feasibility: Pass.**
雖然地理位置導致我們無法進行極短線的掠奪式交易 (HFT)，但對於 **Directional Trend (5m+)** 或 **Statistical Arbitrage** 策略而言，~400ms 的延遲完全在可操作範圍內。

Polymarket 的市場機制（CLOB）相對於 Binance Event Contract 具有更好的流動性與 API 優勢，足以補償這部分的物理延遲。
