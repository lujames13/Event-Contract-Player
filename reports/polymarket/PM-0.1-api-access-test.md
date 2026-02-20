# PM-0.1: Public API Access Test (Taiwan IP)

## 測試環境
- **測試時間**: 2026-02-21
- **測試 IP**: 111.241.139.91 (台灣, 台北)
- **工具**: Python `requests` 自編腳本

## 測試結果

| 端點名稱 | URL | 狀態碼 | 延遲 (ms) | 測試結果 |
|---------|-----|-------|-----------|---------|
| Geoblock | `https://polymarket.com/api/geoblock` | 200 | ~79ms | **Blocked** (`blocked: true`) |
| Gamma API | `https://gamma-api.polymarket.com/events` | 200 | ~106ms | **Success** (可獲取市場列表) |
| CLOB REST | `https://clob.polymarket.com/markets` | 200 | ~91ms | **Success** (可獲取 CLOB 市場資訊) |
| CLOB WebSocket | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | 400* | - | **Success** (能觸及 Server, 400 為預期握手失敗) |

*\*400 Bad Request 為 curl 建立普通 HTTP 請求而非完整 WebSocket 握手的預期結果，證實網路路徑未被封鎖。*

## 關鍵發現
1. **Geoblock 狀態**: 台灣 IP 明確被列為受限地區 (`"country": "TW"` -> `"blocked": true`)。
2. **Public Access**: 儘管被 geoblock，但 **Gamma API** 與 **CLOB Read-only Endpoints** 在不帶權證的情況下是可以從台灣 IP 正常存取的。這意味著我們可以在本地採集市場數據（價格、成交量、Order Book）。
3. **Trading Restriction**: 雖然 Read-only API 開放，但預期 `POST /order` 等交易相關端點會依照 Geoblock 結果拒絕請求。

## 結論
**Feasibility: Partial.**
台灣 IP 可用於數據監控與模型採集，但無法用於下單執行。交易執行層必須配合 VPS Relay (PM-0.2)。
