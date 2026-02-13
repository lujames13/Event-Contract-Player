# Project Progress (Revised — MVP-First)

> ★ **Single Source of Truth** — Agent 每次完成任務後必須更新此文件。
>
> 📐 **設計原則變更 (2025-02-14)：** 從「寬優先（先做完所有模型再建系統）」改為
> 「深優先（一個模型打通全鏈路，再水平擴展）」。原因：儘早驗證端到端可行性，
> 避免在模型層投入大量時間後才發現基礎設施有設計缺陷。

## Current Phase: 1 — XGBoost 基線模型
## Current Task: 1.5.1.1 — 風控核心邏輯

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

- [x] **1.2.1** ⭐ **Label 生成邏輯** (2025-02-14)
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

- [x] **1.2.2** 特徵工程：OHLCV + 技術指標 (2025-02-14)
  - 產出：`src/btc_predictor/strategies/xgboost_direction/features.py`
  - 特徵清單：
    - 基礎：returns (多週期)、log returns、volatility (rolling std)
    - TA-Lib：RSI(14), MACD(12,26,9), BB(20,2), ATR(14)
    - 衍生：RSI 離中值距離、MACD histogram 斜率、BB %B、價格相對 BB 位置
    - 時間特徵：hour_of_day, day_of_week (sin/cos encoding)
    - 成交量：volume ratio (vs rolling mean)、OBV 變化率
  - 注意：所有特徵必須只用 t 時刻及之前的數據（嚴禁前視偏差）
  - 驗收：pytest 驗證特徵值合理性 + 無 NaN 洩漏 + 無前視偏差

- [x] **1.2.3** XGBoost 模型訓練邏輯 (2025-02-14)
  - 產出：`src/btc_predictor/strategies/xgboost_direction/model.py`
  - 內容：
    - `train(X, y, params)` → 返回訓練好的 model
    - `predict_proba(model, X)` → 返回 higher 的概率
    - 超參數初始值：max_depth=6, n_estimators=500, learning_rate=0.05,
      scale_pos_weight 根據 label 比例調整, early_stopping_rounds=50
    - 保存/載入 model 的序列化工具
  - 驗收：能在小數據集上跑通 train → predict 流程

- [x] **1.2.4** 統一輸出為 PredictionSignal (2025-02-14)
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

- [x] **1.5.1.1** 風控核心邏輯 (2025-02-14)
  - 產出：`src/btc_predictor/simulation/risk.py`
  - 內容：
    - `should_trade(daily_loss, consecutive_losses, daily_trades) → bool`
    - `calculate_bet(confidence, timeframe_minutes) → float`
    - 從 `project_constants.yaml` 讀取參數，不硬編碼
  - 驗收：pytest 覆蓋閾值邊界、各時間框架

#### 1.5.2 回測框架（基礎設施，所有策略共用）

- [x] **1.5.2.1** Walk-forward 回測引擎 (2025-02-14)

- [x] **1.5.2.2** BaseStrategy 介面擴展 (2025-02-14)

- [x] **1.5.2.3** 回測統計計算 (2025-02-14)
- [x] **1.5.2.4** 回測 CLI 入口 + 報告生成 (2025-02-14)

#### 1.2.3 模型訓練 ✅
- [x] 基礎訓練邏輯完成
- [x] 訓練腳本建立（scripts/train_xgboost_model.py）
- [x] 模型儲存與載入驗證
- [x] 首次訓練完成並產生可用模型

### Phase 1.3 - Risk Management ✅

#### 1.3.1 資金管理模組 ✅
- [x] 凱利公式實作（Kelly Criterion）
- [x] 最大回撤控制
- [x] 單筆交易限額

### Phase 1.4 - Discord Integration ✅

#### 1.4.1 Bot 基礎架構 ✅
- [x] Discord Bot 專案設定
- [x] 指令系統建立
- [x] 訊息發送功能

### Phase 1.5 - MVP Integration 🔄

#### 1.5.1 數據管道整合 ✅
- [x] 歷史數據獲取與更新
- [x] 實時數據串流
- [x] 數據預處理管道

#### 1.5.2 策略整合 ✅
- [x] 策略介面標準化
- [x] 信號生成機制
- [x] 模擬交易紀錄

#### 1.5.3 系統運行 ✅
- [x] 主程式入口（main.py）
- [x] 配置管理（config/）
- [x] 日誌系統

#### 1.5.3.4 即時運行入口 🔄
- [x] 框架建立完成
- [x] WebSocket 監聽機制
- [x] 模型載入機制整合
- [ ] 端到端測試通過（無錯誤運行）

### Phase 1.6 - 首次端到端驗證 🔄

#### 1.6.1 模型訓練驗證
- [x] 訓練腳本可成功執行
- [x] 三個時間框架模型檔案產生
- [x] 訓練準確率在合理範圍（> 50%）

#### 1.6.2 即時預測驗證  
- [x] run_live.py 可正常啟動
- [ ] 1 分鐘 K 線收盤時觸發預測
- [ ] 預測結果格式正確
- [ ] 無崩潰運行 > 1 小時

#### 1.6.3 問題修復記錄
- [x] 修復 "Model not loaded/trained" 錯誤
- [x] 建立模型訓練流程
- [x] 整合模型載入機制**1.5.5.2** 即時模擬 72 小時壓力測試 (Pending)

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
- [x] **1.2** XGBoost 基線模型建立 (2025-02-14)
  - 產出：`src/btc_predictor/data/labeling.py`, `src/btc_predictor/strategies/xgboost_direction/`
  - 成果：
    - **1.2.1**: Label 生成邏輯，處理平盤與數據缺失。
    - **1.2.2**: 特徵工程，包含 OHLCV、技術指標與時間編碼。
    - **1.2.3**: XGBoost 模型訓練、早期停止與序列化工具。
    - **1.2.4**: 整合至 `XGBoostDirectionStrategy` 並統一輸出為 `PredictionSignal`。

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