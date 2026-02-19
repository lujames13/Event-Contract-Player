# Technical Decisions (Immutable)

> ⚠️ **Agent 注意：不要修改此文件。** 如有疑問，寫入 `PROGRESS.md` 的 Discussion 區塊。

本文件記錄所有已確認的技術決策。每條決策附帶 rationale，讓 agent 理解「為什麼」而非只是「是什麼」。

---

## 1. Runtime 環境

| 決策 | 值 | Rationale |
|------|-----|-----------|
| GPU | NVIDIA < 8GB VRAM | 開發機硬體限制，排除大型 Transformer 微調 |
| 資料庫 | SQLite (WAL mode) | 單人使用，無需 PostgreSQL；WAL 提升併發讀取 |
| 語言 | Python 3.12 | 鎖定版本，確保環境一致 |
| 套件管理 | uv (pyproject.toml + uv.lock) | 現代標準，取代 pip + requirements.txt |
| 專案 layout | src layout (`src/btc_predictor/`) | uv init 預設，避免 import 衝突 |
| ML 框架 | PyTorch 優先 | N-BEATS Perceiver 基於 PyTorch；XGBoost/LightGBM 為補充 |
| 技術指標 | ta-lib (C binding) | 需預裝 TA-Lib C library，人類負責處理 |

## 2. Event Contract 規格

這是 Binance Event Contract 的產品規格，非我們的選擇，不可更改。

| 參數 | 值 | 說明 |
|------|-----|------|
| 時間框架 | 10m, 30m, 60m, 1440m | 四個到期時間全部嘗試，Phase 2 用數據收斂 |
| Payout ratio (10m) | 1.80 | 贏時獲得 bet × 1.80 |
| Payout ratio (30m/60m/1d) | 1.85 | 贏時獲得 bet × 1.85 |
| 最低下注 | 5 USDT | — |
| 方向 | higher / lower | 二元分類問題 |

**盈虧平衡勝率** = 1 / payout_ratio：
- 10m: 55.56%
- 30m / 60m / 1d: 54.05%

## 3. 信心度閾值

基於盈虧平衡勝率 + 5% 安全邊際，低於閾值的預測**不下注**：

| 時間框架 | 盈虧平衡 | 閾值 (+ 5%) |
|----------|---------|-------------|
| 10m | 55.56% | **0.606** |
| 30m | 54.05% | **0.591** |
| 60m | 54.05% | **0.591** |
| 1440m | 54.05% | **0.591** |

Rationale: 5% 安全邊際補償模型在樣本外的表現衰減。10m 門檻更高因為 payout 較差。

#### 閾值調整記錄

**2026-02-20 — catboost_v1 (10m) 閾值調整**

- **舊閾值：** 0.606
- **新閾值：** 0.52
- **調整依據：** 174 筆已結算 live prediction signal 的校準分析
- **根本原因：** catboost_v1 為欠校準（underconfident）模型，信心度集中在 [0.50, 0.54) 區間但實際正確率 58-73%。原閾值 0.606 超出模型信心度分佈的 99th percentile，幾乎封鎖所有 signal。
- **數據支撐：**
  - 閾值 0.52：E[PnL/day] = +43.15，Accuracy 61.17%，Signal 數 80.6/天（174 筆樣本）
  - 時間窗口演化：線性斜率 +0.76%/window，判定穩定，無 concept drift
- **lgbm_v2 (60m) 維持不變：** 僅 28 筆樣本，統計信心不足，待累積至 ≥ 100 筆後重新評估
- **下一次評估時機：** catboost_v1 累積 ≥ 500 筆已結算 signal 後重跑校準分析

## 4. 風控參數

| 參數 | 值 | Rationale |
|------|-----|-----------|
| 下注範圍 | 5–20 USDT | 單筆風險可控，信心度線性映射 |
| 信心度→下注 | 線性：閾值→5, 1.0→20 | 簡單透明，避免過度槓桿 |
| 每日最大虧損 | 50 USDT | 達到即當日停止 |
| 最大連敗暫停 | 連敗 8 筆 → 暫停 1 小時 | 防止 tilt |
| 每日最大交易數 | 30 | 硬上限，避免過度交易 |

## 5. 模擬倉要求

| 參數 | 值 | Rationale |
|------|-----|-----------|
| 觸發方式 | 持續監聽 WebSocket | 非定時排程，策略隨時可觸發 |
| 最低交易筆數 | 200 | 累積足夠樣本才進入 Phase 3 |
| Phase 3 門檻 | 勝率 > 盈虧平衡 + 5% 安全邊際 | 模擬倉穩定盈利才值得真金白銀 |

## 6. 設計原則

- **方向準確率 (Directional Accuracy) 是第一優先指標**，RMSE/MAE 僅作輔助參考。所有模型評估以 DA 為主。
- **Walk-forward 驗證**：回測必須使用 walk-forward，禁止簡單 train/test split，防止前視偏差。
- **策略獨立性**：每個策略是獨立模組，共用 data pipeline，但 inference 和特徵工程互不干擾。
- **統一輸出**：所有策略必須輸出 `PredictionSignal`（定義見 `ARCHITECTURE.md`）。
- **Discord Bot 僅自用**：無需多用戶隔離、權限管理。

## 7. 數據記錄原則

| 決策 | 值 | Rationale |
|------|-----|-----------|
| 預測信號記錄 | 全量記錄（不論信心度） | Signal Layer 提供模型校準、閾值優化、drift 偵測的完整數據 |
| 信心度閾值作用 | 僅控制 Execution Layer（是否產生 SimulatedTrade） | 閾值是交易決策，不是數據採集決策 |
| Signal 結算 | 所有 signal 都結算 actual_outcome | 即使不下注的預測也需要知道對錯，用於校準分析 |

**兩層數據模型：**
- **Signal Layer**（`prediction_signals` 表）：每次 `strategy.predict()` 被呼叫就寫入一筆，無條件。用於校準分析、閾值優化、concept drift 偵測。
- **Execution Layer**（`simulated_trades` 表）：僅信心度 ≥ 閾值且通過風控的預測才產生。用於 PnL 計算、資金管理。