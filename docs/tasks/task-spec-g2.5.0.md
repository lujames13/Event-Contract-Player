# Task Spec G2.5.0 — Polymarket Feasibility Study: PM-0 (Access & Legal)

<!-- status: open -->
<!-- created: 2026-02-21 -->
<!-- architect: Antigravity -->

> **Gate:** 2.5（Polymarket Feasibility Study）
> **優先級:** 🔴 High — Blocker gate，決定是否投入 Polymarket 開發
> **前置條件:** 無

---

## 目標

依據 `docs/polymarket-patch.md` 的規劃，執行 **PM-0: Access & Legal Feasibility** 調查。這是整個 Polymarket 調查計畫的 gate-keeper，不通過則終止後續計畫。需要產出 4 份報告回答對應的問題，以評估在台灣開發與運行 Polymarket 自動化交易系統的可行性與法規風險。

---

## 修改範圍（封閉清單）

**新增：**
- `scripts/polymarket/` 目錄以及任何輔助用的 API 測試腳本
- `reports/polymarket/PM-0.1-api-access-test.md`
- `reports/polymarket/PM-0.2-vps-relay-test.md`
- `reports/polymarket/PM-0.3-legal-risk-assessment.md`
- `reports/polymarket/PM-0.4-architecture-latency.md`

**修改：**
- `docs/PROGRESS.md` — 勾選 PM-0.1 至 PM-0.4 完成

**不動：**
- `src/` 底下所有現有程式碼完全不動
- `docs/DECISIONS.md` 和 `docs/ARCHITECTURE.md` 不動
- `tests/` 不動
- `config/` 不動

---

## 實作要求

### PM-0.1：Public API 存取測試（台灣 IP）
1. 建立 `scripts/polymarket/test_public_api.py` 或直接 bash script 測量端點。
2. 測試以下端點在台灣 IP 下的狀態：
   - Geoblock API (`https://polymarket.com/api/geoblock`)
   - Gamma API (`https://gamma-api.polymarket.com/events?active=true&closed=false&limit=5`)
   - CLOB public (`https://clob.polymarket.com/markets`)
   - `py-clob-client` 的 Level 0 方法
   - RTDS WebSocket (`wss://ws-subscriptions-clob.polymarket.com/ws/market`)
3. 產出 `reports/polymarket/PM-0.1-api-access-test.md`，說明每個端點結果與最終結論。

### PM-0.2：VPS Relay 可行性測試
1. 作為 Coding Agent 無法購買真實的 VPS，因此這一步以**模擬和 Ping 測量**為主：尋找歐洲（特別是 London 附近）的公共測試節點或已知伺服器的 IP 進行 `ping` 測試。
2. 創建測試專用的 Polygon 錢包 (`py-clob-client`) 並執行 L1 認證 (不會耗費資金)，測試認證流程是否在未被封鎖的環境/本地執行順暢。如果本地被封鎖，記錄失敗即可。
3. 產出 `reports/polymarket/PM-0.2-vps-relay-test.md`。記錄實作成效，對於實在無法自動測試的項目請依合理預估撰寫結果。

### PM-0.3：台灣法規風險評估
1. 進行網路搜尋與匯總關於 2024 年台灣針對 Polymarket 用戶起訴的案例。
2. 比較賭博罪與一般金融資產預測的適用性分析。
3. 填寫包含具體風險分類的評估矩陣。
4. 產出 `reports/polymarket/PM-0.3-legal-risk-assessment.md`。

### PM-0.4：End-to-End Architecture Latency 評估
1. 將前述步驟的測量延遲數字匯總，並加上本地模型推理延遲預估 (< 1000ms)。
2. 列出各節點 latency breakdown。
3. 依據 `docs/polymarket-patch.md` 列出的策略類型建立適用性分析表。
4. 產出 `reports/polymarket/PM-0.4-architecture-latency.md`。

---

## 不要做的事

- 不要入金或嘗試下單。
- 不要在這份任務實作任何交易邏輯。
- 不要觸碰任何可能修改主系統（Binance EC 相關）的程式檔案。
- 不要使用真實且含有資金的 Polygon 錢包來進行測試。

---

## 驗收標準

```bash
# 1. 檢查目錄及報告是否順利產出
test -d reports/polymarket
test -f reports/polymarket/PM-0.1-api-access-test.md
test -f reports/polymarket/PM-0.2-vps-relay-test.md
test -f reports/polymarket/PM-0.3-legal-risk-assessment.md
test -f reports/polymarket/PM-0.4-architecture-latency.md

# 2. 檢查 PROGRESS.md 是否確實被更新與勾選
grep "\[x\].*PM-0.1" docs/PROGRESS.md
grep "\[x\].*PM-0.4" docs/PROGRESS.md
```

---

## Coding Agent 回報區

### 實作結果
<!-- 請填寫 -->

### 驗收自檢
<!-- 請填寫 -->

### 遇到的問題
<!-- 請填寫 -->

### PROGRESS.md 修改建議
<!-- 請填寫 -->

---

## Review Agent 回報區

### 審核結果
<!-- 請填寫 -->

### 發現的問題
<!-- 請填寫 -->
