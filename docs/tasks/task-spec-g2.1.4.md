# Task Spec G2.1.4 — 自動通知強化：信號 + 結算 embed 升級

<!-- status: completed -->
<!-- created: 2026-02-17 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🟡 Medium
> **前置條件:** G2.1.1 完成（`get_strategy_summary()` 已存在）

---

## 目標

升級 `send_signal()` 和 `send_settlement()` 的 embed 格式，加入閾值資訊和累計統計，讓被動通知也能提供足夠的決策資訊。

---

## 現有問題

- `send_signal()`：有基礎 embed，但缺少「是否達到下注閾值」和「閾值是多少」
- `send_settlement()`：有基礎 embed，但缺少累計統計（DA、PnL）

---

## 實作要求

### 1. 升級 `send_signal()` embed

**檔案：** `src/btc_predictor/discord_bot/bot.py`

目標 embed 格式：
```
🔮 [lgbm_v2] BTCUSDT 60m → HIGHER
─────────────────
📊 信心度:    0.6234
💰 下注建議:  ✅ 8.2 USDT
📍 開倉價:    $104,231.50
⏰ 到期:      2026-02-17 15:00 UTC
🎯 閾值:      0.591（已超過）
```

修改要點：
- 新增「🎯 閾值」field，顯示該 timeframe 的閾值和「已超過」/「未達」
- 使用 `CONFIDENCE_THRESHOLDS` 常數（G2.1.3 已新增在 bot 頂部）
- 如果 G2.1.3 尚未完成，在本任務中新增該常數：
  ```python
  CONFIDENCE_THRESHOLDS = {10: 0.606, 30: 0.591, 60: 0.591, 1440: 0.591}
  ```
- 保持現有的 `if self.paused: return` 邏輯

### 2. 升級 `send_settlement()` embed

目標 embed 格式：
```
✅ WIN [lgbm_v2] 60m HIGHER
─────────────────
開倉: $104,231.50 → 收盤: $104,450.20
盈虧: +7.00 USDT
─────────────────
📊 累計: 48 筆 | DA 55.3% | PnL +8.82
```

修改要點：
- 結算時呼叫 `self.bot.store.get_strategy_summary(trade.strategy_name)` 取得累計數據
- 新增「📊 累計」field，顯示總筆數、DA%、累計 PnL
- 用 `asyncio.to_thread` 包裝 `get_strategy_summary` DB 查詢
- 如果查詢失敗，跳過累計統計（不影響主要結算通知）

### 3. 確保向後相容

- `send_signal(trade)` 和 `send_settlement(trade)` 的方法簽名不變
- trade 物件的欄位不變（讀取 `trade.strategy_name`、`trade.timeframe_minutes`、`trade.confidence` 等現有欄位）
- `/pause` 和 `/resume` 行為不變

---

## 修改範圍（封閉清單）

**修改：**
- `src/btc_predictor/discord_bot/bot.py` — 修改 `send_signal()` 和 `send_settlement()` 的 embed 建構邏輯

**新增：**
- `tests/test_bot_notifications.py` — 通知 embed 的 unit test

**不動：**
- `scripts/run_live.py`
- `src/btc_predictor/infrastructure/store.py` — `get_strategy_summary()` 已在 G2.1.1 新增
- `src/btc_predictor/infrastructure/pipeline.py`
- `docs/`、`config/`
- `src/btc_predictor/strategies/`、`src/btc_predictor/simulation/`
- `src/btc_predictor/models.py`
- 不要修改 `/health`、`/models`、`/stats`、`/predict`、`/pause`、`/resume` 指令

---

## 不要做的事

- 不要改變 `send_signal()` 或 `send_settlement()` 的方法簽名
- 不要改變 trade 物件的結構或 dataclass
- 不要修改 pipeline 的 `_trigger_strategies` 呼叫邏輯
- 不要修改 settler.py 的結算邏輯
- 不要引入新的 pip 套件
- 不要修改 DB schema

---

## 驗收標準

```bash
# 1. send_signal 包含閾值資訊
grep "閾值\|CONFIDENCE_THRESHOLDS" src/btc_predictor/discord_bot/bot.py

# 2. send_settlement 呼叫 get_strategy_summary
grep "get_strategy_summary" src/btc_predictor/discord_bot/bot.py

# 3. 方法簽名未變
grep "async def send_signal(self, trade)" \
    src/btc_predictor/discord_bot/bot.py
grep "async def send_settlement(self, trade)" \
    src/btc_predictor/discord_bot/bot.py

# 4. 測試通過
uv run pytest tests/test_bot_notifications.py -v
```

---

### 實作結果
- 升級了 `src/btc_predictor/discord_bot/bot.py` 中的 `send_signal()`，在 embed description 中加入「🎯 閾值」資訊與下注建議狀態。
- 升級了 `send_settlement()`，透過 `get_strategy_summary` 取得並顯示「📊 累計」統計資料（筆數、DA、PnL）。
- 建立了 `tests/test_bot_notifications.py` 進行新 embed 格式的單元測試與 Mock 驗證。

### 驗收自檢
- [x] 1. send_signal 包含閾值資訊 (包含 `CONFIDENCE_THRESHOLDS` 邏輯)
- [x] 2. send_settlement 呼叫 get_strategy_summary 並顯示累計數據
- [x] 3. 方法簽名未變 (保持 `async def send_signal(self, trade)` 等)
- [x] 4. 測試通過 (`pytest tests/test_bot_notifications.py`)

### 遇到的問題
<!-- 技術障礙、設計疑慮 -->

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->