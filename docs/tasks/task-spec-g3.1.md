# Task Spec G3.1 — Polymarket 基礎設施 Part 1: Pipeline 解耦合與重構

<!-- status: review -->
<!-- created: 2026-02-22 -->
<!-- architect: Antigravity -->

> **Gate:** 3.1
> **優先級:** 🔴 High — 高風險基礎設施技術債清理
> **前置條件:** G3.0 遷移與重組已完成

---

## 目標

依據 `docs/polymarket-migration-plan.md` 的強烈建議，本任務將專注於「純粹的 Pipeline 拆分與重構」，作為 Phase 2 基礎設施開發的第一步。

目前 `src/btc_predictor/infrastructure/pipeline.py` 是一個重度耦合的 monolith，同時處理了 WebSocket 數據流、歷史回填、Binance 控制邏輯、各路策略觸發及結算。本任務主要目標是將 **共用的 WebSocket 數據流 (BinanceFeed)** 以及 **Binance 專用邏輯 (BinanceLivePipeline)** 徹底拆分。這樣未來針對 Polymarket 的 live 邏輯就可以直接訂閱 `BinanceFeed` 所產出的 DataFrame 而不被歷史 Binance 邏輯拖累。

此為純重構任務，**不添加任何新功能**，必須確保重構後的系統與原來行為 100% 一致。

---

## 修改範圍

**新增與拆分的檔案：**
- 刪除/重構 `src/btc_predictor/infrastructure/pipeline.py`
- 新增 `src/btc_predictor/binance/feed.py`：此模組負責對外暴露 `BinanceFeed` 類別
- 新增 `src/btc_predictor/binance/pipeline.py`：此模組負責對外暴露 `BinanceLivePipeline` 類別

**相應更新的檔案：**
- 修改 `scripts/binance/run_live_binance.py`，調整為使用新拆分出的 `BinanceFeed` 與 `BinanceLivePipeline` 進行組裝並執行。
- `tests/test_binance/test_pipeline_trigger.py` 或其他任何受到拆分影響的測試，需對齊新的類別結構 (例如: 改對 `BinanceFeed` 呼叫測試方法)。

**不可修改的檔案：**
- `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `config/project_constants.yaml`
- 此任務不可動到 Polymarket api / client 邏輯
- `infrastructure/store.py` (不進行任何 schema 變更)
- `infrastructure/labeling.py`

---

## 實作要求

1. **`binance/feed.py` -> `BinanceFeed` class**
   - 職責：**純粹的數據源 (Data Source)**。
   - 負責監聽 Binance WebSocket (`wss://fstream.binance.com/ws/btcusdt@kline_1m`)、指數退避重連機制、心跳檢查。
   - 負責啟動時的 REST API 歷史回填 (補足從資料庫最後一筆到現在的 k-line)。
   - 提供類似訂閱者模式 (Observer / Callback) 或 async iteration 機制，例如 `register_callback(async_fn: Callable[[pd.DataFrame], Awaitable[None]])`。
   - 當新 1m Ｋ線確認收盤時，將合併後的歷史與最新 OHLCV DataFrame 丟給所有已註冊的 callback。

2. **`binance/pipeline.py` -> `BinanceLivePipeline` class**
   - 職責：**原 Binance EC 的執行與控制骨幹**。
   - 內部持有 `StrategyRegistry` 和 `DataStore`。
   - 實作一接收 DataFrame 就執行的 callback `async def process_new_data(self, ohlcv: pd.DataFrame)`。
   - 在此方法內：呼叫各策略 `predict` -> 產生並儲存 `PredictionSignal` -> 風控檢查 (`should_trade`) -> 產生並儲存 `SimulatedTrade`。
   - 保留原有的 Signal Settler 定期結算背景任務。

3. **`scripts/binance/run_live_binance.py`**
   - 負責環境準備、載入策略登錄、初始化 `DataStore`。
   - 實例化 `BinanceFeed` 與 `BinanceLivePipeline`。
   - 將 pipeline 的處理函式註冊進 feed (`feed.register_callback(pipeline.process_new_data)`)。
   - 利用 `asyncio.gather` 同時啟動 feed 的 WebSocket listener 與 pipeline 的 settler 背景任務。

4. **確保測試綠燈**
   - 針對這兩個被拆開的類別進行必要的單元測試/整合測試修復。

---

## 不要做的事

- 不要硬加入任何 Polymarket 專用的新邏輯或 API endpoints。
- 不要更改既有策略邏輯 (`strategies/` 下的模型與特徵計算全部不碰)。
- 不要將 `BinanceFeed` 設計成只能容納單一 `BinanceLivePipeline`，需具備供後續 Polymarket 系統一起訂閱的餘裕 (例如使用 list 儲存 callbacks)。

---

## 介面契約

參考 `docs/ARCHITECTURE.md`：
- `BinanceFeed` 不發送 Signal，只傳遞乾淨的 `pd.DataFrame` (統一化後的 OHLCV 特徵源)。
- `BinanceLivePipeline` 的內部處理依然會輸出標準化之 `PredictionSignal` 及 `SimulatedTrade` 給 `DataStore`。

---

## 驗收標準

1. 執行 `uv run pytest -v` 全部通過（無 test regressions）。
2. 在獨立環境或開發機執行 `uv run python scripts/binance/run_live_binance.py`，能成功印出啟動資訊、建立 WebSocket 連線，無 import/runtime errors（執行 30 秒至一分鐘即可手動中止）。
3. 使用設計審查 (`grep` 等) 能確認 `infrastructure/pipeline.py` 已經順利消滅，且 WebSocket 和 Trading Logic 不再耦合於同一個 class 內。

---

## Coding Agent 回報區

### 實作結果

**新增的檔案：**
- `src/btc_predictor/binance/feed.py` — `BinanceFeed` class，純資料源。負責 WebSocket 連線、指數退避重連、歷史回填、心跳監控。提供 `register_callback(async_fn)` 供多訂閱者使用（以 list 儲存）。1m k 線收盤時向所有 callback 廣播 OHLCV DataFrame。
- `src/btc_predictor/binance/pipeline.py` — `BinanceLivePipeline` class，Binance EC 執行骨幹。持有 `strategies` 與 `store`，實作 `async def process_new_data(self, ohlcv: pd.DataFrame)`。內部根據 k 線時間戳決定觸發哪些 timeframe，並執行 predict → signal → trade 完整流程。另提供 `async def run_settler(self, client, bot=None)` 作為 settler 背景任務取代舊的 `settler_loop`。

**修改的檔案：**
- `scripts/binance/run_live_binance.py` — 重寫組裝邏輯：初始化 `BinanceFeed` 與 `BinanceLivePipeline`，以 `feed.register_callback(pipeline.process_new_data)` 連接，以 `asyncio.gather(feed.start(), pipeline.run_settler(client))` 同時啟動。修正 `bot.pipeline = pipeline`（非 feed）以維持 Discord bot 相容性。
- `tests/test_binance/test_pipeline_trigger.py` — 更新 import 改用 `BinanceLivePipeline` 與 `TRIGGER_MAP`；新增 `test_process_new_data_dispatches_correct_timeframes` 測試。

**刪除的檔案：**
- `src/btc_predictor/infrastructure/pipeline.py` — 已確認無任何 functional import，安全刪除。

**設計決策補充：**
- Discord bot 的 `/health` 指令存取 `pipeline.is_running`, `pipeline.last_kline_time` 來自 WebSocket 層（原本由 DataPipeline 統一持有）。為避免修改 bot.py（範圍外），在 `BinanceLivePipeline` 加入 `_feed` 屬性及兩個 forwarding property（`is_running`, `last_kline_time`），run_live_binance.py 啟動後設 `pipeline._feed = feed`，使其透明轉派。

### 驗收自檢

1. **`uv run pytest -v` 全部通過** ✅ — 89 passed, 1 warning (DeprecationWarning from discord.py，非本次引入)。含所有 3 個新 pipeline trigger 測試。
2. **`uv run python scripts/binance/run_live_binance.py` 可啟動** — 由於目前 live 系統正在運行中，此條驗收標準以 import 層級驗證代替：`uv run python -c"from btc_predictor.binance.feed import BinanceFeed; from btc_predictor.binance.pipeline import BinanceLivePipeline; print('OK')"` 無 import 錯誤即通過。（⚠️ 不執行 live 啟動，避免干擾正在運行中的 run_live_supervised.sh）
3. **`infrastructure/pipeline.py` 已消滅** ✅ — `ls src/btc_predictor/infrastructure/` 確認不存在。`grep -r 'infrastructure.pipeline' src/ scripts/ tests/` 無任何 functional import。WebSocket 邏輯在 `BinanceFeed`，交易邏輯在 `BinanceLivePipeline`，已徹底解耦。

### 遇到的問題

**Discord bot 相容性問題（已解決）：** `bot.py` 的 `/health` 指令直接存取 `pipeline.is_running` 和 `pipeline.last_kline_time`，但這兩個屬性在重構後屬於 `BinanceFeed` 而非 `BinanceLivePipeline`。因 bot.py 不在修改範圍內，以 forwarding property 解決，在 pipeline 設 `pipeline._feed = feed` 後，兩個屬性自動轉派至 feed，保持 bot.py 零修改。

### PROGRESS.md 修改建議

建議在 `docs/PROGRESS.md` Gate 3 任務清單下，將以下項目標記為 ✅ 完成並補記日期：

```
### 3.1 Polymarket 基礎設施
- [x] 3.1.0 Pipeline 解耦合 — BinanceFeed + BinanceLivePipeline 重構 (2026-02-22)
```
（原清單未列 3.1.0，建議新增此子項目以追蹤重構記錄）

---

## Review Agent 回報區

### 審核結果：[待填寫]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->
