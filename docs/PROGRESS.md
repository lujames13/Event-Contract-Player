# Project Progress (Revised — MVP-First)

> ★ **Single Source of Truth** — Agent 每次完成任務後必須更新此文件。
>
> 📐 **設計原則變更 (2025-02-14)：** 從「寬優先（先做完所有模型再建系統）」改為
> 「深優先（一個模型打通全鏈路，再水平擴展）」。原因：儘早驗證端到端可行性，
> 避免在模型層投入大量時間後才發現基礎設施有設計缺陷。

## Current Phase: 1 — XGBoost 基線模型
## Current Task: 1.2.1 — Label 生成邏輯

---

## Phase 總覽（修訂後）

| Phase | 名稱 | 目標 | 預估 |
|-------|------|------|------|
| **1** | XGBoost 基線模型 | 一個能跑的方向分類模型 + 特徵工程 | 2 週 |
| **1.5** | MVP 全鏈路 | 回測框架 + 模擬倉 + 風控 + Discord Bot 骨架，用 XGBoost 跑通 | 3 週 |
| **2** | 水平擴展 | 更多模型 (N-BEATS, FreqAI) + 多模態特徵 (F&G, DXY, CryptoBERT) | 4 週 |
| **3** | 真實交易驗證 | Discord Bot 完善 + 手動下單 + 滑價分析 | 2 週 |

---

## Task Breakdown

### Phase 1：XGBoost 基線模型 (目標 2 週)

#### 1.1 環境建設 ✅

- [x] **1.1.1** `uv init` 初始化專案 + 目錄結構 + `project_constants.yaml`
- [x] **1.1.2** Binance REST API 歷史數據抓取
- [x] **1.1.3** SQLite schema 建立 + 讀寫工具

#### 1.2 XGBoost 方向分類

- [ ] **1.2.1** ⭐ **Label 生成邏輯**
  - 產出：`src/btc_predictor/data/labeling.py`
  - 核心：給定 open_time 和 timeframe_minutes，計算 label:
    - 從 OHLCV 中找到 `open_time` 的 close price 作為 open_price
    - 找到 `open_time + timeframe_minutes` 的 close price 作為 close_price
    - label = 1 (higher) if close_price > open_price, else 0 (lower)
  - 邊界處理：
    - 跨 K 線粒度對齊（例：10m 預測用 1m K 線，需聚合 10 根）
    - 缺失數據（交易所維護、API 中斷）→ 該樣本標記為 NaN 並排除
    - 平盤情況 (close_price == open_price) → 根據 Event Contract 規則視為 lose
  - 驗收：pytest 測試覆蓋正常情況 + 所有邊界情況
  - **Rationale：這是 Event Contract 最核心的差異點，所有模型和回測都依賴正確的 label**

- [ ] **1.2.2** 特徵工程：OHLCV + 技術指標
  - 產出：`src/btc_predictor/strategies/xgboost_direction/features.py`
  - 特徵清單：
    - 基礎：returns (多週期)、log returns、volatility (rolling std)
    - TA-Lib：RSI(14), MACD(12,26,9), BB(20,2), ATR(14)
    - 衍生：RSI 離中值距離、MACD histogram 斜率、BB %B、價格相對 BB 位置
    - 時間特徵：hour_of_day, day_of_week (sin/cos encoding)
    - 成交量：volume ratio (vs rolling mean)、OBV 變化率
  - 注意：所有特徵必須只用 t 時刻及之前的數據（嚴禁前視偏差）
  - 驗收：pytest 驗證特徵值合理性 + 無 NaN 洩漏 + 無前視偏差

- [ ] **1.2.3** XGBoost 模型訓練邏輯
  - 產出：`src/btc_predictor/strategies/xgboost_direction/model.py`
  - 內容：
    - `train(X, y, params)` → 返回訓練好的 model
    - `predict_proba(model, X)` → 返回 higher 的概率
    - 超參數初始值：max_depth=6, n_estimators=500, learning_rate=0.05,
      scale_pos_weight 根據 label 比例調整, early_stopping_rounds=50
    - 保存/載入 model 的序列化工具
  - 驗收：能在小數據集上跑通 train → predict 流程

- [ ] **1.2.4** 統一輸出為 PredictionSignal
  - 產出：`src/btc_predictor/strategies/xgboost_direction/strategy.py`
  - 內容：繼承 BaseStrategy，串接 features → model → PredictionSignal
  - confidence = predict_proba 的輸出值
  - direction = "higher" if prob > 0.5 else "lower"
  - confidence = max(prob, 1-prob) — 映射到 0.5~1.0 的信心度
  - 驗收：輸出符合 PredictionSignal 介面，pytest 通過

---

### Phase 1.5：MVP 全鏈路 (目標 3 週)

> **目標：** 用 XGBoost 一個模型跑通「歷史回測 → 即時模擬 → Discord 通知」全鏈路。
> 這個階段完成後，加入新模型只需要實作 BaseStrategy 即可自動接入。

#### 1.5.1 風控模組（回測和模擬都需要，先做）

- [ ] **1.5.1.1** 風控核心邏輯
  - 產出：`src/btc_predictor/simulation/risk.py`
  - 內容：
    - `should_trade(daily_loss, consecutive_losses, daily_trades) → bool`
    - `calculate_bet(confidence, timeframe_minutes) → float`
    - 從 `project_constants.yaml` 讀取參數，不硬編碼
  - 驗收：pytest 覆蓋閾值邊界、各時間框架

#### 1.5.2 回測框架（基礎設施，所有策略共用）

- [ ] **1.5.2.1** Walk-forward 回測引擎
  - 產出：`src/btc_predictor/backtest/engine.py`
  - 設計：
    - 輸入：strategy (BaseStrategy), ohlcv_df, timeframe_minutes, walk-forward 參數
    - Walk-forward 邏輯：
      - 初始訓練窗口（e.g. 60 天）
      - 測試窗口（e.g. 7 天）
      - 步進：每次測試完畢，將測試窗口加入訓練集，滑動前進
    - 每步：strategy.predict() → 判斷信心度 → calculate_bet → 記錄 SimulatedTrade
    - 到期結算：查找對應時間的 close_price，計算 result 和 pnl
  - 輸出：List[SimulatedTrade]
  - **注意：策略需支持 `fit()` 方法用於 walk-forward 重訓練**
  - 驗收：能用 XGBoost 策略跑完一輪 walk-forward

- [ ] **1.5.2.2** BaseStrategy 介面擴展
  - 修改：`src/btc_predictor/strategies/base.py`
  - 新增 `fit(ohlcv, timeframe_minutes)` 抽象方法（用於 walk-forward 重訓練）
  - 新增 `requires_fitting: bool` 屬性（XGBoost=True, 純規則策略=False）
  - **需要同步更新 ARCHITECTURE.md**
  - **Discussion: 此修改需人類確認是否可接受改動 BaseStrategy 介面**

- [ ] **1.5.2.3** 回測統計計算
  - 產出：`src/btc_predictor/backtest/stats.py`
  - 指標：
    - DA (方向準確率) — 分整體 + 分 higher/lower
    - 累計 PnL 曲線
    - Sharpe Ratio (以交易為單位)
    - 最大回撤 (MDD)
    - 最大連敗次數
    - 勝率 vs 閾值勝率的差距
    - 信心度分桶準確率（校準圖）：按 0.6-0.7, 0.7-0.8, 0.8-0.9, 0.9-1.0 分桶
  - 驗收：pytest 用固定交易記錄驗證計算正確性

- [ ] **1.5.2.4** 回測 CLI 入口 + 報告生成
  - 產出：`scripts/backtest.py`
  - 用法：`uv run python scripts/backtest.py --strategy xgboost_v1 --timeframe 10 --train-days 60 --test-days 7`
  - 輸出：終端表格 + JSON 報告 + (可選) matplotlib 圖表存檔
  - 驗收：XGBoost × 4 個時間框架的 DA 報告

#### 1.5.3 模擬倉引擎（即時運行）

- [ ] **1.5.3.1** SimulatedTrade 引擎核心
  - 產出：`src/btc_predictor/simulation/engine.py`
  - 邏輯：
    - 接收 PredictionSignal → 風控檢查 → 建立 SimulatedTrade → 寫入 SQLite
    - 維護當日統計（daily_loss, consecutive_losses, daily_trades）
    - UTC 日切邏輯（每日 00:00 UTC 重置計數器）
  - 驗收：pytest 模擬完整交易流程

- [ ] **1.5.3.2** 到期結算排程器
  - 產出：`src/btc_predictor/simulation/settler.py`
  - 邏輯：
    - 維護一個「待結算」佇列 (按 expiry_time 排序)
    - 定期檢查（或由 WebSocket 觸發）：當前時間 >= expiry_time 時
    - 查詢 expiry_time 對應的 index price → 回填 close_price, result, pnl
    - 查詢方式：先查 SQLite ohlcv 表，若無則呼叫 Binance REST API
  - 邊界處理：
    - 網路中斷時的重試邏輯（指數退避）
    - 結算時 K 線尚未到達 → 延遲重試
  - 驗收：pytest 模擬到期結算流程

- [ ] **1.5.3.3** WebSocket 即時監聽 + 策略觸發
  - 產出：`src/btc_predictor/data/pipeline.py`
  - 邏輯：
    - 連接 Binance WebSocket (kline stream)
    - K 線收盤事件 → 更新 ohlcv SQLite → 觸發所有已啟用策略的 predict()
    - 斷線重連 + 指數退避
    - 啟動時回補斷線期間缺失的 K 線（REST API gap fill）
  - **注意：Event Contract open price 是下單後下一秒的 index price**
    - 模擬時用 signal 產生時的 price 近似，Phase 3 記錄真實滑價
  - 驗收：能連接 WebSocket 並持續觸發策略至少 1 小時不斷線

- [ ] **1.5.3.4** 即時運行入口
  - 產出：`scripts/run_live.py`
  - 整合：WebSocket pipeline + 策略載入 + 模擬引擎 + 結算排程器
  - 配置：從 yaml 讀取策略列表、時間框架
  - Graceful shutdown (SIGINT/SIGTERM)
  - 驗收：能跑起來持續模擬交易

#### 1.5.4 Discord Bot 骨架

- [ ] **1.5.4.1** Bot 基礎架構
  - 產出：`discord_bot/bot.py`
  - 功能：
    - 啟動時連接 Discord
    - 接收模擬引擎的新交易事件 → 推送到指定頻道
  - 訊號格式：
    ```
    🔮 [XGBoost] BTCUSDT 10m → HIGHER
    📊 信心度: 72.3% | 下注: $11.2
    💰 開倉價: $97,234.50
    ⏰ 到期: 2025-02-14 15:20 UTC
    ```

- [ ] **1.5.4.2** 基礎指令
  - `/stats` — 顯示當日/總計統計
  - `/pause` / `/resume` — 暫停/恢復模擬交易
  - 驗收：指令可正常回應

- [ ] **1.5.4.3** 到期結算通知
  - 到期結算後推送結果：
    ```
    ✅ WIN [XGBoost] 10m HIGHER
    開倉: $97,234.50 → 收盤: $97,456.20
    盈虧: +$9.04 | 累計: +$45.30
    今日勝率: 8/12 (66.7%)
    ```

#### 1.5.5 MVP 端到端驗證

- [ ] **1.5.5.1** 歷史回測驗證
  - 跑 XGBoost × 4 個時間框架的完整 walk-forward 回測
  - 輸出 Key Metrics 表格
  - 初步判斷哪些時間框架值得繼續

- [ ] **1.5.5.2** 即時模擬 72 小時壓力測試
  - 連續跑 72 小時，驗證：
    - WebSocket 穩定性（斷線重連）
    - 到期結算準確性（比對手動查價）
    - Discord 通知及時性
    - 日切邏輯正確性
    - 記憶體/CPU 無洩漏
  - 產出：穩定性報告

---

### Phase 2：水平擴展 (目標 4 週)

> **前提：** MVP 已通過 72 小時壓力測試。
> 此階段新增模型只需實作 BaseStrategy，自動接入回測 + 模擬 + Discord。

#### 2.1 更多預測模型

- [ ] **2.1.1** N-BEATS Perceiver 環境搭建 + 本地 inference
- [ ] **2.1.2** N-BEATS 改造為 BTC 方向分類 + PredictionSignal 輸出
- [ ] **2.1.3** (Optional) FreqAI 預測信號提取 + PredictionSignal 輸出
- [ ] **2.1.4** 所有模型 × 4 時間框架 walk-forward 回測對比

#### 2.2 多模態特徵增強

- [ ] **2.2.1** Fear & Greed Index 接入 (alternative.me API)
- [ ] **2.2.2** DXY 美元指數接入 (Yahoo Finance)
- [ ] **2.2.3** CryptoBERT 情緒分析 (inference only, ~2GB VRAM)
- [ ] **2.2.4** 特徵增強後的模型重訓練 + 回測對比

#### 2.3 Boruta/SHAP 特徵選擇與可解釋性

- [ ] **2.3.1** Boruta 特徵選擇 — 確定最終特徵集
- [ ] **2.3.2** SHAP 分析 — 每個時間框架的特徵重要性報告
- [ ] **2.3.3** 信心度校準分析 — 模型輸出概率 vs 實際勝率的偏差

#### 2.4 收斂決策

- [ ] **2.4.1** 累積 ≥ 200 筆模擬交易（每個候選策略 × 時間框架）
- [ ] **2.4.2** 過擬合檢測 (walk-forward OOS vs IS 衰減比)
- [ ] **2.4.3** 確定進入 Phase 3 的最佳策略 × 時間框架組合
  - 判斷標準：OOS DA > breakeven + 5%、Sharpe > 1.0、信心度校準合理

---

### Phase 3：真實交易驗證 (目標 2 週)

> **前提：** 至少一個策略 × 時間框架組合通過收斂標準。

- [ ] **3.1.1** Discord Bot 增加真實交易記錄功能
  - `/record <trade_id> win|lose` — 手動記錄真實結果
  - 或：根據 Binance 帳戶記錄自動比對（如可行）
- [ ] **3.1.2** RealTrade 記錄 + 滑價分析
  - 記錄 actual_open_price, actual_close_price, execution_delay
  - 分析模擬 vs 真實的系統性偏差
- [ ] **3.1.3** 累積 ≥ 50 筆真實交易
- [ ] **3.1.4** 真實 vs 模擬勝率對比報告
  - 若真實勝率顯著低於模擬 → 回到 Phase 2 調整
  - 若真實勝率符合預期 → 考慮逐步提高下注金額

---

## Completed

- [x] **1.1.1** 初始化專案結構與環境搭建 (2025-02-12)
  - 產出：`pyproject.toml`, `.python-version`, `src/btc_predictor/`, `TA-Lib` (C Library + Python Wrapper)
  - 環境：Python 3.12, uv, pandas, torch, xgboost, lightgbm, TA-Lib, shap, etc.
- [x] **1.1.2 & 1.1.3** Binance 數據抓取與 SQLite 儲存層 (2025-02-12)
  - 產出：`scripts/fetch_history.py`, `src/btc_predictor/data/store.py`, `tests/test_store.py`
  - 成果：支援 BTCUSDT 1m/5m/1h/1d 歷史數據抓取並以 UPSERT 方式存入 SQLite。通過 pytest 驗證。

---

## In Progress

_（Agent 正在處理的任務）_

---

## Known Issues / Discussion

- ❓ **BaseStrategy 介面擴展**：walk-forward 回測需要策略支持 `fit()` 方法，但目前
  BaseStrategy 只有 `predict()`。建議新增 `fit()` 抽象方法和 `requires_fitting` 屬性。
  需人類確認是否可以修改 ARCHITECTURE.md 中的介面定義。
- ⚠️ **平盤 (close == open) 的處理**：Event Contract 規則中未明確說明平盤情況的結算，
  但根據 higher/lower 的定義，平盤應視為 lose（既不 higher 也不 lower）。
  需人類確認這個假設。
- ⚠️ **Event Contract open price 新規則 (2026-01-28)**：open price 現在是下單後
  「下一秒」的 index price，而非下單瞬間的 price。這意味著模擬時存在系統性偏差，
  需在 Phase 3 真實交易中追蹤滑價並回饋修正。

---

## Key Metrics

_（Agent 跑完回測/模擬後更新數字）_

| 策略 | 時間框架 | DA (方向準確率) | Sharpe | 樣本數 | 驗證方式 | 日期 | 備註 |
|------|---------|----------------|--------|--------|---------|------|------|
| — | — | — | — | — | — | — | 尚無數據 |