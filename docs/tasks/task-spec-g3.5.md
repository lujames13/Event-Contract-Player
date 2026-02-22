# Task Spec G3.5 — Polymarket Paper Trading Pipeline (3.3.1)

<!-- status: review -->
<!-- created: 2026-02-22 -->
<!-- architect: Antigravity -->

> **Gate:** 3.5 (對應 PROGRESS.md 3.3.1)
> **優先級:** 🔴 High — Live Trading Engine

---

## 目標

在前幾個任務的努力下，我們已經有了 Polymarket 的資料表、Market Tracker、Gamma APIs 以及完成合約對齊的 `pm_v1` 模型。本次 Task 的目標是開發全新的 Polymarket Live Pipeline，將數據串流 (BinanceFeed)、模型預測與市場追蹤 (Tracker) 無縫接軌，實作完整的**模擬交易推進器 (Paper Trading Engine)**。

這將讓我們能開始收集即時產生的 `PredictionSignal` 並且篩選出高 Alpha 得分的信號轉換為模擬的 `PolymarketOrder` 與 `SimulatedTrade`。

主要目標：
1. **Polymarket Live Pipeline (3.3.1)**: 在 `src/btc_predictor/polymarket/pipeline.py` 實作主控邏輯。
2. **模擬下單執行**: 依照 Alpha 是否通過閾值，將 PredictionSignal 轉換成 SimulatedTrade 與 PolymarketOrder 存入 DB。
3. **主程式重置**: 將原本已清空的 `scripts/run_live.py` 重新實作為 Polymarket 版本的系統進入點。

---

## 修改範圍

**新增檔案：**
- `src/btc_predictor/polymarket/pipeline.py` (實作 `PolymarketLivePipeline`)
- `scripts/run_live.py` (新的 Polymarket 主控程式進入點)
- `tests/polymarket/test_pipeline.py` (Pipeline 整合驗證)

**被修改檔案：**
- `docs/PROGRESS.md` (更新進度 3.3.1)
- `config/project_constants.yaml` (如有需要可加入 pm_v1 預設 alpha 閾值)

**不可動的檔案：**
- `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`
- `src/btc_predictor/binance/` 下的任何歷史代碼
- 任何既有策略如 `xgboost_v1` 的程式碼

---

## 實作要求

1. **PolymarketLivePipeline 實作 (`pipeline.py`)**：
    - 建立 `PolymarketLivePipeline` 類別，注入 `BinanceFeed`, `StrategyRegistry`, `DataStore`, 與 `PolymarketTracker`。
    - **非同步監控 (Async Tasks)**：
        - 啟動 `BinanceFeed` 背景收集 1m OHLCV 實時 K 線資訊。
        - 啟動 `PolymarketTracker` 的每分鐘檢查或是排程更新，保持 SQLite 內的 Active Markets 是最新的。
    - **推理與信號階段 (Predict & Signal)**：
        - 當收到 BinanceFeed 生成新的收盤 K 線時，傳入 `StrategyRegistry` 中的 PM 策略（例如 `pm_v1`）進行 `predict()`。
        - 根據架構原則：**無論如何，所有的預測都要產生 `PredictionSignal` 寫入 `prediction_signals` 表（Signal Layer 全量紀錄）**。
    - **決策與模擬階段 (Decision & Simulate)**：
        - 檢視 `PredictionSignal` 的 timeframe，利用 Tracker 的 `get_active_market(timeframe)` 尋找對應的 PM 市場。
        - **計算 Alpha**：根據向 PM API 查詢的實時市場價格 (若有)，設定 `signal.alpha = signal.confidence - market_price`。如果未能正確取得市場，妥善進行 fallback，但原則上下單依賴 Alpha。
        - 根據 `project_constants.yaml` 配置的風控條件（如 `alpha > alpha_thresholds` 且符合資金管理）決策是否下注。
        - 若決定下注，建構 `SimulatedTrade`，再建構對應的 `PolymarketOrder` (標記 order_type 為 `"maker"`，status 為 `"OPEN"`)，並以 Transaction 安全地保存至 DataStore。

2. **主程式 (`scripts/run_live.py`)**：
    - 作為 Polymarket 系統的 live 運行 CLI 進入點。
    - 初始化上述所有相依組件，並支援透過 `asyncio.run(pipeline.start())` 持續運作。
    - 要有良好的 Exception 捕捉與日誌系統，避免一次 WebSocket 斷線就導致整個系統崩潰。

3. **系統單元測試 (`test_pipeline.py`)**：
    - 撰寫 `test_polymarket_pipeline_execution` 測試。
    - 使用 Mocked `BinanceFeed` 送出單筆或兩筆 Fake OHLCV，捕捉 Pipeline 是否正確觸發預測。
    - 驗證當 Alpha 滿足條件時，是否的確觸發了 `save_pm_order` 與 `save_prediction_signal`。

---

## 不要做的事

- **不要**在 Pipeline 中撰寫真實的簽章與下單邏輯 (真實下單屬於 Gate 4)。
- **不要**將 `DiscordBot` 直接耦合於 Pipeline 中，Discord 通知與適配是下一個獨立任務（3.3.2）的重點。
- **不要**影響舊有的 Binance Pipeline 或改動 `binance/pipeline.py`。
- **不要**將 SQLite 持續長開不釋放（長時間佔用 Connection 容易導致 WAL mode 產生 lock 衝突）。

---

## 介面契約

參考 `ARCHITECTURE.md`：
- Pipeline 必須調用 `store.save_prediction_signal`，並在產生 Trade 時呼叫 `store.save_pm_order` 以及寫入 `SimulatedTrade`。
- `PolymarketOrder` 預設生成時狀態應為 `OPEN`。

---

## 驗收標準

1. 執行 `uv run pytest tests/polymarket/test_pipeline.py -v` 需全部通過。
2. 確認 `scripts/run_live.py` 腳本存在並能被無錯執行啟動。
3. `PolymarketLivePipeline` 必須實作嚴密的 Error Handling，任意單一 API Call 逾時 (Timeout) 或 JSON Decode Error 皆不得拋出中斷程序，應紀錄 logger warning 後在下個事件迴圈繼續。
4. `docs/PROGRESS.md` 中的 3.3.1 被標記為 `[x]`。

---

## Coding Agent 回報區

### 實作結果
- 實作了 `PolymarketLivePipeline`，連接 `BinanceFeed`, `DataStore`, `PolymarketTracker`，將推論轉換為 `PredictionSignal`，並過濾 alpha 產生 `SimulatedTrade` + `PolymarketOrder`。
- 新增 `scripts/run_live.py` 啟動主迴圈與追蹤器。
- 新增 `tests/polymarket/test_pipeline.py` 進行整合測試，確認產生流程正確與缺失 market 處理適當。
- 配置了 `config/project_constants.yaml` 中的 pm_v1 預設 alpha 閾值為 `0.02`。

### 驗收自檢
- [x] 所有測試通過
- [x] Pipeline 正確產生 PredictionSignal 與 PolymarketOrder
- [x] scripts/run_live.py 能順利啟動
- [x] Error handling 覆蓋

### 遇到的問題
- 由於需根據市場的實際 `close_price` (Up token) 來反推 alpha，因此若 Tracker 當下無法抓取到目標 market 時 (`pm_market` is None)，將回退不產生交易（只保留 Signal 記錄），避免使用虛假價格去進行下單及回測計算。

### PROGRESS.md 修改建議
- 3.3.1 進度已標註完成，無需額外建議。

### Commit Hash
- `ce33c44`

---

## Review Agent 回報區

### 審核結果
- [PASS / FAIL / BLOCKED]

### 問題與建議
- [檢討與建議...]
