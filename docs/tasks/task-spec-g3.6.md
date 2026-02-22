# Task Spec G3.6 — Discord Bot Polymarket 適配 (3.3.2)

<!-- status: done -->
<!-- created: 2026-02-22 -->
<!-- architect: Antigravity -->

> **Gate:** 3.6 (對應 PROGRESS.md 3.3.2)
> **優先級:** 🟡 Medium — Live Monitoring

---

## 目標

在前一個任務中我們完成了 `PolymarketLivePipeline` 的建置，現在需讓我們的監控介面感知 Polymarket 獨特的數據與行為。本任務目標是更新 Discord Bot，使其在 `/predict` 和自動通知中能夠顯示 Polymarket 特有的 Alpha 和市場價格，並讓 `/stats` 指令能查詢 Polymarket (`pm_orders`) 的盈虧與統計資料。同時修正上一期 Review Agent 發現的 `PredictionSignal` 型別定義不一致問題。

對應 PROGRESS.md: Phase 3 > Task 3.3.2

---

## 修改範圍

**需要修改的檔案：**
- `src/btc_predictor/models.py` — 修正 `PredictionSignal.order_type` 型別。
- `src/btc_predictor/infrastructure/store.py` — 新增聚合 Polymarket 統計資料的方法（例如 `get_pm_order_stats()`），以供 Discord `/stats` 使用。
- `src/btc_predictor/discord_bot/bot.py` (或對應的 Discord bot 檔案) — 更新指令與信號通知格式。
- `tests/discord_bot/` (或相關測試資料夾) — 新增或修改測試以涵蓋 Polymarket 特性的 `/predict` 和 `/stats` 檢查。

**不可修改的檔案：**
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/polymarket/pipeline.py` (Live 下單邏輯不可動)
- `src/btc_predictor/binance/pipeline.py`

---

## 實作要求

1. **介面契約微調 (`models.py`)**：
   - 解決 Review Agent 回報的遺留問題：將 `PredictionSignal.order_type` 型別從 `Literal["maker", "taker"]` 修正為 `Literal["GTC", "FOK", "GTD"]`，與 `PolymarketOrder` 一致。

2. **DataStore 方法擴充 (`store.py`)**：
   - 為 Polymarket 實作統計查詢。原先的 `simulated_trades` 已不包含 PM orders（PM 對應用 `pm_orders`）。請增加類似 `get_pm_stats(strategy_name: str)` 的方法，回傳總量、成功 Fill 的數量、勝率、以及累積 PnL 等數據。

3. **Discord 通知與 `/predict` 輸出適配 (`bot.py`)**：
   - 在產生 `PredictionSignal` 相關文字格式化（例如自動通知或 `/predict` 回應）時，判斷若這是 Polymarket 訊號（例如 `market_slug` / `alpha` 不為 None），則：
     - **必須**將 `alpha` 以及 `market_price_up` 清楚列在 Embed 中。
     - 若有 `order_type` 也可列出。

4. **`/stats` 指令輸出適配 (`bot.py`)**：
   - 當使用者呼叫 `/stats`，需基於 strategy 名稱自動切換調用的 DB 統計：
     - 策略名稱以 `pm_` 開頭時，呼叫 Polymarket 統計 (從 `pm_orders` 取數)。
     - 否則呼叫原本的 Binance EC 統計 (從 `simulated_trades` 取數)。

---

## 不要做的事

- **不要**重構既有的 Binance EC stats 邏輯，盡可能讓舊有策略 (`xgboost_v1`, `lgbm_v2` 等) 的 `/stats` 行為能透過 backward-compatibility 順暢運作。
- **不要**將 Polymarket 的下單機制放進 Discord bot，此處只做「查詢與展示」。
- **不要**將現有 Discord bot 拆開為過度複雜的多檔案架構。

---

## 介面契約

- **`PredictionSignal`**: 修改 `order_type` 為 `Literal["GTC", "FOK", "GTD"] | None`。
- **Store 輸出**: 期待新的 PM stats dictionary 回傳能明確標示 `total_orders`, `filled_orders`, `total_pnl`。

---

## 驗收標準

1. 執行 `uv run pytest` 時所有既有的測試（包含 models 和 store）不報錯。
2. 新增有關 Polymarket discord bot rendering 與 store stats 資料查詢的單元測試，且測試涵蓋成功通過。
3. `PredictionSignal` 中有關 `order_type` 的 Literal Enum 正確更新。
4. `docs/PROGRESS.md` 中進度 3.3.2 若已順利完成應於後續更新標記為 `[x]`。

---

## Coding Agent 回報區

### 實作結果
1. 修正了 `src/btc_predictor/models.py` 中的 `PredictionSignal.order_type` 型別為 `Literal["GTC", "FOK", "GTD"] | None`。
2. 在 `src/btc_predictor/infrastructure/store.py` 實作了專為了 Polymarket 統計的 `get_pm_strategy_summary`, `get_pm_strategy_detail` 與 `get_pm_daily_stats` 方法。
3. 更新了 `src/btc_predictor/discord_bot/bot.py`，支援：
   - `/predict` 會解析並在 Embed 輸出 `signal` 的 Polymarket 參數（`alpha`、`market_price_up`、`order_type`）。
   - 自動通知 `send_signal` 會從資料庫裡透過 `trade.id` 找出關聯訊號並把 Polymarket 參數加到 Embed 中。
   - `/stats` 以及指令 `/models` 會自動基於策略名稱 (`startswith("pm_")`) 來選擇查詢並顯示 Polymarket (`pm_orders`) 或 Binance EC 的數據。
4. 在 `tests/infrastructure/test_store_polymarket.py` 提供 store 聚合資料查詢相關單元測試。
5. 在 `tests/test_bot_predict.py` 與 `tests/test_bot_notifications.py` 新增 Discord bot rendering Polymarket 欄位的單元測試，測試皆能順利通關與如期運作。

### 驗收自檢
- [x] 1. 執行 `uv run pytest` 時所有既有的測試（包含 models 和 store）不報錯。
- [x] 2. 新增有關 Polymarket discord bot rendering 與 store stats 資料查詢的單元測試，且測試涵蓋成功通過。
- [x] 3. `PredictionSignal` 中有關 `order_type` 的 Literal Enum 正確更新。
- [x] 4. `docs/PROGRESS.md` 中進度 3.3.2 若已順利完成應於後續更新標記為 `[x]`。（等待 Review 結束後更新）

### 遇到的問題
原先 `send_signal` 的輸入參數只包含了 `trade: SimulatedTrade` 而缺少了 `alpha` 等欄位，且不可修改負責下單的 `polymarket/pipeline.py` 與 `binance/pipeline.py`。為了解決這問題，直接由 `send_signal` 透過 `trade.id` 去 `prediction_signals` table 將 Polymarket 專屬資料關聯取出來做 render。成功做到了完全不修改舊 pipeline，就能完成擴充。

### PROGRESS.md 修改建議
無，已完美配合現有架構。

---

## Review Agent 回報區

### 審核結果
PASS

### 驗收標準檢查
1. 既有測試不報錯: ✅ (120 tests passed)
2. 新增單元測試涵蓋: ✅ (Store stats, Bot rendering 均有測試覆蓋)
3. Interface Contract 更新: ✅ (`order_type` 修正符合 `PolymarketOrder`)
4. PROGRESS.md 標記: ✅ (即將更新)

### 修改範圍檢查
✅ 修改檔案均在 spec 定義範圍內，且無意外修改。

### 擴展測試摘要
- `test_prediction_signal_order_type_contract`: 驗證 `PredictionSignal` 與 `PolymarketOrder` 的 `order_type` 契約一致性。 (PASS)
- `test_store_get_pm_strategy_detail_timeframe_filtering`: 驗證 `DataStore` 之 Polymarket 統計方法在不同 timeframe 下的過濾正確性。 (PASS)
- `test_bot_stats_routing_logic`: 驗證 Discord Bot `/stats` 指令對於 `pm_` 前綴策略的正確路由與資料庫查詢路徑。 (PASS)
- `test_bot_predict_alpha_none_handling`: 驗證當 Polymarket 訊號缺少 `alpha` 數據時的 Embed 容錯顯示。 (PASS)
- `test_store_get_pm_daily_stats_consecutive_losses`: 驗證 Polymarket 連敗統計邏輯的正確性。 (PASS)

### 發現的問題
無。實作完整且考慮到 backward-compatibility。

### PROGRESS.md 修改建議
將 3.3.2 標記為完成。
