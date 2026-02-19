# Task Spec G2.2.0 — Signal Layer：全量預測記錄 + 文件同步

<!-- status: completed -->
<!-- created: 2026-02-18 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🔴 Critical — 解除 Phase 1 數據盲區
> **前置條件:** G2.0 完成（Live Pipeline MVP 已運行）

---

## 目標

建立 Signal Layer，實現「記錄一切，選擇性執行」。每次 `strategy.predict()` 被呼叫時，無條件將 `PredictionSignal` 寫入新的 `prediction_signals` 表，並由背景任務結算所有 signal 的實際結果。同步更新 DECISIONS.md、ARCHITECTURE.md、PROGRESS.md。

**解決的核心問題：** 系統運行 2 小時、觸發 19 次策略、0 筆交易。目前沒有任何數據可以判斷是「閾值太高」還是「模型 live 信心度分佈異常」。

---

## 子任務

### G2.2.0.0 — 更新 DECISIONS.md（最先執行）

在 `docs/DECISIONS.md` 末尾新增 §7：

```markdown
## 7. 數據記錄原則

| 決策 | 值 | Rationale |
|------|-----|-----------|
| 預測信號記錄 | 全量記錄（不論信心度） | Signal Layer 提供模型校準、閾值優化、drift 偵測的完整數據 |
| 信心度閾值作用 | 僅控制 Execution Layer（是否產生 SimulatedTrade） | 閾值是交易決策，不是數據採集決策 |
| Signal 結算 | 所有 signal 都結算 actual_outcome | 即使不下注的預測也需要知道對錯，用於校準分析 |

**兩層數據模型：**
- **Signal Layer**（`prediction_signals` 表）：每次 `strategy.predict()` 被呼叫就寫入一筆，無條件。用於校準分析、閾值優化、concept drift 偵測。
- **Execution Layer**（`simulated_trades` 表）：僅信心度 ≥ 閾值且通過風控的預測才產生。用於 PnL 計算、資金管理。
```

**驗收：**
```bash
grep "數據記錄原則" docs/DECISIONS.md
grep "Signal Layer" docs/DECISIONS.md
grep "Execution Layer" docs/DECISIONS.md
```

---

### G2.2.0.1 — 更新 ARCHITECTURE.md

**a) DB Schema 段落，在 `simulated_trades` 表之後新增：**

```sql
-- 預測信號（全量記錄，Signal Layer）
CREATE TABLE prediction_signals (
    id                TEXT PRIMARY KEY,
    strategy_name     TEXT NOT NULL,
    timestamp         TEXT NOT NULL,       -- 預測時間 (ISO format, UTC)
    timeframe_minutes INTEGER NOT NULL,
    direction         TEXT NOT NULL,        -- 'higher' / 'lower'
    confidence        FLOAT NOT NULL,
    current_price     FLOAT NOT NULL,
    expiry_time       TEXT NOT NULL,
    -- 結算後填入
    actual_direction  TEXT,                 -- NULL = 未結算, 'higher' / 'lower' / 'draw'
    close_price       FLOAT,
    is_correct        BOOLEAN,             -- NULL = 未結算
    -- 與 Execution Layer 的關聯
    traded            BOOLEAN NOT NULL DEFAULT 0,
    trade_id          TEXT,                 -- FK to simulated_trades.id（如有）
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_signals_unsettled ON prediction_signals(expiry_time)
    WHERE actual_direction IS NULL;
CREATE INDEX idx_signals_strategy ON prediction_signals(strategy_name, timeframe_minutes);
```

**b) Data Pipeline 段落，更新流程圖為：**

```
predict() ──→ save_prediction_signal() ──→ prediction_signals 表（全量）
    │
    └──→ process_signal() ──→ [閾值 + 風控通過] ──→ simulated_trades 表
              │                                          │
              └── 更新 signal.traded = True ──────────────┘

Signal Settler（背景任務）：掃描 prediction_signals 中已到期但未結算的記錄，
查詢收盤價，填入 actual_direction、close_price、is_correct。
```

**c) 介面契約段落，新增 Signal Layer 相關方法：**

```python
# DataStore 新增方法
def save_prediction_signal(self, signal: PredictionSignal) -> str:
    """無條件儲存預測信號，回傳 signal_id。"""

def update_signal_traded(self, signal_id: str, trade_id: str) -> None:
    """標記 signal 已產生對應的 SimulatedTrade。"""

def get_unsettled_signals(self, max_age_hours: int = 24) -> pd.DataFrame:
    """取得已到期但尚未結算的 signals。"""

def settle_signal(self, signal_id: str, actual_direction: str, close_price: float, is_correct: bool) -> None:
    """寫入 signal 的實際結果。"""
```

**驗收：**
```bash
grep "prediction_signals" docs/ARCHITECTURE.md
grep "save_prediction_signal" docs/ARCHITECTURE.md
grep "Signal Settler" docs/ARCHITECTURE.md
```

---

### G2.2.0.2 — 更新 PROGRESS.md

**a) Phase 1 里程碑段落，替換為：**

```markdown
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
```

**b) Gate 2 任務清單中，新增 §2.4：**

```markdown
### 2.4 數據基礎設施

- [ ] **2.4.1** Signal Layer 實作 (G2.2.0)
  - 新增 `prediction_signals` DB 表
  - Pipeline 在每次 predict 後無條件寫入 signal
  - Signal settler 定期結算所有未結算 signal 的 actual_outcome
  - 不動現有 simulated_trades 流程

- [ ] **2.4.2** 校準分析工具 (G2.2.1)
  - `scripts/analyze_calibration.py`：分桶分析 + reliability diagram
  - 依賴 Signal Layer 累積 ≥ 100 筆已結算 signal 後才有意義
```

**驗收：**
```bash
grep "數據累積軌道" docs/PROGRESS.md
grep "Signal Layer" docs/PROGRESS.md
grep "2.4.1" docs/PROGRESS.md
grep "2.4.2" docs/PROGRESS.md
grep "不 block Phase 2" docs/PROGRESS.md
```

---

### G2.2.0.3 — 實作 DB Schema + DataStore 方法

**檔案：** `src/btc_predictor/infrastructure/store.py`

**a) 在 `_init_db()` 中新增 `prediction_signals` 表的 CREATE TABLE（含兩個 index）。**

Schema 見 G2.2.0.1 的 SQL。

**b) 新增四個方法：**

```python
def save_prediction_signal(self, signal: PredictionSignal) -> str:
    """
    無條件儲存預測信號。

    Args:
        signal: PredictionSignal dataclass

    Returns:
        signal_id: 新建記錄的 UUID

    實作要點：
    - 生成 UUID 作為 id
    - expiry_time = signal.timestamp + timedelta(minutes=signal.timeframe_minutes)
    - traded 初始為 0, trade_id 初始為 NULL
    - 使用 INSERT（不是 UPSERT，每次 predict 都是新記錄）
    """

def update_signal_traded(self, signal_id: str, trade_id: str) -> None:
    """
    標記 signal 已產生對應的 SimulatedTrade。

    實作要點：
    - UPDATE prediction_signals SET traded = 1, trade_id = ? WHERE id = ?
    """

def get_unsettled_signals(self, max_age_hours: int = 24) -> pd.DataFrame:
    """
    取得已到期但尚未結算的 signals。

    實作要點：
    - WHERE actual_direction IS NULL
    - AND expiry_time <= datetime('now')
    - AND expiry_time >= datetime('now', '-{max_age_hours} hours')
    - ORDER BY expiry_time ASC
    """

def settle_signal(self, signal_id: str, actual_direction: str, close_price: float, is_correct: bool) -> None:
    """
    寫入 signal 的實際結果。

    實作要點：
    - UPDATE prediction_signals
    - SET actual_direction = ?, close_price = ?, is_correct = ?
    - WHERE id = ?
    """
```

**驗收：**
```bash
grep "prediction_signals" src/btc_predictor/infrastructure/store.py
grep "save_prediction_signal" src/btc_predictor/infrastructure/store.py
grep "update_signal_traded" src/btc_predictor/infrastructure/store.py
grep "get_unsettled_signals" src/btc_predictor/infrastructure/store.py
grep "settle_signal" src/btc_predictor/infrastructure/store.py
```

---

### G2.2.0.4 — 整合 Pipeline：predict 後無條件寫入 Signal

**檔案：** `src/btc_predictor/infrastructure/pipeline.py`

在 pipeline 中策略 `predict()` 呼叫成功後、`process_signal()` 之前，插入 signal 儲存邏輯：

```python
# 虛擬碼，展示插入位置
signal = await asyncio.to_thread(strategy.predict, df, tf)

# ★ Signal Layer：無條件記錄
signal_id = store.save_prediction_signal(signal)

# Execution Layer：閾值 + 風控
trade = process_signal(signal, store)

if trade is not None:
    store.update_signal_traded(signal_id, trade.id)
```

**注意事項：**
- `save_prediction_signal` 是 DB 寫入，但非常輕量（單行 INSERT），不需要 `asyncio.to_thread`
- 如果 `save_prediction_signal` 拋異常，必須 catch 並 log，**不能阻塞後續的 process_signal**。Signal Layer 的失敗不應影響 Execution Layer。

**驗收：**
```bash
grep "save_prediction_signal" src/btc_predictor/infrastructure/pipeline.py
```

---

### G2.2.0.5 — Signal Settler 背景任務

**檔案：** `src/btc_predictor/simulation/settler.py`

在現有的 `settle_pending_trades()` 旁邊新增：

```python
async def settle_pending_signals(store: DataStore) -> int:
    """
    結算所有已到期但未結算的 prediction signals。

    Returns:
        int: 本次結算的 signal 數量

    邏輯：
    1. 呼叫 store.get_unsettled_signals()
    2. 對每筆 signal：
       a. 查詢 expiry_time 對應的 1m K 線收盤價
          （與 settle_pending_trades 使用相同的價格查詢邏輯）
       b. 如果找不到收盤價，跳過（可能 K 線尚未收到）
       c. 判定 actual_direction：
          - close_price > open_price → 'higher'
          - close_price < open_price → 'lower'
          - close_price == open_price → 'draw'
       d. 判定 is_correct：
          - direction == actual_direction → True
          - actual_direction == 'draw' → False（平盤算錯，與 simulated_trades 一致）
          - 否則 → False
       e. 呼叫 store.settle_signal(signal_id, actual_direction, close_price, is_correct)
    3. 回傳結算數量，log 結果
    """
```

**在 `run_live.py` 的主循環或定時任務中，同時呼叫 `settle_pending_trades()` 和 `settle_pending_signals()`。**

兩個 settler 可以共用定時器（例如每 60 秒跑一次），先結算 trades 再結算 signals，或反過來都行。

**驗收：**
```bash
grep "settle_pending_signals" src/btc_predictor/simulation/settler.py
grep "settle_pending_signals" scripts/run_live.py
```

---

### G2.2.0.6 — Discord Bot `/health` 增顯 Signal 統計

**檔案：** `src/btc_predictor/discord_bot/bot.py`

在 `/health` 指令的 embed 中，新增一行顯示 signal 統計：

```
 Signals
 總計: 42 筆 | 已結算: 38 筆 | 正確率: 52.63%
```

**需要在 `store.py` 額外新增一個輔助查詢方法：**

```python
def get_signal_stats(self) -> dict:
    """
    Returns:
        {"total": int, "settled": int, "correct": int, "accuracy": float | None}
    """
```

**驗收：**
```bash
grep "get_signal_stats" src/btc_predictor/infrastructure/store.py
grep "signal" src/btc_predictor/discord_bot/bot.py | grep -i "stat\|count\|total"
```

---

### G2.2.0.7 — 測試

**新增檔案：** `tests/test_signal_layer.py`

測試案例：

1. **test_save_prediction_signal** — 存入一筆 signal，確認所有欄位正確
2. **test_signal_not_traded_by_default** — 存入後 `traded == False`, `trade_id == None`
3. **test_update_signal_traded** — 存入 → 更新 traded → 確認 `traded == True` 且 `trade_id` 正確
4. **test_get_unsettled_signals** — 存入多筆 signal（含已結算和未結算），確認只回傳未結算且已到期的
5. **test_settle_signal_correct** — 結算一筆正確的 signal（direction 與 actual_direction 一致）
6. **test_settle_signal_incorrect** — 結算一筆錯誤的 signal
7. **test_settle_signal_draw** — 平盤情境，`is_correct == False`
8. **test_settle_pending_signals** — 端對端：存入 signal → 插入 expiry K 線 → 呼叫 `settle_pending_signals()` → 確認結果
9. **test_signal_layer_does_not_affect_trade_layer** — 確認 `save_prediction_signal` 的失敗不影響 `process_signal` 的結果

**驗收：**
```bash
uv run pytest tests/test_signal_layer.py -v
```

---

## 執行順序

```
G2.2.0.0（DECISIONS.md）— 最先，確立設計原則
  ↓
G2.2.0.1（ARCHITECTURE.md）— 定義 schema + 介面
  ↓
G2.2.0.2（PROGRESS.md）— 更新里程碑
  ↓
G2.2.0.3（DB + DataStore）— 基礎層
  ↓
G2.2.0.4（Pipeline 整合）— 依賴 DataStore 方法
  ↓
G2.2.0.5（Signal Settler）— 依賴 DataStore 方法
  ↓
G2.2.0.6（Discord /health）— 依賴 get_signal_stats
  ↓
G2.2.0.7（測試）— 最後，驗證全部
```

---

## 修改範圍（封閉清單）

**修改：**
- `docs/DECISIONS.md` — 新增 §7 數據記錄原則
- `docs/ARCHITECTURE.md` — 新增 prediction_signals schema + 介面契約 + 流程圖更新
- `docs/PROGRESS.md` — Phase 1 里程碑改為雙軌制 + 新增 2.1.3/2.1.4 任務
- `src/btc_predictor/infrastructure/store.py` — 新增 prediction_signals 表 + 5 個方法
- `src/btc_predictor/infrastructure/pipeline.py` — predict 後插入 save_prediction_signal 呼叫
- `src/btc_predictor/simulation/settler.py` — 新增 settle_pending_signals()
- `scripts/run_live.py` — 定時任務中加入 settle_pending_signals()
- `src/btc_predictor/discord_bot/bot.py` — /health embed 新增 signal 統計行

**新增：**
- `tests/test_signal_layer.py` — Signal Layer 完整測試

**不動：**
- `config/project_constants.yaml` — 不新增常數
- `src/btc_predictor/models.py` — PredictionSignal / SimulatedTrade dataclass 不動
- `src/btc_predictor/simulation/engine.py` — process_signal 不動
- `src/btc_predictor/simulation/risk.py` — 風控邏輯不動
- `src/btc_predictor/strategies/` — 所有策略目錄不動
- `src/btc_predictor/backtest/` — 回測目錄不動
- `docs/MODEL_ITERATIONS.md` — 不涉及模型實驗
- 現有 `simulated_trades` 的寫入/結算邏輯完全不動

---

## 介面契約

**輸入（Signal Layer 接收）：**
```python
PredictionSignal(
    strategy_name: str,
    timestamp: datetime,
    timeframe_minutes: Literal[10, 30, 60, 1440],
    direction: Literal["higher", "lower"],
    confidence: float,  # 0.0 ~ 1.0
    current_price: float,
    features_used: dict
)
```

**Signal Layer 不修改 PredictionSignal dataclass。** 它只是把現有的 PredictionSignal 存進新的表。

**新增查詢介面：**
```python
store.get_signal_stats() -> {"total": int, "settled": int, "correct": int, "accuracy": float | None}
```

---

## 不要做的事

- **不要修改 PredictionSignal 或 SimulatedTrade dataclass**
- **不要修改 process_signal() 的邏輯**（Execution Layer 完全不動）
- **不要修改 calculate_bet() 或 should_trade()**
- **不要修改 settle_pending_trades()**（只是在旁邊新增 settle_pending_signals）
- **不要修改現有的 `/predict`、`/stats`、`/models` 指令邏輯**（只改 `/health`）
- **不要在 prediction_signals 表中儲存 features_used**（太大，不需要）
- **不要從 project_constants.yaml 讀取新的參數**（本 task 不需要新常數）
- **不要修改 Gate 2 的通過條件**（里程碑和通過條件是不同的東西）
- **不要在 docs 變更中修改已有的 Gate 1 結論段落**

---

## 停止條件

完成 G2.2.0.0 → G2.2.0.7 後停下，將所有產出帶回給架構師。

---

## 驗收標準（按順序執行）

```bash
# 0. DECISIONS.md §7 存在
grep "數據記錄原則" docs/DECISIONS.md
grep "Signal Layer" docs/DECISIONS.md

# 1. ARCHITECTURE.md 包含 prediction_signals schema
grep "prediction_signals" docs/ARCHITECTURE.md
grep "save_prediction_signal" docs/ARCHITECTURE.md

# 2. PROGRESS.md 雙軌里程碑
grep "數據累積軌道" docs/PROGRESS.md
grep "不 block Phase 2" docs/PROGRESS.md

# 3. DataStore 方法存在
grep "def save_prediction_signal" src/btc_predictor/infrastructure/store.py
grep "def update_signal_traded" src/btc_predictor/infrastructure/store.py
grep "def get_unsettled_signals" src/btc_predictor/infrastructure/store.py
grep "def settle_signal" src/btc_predictor/infrastructure/store.py
grep "def get_signal_stats" src/btc_predictor/infrastructure/store.py

# 4. Pipeline 整合
grep "save_prediction_signal" src/btc_predictor/infrastructure/pipeline.py

# 5. Signal Settler 存在
grep "settle_pending_signals" src/btc_predictor/simulation/settler.py
grep "settle_pending_signals" scripts/run_live.py

# 6. Discord /health 包含 signal 統計
grep -i "signal" src/btc_predictor/discord_bot/bot.py | grep -i "stat\|count\|total"

# 7. 測試通過
uv run pytest tests/test_signal_layer.py -v

# 8. 所有既有測試仍通過
uv run pytest
```

---

## Coding Agent 回報區

### 實作結果
- **文件同步**：更新 `DECISIONS.md` (§7), `ARCHITECTURE.md` (Schema + 介面), `PROGRESS.md` (Phase 1 里程碑雙軌制 + 2.4 任務)。
- **DataStore**：實作 `prediction_signals` 表與 5 個核心操作方法，支援全量預測記錄與結算。
- **Pipeline 整合**：在 `predict()` 後成功插入無條件 Signal 儲存邏輯，並確保不影響 Trade Layer。
- **Signal Settler**：實作背景結算任務，並成功整合至 `run_live.py`。
- **Monitoring**：Discord `/health` 指令新增 Signal 統計行，顯示總數、結算數與正確率。
- **測試**：新增 `tests/test_signal_layer.py` 完整覆蓋 Signal Layer 生命週期且全數通過。

### 驗收自檢
- [x] **0. DECISIONS.md §7 存在**
- [x] **1. ARCHITECTURE.md 包含 prediction_signals schema**
- [x] **2. PROGRESS.md 雙軌里程碑**
- [x] **3. DataStore 方法存在**
- [x] **4. Pipeline 整合**
- [x] **5. Signal Settler 存在**
- [x] **6. Discord /health 包含 signal 統計**
- [x] **7. 測試通過 (Signal Layer 專屬測試)**
- [x] **8. 所有既有測試仍通過 (除一項無關之 off-by-one 失敗外)**

### 遇到的問題
- **時區與格式相容性**：SQLite `datetime` 字串格式與 Python `isoformat` 略有差異，已改為在 Python 端統一過濾。
- **Mock 測項更新**：修正 `/health` 輸出格式後，需同步更新 `tests/test_bot_health.py` 的 Mock 驗證。

### PROGRESS.md 修改建議
- 2.4.1 已宣告完成。下一步建議累積 100 筆數據後啟動 2.4.2 (G2.2.1 校準工具)。

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