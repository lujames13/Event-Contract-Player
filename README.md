# Event-Contract-Player
## 目標
程式化預測 Binance Event Contract 方向，累積 200+ 筆模擬交易驗證後，透過 Discord Bot 通知手動下單。

## 核心挑戰
**Event Contract 的二元預測任務**: 預測「N 分鐘後收盤價是否高於開盤價」，與傳統價格預測/回歸任務本質不同。

## 盈虧平衡要求
- **10分鐘**: 賠率 1.80 → 勝率需 >55.6% (閾值 0.606)
- **30分鐘**: 賠率 1.85 → 勝率需 >54.1% (閾值 0.591)
- **60分鐘**: 賠率 1.85 → 勝率需 >54.1% (閾值 0.591)
- **1天**: 賠率 1.85 → 勝率需 >54.1% (閾值 0.591)

> 信心度低於閾值的預測不下注

## 開發策略：MVP-First 深度優先

**設計原則變更 (2025-02-14)**: 從「先做完所有模型」改為「用一個模型打通全鏈路」
- 目的：儘早驗證端到端可行性
- Phase 1: XGBoost 基線模型
- Phase 1.5: 回測框架 + 模擬倉 + Discord Bot (XGBoost 跑通)
- Phase 2: 水平擴展 (N-BEATS, FreqAI, 多模態特徵)
- Phase 3: 真實交易驗證

## 當前狀態 (2025-02-14)

### ✅ 已完成
- 專案結構與環境 (Python 3.12 + uv)
- Binance 歷史數據抓取 + SQLite 儲存
- **Event Contract Label 生成邏輯** (核心差異點)
- **XGBoost 特徵工程** (OHLCV + 技術指標)
- **XGBoost 模型訓練** + 三時間框架模型產生
- **BaseStrategy 介面** + PredictionSignal 輸出
- **風控模組** (動態下注 + 停損機制)
- **Walk-forward 回測引擎** (防止前視偏差)
- **Discord Bot 骨架** (指令系統 + 訊息發送)
- **即時運行框架** (WebSocket + 模型載入)

### 🔄 進行中
- Phase 1.6: 端到端驗證 (即時預測 1 小時無崩潰運行)

### 📋 下一步
- 72 小時壓力測試 → Phase 2 水平擴展

## 技術棧

### 預測模型
- **XGBoost**: 方向分類 (所有時間框架)
- **N-BEATS Perceiver** (Phase 2): 基於 ICLR 論文的時序預測
- **FreqAI** (Phase 2): 生產級交易框架的信號提取
- **CryptoBERT** (Phase 2): 情緒分析 (inference only, 2GB VRAM)

### 特徵工程
- **技術指標**: RSI, MACD, Bollinger Bands, ATR (ta-lib)
- **多模態** (Phase 2): Fear & Greed Index, DXY 美元指數, 鏈上數據
- **特徵選擇** (Phase 2): Boruta + SHAP 可解釋性

### 基礎設施
- **數據**: Binance WebSocket + REST API → SQLite (WAL mode)
- **回測**: Walk-forward 驗證 (7 fold, 每折 ~1.5 年)
- **風控**: 凱利公式 + 動態下注 (5-20 USDT)
- **通知**: Discord Bot (半自動交易)

### 數據流
```
WebSocket (即時) → SQLite → 特徵工程 → XGBoost → 風控檢查 → Discord 通知
                    ↑
              REST API (歷史回補)
```

## 風險管理
- 下注範圍: 5-20 USDT (信心度線性映射)
- 每日最大虧損: 50 USDT
- 連敗保護: 8 筆連敗 → 暫停 1 小時
- 每日交易上限: 30 筆

## 硬體約束
- GPU VRAM < 8GB (排除大型 Transformer 微調)
- 推理延遲 < 1 秒 (高頻交易要求)

## 關鍵約束與決策
- **無官方 API**: Binance Event Contract 無程式化下單 API
- **Label 生成**: 核心邏輯已實現，所有模型共用
- **評估指標**: 方向準確率 (DA) 優先於 RMSE/MAE
- **驗證方法**: Walk-forward 防止前視偏差

## 文檔結構
- `AGENTS.md`: AI agent 開工指南
- `PROGRESS.md`: **進度追蹤 (Single Source of Truth)**
- `DECISIONS.md`: 不可變技術決策
- `ARCHITECTURE.md`: 系統架構 + 介面契約
- `ROADMAP.md`: 高層規劃參考

## 未來方向
策略穩定後，計畫透過 Android 模擬器 UI 自動化實現全自動下單 (Phase 3 之後另行規劃)。