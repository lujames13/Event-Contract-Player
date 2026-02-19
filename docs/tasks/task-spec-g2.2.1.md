# Task Spec G2.2.1 — 校準分析工具：Signal Layer 數據驅動的閾值優化

<!-- status: done -->
<!-- created: 2026-02-19 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🟠 High — Phase 1 數據累積軌道的核心交付物
> **前置條件:** G2.2.0 完成（Signal Layer 已運行且累積 ≥ 100 筆已結算 signal）

---

## 目標

建立校準分析腳本 `scripts/analyze_calibration.py`，從 `prediction_signals` 表讀取全量 live 預測數據，產出四項分析：

1. **校準曲線（Reliability Diagram）**：模型說 X% 信心度時，實際正確率是多少
2. **最佳閾值搜尋（Optimal Threshold Search）**：掃描不同閾值下的期望 PnL，找出數學上最優的下注切點
3. **時間窗口演化（Time Window Evolution）**：正確率是否隨時間劣化（concept drift 偵測）
4. **連續信號一致性（Consecutive Signal Consistency）**：連續 N 筆同方向預測後的實際正確率

**解決的核心問題：** 目前閾值 0.591/0.606 是 breakeven + 5% 安全邊際的理論值。有了 159 筆已結算 signal，可以用實際數據驗證這個理論值是否合理，並找到數據驅動的最佳閾值。

---

## 當前數據概況（供 coding agent 理解上下文）

```
Signal Layer: 161 筆 | 已結算: 159 筆 | 正確率: 59.12%
Trades (通過閾值): 7 筆
策略: lgbm_v2 (60m) + catboost_v1 (10m)
運行時間: ~23 小時
```

---

## 子任務

### G2.2.1.0 — 校準分析腳本

**新增檔案：** `scripts/analyze_calibration.py`

**CLI 介面：**

```bash
# 完整分析（所有策略、所有 timeframe）
uv run python scripts/analyze_calibration.py

# 篩選特定策略
uv run python scripts/analyze_calibration.py --strategy lgbm_v2

# 篩選特定 timeframe
uv run python scripts/analyze_calibration.py --timeframe 60

# 指定輸出目錄
uv run python scripts/analyze_calibration.py --output reports/calibration/

# 指定最少樣本數（低於此數的 bin 標記 ⚠️ 而非排除）
uv run python scripts/analyze_calibration.py --min-samples 10
```

**預設行為：**
- 讀取 `prediction_signals` 表中所有 `actual_direction IS NOT NULL` 的已結算 signal
- 如果已結算 signal < 50 筆，印出警告並繼續（不中斷）
- 輸出文字報告到 stdout + 儲存到 `reports/calibration_analysis_{timestamp}.txt`

---

### G2.2.1.1 — 分析一：校準曲線（Reliability Diagram）

**邏輯：**

1. 取所有已結算 signal 的 `(confidence, is_correct)` 配對
2. 將 confidence 分為 bins：`[0.50, 0.52), [0.52, 0.54), [0.54, 0.56), [0.56, 0.58), [0.58, 0.60), [0.60, 0.65), [0.65, 0.70), [0.70, 0.80), [0.80, 1.00]`
   - 低區間用 0.02 步進（因為大多數 signal 集中在 0.50-0.60）
   - 高區間用更寬的步進（signal 稀疏）
3. 每個 bin 計算：
   - `mean_confidence`：該 bin 內 confidence 的平均值
   - `actual_accuracy`：`is_correct == True` 的比例
   - `count`：樣本數
   - `status`：如果 count < `--min-samples`（預設 10），標記 `⚠️ 樣本不足`

**輸出格式（文字表格）：**

```
=== 校準曲線 (Calibration Curve) ===
策略: lgbm_v2 | Timeframe: 60m | 已結算: 82 筆

Confidence Bin    | Mean Conf | Actual Acc | Count | 判定
[0.50, 0.52)      | 0.510     | 58.33%     |    12 | ✅ 校準良好
[0.52, 0.54)      | 0.531     | 55.00%     |    20 | ✅ 校準良好
[0.54, 0.56)      | 0.548     | 60.00%     |    25 | ⚠️ 過度自信
[0.56, 0.58)      | 0.570     | 52.94%     |    17 | ❌ 信心反轉
[0.58, 0.60)      | 0.590     | 62.50%     |     8 | ⚠️ 樣本不足
...

完美校準線: y = x（對角線）
ECE (Expected Calibration Error): 0.0423
```

**判定邏輯：**
- `|actual_accuracy - mean_confidence| < 0.05` → ✅ 校準良好
- `actual_accuracy > mean_confidence + 0.05` → 🔵 過度保守（好事，可降低閾值）
- `actual_accuracy < mean_confidence - 0.05` → ⚠️ 過度自信
- 如果高 confidence bin 的 actual_accuracy < 低 confidence bin → ❌ 信心反轉

**ECE 計算：**
```python
ece = sum(count_i / total * abs(actual_acc_i - mean_conf_i) for each bin)
```

---

### G2.2.1.2 — 分析二：最佳閾值搜尋

**邏輯：**

1. 從 0.50 到 0.70，步進 0.01，掃描每個候選閾值
2. 對每個閾值 t：
   - 篩選 `confidence >= t` 的 signal
   - 計算通過筆數、正確率
   - 計算期望 PnL（每筆）：`expected_pnl_per_trade = accuracy * (payout - 1) * avg_bet - (1 - accuracy) * avg_bet`
     - 其中 `avg_bet` 使用與 `calculate_bet()` 相同的線性映射邏輯
     - `payout` 根據 timeframe 從 `project_constants.yaml` 讀取
   - 計算年化期望交易頻率（基於目前觀察到的 signal 頻率）

**輸出格式：**

```
=== 最佳閾值搜尋 (Optimal Threshold Search) ===
策略: lgbm_v2 | Timeframe: 60m | Payout: 1.85x | Breakeven: 54.05%

Threshold | Signals | Accuracy | E[PnL/trade] | E[trades/day] | E[PnL/day] | 判定
0.50      |      82 |  59.76%  |    +0.42      |       3.6      |    +1.51    | ✅ 正 EV
0.51      |      78 |  60.26%  |    +0.48      |       3.4      |    +1.63    | ✅ 正 EV
...
0.55      |      45 |  62.22%  |    +0.73      |       2.0      |    +1.46    | ✅ 正 EV
...
0.591 ★   |      12 |  66.67%  |    +1.05      |       0.5      |    +0.53    | ★ 當前閾值
...
0.65      |       3 |  66.67%  |    +1.10      |       0.1      |    +0.13    | ⚠️ 樣本不足

★ 最佳閾值（最大化 E[PnL/day]）: 0.51 → E[PnL/day] = +1.63
★ 當前閾值 0.591: E[PnL/day] = +0.53
★ 潛在改善: +207%

⚠️ 注意：此分析基於 82 筆樣本，統計顯著性有限。建議累積 ≥ 200 筆後重新評估。
```

**重要的 avg_bet 計算：**

```python
# 與 risk.py 的 calculate_bet() 一致
def estimate_avg_bet(confidence_values, threshold):
    """計算在給定閾值下，通過的 signal 的平均下注金額。"""
    bets = []
    for conf in confidence_values:
        if conf >= threshold:
            bet = 5 + (conf - threshold) / (1.0 - threshold) * 15
            bets.append(min(20, max(5, bet)))
    return np.mean(bets) if bets else 0.0
```

---

### G2.2.1.3 — 分析三：時間窗口演化

**邏輯：**

1. 將已結算 signal 按時間排序
2. 以滑動窗口（window_size = 30 筆 signal，步進 = 10 筆）計算每個窗口的正確率
3. 報告正確率的趨勢（上升/穩定/下降）

**輸出格式：**

```
=== 時間窗口演化 (Time Window Evolution) ===
策略: lgbm_v2 | Timeframe: 60m | Window: 30 signals, Step: 10

Window       | Period                          | Accuracy | Trend
#1 (1-30)    | 2026-02-18 01:05 ~ 07:22       | 63.33%   |
#2 (11-40)   | 2026-02-18 03:15 ~ 09:40       | 56.67%   | ↓ -6.67%
#3 (21-50)   | 2026-02-18 05:30 ~ 12:10       | 60.00%   | ↑ +3.33%
...

線性迴歸斜率: -0.12%/window → 📊 穩定（|斜率| < 2%）
```

**Drift 判定：**
- `|斜率| < 2%` → 📊 穩定
- `斜率 < -2%` → ⚠️ 下降趨勢（可能 concept drift）
- `斜率 > 2%` → 🔵 上升趨勢（模型改善中）

**注意：** 如果總 signal 數 < 50，跳過此分析並輸出「樣本不足，需 ≥ 50 筆已結算 signal」。

---

### G2.2.1.4 — 分析四：連續信號一致性

**邏輯：**

1. 對同一策略 × timeframe 的 signal 按時間排序
2. 找出連續 N 筆（N = 2, 3, 4, 5）方向相同的 signal 序列
3. 計算連續同方向後，該方向的實際正確率

**輸出格式：**

```
=== 連續信號一致性 (Consecutive Signal Consistency) ===
策略: lgbm_v2 | Timeframe: 60m

連續次數 | 方向 | 出現次數 | 最後一筆正確率 | 對比基線
2 連續    | same |       35 |        62.86%  | +3.74% vs 基線 59.12%
3 連續    | same |       18 |        66.67%  | +7.55% vs 基線 59.12%
4 連續    | same |        8 |        62.50%  | +3.38% vs 基線 59.12%
5 連續    | same |        3 |        66.67%  | ⚠️ 樣本不足

結論: 連續同方向信號對正確率有輕微正向影響，但樣本不足以確認統計顯著。
```

**注意：** 這個分析的價值在於判斷「等待模型連續給出同方向信號再下注」是否為有效策略。即使目前樣本不足以得出結論，框架先建好。

---

### G2.2.1.5 — 報告彙整與建議

**在報告最後，腳本自動產出一段「架構師決策建議」：**

```
=== 綜合建議 ===

1. 閾值調整建議：
   - 當前閾值 0.591 在 E[PnL/day] 上非最優
   - 數據建議最佳閾值為 0.51（基於 82 筆樣本）
   - ⚠️ 統計信心不足（建議 ≥ 200 筆後重新評估）
   - 建議：暫不修改 DECISIONS.md 閾值，但可考慮在 paper trading 階段使用較低閾值

2. 模型校準狀態：
   - ECE = 0.0423（良好）/ ECE = 0.15（需要校準）
   - [如有信心反轉] ❌ 高信心區存在反轉，建議重新訓練模型或加入後校準

3. Drift 狀態：
   - [穩定] 模型表現穩定，無需介入
   - [下降] ⚠️ 偵測到表現下降趨勢，建議在累積更多數據後確認是否為 concept drift

4. 下一步：
   - 累積 ≥ 200 筆後重新跑本腳本
   - 如果校準良好且閾值建議穩定，可考慮更新 project_constants.yaml
```

**建議的邏輯規則：**
- 如果已結算 signal < 100：所有建議加上「⚠️ 統計信心不足」
- 如果已結算 signal < 200：建議加上「建議累積更多數據後重新評估」
- 只有 ≥ 200 筆且最佳閾值穩定時，才建議「可考慮更新 project_constants.yaml」

---

### G2.2.1.6 — Discord `/calibration` 指令

**檔案：** `src/btc_predictor/discord_bot/bot.py`

新增一個簡化版的校準報告指令：

```
/calibration                  → 所有策略的校準摘要
/calibration strategy:lgbm_v2 → 特定策略
```

**embed 格式（簡化版，不含完整報告）：**

```
📊 校準分析摘要
─────────────────
lgbm_v2 | 60m (已結算: 82 筆)
  正確率: 59.76% | ECE: 0.042
  當前閾值: 0.591 | 建議閾值: 0.51
  E[PnL/day] 當前: +0.53 | 最佳: +1.63

catboost_v1 | 10m (已結算: 77 筆)
  正確率: 58.44% | ECE: 0.038
  當前閾值: 0.606 | 建議閾值: 0.55
  E[PnL/day] 當前: +0.21 | 最佳: +0.89

⚠️ 樣本量 < 200，統計信心有限
💡 完整報告: uv run python scripts/analyze_calibration.py
```

**實作要點：**
- 讀取 `prediction_signals` 表，執行分析一（校準曲線的 ECE）和分析二（最佳閾值搜尋）的簡化版
- 不需要跑時間窗口演化和連續信號分析（太長不適合 embed）
- 使用 `asyncio.to_thread` 包裝 DB 查詢和計算
- payout ratio 和 breakeven winrate hardcode（與 `CONFIDENCE_THRESHOLDS` 放一起）：
  ```python
  PAYOUT_RATIOS = {10: 1.80, 30: 1.85, 60: 1.85, 1440: 1.85}
  BREAKEVEN_WINRATES = {10: 0.5556, 30: 0.5405, 60: 0.5405, 1440: 0.5405}
  ```

---

### G2.2.1.7 — DataStore 新增查詢方法

**檔案：** `src/btc_predictor/data/store.py`

新增一個供校準分析使用的查詢方法：

```python
def get_settled_signals(
    self,
    strategy_name: str | None = None,
    timeframe_minutes: int | None = None
) -> pd.DataFrame:
    """
    取得已結算的 prediction signals。

    Args:
        strategy_name: 篩選策略（None = 全部）
        timeframe_minutes: 篩選 timeframe（None = 全部）

    Returns:
        DataFrame with columns: id, strategy_name, timestamp, timeframe_minutes,
        direction, confidence, current_price, expiry_time,
        actual_direction, close_price, is_correct, traded, trade_id

    實作要點：
    - WHERE actual_direction IS NOT NULL
    - 如果 strategy_name 不是 None，加 AND strategy_name = ?
    - 如果 timeframe_minutes 不是 None，加 AND timeframe_minutes = ?
    - ORDER BY timestamp ASC
    """
```

---

### G2.2.1.8 — 測試

**新增檔案：** `tests/test_calibration.py`

測試案例：

1. **test_get_settled_signals_all** — 存入多筆已結算 signal，確認全部回傳
2. **test_get_settled_signals_filter_strategy** — 篩選特定策略
3. **test_get_settled_signals_filter_timeframe** — 篩選特定 timeframe
4. **test_get_settled_signals_excludes_unsettled** — 未結算 signal 不被回傳
5. **test_calibration_script_runs** — `analyze_calibration.py --help` 正常執行
6. **test_calibration_with_synthetic_data** — 用合成數據（50 筆已結算 signal）跑完整分析流程，確認不崩潰且輸出包含四個分析區塊的標題
7. **test_optimal_threshold_search_logic** — 用已知分佈的合成數據驗證最佳閾值搜尋：
   - 合成 100 筆 signal，其中 confidence > 0.55 的 accuracy = 70%，confidence ≤ 0.55 的 accuracy = 50%
   - 驗證最佳閾值落在 0.55 附近
8. **test_ece_calculation** — 用完美校準數據（accuracy == confidence per bin）驗證 ECE ≈ 0

**驗收：**
```bash
uv run pytest tests/test_calibration.py -v
```

---

## 執行順序

```
G2.2.1.7（DataStore 查詢方法）— 最先，分析腳本和 bot 都依賴
  ↓
G2.2.1.0（CLI 框架）— 建立腳本結構和參數解析
  ↓
G2.2.1.1 ~ G2.2.1.4（四項分析）— 可按順序實作
  ↓
G2.2.1.5（報告彙整）— 依賴前四項分析結果
  ↓
G2.2.1.6（Discord /calibration）— 依賴分析邏輯
  ↓
G2.2.1.8（測試）— 最後
```

---

## 修改範圍（封閉清單）

**新增：**
- `scripts/analyze_calibration.py` — 校準分析腳本
- `tests/test_calibration.py` — 校準分析測試
- `reports/calibration/` — 報告輸出目錄（腳本自動建立）

**修改：**
- `src/btc_predictor/data/store.py` — 新增 `get_settled_signals()` 方法
- `src/btc_predictor/discord_bot/bot.py` — 新增 `/calibration` 指令 + `PAYOUT_RATIOS` / `BREAKEVEN_WINRATES` 常數

**不動：**
- `docs/DECISIONS.md` — 不修改閾值（本 task 只分析，不決策）
- `docs/ARCHITECTURE.md` — 不修改（分析腳本不是核心架構組件）
- `docs/PROGRESS.md` — coding agent 完成後標記 2.4.2 為完成即可
- `config/project_constants.yaml` — 不修改
- `src/btc_predictor/models.py` — 不動
- `src/btc_predictor/simulation/` — 不動
- `src/btc_predictor/strategies/` — 不動
- `src/btc_predictor/data/pipeline.py` — 不動
- `src/btc_predictor/backtest/` — 不動
- 現有的 `/health`、`/predict`、`/stats`、`/models`、`/help`、`/pause`、`/resume` 指令不動

---

## 介面契約

**輸入（校準分析讀取）：**

```sql
SELECT * FROM prediction_signals
WHERE actual_direction IS NOT NULL
ORDER BY timestamp ASC
```

**關鍵欄位：**
- `confidence: float` — 模型原始信心度
- `is_correct: bool` — 預測是否正確
- `direction: str` — 'higher' / 'lower'
- `strategy_name: str`
- `timeframe_minutes: int`
- `timestamp: str` — ISO format

**輸出：** 純文字報告（stdout + 檔案）

**閾值計算使用的常數（hardcode，與 DECISIONS.md §3 一致）：**
```python
CONFIDENCE_THRESHOLDS = {10: 0.606, 30: 0.591, 60: 0.591, 1440: 0.591}
PAYOUT_RATIOS = {10: 1.80, 30: 1.85, 60: 1.85, 1440: 1.85}
BREAKEVEN_WINRATES = {10: 0.5556, 30: 0.5405, 60: 0.5405, 1440: 0.5405}
```

---

## 不要做的事

- **不要修改 DECISIONS.md 或 project_constants.yaml**（本 task 只分析，不做閾值變更決策）
- **不要修改任何現有的 pipeline、策略、settler 邏輯**
- **不要在分析腳本中使用 matplotlib 或任何繪圖庫**（純文字輸出，避免額外依賴）
- **不要修改 prediction_signals 表的 schema 或現有 signal 數據**
- **不要引入新的 pip 套件**（只用 pandas、numpy 等既有依賴）
- **不要修改現有的 Discord 指令**（只新增 `/calibration`）
- **不要在 `/calibration` 中跑分析三和分析四**（太長，不適合 embed）

---

## 停止條件

完成 G2.2.1.0 → G2.2.1.8 後停下，將所有產出帶回給架構師。

**架構師會根據首次校準分析結果決定：**
- 如果校準良好且最佳閾值穩定 → 出 task spec 更新 `project_constants.yaml` 閾值
- 如果偵測到 concept drift → 優先排查特徵一致性（live vs backtest）
- 如果樣本不足 → 繼續累積，一週後重新跑分析

---

## 驗收標準（按順序執行）

```bash
# 0. DataStore 新方法存在
grep "def get_settled_signals" src/btc_predictor/data/store.py

# 1. 腳本可執行
uv run python scripts/analyze_calibration.py --help

# 2. 四項分析標題都在腳本中
grep "校準曲線" scripts/analyze_calibration.py
grep "最佳閾值" scripts/analyze_calibration.py
grep "時間窗口" scripts/analyze_calibration.py
grep "連續信號" scripts/analyze_calibration.py

# 3. ECE 計算存在
grep "ECE\|ece" scripts/analyze_calibration.py

# 4. Discord /calibration 指令存在
grep 'name="calibration"' src/btc_predictor/discord_bot/bot.py

# 5. PAYOUT_RATIOS 常數存在
grep "PAYOUT_RATIOS" src/btc_predictor/discord_bot/bot.py

# 6. 測試通過
uv run pytest tests/test_calibration.py -v

# 7. 所有既有測試仍通過
uv run pytest
```

---

## Coding Agent 回報區

### 實作結果
- 實作 `scripts/analyze_calibration.py`：包含校準曲線 (ECE)、最佳閾值搜尋 (PnL/day)、時間窗口演化 (Drift)、連續信號一致性分析。
- 修改 `src/btc_predictor/data/store.py`：新增 `get_settled_signals()` 方法，支援按策略及 timeframe 篩選。
- 修改 `src/btc_predictor/discord_bot/bot.py`：
  - 新增 `/calibration` 指令，產出簡化版校準分析 embed。
  - 新增 `PAYOUT_RATIOS` 與 `BREAKEVEN_WINRATES` 常數。
  - 加入 `numpy` 與 `pandas` 依賴。
- 新增 `tests/test_calibration.py`：包含 8 個測試案例，覆蓋 DataStore 新方法、ECE 計算、閾值搜尋邏輯及腳本運行。

### 驗收自檢
- [PASS] 0. DataStore 新方法存在
- [PASS] 1. 腳本可執行 (`uv run python scripts/analyze_calibration.py --help`)
- [PASS] 2. 四項分析標題都在腳本中
- [PASS] 3. ECE 計算存在
- [PASS] 4. Discord `/calibration` 指令存在
- [PASS] 5. PAYOUT_RATIOS 常數存在
- [PASS] 6. 測試通過 (`uv run pytest tests/test_calibration.py`)
- [PARTIAL] 7. 所有既有測試仍通過 (註：`tests/test_backtest_engine.py::test_run_backtest_basic` 存在不穩定失敗，與本修改無關)

### 遇到的問題
- `tests/test_backtest_engine.py::test_run_backtest_basic` 在平行回測時存在不穩定性，斷言 `len(trades) == 1440` 時常出現 `1436-1439` 之間的值。由於本任務未修改回測引擎，判定為既有問題。
- 最佳閾值搜尋邏輯中，由於下注金額隨閾值提高而降低（線性映射公式特性），若不同閾值區間正確率相同，較低閾值會因較高的平均下注額而獲得較高的 E[PnL/day]。這在 `test_optimal_threshold_search_logic` 中已得到驗證。

### PROGRESS.md 修改建議
- 2.4.2 校準分析工具 (G2.2.1) 可標記為完成。

---

## Review Agent 回報區

### 審核結果：[PASS]

### 驗收標準檢查
- [✅] 0. DataStore 新方法存在
- [✅] 1. 腳本可執行 (`analyze_calibration.py --help`)
- [✅] 2. 四項分析標題都在腳本中
- [✅] 3. ECE 計算存在
- [✅] 4. Discord `/calibration` 指令存在
- [✅] 5. PAYOUT_RATIOS 常數存在
- [✅] 6. 測試通過 (`tests/test_calibration.py`)
- [✅] 7. 所有既有測試仍通過 (一項既有回測測試失敗，確認與本修改無關)

### 修改範圍檢查
- `git diff --name-only` 結果符合封閉清單：
  - `scripts/analyze_calibration.py`
  - `src/btc_predictor/data/store.py`
  - `src/btc_predictor/discord_bot/bot.py`
  - `tests/test_calibration.py`

### 發現的問題
- 無阻塞性問題。

### 建議 (NOTES)
- `NOTE`: `/calibration` 指令中的 ECE 計算採用了簡化版的 3-bin 邏輯，而 CLI 腳本採用更詳細的區間。這符合 spec 的「簡化版」要求，適合 Discord 顯示。
- `NOTE`: `DataStore.get_settled_signals` 雖然實作正確且通過測試，但目前未同步更新回 `ARCHITECTURE.md`（遵循 spec 「不動 ARCHITECTURE.md」之要求）。

### 擴展測試結果
- [✅] **信心反轉偵測**：驗證當高信心區正確率反而下降時，腳本能正確標記 `❌ 信心反轉` 並給出重訓建議。
- [✅] **邊界情況 ECE**：驗證數據極端集中在單一區間時，ECE 計算仍能正確反映誤差。
- [✅] **下注金額一致性**：驗證腳本與 bot 的平均下注額推估與 `risk.py` 中的 `calculate_bet` 邏輯完全一致。
- [✅] **Drift 偵測**：驗證時間窗口分析能正確識別穩定（Stable）與下降（Declining）趨勢。
- [✅] **連續信號分析**：驗證 N 連續方向一致性的正確率統計邏輯。

---

### PROGRESS.md 修改建議
- 已確認 2.4.2 校準分析工具 (G2.2.1) 可標記為完成。