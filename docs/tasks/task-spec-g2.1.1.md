# Task Spec G2.1.1 — `/models` 已載入模型總覽

<!-- status: draft -->
<!-- created: 2026-02-17 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🟠 High
> **前置條件:** G2.1.0 完成（bot 已有 `self.bot.pipeline` 存取能力）

---

## 目標

新增 `/models` slash command，列出所有已載入策略及其 timeframe、交易數、DA、PnL。同時新增 `DataStore.get_strategy_summary()` 方法供本任務及後續任務使用。

---

## 輸出 embed 格式

```
🤖 已載入模型
─────────────────
📈 lgbm_v2
   Timeframes: 60m
   Live 交易: 47 筆 | DA: 55.3% | PnL: +1.82 USDT

📈 catboost_v1
   Timeframes: 10m
   Live 交易: 123 筆 | DA: 53.7% | PnL: -2.41 USDT
```

---

## 實作要求

### 1. DataStore 新增 `get_strategy_summary()` 方法

**檔案：** `src/btc_predictor/infrastructure/store.py`

```python
def get_strategy_summary(self, strategy_name: str) -> dict:
    """回傳指定策略的累計統計摘要。"""
    with self._get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result IS NOT NULL THEN 1 ELSE 0 END) as settled,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM simulated_trades
            WHERE strategy_name = ?
        """, (strategy_name,)).fetchone()
    total, wins, settled, pnl = row
    da = wins / settled if settled > 0 else 0.0
    return {
        "total_trades": total,
        "settled_trades": settled,
        "wins": wins,
        "da": da,
        "total_pnl": pnl
    }
```

### 2. Bot 新增 `/models` 指令

**檔案：** `src/btc_predictor/discord_bot/bot.py`

在 `EventContractCog` 中新增：

```python
@app_commands.command(name="models", description="列出所有已載入模型")
async def models(self, interaction: discord.Interaction):
```

邏輯要點：
- 從 `self.bot.pipeline.strategies` 取得策略清單
- 如果 `self.bot.pipeline is None`，回傳「無法取得模型清單（Pipeline 未連線）」
- 對每個策略：
  - 顯示 `strategy.name`
  - 顯示 `strategy.available_timeframes`（用 `", ".join` 格式化為 "10m, 60m"）
  - 用 `self.bot.store.get_strategy_summary(strategy.name)` 取得統計
  - DA 以百分比顯示（如 "55.3%"），PnL 帶 +/- 符號（如 "+1.82"）
- 無已結算交易時顯示「尚無交易紀錄」
- 使用 `interaction.response.defer()` 後用 `followup.send`（DB 查詢可能稍慢）

---

## 修改範圍（封閉清單）

**修改：**
- `src/btc_predictor/discord_bot/bot.py` — 新增 `/models` 指令
- `src/btc_predictor/infrastructure/store.py` — 新增 `get_strategy_summary()` 方法

**新增：**
- `tests/test_bot_models.py` — `/models` 指令的 unit test

**不動：**
- `scripts/run_live.py` — 已在 G2.1.0 修改完畢
- `src/btc_predictor/infrastructure/pipeline.py` — 已在 G2.1.0 修改完畢
- `docs/` — 所有文件不動
- `config/` — 不動
- `src/btc_predictor/strategies/` — 不動
- `src/btc_predictor/simulation/` — 不動
- `src/btc_predictor/models.py` — 不動
- 不要修改 G2.1.0 新增的 `/health` 指令

---

## 不要做的事

- 不要修改任何 dataclass
- 不要修改 pipeline 邏輯
- 不要修改現有指令（`/health`、`/stats`、`/pause`、`/resume`）
- 不要引入新的 pip 套件
- 不要修改 DB schema

---

## 驗收標準

```bash
# 1. /models 指令存在
grep 'name="models"' src/btc_predictor/discord_bot/bot.py

# 2. DataStore 新方法存在
grep "def get_strategy_summary" src/btc_predictor/infrastructure/store.py

# 3. 測試通過
uv run pytest tests/test_bot_models.py -v
```

---

## Coding Agent 回報區

### 實作結果
- 新增 `DataStore.get_strategy_summary()` 於 `src/btc_predictor/infrastructure/store.py`，用於查詢策略累計統計。
- 新增 `/models` slash command 於 `src/btc_predictor/discord_bot/bot.py`，以 Embed 格式展示已載入模型狀態。
- 新增 `tests/test_bot_models.py` 並通過測試。

### 驗收自檢
1. `/models` 指令存在：✅ (`grep` 通過)
2. `DataStore.get_strategy_summary` 存在：✅ (`grep` 通過)
3. 測試通過：✅ (`pytest tests/test_bot_models.py` 通過)

### 遇到的問題
- 無。

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->