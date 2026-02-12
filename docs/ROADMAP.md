# BTC 價格預測 × Binance Event Contract — Roadmap

> **目標：** 程式化預測 BTC 價格方向，建立多策略模擬倉系統，勝率穩定後透過 Discord Bot 通知自己手動下單。
>
> **未來方向：** 策略穩定後，計畫透過 Android 模擬器 UI 自動化實現全自動下單（Phase 3 之後另行規劃）。

此文件為高層規劃參考，不需頻繁更新。任務追蹤請見 `PROGRESS.md`。

---

## Phase 1：模型選型與複製 (4–6 週)

複製 2–3 個已發表的預測策略，在本地跑通 inference，對 4 個時間框架輸出方向預測。

**策略 A — N-BEATS Perceiver（首選基線）**
- 來源：Sbrana & Lima de Castro, 2024, Computational Economics
- 開源：https://osf.io/fjsuh/
- 改造：投資組合價格回歸 → BTC 單幣種方向分類
- 預估：2 週

**策略 B — XGBoost 方向分類（輕量高效）**
- 依據：文獻 DA 81.1%（vs LSTM 48.8%）
- 特徵：OHLCV + RSI, MACD, BB, ATR + Boruta 特徵選擇
- 預估：1 週

**策略 C — freqtrade + FreqAI（生產級備選）**
- 只取預測信號，不用下單功能
- 預估：2 週（學習曲線較陡）

## Phase 2：模擬倉系統 (3–4 週)

多策略 7×24 運行模擬倉，累積 200+ 筆交易後統計分析，收斂出最佳策略 × 時間框架組合。

核心工作：模擬倉引擎、風控邏輯、統計監控、多模態特徵增強（Fear & Greed → DXY → CryptoBERT → 鏈上指標）。

## Phase 3：Discord Bot + 手動下單 (2–3 週)

**前提：** 模擬倉勝率穩定 > 盈虧平衡 + 5%。

Discord Bot 推送訊號 → 自己手動下單 → 記錄真實結果 → 比對模擬 vs 真實表現。

---

## 技術棧

Python 3.12 · uv · PyTorch · XGBoost · LightGBM · SQLite (WAL) · Binance WebSocket/REST · CryptoBERT · asyncio · discord.py · pandas · ta-lib · SHAP

---

詳細技術決策見 `DECISIONS.md`，系統架構見 `ARCHITECTURE.md`，進度追蹤見 `PROGRESS.md`。