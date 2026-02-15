# Task Spec G1.1 — Baseline 補全與自主迭代啟動

> **Gate:** 1（模型實驗池）
> **優先級:** 🟡 High — Gate 1 的核心工作
> **前置條件:** G1.0 完成（Registry 可用、bug 已修、文件已替換）

---

## 目標

1. 補跑 xgboost_v1 在 30m / 60m / 1440m 的回測，建立完整的 4-timeframe baseline
2. 進入自主迭代模式：依照 `docs/MODEL_ITERATIONS.md` 的規則，持續改進模型直到達到收斂標準或觸發停止條件

---

## 子任務

### G1.1.1 — 補跑 xgboost_v1 baseline（30m / 60m / 1440m）

**步驟：**

1. 確認資料庫中有足夠的歷史數據：
   - 30m/60m 回測需要 1m K 線數據
   - 1440m (1d) 回測需要 1h 或 1d K 線數據
   - 如果數據不足，先執行 `uv run python scripts/fetch_history.py --symbol BTCUSDT --intervals 1m,1h,1d` 補資料

2. 訓練並回測每個 timeframe：
   ```bash
   for tf in 30 60 1440; do
     uv run python scripts/train_model.py --strategy xgboost_v1 --timeframe $tf
     uv run python scripts/backtest.py --strategy xgboost_v1 --timeframe $tf
   done
   ```

3. **重跑 10m**（因為 G1.0.2 修復了平盤 bug，原始結果需要更新）：
   ```bash
   uv run python scripts/train_model.py --strategy xgboost_v1 --timeframe 10
   uv run python scripts/backtest.py --strategy xgboost_v1 --timeframe 10
   ```

4. 將結果填入 `docs/MODEL_ITERATIONS.md` 的 Experiment 001 表格

**1440m 的特殊注意事項：**
- 1d timeframe 的訓練樣本數會遠少於分鐘級（每天只有一個樣本）
- 確認 walk-forward 的 train_days 和 test_days 對 1d 是否合理。如果 train_days=60 對 1d 來說只有 60 個樣本，可能需要調大到 365 天
- 如果樣本數不足以支撐有意義的回測（< 100 筆 OOS 交易），在 MODEL_ITERATIONS 中記錄此限制，不算實驗失敗

**驗收：**
1. `reports/` 目錄下有 4 個新的回測報告 JSON
2. `docs/MODEL_ITERATIONS.md` 的 Experiment 001 表格有 4 個 timeframe 的完整數據
3. `docs/PROGRESS.md` 的 Gate 1 回測結果摘要表已更新

**不要做的事：**
- 不要修改回測引擎的參數（train_days, test_days）除非 1440m 有上述樣本數問題
- 不要修改特徵工程或模型超參數（這是 baseline，後續實驗才改）

---

### G1.1.2 — 自主迭代（持續性任務）

**這是一個開放式任務。** 完成 G1.1.1 後，agent 根據 `docs/MODEL_ITERATIONS.md` 中的規則進入自主迭代模式。

**工作流程：**

```
讀 MODEL_ITERATIONS.md 最新實驗結果
  ↓
分析問題（校準反轉？DA 太低？哪些特徵沒用？）
  ↓
選擇改進方向（從清單中選 or 自行提出）
  ↓
寫下假設 → 實作修改 → 跑回測（4 timeframe）→ 記錄結果
  ↓
比較是否改善 → 決定下一步
```

**每輪實驗必做的事：**

1. 在 `docs/MODEL_ITERATIONS.md` 新增 Experiment N+1 區塊，寫下：
   - 假設（為什麼這個改進可能有效）
   - 修改內容（具體改了什麼程式碼）
   - 預期影響（預期哪個指標會改善）

2. 跑 4 個 timeframe 的 walk-forward 回測

3. 記錄結果到 Experiment 區塊的結果表格

4. 更新 Scoreboard（按 DA 排序）

5. 更新 `docs/PROGRESS.md` 的 Gate 1 回測結果摘要表

**如果改進涉及新策略架構：**

1. 在 `src/btc_predictor/strategies/` 下建立新目錄（例如 `lgbm_v1/`）
2. 實作 `strategy.py` 繼承 BaseStrategy
3. 確保 StrategyRegistry 可以自動發現
4. 新增對應的 pytest 測試

**停止條件（三者觸發任一即停）：**

1. ✅ **成功**：任何「策略 × timeframe」組合的 OOS DA > breakeven，且信心度校準不反轉
   → 在 PROGRESS.md 標記 Gate 1 候選，繼續優化其他組合或停下等架構師 review

2. 🛑 **瓶頸**：連續 3 輪實驗所有 timeframe 的 DA 都沒有提升
   → 在 MODEL_ITERATIONS.md 的 Discussion 區記錄瓶頸分析，停止等架構師 review

3. 🐛 **基礎設施問題**：發現回測引擎、label 邏輯、或 data pipeline 有 bug
   → 在 PROGRESS.md Known Issues 記錄，停止模型實驗等修復

**不要做的事：**
- 不要修改 `docs/DECISIONS.md` 或 `config/project_constants.yaml`
- 不要修改 `BaseStrategy` 介面（如需要，記錄在 Known Issues）
- 不要修改回測引擎核心邏輯（`backtest/engine.py` 的 walk-forward 流程）
- 不要修改風控邏輯（`simulation/risk.py`）
- 不要引入需要新數據源的特徵（F&G, DXY, CryptoBERT 等）— 只用 Binance OHLCV
- 不要嘗試需要 > 8GB VRAM 的模型
- 不要在單次實驗中同時改多個變數（一次只改一個，才能歸因效果）

---

## 建議的前 3 輪實驗方向

> 這是建議，agent 可以根據 Experiment 001 的結果自行調整。

**Experiment 002：修復 XGBoost 過擬合（訓練流程改進）**
- 假設：目前訓練沒用 validation set 做 early stopping，導致過擬合
- 修改：在 walk-forward 的 train window 內切出 20% 作為 validation set，用 early stopping
- 可能額外加入：purged gap（train 和 test 之間留 timeframe_minutes 的 gap 避免 label leakage）
- 預期：信心度校準改善，高 confidence 不再反轉

**Experiment 003：特徵選擇（Boruta 或 SHAP-based）**
- 假設：目前 ~40 個特徵中有大量噪音，XGBoost 過擬合於噪音特徵
- 修改：用 Boruta 或 SHAP importance 排名，只保留顯著特徵
- 預期：減少過擬合，OOS DA 提升

**Experiment 004：LightGBM 對比**
- 假設：LightGBM 的 leaf-wise 生長策略可能更適合此類數據
- 修改：新建 `lgbm_v1/` 策略，用與 xgboost_v1 相同的特徵集
- 預期：建立跨架構的對比基線

---

## 修改範圍

**G1.1.1（封閉範圍）：**
- `docs/MODEL_ITERATIONS.md`（更新 Experiment 001 結果表）
- `docs/PROGRESS.md`（更新 Gate 1 摘要表）
- `reports/`（新增 4 個回測報告）

**G1.1.2（開放範圍，但有邊界）：**
- 可以新增：`src/btc_predictor/strategies/` 下的新策略目錄
- 可以修改：`src/btc_predictor/strategies/xgboost_v1/` 下的檔案（建新版本時複製為新目錄更佳）
- 可以新增：`tests/test_strategies/` 下的新測試
- 必須更新：`docs/MODEL_ITERATIONS.md`、`docs/PROGRESS.md`
- **不可修改**：上方「不要做的事」列出的所有檔案

---

## 驗收標準

### G1.1.1 驗收

```bash
# 4 個 timeframe 的回測報告都存在
ls reports/backtest_xgboost_v1_10m_*.json
ls reports/backtest_xgboost_v1_30m_*.json
ls reports/backtest_xgboost_v1_60m_*.json
ls reports/backtest_xgboost_v1_1440m_*.json

# MODEL_ITERATIONS.md 的 Experiment 001 有 4 行完整數據
grep -c "xgboost_v1" docs/MODEL_ITERATIONS.md
```

### G1.1.2 驗收（每輪實驗後自我檢查）

```bash
# 所有測試通過
uv run pytest

# MODEL_ITERATIONS.md 有對應的 Experiment 區塊
# Scoreboard 已更新
# PROGRESS.md 摘要表已同步
```

---

## 回報區（由 coding agent / review agent 填寫）

### Coding Agent 回報

_（每輪實驗完成後附加記錄：實驗編號、結果摘要、下一步計畫）_

### Review Agent 回報

_（Review 後填寫）_