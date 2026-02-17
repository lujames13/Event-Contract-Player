# Task Spec G2.1.0 — `/health` 系統健康檢查指令

<!-- status: draft -->
<!-- created: 2026-02-17 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🔴 最高 — 目前無法確認 live pipeline 是否在運行
> **前置條件:** G2.0 已完成並運行中

---

## 目標

新增 `/health` slash command，讓使用者一個指令就能確認系統各組件是否正常運行。

---

## 背景

目前 live pipeline 已在運行，但使用者完全無法觀測狀態：不知道 WebSocket 是否連線、策略有沒有被觸發、DB 有沒有在寫入。`/health` 是最基礎的觀測能力。

---

## 輸出 embed 格式

```
🏥 系統健康檢查
─────────────────
🔌 WebSocket:  ✅ 連線中 | 最後收到 K 線: 2 秒前
📊 Pipeline:   ✅ 運行中 | 已觸發策略: 142 次
🤖 策略數:     2 個已載入
💾 DB:         ✅ | ohlcv: 523,412 筆 | trades: 87 筆
⏱️ Uptime:     3d 14h 22m
```

---

## 實作要求

### 1. Pipeline 新增 `trigger_count` 屬性

**檔案：** `src/btc_predictor/data/pipeline.py`

在 `DataPipeline.__init__` 中新增：
```python
self.trigger_count = 0
```

在 `_trigger_strategies` 方法開頭新增：
```python
self.trigger_count += 1
```

### 2. run_live.py 將 pipeline 傳給 bot

**檔案：** `scripts/run_live.py`

在建立 pipeline 之後、啟動之前，新增一行：
```python
bot.pipeline = pipeline
```

具體位置：在 `pipeline = DataPipeline(...)` 之後、`asyncio.create_task(pipeline.start())` 之前。同時在 bot 初始化後加上預設值：
```python
bot.pipeline = None  # Will be set after pipeline creation
```

### 3. DataStore 新增 `get_table_counts()` 方法

**檔案：** `src/btc_predictor/data/store.py`

```python
def get_table_counts(self) -> dict[str, int]:
    """回傳各 table 的 row count。"""
    with self._get_connection() as conn:
        ohlcv_count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        trades_count = conn.execute("SELECT COUNT(*) FROM simulated_trades").fetchone()[0]
    return {"ohlcv": ohlcv_count, "simulated_trades": trades_counts}
```

### 4. Bot 新增 uptime 追蹤 + `/health` 指令

**檔案：** `src/btc_predictor/discord_bot/bot.py`

在 `EventContractBot.__init__` 中新增：
```python
self.pipeline = None
self.start_time = None
```

在 `on_ready` 中新增：
```python
self.start_time = datetime.now(timezone.utc)
```

在 `EventContractCog` 中新增 `/health` 指令：

```python
@app_commands.command(name="health", description="顯示系統健康狀態")
async def health(self, interaction: discord.Interaction):
```

邏輯要點：
- 用 `self.bot.pipeline` 讀取 pipeline 狀態（`is_running`、`last_kline_time`、`trigger_count`、`strategies`）
- 如果 `self.bot.pipeline is None`，顯示「Pipeline: ❌ 未連線」
- 用 `self.bot.store.get_table_counts()` 讀取 DB 筆數
- 用 `self.bot.start_time` 計算 uptime
- WebSocket 狀態：取 `pipeline.last_kline_time` 中最近的時間，計算距離現在幾秒

---

## 修改範圍（封閉清單）

**修改：**
- `src/btc_predictor/discord_bot/bot.py` — 新增 `/health` 指令 + `pipeline` 和 `start_time` 屬性
- `src/btc_predictor/data/store.py` — 新增 `get_table_counts()` 方法
- `src/btc_predictor/data/pipeline.py` — 新增 `trigger_count` 屬性（init + increment）
- `scripts/run_live.py` — 新增 `bot.pipeline = pipeline`

**新增：**
- `tests/test_bot_health.py` — `/health` 指令的 unit test

**不動：**
- `docs/` — 所有文件不動
- `config/` — 不動
- `src/btc_predictor/strategies/` — 不動
- `src/btc_predictor/backtest/` — 不動
- `src/btc_predictor/simulation/` — 不動
- `src/btc_predictor/models.py` — 不動

---

## 不要做的事

- 不要修改任何 dataclass（PredictionSignal、SimulatedTrade）
- 不要修改 pipeline 的觸發邏輯或 WebSocket 處理（只加一個 counter）
- 不要修改現有的 `/stats`、`/pause`、`/resume` 指令
- 不要修改 `send_signal()` 或 `send_settlement()`
- 不要引入新的 pip 套件
- 不要修改 DB schema

---

## 驗收標準

```bash
# 1. /health 指令存在
grep 'name="health"' src/btc_predictor/discord_bot/bot.py

# 2. DataStore 新方法存在
grep "def get_table_counts" src/btc_predictor/data/store.py

# 3. Pipeline trigger_count 存在
grep "trigger_count" src/btc_predictor/data/pipeline.py

# 4. run_live.py 傳遞 pipeline 給 bot
grep "bot.pipeline" scripts/run_live.py

# 5. 測試通過
uv run pytest tests/test_bot_health.py -v
```

---

## Coding Agent 回報區

### 實作結果
- 🟢 **src/btc_predictor/data/pipeline.py**: 新增 `trigger_count` 追蹤策略觸發次數。
- 🟢 **src/btc_predictor/data/store.py**: 新增 `get_table_counts()` 用於統計 OHLCV 與交易筆數。
- 🟢 **src/btc_predictor/discord_bot/bot.py**:
    - 新增 `pipeline` 與 `start_time` 屬性。
    - 實作 `/health` 指令，整合 WebSocket 狀態、Pipeline 進度、DB 統計與 Uptime。
    - `on_ready` 時自動記錄啟動時間。
- 🟢 **scripts/run_live.py**: 在啟動時將 `pipeline` 實例傳遞給 `bot`。
- 🟢 **tests/test_bot_health.py**: 新增單元測試，驗證指令邏輯。

### 驗收自檢
- [x] 1. `/health` 指令存在
- [x] 2. DataStore 新方法存在
- [x] 3. Pipeline trigger_count 存在
- [x] 4. run_live.py 傳遞 pipeline 給 bot
- [x] 5. 測試通過 (`uv run pytest tests/test_bot_health.py -v`)

### 遇到的問題
- 無。實作過程順利，已修正 Task Spec 中的一點小 typo (`trades_counts` -> `trades_count`)。

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->