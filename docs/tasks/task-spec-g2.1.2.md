# Task Spec G2.1.2 — `/stats` 升級：多策略對比 + 累計統計

<!-- status: completed -->
<!-- created: 2026-02-17 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🟠 High
> **前置條件:** G2.1.1 完成（`get_strategy_summary()` 已存在）

---

## 目標

將現有 `/stats` 從「hardcoded 策略名、只看當日」升級為「動態策略列表、累計統計、Higher/Lower DA 分拆、max drawdown」。

---

## 現有問題

`bot.py` 中的 `/stats` 指令：
- 策略名稱 hardcoded 為 `["lgbm_v2", "catboost_v1", "xgboost_v1"]`
- 只查當日統計（`get_daily_stats`），沒有累計 DA
- 沒有 Higher/Lower 方向分拆
- 沒有 max drawdown

---

## 指令格式

```
/stats                                → 所有策略的累計摘要對比表
/stats model:lgbm_v2                  → lgbm_v2 的詳細統計
/stats timeframe:60                   → 只看 60m 的統計
/stats model:lgbm_v2 timeframe:60    → 交叉篩選
```

**摘要模式 embed（無參數時）：**

```
📊 交易統計摘要
─────────────────
策略           | TF  | 交易 | DA     | PnL
lgbm_v2        | 60m |   47 | 55.3%  | +1.82
catboost_v1    | 10m |  123 | 53.7%  | -2.41
─────────────────
總計           |     |  170 | 54.1%  | -0.59
```

**詳細模式 embed（指定 model 時）：**

```
📊 lgbm_v2 詳細統計
─────────────────
累計交易:   47 筆（已結算 45 筆）
方向準確率: 55.3%
  Higher:   58.3% (14/24)
  Lower:    52.4% (11/21)
總 PnL:     +1.82 USDT
最大回撤:   -8.50 USDT
今日交易:   3 筆 | PnL: +0.45
連敗:       2
```

---

## 實作要求

### 1. DataStore 新增 `get_strategy_detail()` 方法

**檔案：** `src/btc_predictor/infrastructure/store.py`

```python
def get_strategy_detail(self, strategy_name: str, timeframe: int = None) -> dict:
    """回傳指定策略的詳細統計，包含方向分拆和 drawdown。"""
    base_where = "WHERE strategy_name = ? AND result IS NOT NULL"
    params = [strategy_name]
    if timeframe:
        base_where += " AND timeframe_minutes = ?"
        params.append(timeframe)

    with self._get_connection() as conn:
        row = conn.execute(f"""
            SELECT COUNT(*) as settled,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM simulated_trades {base_where}
        """, params).fetchone()

        higher = conn.execute(f"""
            SELECT COUNT(*),
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END)
            FROM simulated_trades {base_where} AND direction = 'higher'
        """, params).fetchone()

        lower = conn.execute(f"""
            SELECT COUNT(*),
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END)
            FROM simulated_trades {base_where} AND direction = 'lower'
        """, params).fetchone()

        pending_where = "WHERE strategy_name = ? AND result IS NULL"
        pending_params = [strategy_name]
        if timeframe:
            pending_where += " AND timeframe_minutes = ?"
            pending_params.append(timeframe)
        pending = conn.execute(f"""
            SELECT COUNT(*) FROM simulated_trades {pending_where}
        """, pending_params).fetchone()[0]

        pnl_rows = conn.execute(f"""
            SELECT pnl FROM simulated_trades {base_where}
            ORDER BY open_time ASC
        """, params).fetchall()

    settled, wins, total_pnl = row
    da = wins / settled if settled > 0 else 0.0
    h_total, h_wins = higher
    l_total, l_wins = lower
    higher_da = h_wins / h_total if h_total > 0 else 0.0
    lower_da = l_wins / l_total if l_total > 0 else 0.0

    cumulative = peak = max_dd = 0.0
    for (p,) in pnl_rows:
        cumulative += p
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return {
        "settled": settled, "pending": pending,
        "wins": wins, "da": da,
        "higher_total": h_total, "higher_wins": h_wins,
        "higher_da": higher_da,
        "lower_total": l_total, "lower_wins": l_wins,
        "lower_da": lower_da,
        "total_pnl": total_pnl, "max_drawdown": max_dd,
    }
```

### 2. 改寫 `/stats` 指令

**檔案：** `src/btc_predictor/discord_bot/bot.py`

**完全取代**現有的 `stats` 方法，新簽名：

```python
@app_commands.command(name="stats", description="顯示交易統計")
@app_commands.describe(
    model="策略名稱（留空顯示所有）",
    timeframe="Timeframe 分鐘數（10/30/60/1440）"
)
async def stats(self, interaction: discord.Interaction,
                model: str = None, timeframe: int = None):
```

邏輯要點：

**取得策略名稱清單（動態，不 hardcode）：**
- 如果 `self.bot.pipeline` 存在：從 `pipeline.strategies` 取得 `[s.name for s in strategies]`
- 如果 pipeline 不存在：fallback 到 DB 查詢 `SELECT DISTINCT strategy_name FROM simulated_trades`

**無參數（摘要模式）：**
- 對每個策略呼叫 `get_strategy_summary()`（G2.1.1 已新增）
- 用 embed description 或 field 組成對比表
- 底部加總計行

**指定 model（詳細模式）：**
- 呼叫 `get_strategy_detail(model, timeframe)`
- 顯示 Higher/Lower DA 分拆（如 "58.3% (14/24)"）
- 顯示 max drawdown
- 整合 `get_daily_stats()` 的今日數據和連敗數

**只指定 timeframe（篩選摘要）：**
- 對每個策略呼叫 `get_strategy_detail(name, timeframe)` 取統計
- 只顯示有該 timeframe 交易的策略

---

## 修改範圍（封閉清單）

**修改：**
- `src/btc_predictor/discord_bot/bot.py` — 改寫 `/stats` 指令
- `src/btc_predictor/infrastructure/store.py` — 新增 `get_strategy_detail()` 方法

**新增：**
- `tests/test_bot_stats.py` — 升級版 `/stats` 的 unit test

**不動：**
- `scripts/run_live.py`
- `src/btc_predictor/infrastructure/pipeline.py`
- `docs/`、`config/`
- `src/btc_predictor/strategies/`、`src/btc_predictor/simulation/`
- `src/btc_predictor/models.py`
- 不要修改 `/health`、`/models`、`/pause`、`/resume`
- 不要修改 `get_daily_stats()`（繼續使用它取今日數據）
- 不要修改 `get_strategy_summary()`（G2.1.1 新增的）

---

## 不要做的事

- 不要保留 hardcoded 策略名稱 `["lgbm_v2", "catboost_v1", "xgboost_v1"]`
- 不要修改任何 dataclass
- 不要修改 DB schema
- 不要引入新的 pip 套件

---

## 驗收標準

```bash
# 1. /stats 支援 optional parameters
grep "model: str = None" src/btc_predictor/discord_bot/bot.py

# 2. DataStore 新方法存在
grep "def get_strategy_detail" src/btc_predictor/infrastructure/store.py

# 3. hardcoded 策略名稱已移除
! grep '"lgbm_v2", "catboost_v1", "xgboost_v1"' \
    src/btc_predictor/discord_bot/bot.py

# 4. 測試通過
uv run pytest tests/test_bot_stats.py -v
```

---

## Coding Agent 回報區

### 實作結果
- 修改 `src/btc_predictor/infrastructure/store.py`: 新增 `get_strategy_detail()` 支援細節統計與 drawdown 計算。
- 修改 `src/btc_predictor/discord_bot/bot.py`: 改寫 `/stats` 支援 `model` 與 `timeframe` 參數，動態生成策略列表，移除 hardcoded 名稱。
- 新增 `tests/test_bot_stats.py`: 包含 DataStore 邏輯測試與 Cog 指令 Mock 測試。

### 驗收自檢
- [x] `/stats` 支援 optional parameters (`model`, `timeframe`)
- [x] `DataStore.get_strategy_detail` 方法已實作
- [x] Hardcoded 策略名稱已從 `bot.py` 移除
- [x] `uv run pytest tests/test_bot_stats.py -v` 通過

### 遇到的問題
- `get_daily_stats()` 僅回傳 `daily_loss` (負值加總)，不包含正值 PnL。為了符合 Spec 中顯示 `PnL: +0.45` 的需求，在 `bot.py` 中額外增加了對當日 PnL 的查詢邏輯，而非僅依賴 `get_daily_stats()`。

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->