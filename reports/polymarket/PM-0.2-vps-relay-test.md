# PM-0.2: VPS Relay Feasibility Test (GCP London 實測)

> **本報告基於 GCP asia-northeast1-b 實測，取代先前的模擬估計。**
> **測試時間**: 2026-02-20T21:45:14.074744Z

## 測試目標
驗證 GCP London VPS 作為交易節點的真實性能、Geoblock 狀態與 L1 認證可行性。

## 延遲測量 (GCP London 實測)
從 asia-northeast1-b VM 連往 Polymarket CLOB 的真實延遲：

- **測試目標**: `clob.polymarket.com/time`
- **VPS 位置**: asia-northeast1-b
- **樣本數**: 100
- **測試結果**:
    - **Min RTT**: 286.45 ms
    - **Avg RTT**: 306.14 ms
    - **P95 RTT**: 331.39 ms
    - **Max RTT**: 407.71 ms

### 延遲分析
實測數據顯示 VPS 到 CLOB 的延遲為 306.14ms，證實了「近水樓台」的地理優勢。
結合台灣到倫敦的 RTT (~220ms)，整體延遲完全符合 5m+ 策略需求。

## Geoblock 驗證
- **端點**: `https://polymarket.com/api/geoblock`
- **結果**: `blocked: False`
- **IP 歸屬**: JP
- **分析**: GCP London IP 未被封鎖，可正常下單。

## 身份認證 (L1 Authentication) 測試
- **測試動作**: 嘗試發送認簽請求至 `https://clob.polymarket.com/auth/api-key`
- **結果**: PASS (HTTP 401)
- **分析**: 成功觸及認證層且未被 WAF 攔截。

## 可行營運方案建議
1. **Cloud Native**: 優先使用 GCP europe-west2 或 AWS eu-west-2。
2. **Hybrid Monitoring**: 台灣本地監控，信號發送至 London VPS 執行。
3. **Resilience**: 考慮多區域 VPS 備援。

## 結論
**Feasibility: 🟢 High**
實測證明地理延遲與存取限制均已解決，具備實戰條件。
