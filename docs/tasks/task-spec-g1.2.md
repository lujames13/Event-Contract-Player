# Task Spec G1.2 — 超參數調優、MLP Baseline 與文件同步更新

<!-- status: draft -->
<!-- created: 2026-02-15 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 1（模型實驗池）
> **優先級:** 🟡 High — Gate 1 核心迭代工作
> **前置條件:** G1.1 完成（xgboost_v1/v2, lgbm_v1/v2 已有回測結果）

---

## 目標

1. **文件同步更新**：反映三項已確認的決策變更（1440m 排除、校準要求取消、Gate 1 通過條件修訂）
2. **Experiment 006**：對目前表現最佳的 lgbm 30m 進行 Optuna 超參數調優，嘗試突破 DA 瓶頸
3. **Experiment 007**：建立 MLP (PyTorch) baseline，填補 Gate 1 的「≥3 差異化架構」要求
4. **附帶分析**：每輪實驗同時報告反轉 DA 與各 fold 穩定性

---

## 子任務

### G1.2.0 — 文件同步更新（必須最先執行）

以下三項決策變更已由架構師與使用者確認，需同步到相關文件：

**變更 1：1440m 排除於 Gate 1 評估**

- **`docs/PROGRESS.md`**：
  - Gate 1 通過條件中，將「4 個 timeframe」改為「3 個 timeframe（10m / 30m / 60m）」
  - 新增說明：「1440m 因現有資料量不足以支撐有意義的 walk-forward 驗證，暫時排除。待資料累積 ≥ 3 年後重新評估。」
  - 回測結果摘要表中，移除 1440m 相關的列
- **`docs/MODEL_ITERATIONS.md`**：
  - 收斂標準表中，1440m 行加註「⏸ 暫停」
  - Scoreboard 中移除 1440m 段落，改為一行說明：「1440m 暫停評估，見 PROGRESS.md」
  - Agent 自主迭代規則中，回測指令改為 `for tf in 10 30 60`

**變更 2：校準要求取消**

- **`docs/PROGRESS.md`**：
  - Gate 1 通過條件中，刪除「該組合的信心度校準不反轉（高 confidence bucket 勝率 ≥ 低 confidence bucket）」
  - 替換為：「該組合的 OOS PnL > 0（在回測的模擬交易中淨盈利）」
  - 完整的 Gate 1 通過條件應改為：
    ```
    - [ ] ≥3 個差異化策略架構有完整回測數據
    - [ ] 每個策略覆蓋 3 個 timeframe（10m / 30m / 60m）
    - [ ] 至少 1 個「策略 × timeframe」組合 OOS DA > breakeven（10m: 55.56%, 其餘: 54.05%）
    - [ ] 該組合的 OOS PnL > 0（回測模擬交易淨盈利）
    - [ ] 該組合 OOS 交易筆數 ≥ 500
    ```
- **`docs/MODEL_ITERATIONS.md`**：
  - 收斂標準段落中，刪除「信心度校準要求」整段
  - 替換為：「**PnL 要求：** 達標組合的 OOS 模擬交易 PnL 必須 > 0。」
  - Scoreboard 表格中，「校準」欄位改為「PnL」欄位（顯示正負）
  - Agent 停止條件中的「成功」定義，移除校準相關條件

**變更 3：更新 Scoreboard 欄位**

同步 Scoreboard 表頭，將「校準」欄改為「PnL ✓」，以 ✅ / ❌ 標示 PnL 正負。

**驗收：**
1. `grep -c "1440" docs/PROGRESS.md` — 確認 1440m 不再出現在 Gate 1 通過條件中
2. `grep -c "校準不反轉" docs/PROGRESS.md` — 返回 0
3. `grep -c "校準不反轉" docs/MODEL_ITERATIONS.md` — 返回 0
4. `grep "PnL > 0" docs/PROGRESS.md` — 至少出現一次

**不要做的事：**
- 不要修改 `docs/DECISIONS.md`（校準閾值保留作為信心度過濾門檻的參考，只是不再作為 Gate 1 通過條件）
- 不要修改已完成的實驗記錄內容（Exp 001-005 的結果保持原樣）
- 不要修改 `config/project_constants.yaml`

---

### G1.2.1 — Experiment 006: LightGBM Optuna 超參數調優

**假設：** lgbm_v1 30m 是目前唯一正 PnL 組合（DA 54.34%, PnL +14.93），但使用的是 LightGBM 預設參數。透過 Optuna 貝葉斯搜索找到更好的超參數組合，預期可以提升 DA。

**實作要求：**

1. **新建策略 `lgbm_v1_tuned`**（不修改 lgbm_v1）：
   - 目錄：`src/btc_predictor/strategies/lgbm_v1_tuned/`
   - 從 `lgbm_v1` 複製 `features.py`（特徵集不變，控制單一變數）
   - 新增 `tuning.py`：Optuna 調優邏輯
   - `strategy.py`：繼承 BaseStrategy，使用調優後的最佳參數

2. **Optuna 搜索空間：**
   ```python
   search_space = {
       "num_leaves": (15, 127),           # LightGBM 核心，控制模型複雜度
       "min_child_samples": (10, 100),     # 防止過擬合的關鍵
       "learning_rate": (0.01, 0.3),       # log scale
       "subsample": (0.5, 1.0),            # 行採樣
       "colsample_bytree": (0.3, 1.0),     # 列採樣
       "reg_alpha": (1e-8, 10.0),          # L1 正則化, log scale
       "reg_lambda": (1e-8, 10.0),         # L2 正則化, log scale
       "early_stopping_rounds": (50, 150), # 搜索最佳早停輪數
   }
   ```

3. **Objective function 設計（關鍵）：**
   - 在 walk-forward 框架內跑 Optuna，**不是**用簡單 train/test split
   - 具體做法：對每個 trial 的超參數組合，跑一次完整的 walk-forward backtest（僅限 30m）
   - Objective = OOS DA（主要指標）
   - **Seed stability**：每個 trial 跑 3 個 random seed（`random_state` = 42, 123, 456），取平均 DA 作為 objective。這防止單一 seed 的隨機性影響搜索方向。
   - 搜索次數 **≤ 50 trials**（3 seeds × 50 trials = 150 次 walk-forward，需控制計算時間）
   - 如果單次 walk-forward 回測耗時過長（> 10 分鐘），可降低為 ≤ 30 trials

4. **訓練參數：**
   - `train_days=180`（與 lgbm_v1 一致）
   - `early_stopping_rounds` 從搜索空間取值（不固定 50）
   - Validation split: 20% with purged gap（與 xgboost_v2 一致）

5. **調優完成後：**
   - 用最佳參數跑 **10m / 30m / 60m** 三個 timeframe 的完整回測
   - 記錄最佳參數組合到 Experiment 006 區塊
   - 記錄 Optuna 搜索的 top-5 trials（參數 + DA）供參考

**驗收：**
1. `src/btc_predictor/strategies/lgbm_v1_tuned/` 目錄存在且包含 `strategy.py`, `features.py`, `tuning.py`
2. `uv run pytest tests/test_strategies/test_lgbm_v1_tuned.py` 通過
3. `docs/MODEL_ITERATIONS.md` 有 Experiment 006 完整記錄（含最佳參數、3 個 TF 結果、top-5 trials）
4. `reports/` 下有 3 個新的回測報告 JSON（lgbm_v1_tuned 的 10m/30m/60m）

**不要做的事：**
- 不要修改 `lgbm_v1` 的任何檔案（這是對照組）
- 不要在 Optuna 中搜索特徵集（本次控制特徵不變）
- 不要超過 50 trials（計算資源有限）
- 不要用 Optuna 的 multi-objective 模式
- 不要在 30m 以外的 timeframe 上跑 Optuna（其他 TF 只用 30m 的最佳參數跑回測）

---

### G1.2.2 — Experiment 007: Simple MLP Baseline (PyTorch)

**假設：** Neural network 可能捕捉 tree-based models 遺漏的非線性交互效應。MLP 是最低成本的 neural baseline，用來判斷是否值得投入更複雜的架構（如 N-BEATS）。

**實作要求：**

1. **新建策略 `mlp_v1`**：
   - 目錄：`src/btc_predictor/strategies/mlp_v1/`
   - `features.py`：從 `lgbm_v1/features.py` 複製，但新增 **rolling z-score normalization**
     - 重要：z-score 必須是 rolling window（如 past 60 bars），不可用全局統計量，避免 look-ahead bias
     - 公式：`z = (x - rolling_mean(x, 60)) / rolling_std(x, 60)`
   - `model.py`：PyTorch MLP 定義與訓練邏輯
   - `strategy.py`：繼承 BaseStrategy

2. **MLP 架構：**
   ```
   Input (N features)
     → Linear(N, 128) → BatchNorm → ReLU → Dropout(0.3)
     → Linear(128, 64) → BatchNorm → ReLU → Dropout(0.3)
     → Linear(64, 1) → Sigmoid
   ```
   - Loss: `BCELoss`
   - Optimizer: `Adam(lr=1e-3, weight_decay=1e-5)`
   - Epochs: 50，with early stopping (patience=10) on validation loss
   - Batch size: 512
   - Validation split: 20% with purged gap

3. **Input 設計：**
   - 不使用序列輸入（那是 RNN/N-BEATS 的事）
   - 直接使用 t 時刻的 feature vector（跟 tree models 一致）
   - 這確保我們在比較 MLP vs tree 時，唯一的變數是模型架構

4. **訓練參數：**
   - `train_days=180`
   - 使用 GPU（`torch.device('cuda' if torch.cuda.is_available() else 'cpu')`）
   - 模型序列化：`torch.save(model.state_dict(), path)`

5. **跑 10m / 30m / 60m 三個 timeframe 的完整回測**

**驗收：**
1. `src/btc_predictor/strategies/mlp_v1/` 目錄存在且包含 `strategy.py`, `features.py`, `model.py`
2. `uv run pytest tests/test_strategies/test_mlp_v1.py` 通過
3. `uv run python scripts/train_model.py --strategy mlp_v1 --timeframe 30` 可正常執行
4. `docs/MODEL_ITERATIONS.md` 有 Experiment 007 完整記錄
5. `reports/` 下有 3 個新的回測報告 JSON
6. 推理延遲 < 1 秒（單次 predict 呼叫）

**不要做的事：**
- 不要使用序列模型（RNN, LSTM, Transformer）— 那是不同的架構類別
- 不要使用全局 normalization（必須是 rolling z-score）
- 不要嘗試超過 3 層的 MLP（保持簡單，這是 baseline）
- 不要引入 `torchvision` 或其他不必要的 PyTorch 子套件
- 不要使用 > 4GB VRAM 的配置（batch_size 和 hidden_dim 要保守）

---

### G1.2.3 — 附帶分析：反轉 DA 與 Fold 穩定性

**背景：** 使用者提出「反轉過擬合模型」的假設。需要零成本驗證。

**實作要求：**

在 `src/btc_predictor/backtest/stats.py` 的 `calculate_backtest_stats()` 中新增兩個欄位：

1. **`inverted_da`**：`1.0 - total_da`，反轉後的理論 DA
2. **`per_fold_da`**：一個 list，記錄每個 walk-forward fold 的獨立 DA

具體做法：
- 在 `run_backtest()` 的回傳值中，trades 已經包含 `open_time`。根據 walk-forward 的 `test_days` 邊界，將 trades 分組到各 fold。
- 計算每個 fold 的 DA，存為 list。
- 在 backtest report JSON 中新增 `"inverted_da"` 和 `"per_fold_da"` 欄位。

**MODEL_ITERATIONS.md 更新：** 從 Experiment 006 起，結果表格新增兩欄：
- `Inv. DA`：反轉 DA
- `Fold σ`：各 fold DA 的標準差（穩定性指標，越低越好）

**驗收：**
1. `uv run pytest tests/test_backtest_stats.py` 通過（含新欄位的測試）
2. 回測報告 JSON 包含 `inverted_da` 和 `per_fold_da` 欄位
3. Experiment 006 和 007 的結果表格有 `Inv. DA` 和 `Fold σ` 欄

**不要做的事：**
- 不要修改 `run_backtest()` 的函數簽名或核心邏輯
- 不要建立獨立的反轉策略模型（只是在統計報告中加一個計算值）

---

## 執行順序

```
G1.2.0（文件更新）— 必須最先，後續實驗依賴新的收斂標準
  ↓
G1.2.3（stats 擴展）— 後續實驗需要用到新欄位
  ↓
G1.2.1（Exp 006: Optuna）— 計算量最大，先跑
  ↓
G1.2.2（Exp 007: MLP）— 與 Optuna 結果無依賴
```

---

## 修改範圍（封閉清單）

**新增：**
- `src/btc_predictor/strategies/lgbm_v1_tuned/` — 整個目錄（`__init__.py`, `strategy.py`, `features.py`, `tuning.py`）
- `src/btc_predictor/strategies/mlp_v1/` — 整個目錄（`__init__.py`, `strategy.py`, `features.py`, `model.py`）
- `tests/test_strategies/test_lgbm_v1_tuned.py`
- `tests/test_strategies/test_mlp_v1.py`

**修改：**
- `docs/PROGRESS.md` — Gate 1 通過條件、回測結果摘要表
- `docs/MODEL_ITERATIONS.md` — 收斂標準、Scoreboard、新增 Exp 006/007、停止條件更新
- `src/btc_predictor/backtest/stats.py` — 新增 `inverted_da` 和 `per_fold_da`
- `tests/test_backtest_stats.py` — 新增對應測試

**不動：**
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/strategies/base.py`
- `src/btc_predictor/backtest/engine.py`
- `src/btc_predictor/simulation/risk.py`
- `src/btc_predictor/strategies/xgboost_v1/`
- `src/btc_predictor/strategies/xgboost_v2/`
- `src/btc_predictor/strategies/lgbm_v1/`
- `src/btc_predictor/strategies/lgbm_v2/`

---

## 停止條件

**本 task spec 是有限範圍任務（Exp 006 + 007），不是無限自主迭代。**

完成 G1.2.0 → G1.2.3 → G1.2.1 → G1.2.2 後，無論結果如何，停下等架構師 review 再決定下一步。

成功判定標準（用於 MODEL_ITERATIONS.md Scoreboard 標記）：
- ✅ **達標**：OOS DA > breakeven + OOS PnL > 0 + 交易筆數 ≥ 500
- ❌ **未達標**：任一條件不滿足

---

## 驗收標準（按順序執行）

```bash
# 0. 文件更新驗證
grep "PnL > 0" docs/PROGRESS.md                        # 應出現
grep -c "校準不反轉" docs/MODEL_ITERATIONS.md            # 應返回 0

# 1. 所有測試通過
uv run pytest

# 2. 新策略可被 Registry 發現
uv run python -c "
from pathlib import Path
from btc_predictor.strategies.registry import StrategyRegistry
reg = StrategyRegistry()
reg.discover(Path('src/btc_predictor/strategies'), Path('models'))
names = reg.list_names()
assert 'lgbm_v1_tuned' in names, f'lgbm_v1_tuned not found in {names}'
assert 'mlp_v1' in names, f'mlp_v1 not found in {names}'
print('✅ Registry discovers both new strategies')
"

# 3. 回測報告包含新欄位
uv run python -c "
import json, glob
reports = glob.glob('reports/backtest_lgbm_v1_tuned_*.json')
assert len(reports) >= 3, f'Expected 3+ reports, found {len(reports)}'
with open(reports[0]) as f:
    data = json.load(f)
assert 'inverted_da' in data['stats'], 'Missing inverted_da'
assert 'per_fold_da' in data['stats'], 'Missing per_fold_da'
print('✅ New stats fields present')
"

# 4. MODEL_ITERATIONS.md 有 Exp 006 和 007
grep "Experiment 006" docs/MODEL_ITERATIONS.md
grep "Experiment 007" docs/MODEL_ITERATIONS.md
```

---

## Coding Agent 回報區

### 實作結果
<!-- 完成了什麼，修改了哪些檔案 -->

### 驗收自檢
<!-- 逐條列出驗收標準的 pass/fail -->

### 遇到的問題
<!-- 技術障礙、設計疑慮 -->

### PROGRESS.md 修改建議
<!-- 如果實作過程中發現規劃需要調整，在此說明 -->

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->

### PROGRESS.md 修改建議
<!-- 如有 -->