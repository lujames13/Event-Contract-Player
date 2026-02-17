# Task Spec G2.1.3 — `/predict` 手動觸發即時預測

<!-- status: draft -->
<!-- created: 2026-02-17 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🟠 High
> **前置條件:** G2.1.0 完成（bot 已有 `self.bot.pipeline` 存取能力）

---

## 目標

新增 `/predict` slash command，手動觸發所有已載入模型的即時預測，回傳方向、信心度、下注建議。這是驗證「模型推理是否正常」的最直接方式。

---

## 指令格式

```
/predict                      → 跑所有策略的所有 timeframe
/predict timeframe:60         → 只跑 60m
```

## 輸出 embed 格式

```
🔮 即時預測（基於最新 K 線: 2026-02-17 14:32 UTC）
─────────────────
📈 lgbm_v2 | 60m
   方向: HIGHER | 信心度: 0.6234
   下注建議: ✅ 8.2 USDT（超過閾值 0.591）

📈 catboost_v1 | 10m
   方向: LOWER | 信心度: 0.5501
   下注建議: ❌ 不下注（低於閾值 0.606）

⏱️ 推理耗時: 0.34s
```

---

## 實作要求

### Bot 新增 `/predict` 指令

**檔案：** `src/btc_predictor/discord_bot/bot.py`

**指令簽名：**

```python
@app_commands.command(name="predict", description="手動觸發即時預測")
@app_commands.describe(timeframe="Timeframe 分鐘數（10/30/60/1440）")
async def predict(self, interaction: discord.Interaction,
                  timeframe: int = None):
```

**信心度閾值（hardcode 在 bot 頂部，從 DECISIONS.md 複製）：**

```python
CONFIDENCE_THRESHOLDS = {10: 0.606, 30: 0.591, 60: 0.591, 1440: 0.591}
```

**邏輯要點：**

1. `defer()` 先回應（推理可能需要幾秒）
2. 檢查 pipeline 是否存在，不存在回傳錯誤
3. 從 DB 取最新數據：`store.get_latest_ohlcv("BTCUSDT", "1m", limit=500)`
4. 如果 DB 無數據，回傳「資料庫無 K 線數據，無法預測」
5. 記錄最新 K 線時間用於 embed 標題
6. 記錄開始時間（用於計算推理耗時）
7. 遍歷 `pipeline.strategies`：
   ```python
   for strategy in self.bot.pipeline.strategies:
       for tf in strategy.available_timeframes:
           if timeframe and tf != timeframe:
               continue
           try:
               signal = await asyncio.to_thread(strategy.predict, df, tf)
               # 組裝結果
           except Exception as e:
               # 該策略顯示 "❌ 推理失敗: {e}"
   ```
8. **使用 `asyncio.to_thread`** 包裝 predict（CPU-intensive，避免阻塞事件循環）
9. 下注建議判斷：
   - `confidence >= CONFIDENCE_THRESHOLDS[tf]` → ✅ 顯示計算的下注金額
   - 否則 → ❌ 不下注
   - 下注金額計算（線性映射）：`bet = 5 + (confidence - threshold) / (1.0 - threshold) * 15`
10. 計算推理總耗時，顯示在 embed 底部

**錯誤隔離**：單一策略 predict 拋 exception 時，其他策略繼續跑。失敗的策略在 embed 中顯示錯誤訊息。

---

## 修改範圍（封閉清單）

**修改：**
- `src/btc_predictor/discord_bot/bot.py` — 新增 `/predict` 指令 + `CONFIDENCE_THRESHOLDS` 常數

**新增：**
- `tests/test_bot_predict.py` — `/predict` 指令的 unit test

**不動：**
- `scripts/run_live.py`
- `src/btc_predictor/data/store.py` — 不新增方法（用現有的 `get_latest_ohlcv`）
- `src/btc_predictor/data/pipeline.py`
- `docs/`、`config/`
- `src/btc_predictor/strategies/`、`src/btc_predictor/simulation/`
- `src/btc_predictor/models.py`
- 不要修改 `/health`、`/models`、`/stats`、`/pause`、`/resume`

---

## 不要做的事

- **不要在 bot 中 import project_constants.yaml**（閾值 hardcode，避免 path 依賴）
- **不要實作自動下單**（純顯示，不執行交易）
- **不要建立新的 predict 邏輯**（直接呼叫 `strategy.predict()`）
- 不要修改任何 dataclass
- 不要修改 DB schema
- 不要引入新的 pip 套件

---

## 驗收標準

```bash
# 1. /predict 指令存在
grep 'name="predict"' src/btc_predictor/discord_bot/bot.py

# 2. 閾值常數存在
grep "CONFIDENCE_THRESHOLDS" src/btc_predictor/discord_bot/bot.py

# 3. 使用 asyncio.to_thread
grep "asyncio.to_thread" src/btc_predictor/discord_bot/bot.py

# 4. 測試通過
uv run pytest tests/test_bot_predict.py -v
```

---

## Coding Agent 回報區

### 實作結果
<!-- 完成了什麼，修改了哪些檔案 -->

### 驗收自檢
<!-- 逐條列出驗收標準的 pass/fail -->

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