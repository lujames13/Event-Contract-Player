# Event-Contract-Player

## 目標
程式化預測 Binance Event Contract 方向，透過多策略 Live 驗證與統計顯著（各策略 200+ 筆交易）後，透過 Discord Bot 進行即時預測與自動化訊號推送，最終實現手動或自動下單。

## 核心挑戰
**Event Contract 的二元預測任務**: 預測「N 分鐘後收盤價是否高於開盤價」，與傳統價格預測/回歸任務本質不同。

## 盈虧平衡要求
| Timeframe | 賠率 | 盈虧平衡勝率 | 信心度下注閾值 (+5% 邊際) |
|-----------|------|--------------|---------------------------|
| 10 分鐘   | 1.80 | 55.6%        | 0.606                     |
| 30 分鐘   | 1.85 | 54.1%        | 0.591                     |
| 60 分鐘   | 1.85 | 54.1%        | 0.591                     |
| 1 天      | 1.85 | 54.1%        | 0.591                     |

> 信心度低於閾值的預測不建議下注。

## 開發策略：Gate-based 推進 (2026-02-15 起)

1. **Gate 0: 基礎設施就緒** — ✅ **PASSED** (2026-02-14)
2. **Gate 1: 模型實驗池成熟** — ✅ **PASSED** (2026-02-17)
3. **Gate 2: Live 系統 + 多模型同步驗證** — 🔄 **ACTIVE** (當前階段)
4. **Gate 3: 模擬交易統計顯著** — ⏳ 待進入
5. **Gate 4: 真實交易驗證** — ⏳ 待進入

## 當前狀態 (2026-02-18)

### ✅ 已完成
- **基礎設施**: `uv` 環境、Binance 數據管線、SQLite (WAL mode)。
- **回測引擎**: 支援平行化處理的 Walk-forward 回測，驗證防止前視偏差。
- **多模型架構**: 支援 XGBoost, LightGBM, CatBoost 同時運行。
- **Gate 1 達成**: `lgbm_v2` (60m) DA 54.99%, `catboost_v1` (10m) DA 56.56% 通過 OOS 驗證。
- **Live Pipeline MVP**: 多策略同時載入、WebSocket 即時推理、非同步效能優化。
- **Discord Bot UX**: 支援 `/help`, `/predict`, `/stats`, `/models` 指令，具備 Autocomplete 與 Choice 下拉選單。
- **自動通知**: 具備即時預測信號推送與結算結果反饋功能。

### 🔄 進行中
- **Gate 2 Phase 2**: Discord Bot 智慧指令優化與系統穩定性監測。
- **數據累積**: 累積各模型 Live 運行下的模擬交易數據（目標每組合 ≥ 200 筆）。

### 📋 下一步
- 實作 Ensemble / Stacking 模型。
- 72 小時穩定性監控與系統錯誤隔離強化。

## 技術棧

### 預測模型
- **Tree-based**: XGBoost, LightGBM, CatBoost (目前主力，已穩定)。
- **Neural**: MLP (目前 DA ~50%, 迭代中)。
- **Future**: N-BEATS, Ensemble / Stacking (Gate 2 後期計畫)。

### 特徵工程
- **技術指標**: RSI, MACD, Bollinger Bands, ATR (ta-lib)。
- **高階特徵**: 時間循環編碼、波動率特徵、成交量動能。
- **多模態 (Planned)**: CryptoBERT 情緒分析、Fear & Greed Index、DXY 指數。

### 基礎設施
- **語言**: Python 3.12 + `uv`
- **數據**: Binance WebSocket (即時) + REST API (補洞/歷史)
- **資料庫**: SQLite (WAL 模式，支援高併發讀取)
- **通知**: Discord Bot (Slash Commands + Rich Embeds)

## 數據流
```
[WebSocket Market Data] ──▶ [SQLite Data Pipeline] ──▶ [Feature Engineering]
                                                            │
    ┌───────────────────────────────────────────────────────┘
    ▼
[Strategy Registry] ──▶ [Multi-Model Inference] ──▶ [Risk Control Check] ──▶ [Discord Notification]
```

## 風險管理
- **下注範圍**: 5-20 USDT (基於信心度的線性映射)。
- **凱利公式**: 預計於 Gate 2.2 導入。
- **熔斷機制**: 
  - 每日最大虧損限制 (50 USDT)。
  - 連敗保護 (8 連敗暫停 1 小時)。
  - 每日交易筆數上限 (30 筆)。

## 硬體與性能約束
- **GPU**: NVIDIA < 8GB VRAM。
- **延遲**: 即時推理需在下一根 K 線開盤前完成 (< 1 秒)。

## 文檔導覽
- `docs/PROGRESS.md`: **單一事實來源 (SSOT)**，詳載 Gate 進度。
- `docs/MODEL_ITERATIONS.md`: 詳盡的模型實驗記錄與回測數據。
- `docs/ARCHITECTURE.md`: 系統架構定義與模組間介面契約。
- `docs/DECISIONS.md`: 關鍵技術決策日誌。
- `AGENTS.md`: Coding Agent 操作與規範守則。

---
*Last updated: 2026-02-18*