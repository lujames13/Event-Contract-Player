# Task Spec G4.1 — Polymarket CLOB API 交易客戶端整合 (4.1.2)

<!-- status: done -->
<!-- created: 2026-02-23 -->
<!-- architect: Antigravity -->

> **Gate:** 4.1 (對應 PROGRESS.md Task 4.1.2)
> **優先級:** 🟡 Medium — 與 Gate 3 樣本累積並行推進

---

## 目標

Gate 3 模擬交易目前正在累積達到 200+ 樣本的過程中。為了避免未來 Gate 3 驗證通過後出現延遲，現在需要提早實作 Gate 4 (真實交易) 的核心基礎設施：**Polymarket CLOB 交易客戶端 (Trading Client)**。該客戶端需要負責管理 L2 (Polygon) 的私鑰，對 Order Payload 進行 EIP-712 簽名，並提交到 Polymarket API。

對應 `PROGRESS.md`: Phase 4 > Task 4.1.2 CLOB API trading client（EIP-712 簽名）

---

## 修改範圍

**需要新增/修改的檔案：**
- `src/btc_predictor/polymarket/trading_client.py` (新增) — 主客戶端程式碼介面。
- `tests/polymarket/test_trading_client.py` (新增) — 對交易客戶端及 EIP-712 簽名的 Unit Tests。
- `scripts/polymarket/verify_live_order.py` (新增) — 配合 VPN 進行安全 Integration Test 的腳本。
- `.env.example` / `.env` (視需要新增 Polymarket API 金鑰相關欄位)
- `pyproject.toml` (視需要新增套件，如 `py-clob-client` 或 `eth-account`)

**不可修改的檔案：**
- `docs/DECISIONS.md`
- `src/btc_predictor/polymarket/pipeline.py` (此任務不負責整合至 Pipeline)
- `scripts/run_live.py`

---

## 實作要求

1. **認證與配置**：
   - 設定所需的環境變數（對應 `.env.example` 中的 `POLYMARKET_API_KEY_DEV/STAGE/PROD`, `POLYMARKET_SECRET_*`, `POLYMARKET_PASSPHRASE_*` 等系列金鑰）。初始化 `TradeCLOBClient` 時應支援不同環境的切換 (例如傳入 `env='DEV'` 等參數)。
   - **簽名實作由程式碼負責**：這部分完全是你 (Coding Agent) 要實作的範圍。
     - 請優先嘗試使用 Polymarket 官方 Python SDK：`uv add py-clob-client`，它的底層應該會自動處理 EIP-712 簽名邏輯。
     - ⚠️ 若 `py-clob-client` 與 Python 3.12 或是現有依賴發生無法解決的衝突，**必須手動使用 `eth_account` 與 `httpx` 來建構 EIP-712 簽名並發送 REST 請求**。

2. **核心方法實作** (`trading_client.py`)：
   - 建立 `TradeCLOBClient` (可繼承或包裝現有 `CLOBClient`)，這是一個具備狀態 (帶有 API Credentials) 的連線端點。
   - 包含以下核心方法：
     - `create_and_post_order(token_id: str, price: float, size: float, side: str)`: 建立 Limit Order 或 Maker Order 並完成簽名後發送 POST。
     - `cancel_order(order_id: str)`: 撤銷尚未成交的訂單。
     - `get_open_orders()`: 查詢當前未完全成交的訂單。
     - `get_order_status(order_id: str)`: 查詢單一訂單狀態。

3. **測試與 VPN 環境處理 (Critical)**：
   - 即便你透過 VPN 突破了 Geoblock，**在自動化的 Unit Tests (如 `test_trading_client.py`) 中，依然必須使用 `unittest.mock` 或 `pytest-mock` 進行離線測試。**確保 CI 或沒開 VPN 的環境也能跑乾淨測試，且不消耗真實資金。
   - 測試目標是「確保 payload 的結構、EIP-712 簽名過程無拋出異常，且 HTTP Request 的參數正確傳遞」。
   - **新增手動連線測試腳本：** 請新增 `scripts/polymarket/verify_live_order.py` 作為 Integration Test，利用 VPN 實際與 API 互動。
     - **安全極端價格機制：** 此腳本如果要發送建立訂單請求，必須發送一個**絕對不會成交的極端價格（例如 $0.01 或 $0.99）**，並在成功發送後**立刻呼叫 cancel_order 撤銷該訂單**，以證明 E2E 簽名與下單流程通順，又不會意外搓合。

---

## 不要做的事

- **不要將這個 Client 和實盤機器人 (`pipeline.py`) 的主迴圈綁定**。這個任務僅聚焦在底層的 Client 原語 (Primitive)。
- **絕對不要在自動化 Unit Test 中發送真實交易**。真實網路下單測試只能在手動執行的 `verify_live_order.py` 進行，並加上必定不會成交的安全防護（極端價格 + 立即撤單）。
- **不要繞過 Type Hints 檢查**，所有的對外方法必須明確標示參數與返回值型別。

---

## 驗收標準

1. 透過 `uv run pytest tests/polymarket/test_trading_client.py -v` 執行，所有的 mock 測試 100% 通過。
2. 測試必須涵蓋下列斷言：
   - Order 發送時的 EIP-712 payload 足以正確建構。
   - API endpoints (`/order`, `/auth` 等) 被傳遞了正確的參數和 headers (尤其是 `POLYMARKET-API-KEY`, `POLYMARKET-API-SIGNATURE` 等認證依據)。
3. `pyproject.toml` 中的新依賴 (如有) 能使用 `uv sync` 無痛同步安裝。

---

## Coding Agent 回報區

### 實作結果
- 成功使用官方 SDK `py-clob-client` 實作了 `TradeCLOBClient` (位於 `src/btc_predictor/polymarket/trading_client.py`)，包含建立、取消及查詢訂單的方法。
- 撰寫 `test_trading_client.py` 成功透過 mock 驗證建構 EIP-712 payload、環境設定，並覆蓋所有的 HTTP Requests 認證與參數邏輯。
- 新增 `verify_live_order.py` 進行 integration 測試。

### 驗收自檢
- [x] 1. 執行 `uv run pytest tests/polymarket/test_trading_client.py -v` 100% 通過。
- [x] 2. Payload 建構與認證 Headers 的構造邏輯已被測試涵蓋。
- [x] 3. 未修改限制範圍外的檔案。

### 遇到的問題
- 為了讓 mock test 能順利運行，必須對 SDK 中的 `get_tick_size` 與 `get_neg_risk` 方法以及 session/http requests 進行 mock，以免觸發真實網路請求並拋出 KeyError。
- `py-clob-client` 強制檢查 `OrderArgs` 的 side 為大寫 `'BUY'` 或 `'SELL'`，而在建立 `TradeCLOBClient` 時需做好小寫、大寫防呆。

### PROGRESS.md 修改建議
建議在 PROGRESS.md 的 Gate 4.1 中勾選 4.1.2 CLOB API trading client（EIP-712 簽名）。

**Commit Hash:** `cc44d345bba6e3de3217b03b5363e8efbca6af9d`

---

## Review Agent 回報區

### 審核結果
PASS

### 驗收標準檢查
- [x] 1. 修改範圍符合 spec 要求，未動及禁動檔案。
- [x] 2. 介面契約符合 `ARCHITECTURE.md` 定義。
- [x] 3. 既有測試 `test_trading_client.py` 100% 通過。
- [x] 4. 擴展測試 `test_trading_client_extended.py` 通過，驗證了環境切換與輸入彈性。

### 發現的問題
無。

### 建議
- **NOTE**: 目前 `TradeCLOBClient.HOST_MAPPING` 在所有環境皆使用生產環境 URL `https://clob.polymarket.com`。若未來 Polymarket 提供測試網 (Mumbai/Amoy) 的 CLOB URL，應將 `DEV` / `STAGE` 分開配置。
- **NOTE**: `get_open_orders` 的 `OpenOrderParams()` 預設行為取決於 SDK 版本，建議未來若需分頁或篩選市場，再行擴充參數。
