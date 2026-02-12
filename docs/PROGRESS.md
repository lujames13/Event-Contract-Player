# Project Progress

> ★ **Single Source of Truth** — Agent 每次完成任務後必須更新此文件。

## Current Phase: 1 — 模型選型與複製
## Current Task: 1.1.1 — 專案結構初始化

---

## Task Breakdown

### Phase 1：模型選型與複製 (目標 4–6 週)

#### 1.1 環境建設

- [x] **1.1.1** `uv init` 初始化專案 + 目錄結構 + `project_constants.yaml`
  - 產出：`pyproject.toml`、`.python-version`（3.12）、完整目錄結構、`src/btc_predictor/strategies/base.py`
  - 執行：`uv init --name btc-predictor`，然後 `uv add` 核心依賴
- [ ] **1.1.2** Binance REST API 歷史數據抓取
  - 產出：`scripts/fetch_history.py`、`src/btc_predictor/data/store.py`
  - 驗收：BTCUSDT 1m/5m/1h/1d 數據寫入 SQLite，無缺漏
- [ ] **1.1.3** SQLite schema 建立 + 讀寫工具
  - 產出：`src/btc_predictor/data/store.py` 含 OHLCV 讀寫 + simulated_trades 表
  - 驗收：pytest 通過

#### 1.2 XGBoost 方向分類（輕量基線，先做）

- [ ] **1.2.1** 特徵工程：OHLCV + RSI, MACD, BB, ATR
  - 產出：`src/btc_predictor/strategies/xgboost_direction/features.py`
  - 驗收：特徵計算正確，pytest 通過
- [ ] **1.2.2** Boruta / SHAP 特徵選擇
  - 產出：特徵重要性報告
- [ ] **1.2.3** XGBoost 二元分類模型訓練 + walk-forward 回測
  - 產出：`src/btc_predictor/strategies/xgboost_direction/model.py`、回測腳本
  - 驗收：4 個時間框架的 DA 報告
- [ ] **1.2.4** 統一輸出為 PredictionSignal
  - 產出：`src/btc_predictor/strategies/xgboost_direction/strategy.py` 繼承 BaseStrategy
  - 驗收：輸出符合 PredictionSignal 介面

#### 1.3 N-BEATS Perceiver

- [ ] **1.3.1** Clone 原始 repo + 環境搭建
  - 來源：https://osf.io/fjsuh/
  - 驗收：原始模型可在本地 inference
- [ ] **1.3.2** 改造為 BTC 單幣種方向分類
  - 產出：`src/btc_predictor/strategies/nbeats_perceiver/` 模組
  - 驗收：4 個時間框架 DA 報告
- [ ] **1.3.3** 統一輸出為 PredictionSignal
  - 驗收：輸出符合 PredictionSignal 介面

#### 1.4 (Optional) freqtrade + FreqAI

- [ ] **1.4.1** freqtrade 環境搭建 + 配置學習
- [ ] **1.4.2** FreqAI 預測信號提取
- [ ] **1.4.3** 統一輸出為 PredictionSignal

#### 1.5 Phase 1 回測報告

- [ ] **1.5.1** 統一回測框架：walk-forward 驗證
  - 產出：`scripts/backtest.py`
- [ ] **1.5.2** 各策略 × 4 個時間框架回測報告
  - 驗收：DA、Sharpe Ratio、樣本內 vs 樣本外表現

---

### Phase 2：模擬倉系統 (目標 3–4 週)

#### 2.1 模擬倉引擎

- [ ] **2.1.1** SimulatedTrade 引擎核心邏輯
  - 產出：`src/btc_predictor/simulation/engine.py`
- [ ] **2.1.2** 風控模組
  - 產出：`src/btc_predictor/simulation/risk.py`
- [ ] **2.1.3** WebSocket 即時監聽 + 策略觸發
  - 產出：`src/btc_predictor/data/pipeline.py` (WebSocket 部分)
- [ ] **2.1.4** 到期結算回填邏輯
  - 驗收：到期時自動回填 close_price、result、pnl

#### 2.2 統計監控

- [ ] **2.2.1** 統計計算模組
  - 產出：`src/btc_predictor/simulation/stats.py`
  - 指標：DA、累計 PnL、Sharpe、最大連敗、信心度校準
- [ ] **2.2.2** 每日自動統計報告 (JSON + CLI)
- [ ] **2.2.3** 信心度校準分析

#### 2.3 多模態特徵增強（逐步加入）

- [ ] **2.3.1** Fear & Greed Index 接入
- [ ] **2.3.2** DXY 美元指數接入
- [ ] **2.3.3** CryptoBERT 情緒 (如 VRAM 允許)

#### 2.4 收斂決策

- [ ] **2.4.1** 累積 ≥ 200 筆模擬交易
- [ ] **2.4.2** 過擬合檢測 (walk-forward vs 樣本外)
- [ ] **2.4.3** 確定進入 Phase 3 的策略 × 時間框架組合

---

### Phase 3：Discord Bot + 手動下單驗證 (目標 2–3 週)

- [ ] **3.1.1** Discord Bot 基礎架構 (discord.py)
- [ ] **3.1.2** 訊號推送格式實作
- [ ] **3.1.3** `/stats` `/pause` `/resume` 指令
- [ ] **3.1.4** `/record win|lose` 真實結果記錄
- [ ] **3.2.1** RealTrade 記錄 + 滑價分析
- [ ] **3.2.2** 累積 ≥ 50 筆真實交易
- [ ] **3.2.3** 真實 vs 模擬勝率對比報告

---

## Completed

_（Agent 完成任務後移到這裡，附日期和關鍵產出）_

- [x] **1.1.1** 初始化專案結構與環境搭建 (2025-02-12)
  - 產出：`pyproject.toml`, `.python-version`, `src/btc_predictor/`, `TA-Lib` (C Library + Python Wrapper)
  - 環境：Python 3.12, uv, pandas, torch, xgboost, lightgbm, TA-Lib, shap, etc.


---

## In Progress

_（Agent 正在處理的任務）_

---

## Known Issues / Discussion

_（Agent 發現的問題、需要人類決策的事項）_

<!-- 範例：
- ⚠️ Binance WebSocket 在 1m K 線高頻下偶爾斷線，需加 reconnect + 指數退避
- ❓ N-BEATS Perceiver 原始 repo 使用 TensorFlow，是否改用 PyTorch 重寫或直接用 TF？
-->

---

## Key Metrics

_（Agent 跑完回測/模擬後更新數字）_

| 策略 | 時間框架 | DA (方向準確率) | Sharpe | 樣本數 | 驗證方式 | 日期 | 備註 |
|------|---------|----------------|--------|--------|---------|------|------|
| — | — | — | — | — | — | — | 尚無數據 |