# Task Spec G3.3 — 修復 pm_v1 介面契約與補齊 Polymarket 基礎設施

<!-- status: review -->
<!-- created: 2026-02-22 -->
<!-- architect: Antigravity -->

> **Gate:** 3.3 (修復 G3.1 & G3.2)
> **優先級:** 🔴 High — Blocker Resolution

---

## 目標
前一輪 (G3.2) 的實作雖然完成了基本的回測，但嚴重違反了系統介面契約，且遺漏了 G3.1 的核心基礎設施 (API Clients)。本次 Task 將專注於**修補這些架構與合規性漏洞**，確保系統與 `ARCHITECTURE.md` 的定義完全對齊。

主要修復項目包含：
1. 補齊 G3.1 遺漏的 Polymarket Gamma 與 CLOB 唯讀 API Clients。
2. 修正 `models.py` 的型別定義，支援 Polymarket 的 timeframes (5, 15)。
3. 修正 `pm_v1` 模型實作，使其 `PredictionSignal` 輸出完全符合介面契約 (包含正確的型別與 Polymarket 擴展欄位 alpha 等)。
4. 補齊 4h 與 1d 的 timeframe 訓練與回測，並更新報告。
5. 補齊 `pm_v1` 模型的單元測試。

---

## 修改範圍

**新增檔案：**
- `src/btc_predictor/polymarket/gamma_client.py` (Gamma API Client 實作)
- `src/btc_predictor/polymarket/clob_client.py` (CLOB 唯讀 API Client 實作)
- `tests/polymarket/test_clients.py` (API Clients 的單元測試)
- `tests/strategies/test_pm_v1.py` (`pm_v1` 策略的單元測試)

**被修改檔案：**
- `src/btc_predictor/models.py` (修正 `SimulatedTrade.timeframe_minutes` 等型別支援 5, 15, 240)
- `src/btc_predictor/strategies/pm_v1/strategy.py` (修正 `features_used` 型別，並新增邏輯計算 alpha 並填寫 Polymarket 擴展欄位)
- `reports/polymarket/PM-V1-WalkForward-Report.md` (補上 4h, 1d 數據)
- `docs/PROGRESS.md` (更新進度)

**不可動的檔案：**
- `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `config/project_constants.yaml` (不可更動這些架構與決策文件)
- Binance 相關策略 (`xgboost_v1`, `lgbm_v2` 等)

---

## 實作要求

1. **基礎設施補齊 (API Clients)**
   - 實作 `gamma_client.py`：使用 `httpx` (或 `requests`) 針對 Gamma API 進行查詢，取得 5m BTC 市場 metadata。需實作明確的 error handling 與 timeout。
   - 實作 `clob_client.py`：實作唯讀功能，以取得當前訂單簿與市價 (用於後續 live 抓取)。
   - 遵循 `docs/code-style-guide.md` 所有的 I/O 與 Async 規範。

2. **型別與介面契約修正**
   - 編輯 `src/btc_predictor/models.py`：將 `SimulatedTrade.timeframe_minutes` 的 Literal 擴充，加入 5, 15, 240。
   - 編輯 `src/btc_predictor/strategies/pm_v1/strategy.py`：
     - 將 `PredictionSignal.features_used` 的實作改成回傳 `list[str]` (原先錯誤地傳入了 dict)。
     - 依照計畫，Polymarket 交易的核心在於 alpha (model_prob - market_price)。若回測過程中無法取得實時市場價格，也必須確保 `alpha`, `market_slug`, `market_price_up` 欄位被正確賦予預設值，或基於某種 proxy 進行計算 (例如 `模型輸出機率 - 盈虧平衡勝率 50%`)，不可置之不理。

3. **補齊 Timeframe 回測**
   - 對 `pm_v1` 執行 4h (240m) 與 1d (1440m) 的訓練與 Walk-forward 回測。
   - 將結果整合進 `reports/polymarket/PM-V1-WalkForward-Report.md` 中。

4. **單元測試**
   - 撰寫 `test_clients.py` 驗證 API client 的初始化與基本運作 (使用 mock)。
   - 撰寫 `test_pm_v1.py` 驗證策略輸出的 `PredictionSignal` 格式是否完全合法，確保不會發生跟 G3.2 一樣的型別報錯。

---

## 不要做的事
- **不要**在 `pm_v1` 的回測邏輯中強行呼叫線上 API 來取得歷史價格（API 不支援這樣的要求且違反時間序列紀律）；回測時的 market price 可以固定為 0.5 或者透過歷史數據庫載入。
- **不要**修改或放寬 `ARCHITECTURE.md` 的介面契約來迎合原本錯誤的程式碼。遇到不相容，改程式碼，不能改契約。

---

## 驗收標準
1. 執行 `uv run pytest -v` 所有測試通過，包含 `tests/review/specg3.2/test_pm_v1_integrity.py`。
2. `pm_v1` 中 `PredictionSignal` 輸出的 `features_used` 必須是 `list[str]`。
3. `PredictionSignal` 的 Polymarket 擴展欄位 (`alpha`, `market_slug`, `market_price_up`) 都有對應處理或給予合理的 mock 值，不得全部為 `None` 或直接不實作。
4. `PM-V1-WalkForward-Report.md` 包含 5m, 15m, 60m, 4h, 1d 的完整結果比較。
5. 成功建立 `gamma_client.py` 與 `clob_client.py` 並且有基本的 tests。

---

## Coding Agent 回報區

### 實作結果
1. **Polymarket 基礎設施**:
   - 實作了 `src/btc_predictor/polymarket/gamma_client.py` (支援 async fetch_events, fetch_market)。
   - 實作了 `src/btc_predictor/polymarket/clob_client.py` (支援 async get_markets, get_orderbook, get_price)。
   - 新增 `tests/polymarket/test_clients.py` 並通過測試。
2. **型別與介面修正**:
   - `src/btc_predictor/models.py`: `SimulatedTrade.timeframe_minutes` 擴充支援 `5, 15, 240`。
   - `src/btc_predictor/strategies/pm_v1/strategy.py`: 修正 `features_used` 為 `list[str]`，並補齊 `alpha` (model - 0.5), `market_slug`, `market_price_up` 等 Polymarket 擴展欄位。
3. **訓練與回測**:
   - 完成 `pm_v1` 在 4h (240m) 與 1d (1440m) 的模型訓練。
   - 修正了 `src/btc_predictor/backtest/engine.py` 中計算 step 的 bug (原先未考慮非 1m 的資料間隔)，確保 1h interval 的回測數據正確。
   - 執行 4h 與 1d 完整回測，並將數據更新至 `reports/polymarket/PM-V1-WalkForward-Report.md`。
4. **測試**:
   - 新增 `tests/strategies/test_pm_v1.py` 驗證策略誠信度。
   - 執行 `uv run pytest` 通過所有相關測試，包含 `tests/review/specg3.2/test_pm_v1_integrity.py`。
5. **依賴**:
   - 在 `pyproject.toml` 中新增 `httpx>=0.28.0` 以支援 async API clients。


### 驗收自檢
- [x] `uv run pytest -v` 所有測試通過 (含 integrity test)
- [x] `PredictionSignal.features_used` 為 `list[str]`
- [x] Polymarket 擴展欄位 (`alpha` 等) 已正確處理
- [x] `PM-V1-WalkForward-Report.md` 已補齊所有 5 個 timeframe 的對比
- [x] `gamma_client.py` 與 `clob_client.py` 成功建立並有測試覆蓋

### 遇到的問題
1. **Backtest Engine Bug**: 發現 `engine.py` 在處理 1h 資料時 step 計算錯誤 (強制用 `timeframe_minutes` 當 step)，導致 1440m 策略在 1h 數據上每 60 天才產生一筆預測。已修復為根據資料頻率動態計算 step。
2. **HTTpx 缺失**: 原本環境不含 `httpx`，已手動加入 `pyproject.toml` 以符合 Style Guide 的 async I/O 要求。

### PROGRESS.md 修改建議
1. **Gate 3.1 & 3.2**: 建議標記為 [✅] 已解決/通過，因為 G3.3 已補齊所有遺漏的介面與基礎設施。
2. **Timeframe 優先級**: 根據回測報告，5m 表現最優，建議在 Gate 3.3 後續任務中鎖定 5m 作為模擬交易首選。

---

## Review Agent 回報區

### 審核結果
(需填寫)

Git Commit: 1dfd17b
