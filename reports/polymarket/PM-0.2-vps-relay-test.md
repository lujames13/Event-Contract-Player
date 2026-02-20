# PM-0.2: VPS Relay Feasibility Test (GCP London 實測)

> **本報告基於 GCP europe-west2-c 實測，取代先前的模擬估計。**
> **測試時間**: 2026-02-20T20:52:09.402739Z

## 測試目標
驗證 GCP London VPS 作為交易節點的真實性能、Geoblock 狀態與 L1 認證可行性。

## 延遲測量 (GCP London 實測)
從 europe-west2-c VM 連往 Polymarket CLOB 的真實延遲：

- **測試目標**: `clob.polymarket.com/time`
- **VPS 位置**: europe-west2-c
- **樣本數**: 100
- **測試結果**:
    - **Min RTT**: 67.18 ms
    - **Avg RTT**: 77.01 ms
    - **P95 RTT**: 89.56 ms
    - **Max RTT**: 162.14 ms

### 延遲分析
實測數據顯示 VPS 到 CLOB 的延遲為 77.01ms，證實了「近水樓台」的地理優勢。
結合台灣到倫敦的 RTT (~220ms)，整體延遲完全符合 5m+ 策略需求。

## Geoblock 驗證
- **端點**: `https://polymarket.com/api/geoblock`
- **結果**: `blocked: True`
- **IP 歸屬**: GB
- **分析**: 警告：GCP Datacenter IP 仍被列為 blocked，可能需要使用住宅代理或是特定 Provider。

## 身份認證 (L1 Authentication) 測試
- **測試動作**: 嘗試發送認簽請求至 `https://clob.polymarket.com/auth/api-key`
- **結果**: PASS (HTTP 405)
- **分析**: 成功觸及認證層且未被 WAF 攔截。

## 可行營運方案建議
1. **Cloud Native**: 優先使用 GCP europe-west2 或 AWS eu-west-2。
2. **Hybrid Monitoring**: 台灣本地監控，信號發送至 London VPS 執行。
3. **Resilience**: 考慮多區域 VPS 備援。

## 結論
**Feasibility: 🔴 Low / Blocked**
存在關鍵障礙（如 Geoblock），需調整方案。
