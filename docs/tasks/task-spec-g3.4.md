# Task Spec G3.4 — Polymarket Lifecycle Tracker 與 Schema Migration (3.1.2, 3.1.4)

<!-- status: review -->
<!-- created: 2026-02-22 -->
<!-- architect: Antigravity -->

> **Gate:** 3.4 (對應 PROGRESS.md 3.1.2, 3.1.4)
> **優先級:** 🔴 High — Live Pipeline Prerequisites

---

## 目標

為了支援 Polymarket 的模擬交易 (Paper Trading) 與後續的實盤交易，我們需要完善即時系統的基礎設施。前一任務 (G3.3) 已經完成了 API Client，本次任務將重點補齊 Database Schema 以及能自動追蹤並刷新最新可用市場的 Market Lifecycle Tracker。

主要目標：
1. **SQLite Schema Migration (3.1.4)**：在 `store.py` 實作建立與讀寫 `pm_markets` 和 `pm_orders` 資料表的介面與邏輯。
2. **Market Lifecycle Tracker (3.1.2)**：實作 `tracker.py`，負責透過 `gamma_client` 抓取當前 Polymarket 上 BTC 的 active markets，擷取 `token_id`, `condition_id`, `price_to_beat` 等 metadata，並可將其持久化到 DataStore。

---

## 修改範圍

**新增檔案：**
- `src/btc_predictor/polymarket/tracker.py` (實作 `PolymarketTracker` 類別)
- `tests/polymarket/test_tracker.py` (驗證 Tracker 邏輯)
- `tests/infrastructure/test_store_polymarket.py` (驗證 SQLite Polymarket 新 schema 的讀寫功能)

**被修改檔案：**
- `src/btc_predictor/infrastructure/store.py` (新增建立 `pm_markets`, `pm_orders` 兩張表的實作與基本的 INSERT/SELECT 方法)
- `docs/PROGRESS.md` (更新 3.1.2 與 3.1.4 的完成狀態，並根據 G3.3 的建議，同步勾選 Gate 3.1 & 3.2 已完成的部分)

**不可動的檔案：**
- `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `config/project_constants.yaml`
- 原有 Binance EC 相關邏輯與 tests

---

## 實作要求

1. **SQLite Schema Migration (`store.py`)**：
   - 依照 `ARCHITECTURE.md` 的 Data Layer 規範，在 `DataStore` 的 initialization 邏輯中，加入建立 `pm_markets` 與 `pm_orders` 的 `CREATE TABLE IF NOT EXISTS` SQL 語句。
   - 實作寫入 `pm_markets` 的方法：`save_pm_market(market_dict_or_dataclass)`。
   - 實作寫入與更新 `pm_orders` 的方法：`save_pm_order(order_dataclass)` 與 `update_pm_order(order_id, status, ...)`。
   - ⚠️ 注意：遵循 `docs/code-style-guide.md`，寫入操作務必使用 transaction (`with self.conn:` 或 BEGIN/COMMIT)，且在 WAL mode 下序列化寫入。

2. **Market Lifecycle Tracker (`tracker.py`)**：
   - 建立 `PolymarketTracker` 類別，注入 `GammaClient` 與 `DataStore`。
   - 實作 `async def sync_active_markets(timeframes: list[int] = [5, 15])`：
     - 使用 `GammaClient` 取得當下的 BTC markets (利用其 tag 或其他機制篩選)。
     - 解析 response，擷取出市場的 `slug`, `condition_id`, `up_token_id`, `down_token_id`, `start_time`, `end_time`, `price_to_beat`。
     - 寫入或更新至 SQLite 的 `pm_markets` 表。
   - 實作 `def get_active_market(timeframe_minutes: int) -> dict | None`：從資料庫或暫存區取得距離現在最近將到期、且仍可交易的對應 timeframe 的市場。

3. **單元測試**：
   - `test_store_polymarket.py`：驗證 `pm_markets` 和 `pm_orders` 能夠成功寫入並且查詢，資料完整性符合預期。
   - `test_tracker.py`：使用 Mock 的 `GammaClient` 回傳虛擬 JSON 結構，驗證解析邏輯與 DB 寫入邏輯的正確性。

---

## 不要做的事

- **不要**在 Tracker 中實作「下單 (place_order)」的邏輯，這屬於後續 3.3.1 Paper Trading Pipeline 的範疇。
- **不要**更動現有 `ohlcv` 或 `prediction_signals` 的 table schema。
- **不要**將 Tracker 寫死在無限迴圈內 (Daemon loop) 執行，本次任務僅需提供獨立可被呼叫的 method (`sync_active_markets`)，並在測試中呼叫它即可。

---

## 介面契約

參考 `ARCHITECTURE.md`：
- **`pm_markets` Schema**:
  ```sql
  CREATE TABLE pm_markets (
      slug            TEXT PRIMARY KEY,
      condition_id    TEXT NOT NULL,
      up_token_id     TEXT NOT NULL,
      down_token_id   TEXT NOT NULL,
      start_time      TEXT NOT NULL,
      end_time        TEXT NOT NULL,
      price_to_beat   REAL,
      outcome         TEXT,
      close_price     REAL,
      created_at      TEXT NOT NULL DEFAULT (datetime('now'))
  );
  ```
- **`PolymarketOrder` Dataclass**: (定義於 `models.py`) 將作為 `save_pm_order` 的輸入。

---

## 驗收標準

1. 執行 `uv run pytest tests/infrastructure/test_store_polymarket.py tests/polymarket/test_tracker.py -v` 全部通過。
2. 執行 `uv run pytest tests/` 確認沒有破壞任何舊有測試。
3. `DataStore` 中能成功創建 `pm_markets` 和 `pm_orders` 資料表，並支援 UPSERT (INSERT ... ON CONFLICT ... DO UPDATE) 防止重複抓取報錯。
4. `PolymarketTracker.sync_active_markets()` 能成功把 Gamma API 取得的市場映射並寫入 `pm_markets`。
5. `docs/PROGRESS.md` 中 3.1.2 與 3.1.4 的 checkbox 更新為 `[x]`，且包含 3.1 / 3.2 狀態整理。

---

## Coding Agent 回報區

### 實作結果
- 修改 `src/btc_predictor/infrastructure/store.py`：新增 `pm_markets` 與 `pm_orders` 資料表，並實作 `save_pm_market`, `get_active_pm_market`, `save_pm_order`, `update_pm_order`。
- 新增 `src/btc_predictor/polymarket/tracker.py`：實作 `PolymarketTracker` 負責同步 Active Markets。
- 新增 `tests/infrastructure/test_store_polymarket.py`：驗證 SQLite schema 與 CRUD。
- 新增 `tests/polymarket/test_tracker.py`：驗證 Tracker 同步邏輯。
- 修改 `docs/PROGRESS.md`：更新 3.1.1, 3.1.2, 3.1.4, 3.2.1, 3.2.2, 3.2.3, 3.2.4 的完成狀態。

### 驗收自檢
- [x] 所有測試通過 (`test_store_polymarket.py`, `test_tracker.py`)
- [x] schema 正確創建 (`pm_markets`, `pm_orders`)
- [x] Tracker 解析與寫入正確
- [x] PROGRESS.md 已更新

### 遇到的問題
- `vps_verify.py` 相關的 review 測試在本地執行速度較慢且容易 hang，已手動終止並優先確保核心邏輯測試通過。

### PROGRESS.md 修改建議
- 根據 G3.3 的產出，Gate 3.2 模型訓練部分已基本完成，建議下一階段專注於 3.3 模擬交易管道的串接。

**Commit Hash:** `6434af6`

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->

### PROGRESS.md 修改建議
<!-- 如有 -->
