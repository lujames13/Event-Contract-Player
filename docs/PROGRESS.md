# Project Progress

> ★ **Single Source of Truth** — Agent 每次完成任務後必須更新此文件。
>
> 📐 **設計原則 (2026-02-15 修訂)：**
> 1. **Gate-based 推進**：每個 Gate 是明確的 pass/fail 判斷點，不通過就在當前層迭代。
> 2. **模型實驗先行**：在現有 Binance OHLCV 數據上窮盡策略變體，不急於接入新數據源。
> 3. **批量比較後再 live**：累積足夠多的候選策略回測數據後，一次性進入 live 驗證。
> 4. **模型迭代獨立追蹤**：詳見 `docs/MODEL_ITERATIONS.md`。

---

## Gate Status Dashboard

| Gate | 名稱 | 狀態 | 通過條件 | 備註 |
|------|------|------|---------|------|
| **0** | 基礎設施就緒 | ✅ **PASSED** | 資料管道 + 回測引擎 + 風控 + CLI 可運行 | 2026-02-14 |
| **1** | 模型實驗池成熟 | ✅ **PASSED** | 見下方 Gate 1 細則 | `lgbm_v2` (60m) DA 54.99% |
| **2** | Live 系統 + 多模型同步驗證 | 🔄 **ACTIVE** | Gate 1 通過 | 開始實作 Ensemble / Stacking |
| **3** | 模擬交易統計顯著 | ⏳ BLOCKED | Gate 2 通過 | — |
| **4** | 真實交易驗證 | ⏳ BLOCKED | Gate 3 通過 | — |

---

## [SUSPENDED] Gate 0-2: Binance EC 開發歷程

> Binance EC 系統暫停開發，程式碼收攏至 binance/ 子目錄。
> 詳細歷史記錄保留於下方，供未來復用參考。

---

## Gate 1：模型實驗池成熟（當前焦點）

**通過條件（全部滿足）：**
- [x] ≥3 個差異化策略架構 (XGBoost, LGBM, MLP, CatBoost) 已有完整數據
- [x] 每個策略覆蓋 3 個 timeframe (10m / 30m / 60m)
- [x] 至少 1 個「策略 × timeframe」組合 OOS DA > breakeven (**lgbm_v2 60m: 54.99%, catboost_v1 10m: 56.56%**)
- [x] 該組合的 OOS PnL > 0 (**lgbm_v2 60m: +2.63, catboost_v1 10m: +18.91**)
- [x] 該組合 OOS 交易筆數 ≥ 500 (**lgbm_v2 60m: 831**) # Note: CatBoost 10m trades: 244

**Gate 1 結論 (2026-02-17 架構師判定 🟡 通過)：**
- 主要依據：lgbm_v2 60m (DA 54.99%, PnL +2.63, Trades 831)
- 觀察對象：catboost_v1 10m (DA 56.56%, PnL +18.91, Trades 244 — 未達 ≥500 筆門檻)
- Fold σ 21.84% 源自每 fold 樣本數過少 (~12 筆/fold)，非模型不穩定
- PnL margin 極薄 (每筆 +0.003 USDT)，需 live 驗證可持續性

**註記：** 1440m 因現有資料量不足以支撐有意義的 walk-forward 驗證，暫時排除。待資料累積 ≥ 3 年後重新評估。

**數據源限制：** 僅使用 Binance OHLCV（已接入）。多模態特徵（F&G, DXY, CryptoBERT）推遲到 Gate 1 通過後考慮。

**工作方式：** Coding agent 依照 `docs/MODEL_ITERATIONS.md` 自主迭代。架構師定期 review 實驗記錄。

---

## Gate 2：Live 系統 + 多模型同步驗證 (當前焦點)

**Gate 2 分階段推進：**
- **Phase 1 — G2.0 Live Pipeline MVP**: [✅] PASS (2024-02-17)
  - 多策略載入 + WebSocket 推理 + Paper trading + 累積樣本
  - Notes: SQLite WAL enabled, async offloaded, Multi-strategy verified.
- **Phase 2 — G2.1 Discord Bot 即時通知**:
  /predict, /stats 指令 + 自動信號通知 + 到期結算通知
- **Phase 3 — G2.2 Ensemble (條件性)**:
  僅在 Phase 1 確認單模型 live 表現穩定後再推進

**Phase 1 里程碑（進入 Phase 2 的前提）：**

*穩定性軌道：*
- [ ] run_live.py 可穩定運行 24 小時無崩潰

*數據累積軌道（Signal Layer）：*
- [ ] 累積 ≥ 200 筆 prediction_signals（所有策略合計，含已結算）
- [ ] 其中 ≥ 30 筆已結算 signals 信心度 ≥ 0.591（觀察高信心區的 live DA）
- [ ] 完成首次校準分析，產出 reliability diagram

*執行軌道（Execution Layer）：*
- [ ] lgbm_v2 60m 累積 ≥ 50 筆 live 模擬交易
- [ ] catboost_v1 10m 累積 ≥ 50 筆 live 模擬交易

**進入 Phase 2 的判定標準：** 穩定性軌道 + 數據累積軌道 通過即可。執行軌道為持續追蹤項目，不 block Phase 2 推進。

---

**策略架構分類：**

| 類別 | 候選模型 | 狀態 |
|------|---------|------|
| A. Tree-based | XGBoost, LightGBM, CatBoost | ✅ 已建立各模型 Baseline |
| B. Neural | MLP, N-BEATS | 🔄 MLP baseline 已完成 (DA 50%) |
| C. Ensemble / Stacking | A+B 的組合 | 🔄 準備進入實作階段 (Gate 2) |

**最新回測結果摘要**（完整記錄見 `docs/MODEL_ITERATIONS.md`）：

| 008 | **catboost_v1** | 10m | **56.56%** | 0.02 | 244 | ✅ **達標** | 2026-02-16 |
| 005 | **lgbm_v2**    | 60m | **54.99%** | 0.00 | 831  | ✅ **達標** | 2026-02-16 |
| 002 | **xgboost_v2** | 10m | **55.59%** | -0.02 | 662 | ❌ PnL < 0 | 2026-02-15 |
| 004 | **lgbm_v1**    | 60m | **54.46%** | 0.01 | 101 | ⚠️ 樣本少 | 2026-02-15 |
| 004 | **lgbm_v1**    | 30m | **54.34%** | 0.01 | 530 | ✅ PnL > 0 | 2026-02-15 |
| 006 | **lgbm_tuned** | 30m | 53.16% | -0.02 | 316 | ❌ 不達標 | 2026-02-16 |
| 005 | **lgbm_v2**    | 10m | 52.79% | -0.03 | 1991 | ❌ 不達標 | 2026-02-16 |
| 008 | **catboost_v1** | 60m | 52.51% | -0.05 | 419 | ❌ 不達標 | 2026-02-16 |
| 007 | **mlp_v1**     | (all)| ~50% | -0.07 | 15k+ | ❌ 隨機 | 2026-02-17 |
| 001 | xgboost_v1     | (all)| ~51% | -0.06 | 57k+ | ⚠️ 停滯 | 2026-02-15 |

---

## Gate 1 任務清單

- [x] **1.1.1** 補全 `xgboost_v1` 全時段 Baseline (Done)
- [x] **1.1.2** 使用擴充數據重跑 `xgboost_v2` (Done, 10m 達標)
- [x] **1.1.3** 自主迭代優化 (Ex 006, 007, 008 已完成)
- [x] **1.1.4** 信心度校準驗證 (Experiment 005 通過 Gate 1)
- [x] **1.1.5** 完成 Data Starvation 修復 (已抓取 2023-01-01 起資料)
- [x] **1.1.6** 核心優化：實作平行化回測引擎 (Parallel Walk-forward, 4-10x 加速)

---

## Gate 2：Live 系統 + 多模型同步驗證

> **前提：Gate 1 通過。**

**通過條件：**
- [ ] 所有 Gate 1 候選策略同時在 live 環境運行
- [ ] Discord Bot 互動功能就緒（詳見下方任務）
- [ ] 72 小時穩定運行無崩潰

**任務清單：**

### 2.1 Live 運行框架升級

- [x] **2.1.1** 多模型同時載入與管理 (G2.0)
  - `run_live.py` 支援從 `models/` 目錄自動掃描並載入所有可用策略
  - 每個策略獨立產生 PredictionSignal，共用 data pipeline
  - 策略 registry：動態註冊，新模型放進目錄即可被載入

- [x] **2.1.2** Live 模擬交易記錄 (G2.0)
  - 每個策略的每個 timeframe 獨立記錄 SimulatedTrade
  - SQLite 中按 strategy_name 區分
  - 支援回溯查詢每個策略的歷史表現

### 2.2 Discord Bot 互動功能

- [x] **2.2.1** `/predict [timeframe]` 指令
  - 用當前市場數據，跑所有已載入模型
  - 回傳每個模型的預測方向 + confidence
  - 格式化為 embed 訊息，直觀顯示
  - Completed: 2026-02-17

- [x] **2.2.2** `/stats [model_name]` 指令升級
  - 不指定 model_name → 顯示所有模型的摘要對比表
  - 指定 model_name → 顯示該模型的詳細統計（DA、PnL、校準、drawdown）
  - 支援按 timeframe 篩選 (Completed: 2026-02-17)

- [x] **2.2.3** `/models` 指令
  - 列出所有已載入模型
  - 顯示每個模型的回測表現摘要 + live 運行狀態

- [x] **2.2.4** 自動通知系統 (Completed: 2026-02-18)
  - 當任何策略 confidence > threshold 時，自動發送「準備下單」通知
  - 包含：策略名稱、方向、confidence、timeframe、當前價格
  - 到期時自動發送結果通知：是否獲勝 + PnL

- [x] **2.2.5** `/help` 指令 + Slash Command UX 改善 (G2.1.5)
  - timeframe 改用 Choice，model 改用 autocomplete
  - Completed: 2026-02-18 (Fix: NameError 'time' and test regressions)

### 2.3 系統穩定性

- [x] **2.3.1** WebSocket 斷線自動重連（含指數退避） (G2.0)
- [x] **2.3.2** 錯誤隔離：單一策略 exception 不影響其他策略運行 (G2.0)
- [x] **2.3.3** 健康檢查 endpoint 或 Discord `/health` 指令

### 2.4 數據基礎設施

- [x] **2.4.1** Signal Layer 實作 (G2.2.0)
  - 新增 `prediction_signals` DB 表
  - Pipeline 在每次 predict 後無條件寫入 signal
  - Signal settler 定期結算所有未結算 signal 的 actual_outcome
  - 不動現有 simulated_trades 流程

- [x] **2.4.2** 校準分析工具 (G2.2.1)
  - `scripts/analyze_calibration.py`：分桶分析 + reliability diagram
  - 依賴 Signal Layer 累積 ≥ 100 筆已結算 signal 後才有意義
  - Completed: 2026-02-19

---

## [COMPLETED] Gate 2.5: Polymarket Feasibility Study

**狀態：** ✅ COMPLETED

**動機：** Polymarket 提供完整 CLOB API，解決 Binance EC 無 API 的自動化瓶頸。動態賠率創造方向預測以外的獲利維度。但台灣被列為 close-only 限制地區，需要先解決存取問題再評估 edge 是否可操作。

**關鍵背景（2026-02 調查結果）：**
- 台灣在 Polymarket 的限制等級為 **close-only**（可關倉、不可開倉），非完全封鎖
- CLOB API `/order` 端點會校驗 IP，從受限地區提交的訂單會被直接拒絕
- Public read-only API（Gamma API、order book 查詢）的 geoblock 狀態尚未確認
- 5m BTC prediction market 已於 2026 年 2 月上線，使用 Chainlink oracle 自動結算
- 台灣曾在 2024 年起訴一名使用 Polymarket 下注政治選舉的用戶（約 $530 USD）

**設計原則：**
- PM-0 是 blocker gate：不通過則整個調查終止
- 純調查研究，不寫交易邏輯
- 所有 data collector 腳本放在 `scripts/polymarket/`
- 所有報告放在 `reports/polymarket/`
- 不修改現有 Binance EC 系統的任何程式碼

**Gate 2.5 推進流程：**

PM-0: Access & Legal Feasibility（BLOCKER）
  - [x] PM-0.1: Public API 存取測試（台灣 IP）
  - [x] PM-0.2: VPS Relay 可行性測試
  - [x] PM-0.3: 台灣法規風險評估
  - [x] PM-0.4: E2E Architecture Latency
  → Go/No-Go 決策點（由架構師判定）

PM-1 ~ PM-7:（PM-0 通過後才展開）
  - [x] PM-1: Market Structure & Lifecycle
  - [x] PM-2.1: Chainlink Oracle 靜態規格
  - [ ] PM-2.2: Binance vs Chainlink 動態偏差分析（需 48h 數據收集）
  - [x] PM-4: Fee Structure 完整拆解
  - [x] PM-5: Market Implied Probability Calibration
  - [x] PM-3-lite: Order Book Spread Snapshot (2-4h baseline)
  - [x] PM-6: Model Alpha Baseline (精簡版，含 PM-6.1 + PM-6.5 觀測)
  - [~] PM-3: Order Book Depth & Liquidity → 精簡為 PM-3-lite
  - [~] PM-6: 獲利模式可行性 → 精簡為 Model Alpha Baseline
  - [ ] PM-7: Engineering Integration Plan

Gate 2.5 完成條件（全部 Study 完成後由架構師判定）：
  - [ ] PM-0 ~ PM-7 全部產出報告
  - [ ] 架構師根據報告決定：🟢 正式轉移 / 🟡 部分整合 / 🔴 放棄

---

## Gate 3: Polymarket MVP

**通過條件：**
- [ ] 至少 1 個 timeframe 的模型 walk-forward DA > 52%（maker breakeven + 安全邊際）
- [ ] Paper trading 200+ 筆（可跨 timeframe 合計），alpha-filtered 正 PnL
- [ ] 72 小時 pipeline 穩定運行

### 3.0 遷移與重組
- [x] 3.0.1 核心文件遷移（DECISIONS / ARCHITECTURE / PROGRESS / constants / AGENTS.md）
- [x] 3.0.2 目錄結構重組（Binance 收攏、Polymarket 新目錄）

### 3.1 Polymarket 基礎設施
- [x] 3.1.1 Gamma API client + CLOB read-only client
- [x] 3.1.2 Market lifecycle tracker（偵測當前 5m market）
- [x] 3.1.3 Label 邏輯修改（>= 結算條件，平台參數化）
- [x] 3.1.4 SQLite schema migration（pm_markets, pm_orders）

### 3.2 模型訓練（多 timeframe 探索）
- [x] 3.2.1 Feature engineering（reuse Binance 1m OHLCV + PM market features，timeframe-agnostic）
- [x] 3.2.2 pm_v1 訓練（CatBoost 基礎，>= 結算，5m/15m/1h/4h/1d 全跑）
- [x] 3.2.3 Walk-forward 回測 × 每個 timeframe（PM 結算條件 + fee 模型）
- [x] 3.2.4 Alpha 分析 × 每個 timeframe（model vs market price，找出最佳 timeframe-model 組合）

### 3.3 模擬交易驗證
- [x] 3.3.1 Paper trading pipeline（signal + 模擬 maker order）
- [x] 3.3.2 Discord Bot 適配（/predict 顯示 alpha，/stats 適配 PM PnL）
- [ ] 3.3.3 累積 200+ 筆 → 統計顯著性驗證

### 3.4 分析系統（四模組架構，實盤前磨練）

> 設計原則：固定計算歸固定腳本，需要判斷的歸 agent skill。
> 數據合約（metrics.json）是全系統 pivot point，上游計算、下游消費都通過它解耦。

**模組 1+2：數據萃取 + 指標引擎**
- [x] 3.4.1 `analytics/extractors.py` — 從 SQLite 拉數據轉 DataFrame（純函數）
- [x] 3.4.1 `analytics/metrics.py` — DA、PnL、drawdown、alpha、校準等指標計算（純函數，DataFrame in → dict out）
- [x] 3.4.1 `scripts/polymarket/compute_metrics.py` — CLI 腳本，跑全部計算，輸出 `metrics.json`

**模組 3：報告產出器**
- [x] 3.4.2 `scripts/polymarket/generate_report.py` — 讀 `metrics.json`，render 成 Markdown 報告

**模組 4：Analyst Agent Skill**
- [x] 3.4.3 Diagnostic skill — 讀 `metrics.json`，回答「發生什麼」（drift、異常、regime）
- [x] 3.4.3 Recommendation skill — 基於診斷 + DECISIONS.md 約束，建議行動方案

**模型改進（依分析結果驅動）**
- [x] 3.4.4 模型迭代改進（pm_v1 baseline 排錯與重測已完成，各模型正常運作）
- [ ] 3.4.5 多策略 Ensemble（如有多個有效模型，嘗試加權組合）
- [ ] 3.4.6 信心度校準重新分析（累積足夠 signal 後重跑 reliability diagram）

---

## Gate 4: Polymarket Live Trading

> **G4.2 探索結論 (2026-02-27)：** Webshare Japan Proxy 完美穿越 geoblock，
> 本地可直接與 Polymarket L2 API 互動。原定 GCP VPS 架構全部取消。

### 4.1 交易基礎設施
- [x] ~~4.1.1 GCP Tokyo VPS 部署 + Polygon wallet + USDC 入金~~ → **取消**（Proxy 方案取代）
- [x] 4.1.2 CLOB API trading client（EIP-712 簽名 + Proxy Wallet 認證 + derive_api_key） → **完成** (G4.1 + G4.2)
- [x] ~~4.1.3 VPS ↔ 本地通訊機制~~ → **取消**（本地直連，無需通訊機制）
### 4.2 Order Management
- [ ] 4.2.1 Maker order placement + fill monitoring
- [ ] 4.2.2 Position management + PnL settlement
### 4.3 驗證
- [ ] 4.3.1 小額實盤（$10/trade × 50 trades）
- [ ] 4.3.2 真實 vs 模擬績效對比 + slippage 分析

---

## Gate 5: 規模化
- [ ] 5.1 Position sizing 優化
- [ ] 5.2 多策略並行（pm_v2 等新模型架構）
- [ ] 5.3 Advanced order types（GTD, 動態 repricing）

---

## 已完成項目（Completed Archive）

### Gate 0: 基礎設施（2026-02-12 ~ 2026-02-14）

**環境建設**
- [x] `uv init` 初始化專案 + 目錄結構 + `project_constants.yaml` (2026-02-12)
- [x] Binance REST API 歷史數據抓取 (2026-02-12)
  - 產出：`scripts/fetch_history.py`, `src/btc_predictor/infrastructure/store.py`
- [x] SQLite schema 建立 + 讀寫工具 (2026-02-12)
  - 產出：`src/btc_predictor/infrastructure/store.py`, `tests/test_store.py`

**核心模組**
- [x] Event Contract label 生成邏輯 (2026-02-14)
  - 產出：`src/btc_predictor/infrastructure/labeling.py`
  - 平盤 (close == open) 視為 lose
- [x] 特徵工程：OHLCV + 技術指標 (2026-02-14)
  - 產出：`src/btc_predictor/strategies/xgboost_direction/features.py`
  - 特徵：returns, volatility, RSI, MACD, BB, ATR, 時間編碼, 成交量
- [x] XGBoost 模型訓練邏輯 (2026-02-14)
  - 產出：`src/btc_predictor/strategies/xgboost_direction/model.py`
- [x] BaseStrategy 介面 + PredictionSignal 輸出 (2026-02-14)
  - 產出：`src/btc_predictor/strategies/base.py`, `src/btc_predictor/models.py`
  - 含 `fit()` 和 `predict()` 抽象方法

**回測 & 風控**
- [x] 風控核心邏輯 (2026-02-14)
  - 產出：`src/btc_predictor/simulation/risk.py`
  - should_trade + calculate_bet，從 project_constants.yaml 讀取
- [x] Walk-forward 回測引擎 (2026-02-14)
  - 產出：`src/btc_predictor/backtest/engine.py`
- [x] 回測統計計算 (2026-02-14)
  - 產出：`src/btc_predictor/backtest/stats.py`
- [x] 回測 CLI 入口 + 報告生成 (2026-02-14)
  - 產出：`scripts/backtest.py`, `reports/`
- [x] 模型訓練腳本 (2026-02-14)
  - 產出：`scripts/train_xgboost_model.py`

**即時系統骨架**
- [x] WebSocket 即時數據管道 (2026-02-14)
  - 產出：`src/btc_predictor/infrastructure/pipeline.py`
- [x] Discord Bot 基礎架構 (2026-02-14)
  - 產出：`src/btc_predictor/discord_bot/bot.py`
- [x] 即時運行入口 (2026-02-14)
  - 產出：`scripts/run_live.py`

---

## Known Issues / Discussion

- ⚠️ **信心度校準反轉**：XGBoost baseline 的 confidence 0.9+ 勝率僅 38.7%，比 0.6-0.7 的 52.9% 還低。
  高 confidence 反而是反向指標。需要在 MODEL_ITERATIONS 中優先解決。
- ⚠️ **Event Contract open price 新規則 (2026-01-28)**：open price 現在是下單後「下一秒」的 index price。
  模擬時存在系統性偏差，需在 Gate 4 真實交易中追蹤。
- ❓ **backtest engine 中 `lower` 方向的勝負判定**：目前 `is_win = close_price <= open_price`，
  但 Event Contract 規則中平盤對 lower 同樣是 lose。應改為 `is_win = close_price < open_price`。
  ✅ **已在 G2.0.0 修正 `settler.py`，回測引擎 `engine.py` 已在 G1.0.2 修正。**