# Task Spec G2.1.5 — `/help` 指令 + Slash Command UX 改善

<!-- status: completed -->
<!-- created: 2026-02-18 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🟢 Low — 功能性零影響，純 UX 改善
> **前置條件:** G2.1.0~G2.1.4 完成

---

## 目標

三項 UX 改善：

1. 新增 `/help` 指令，列出所有可用指令及說明
2. 所有 `timeframe` 參數改用 `app_commands.Choice`，使用者從 4 個固定選項中點選
3. 所有 `model` 參數改用 `autocomplete`，動態列出已載入的策略名稱

---

## 背景

目前使用者需要手動輸入 timeframe 數字（容易打錯，例如輸入 `1440` 才代表 1 天）和精確的 model 名稱（需要記住 `lgbm_v2` 等字串）。改善後，所有參數都能從下拉選單點選。

---

## 實作要求

### 1. Timeframe Choice 定義（檔案頂部常數）

**檔案：** `src/btc_predictor/discord_bot/bot.py`

在 `CONFIDENCE_THRESHOLDS` 附近新增：

```python
TIMEFRAME_CHOICES = [
    app_commands.Choice(name="10 分鐘", value=10),
    app_commands.Choice(name="30 分鐘", value=30),
    app_commands.Choice(name="1 小時", value=60),
    app_commands.Choice(name="1 天", value=1440),
]
```

### 2. Model Autocomplete Callback

**檔案：** `src/btc_predictor/discord_bot/bot.py`

在 `EventContractCog` class 中新增 autocomplete callback：

```python
async def model_autocomplete(
    self, interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """動態回傳已載入的策略名稱。"""
    pipeline = getattr(self.bot, 'pipeline', None)
    if not pipeline or not pipeline.strategies:
        return []
    
    names = [s.name for s in pipeline.strategies]
    # 過濾：如果使用者已輸入部分文字，只顯示匹配的
    if current:
        names = [n for n in names if current.lower() in n.lower()]
    
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]
```

> Discord autocomplete 上限 25 個選項，目前策略數遠低於此，但加上 `[:25]` 防禦。

### 3. 改寫 `/predict` 指令簽名

**改動前：**
```python
@app_commands.command(name="predict", description="手動觸發即時預測")
@app_commands.describe(timeframe="Timeframe 分鐘數（10/30/60/1440）")
async def predict(self, interaction: discord.Interaction,
                  timeframe: int = None):
```

**改動後：**
```python
@app_commands.command(name="predict", description="手動觸發即時預測")
@app_commands.describe(timeframe="選擇預測時間框架")
@app_commands.choices(timeframe=TIMEFRAME_CHOICES)
async def predict(self, interaction: discord.Interaction,
                  timeframe: app_commands.Choice[int] = None):
```

**函數內部取值方式變更：**
- 改動前：`timeframe` 直接是 `int` 或 `None`
- 改動後：`timeframe` 是 `app_commands.Choice[int]` 或 `None`，實際值用 `timeframe.value`

需要在函數開頭做轉換，讓下游邏輯不變：

```python
tf_value = timeframe.value if timeframe else None
```

然後把原本所有用到 `timeframe` 的地方替換成 `tf_value`。

### 4. 改寫 `/stats` 指令簽名

**改動前：**
```python
@app_commands.command(name="stats", description="顯示交易統計")
@app_commands.describe(
    model="策略名稱（留空顯示所有）",
    timeframe="Timeframe 分鐘數（10/30/60/1440）"
)
async def stats(self, interaction: discord.Interaction,
                model: str = None, timeframe: int = None):
```

**改動後：**
```python
@app_commands.command(name="stats", description="顯示交易統計")
@app_commands.describe(
    model="選擇策略（留空顯示所有）",
    timeframe="選擇時間框架（留空顯示所有）"
)
@app_commands.choices(timeframe=TIMEFRAME_CHOICES)
async def stats(self, interaction: discord.Interaction,
                model: str = None,
                timeframe: app_commands.Choice[int] = None):
```

**同樣在函數開頭做轉換：**
```python
tf_value = timeframe.value if timeframe else None
```

然後把原本所有用到 `timeframe` 的地方替換成 `tf_value`。

**Autocomplete 綁定**（用寫法 A，在 Cog 內更可靠）：

```python
@stats.autocomplete('model')
async def stats_model_autocomplete(self, interaction: discord.Interaction, current: str):
    return await self.model_autocomplete(interaction, current)
```

> 這段需要放在 `stats` 方法定義之後。`model_autocomplete` 是共用邏輯，`stats_model_autocomplete` 是綁定到 `/stats` 的 wrapper。

> **注意：** `model` 參數型別仍然是 `str`，autocomplete 只是提供建議，不強制。這是 discord.py 的設計——autocomplete 參數的型別不變，只是多了下拉建議。

### 5. 新增 `/help` 指令

```python
@app_commands.command(name="help", description="顯示所有可用指令")
async def help_command(self, interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Event Contract Bot — 指令總覽",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🔍 觀測",
        value=(
            "`/health` — 系統健康檢查（WebSocket、Pipeline、DB）\n"
            "`/models` — 已載入模型及 live 表現"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 交易",
        value=(
            "`/predict [timeframe]` — 即時預測（可選時間框架）\n"
            "`/stats [model] [timeframe]` — 交易統計摘要或詳細"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ 控制",
        value=(
            "`/pause` — 暫停訊號推送\n"
            "`/resume` — 恢復訊號推送"
        ),
        inline=False
    )
    
    embed.set_footer(text="💡 所有參數都可從下拉選單選取，不需手動輸入")
    
    await interaction.response.send_message(embed=embed)
```

> 方法名用 `help_command` 避免與 Python 內建 `help()` 或 discord.py default help 衝突。

### 6. Autocomplete 裝飾器語法注意

discord.py 的 `@app_commands.autocomplete` 在 Cog 內有兩種寫法：

**寫法 A（推薦）— 用 command 方法的 decorator：**
```python
@stats.autocomplete('model')
async def stats_model_autocomplete(self, interaction, current):
    ...
```

**寫法 B — 在 command decorator 中引用：**
```python
@app_commands.autocomplete(model=model_autocomplete)
```

> Coding agent 請依 discord.py 2.x 文件選擇在 Cog 內能正確運作的寫法。**寫法 A 在 Cog 中更可靠**，因為 Cog 方法的 binding 在 decorator 階段可能尚未完成。如果選寫法 A，autocomplete wrapper 需定義在對應 command 方法之後。

---

## 修改範圍（封閉清單）

**修改：**
- `src/btc_predictor/discord_bot/bot.py`：
  - 新增 `TIMEFRAME_CHOICES` 常數
  - 新增 `model_autocomplete` 共用方法
  - 改寫 `/predict` 簽名（Choice）+ 內部 `tf_value` 轉換
  - 改寫 `/stats` 簽名（Choice + autocomplete）+ 內部 `tf_value` 轉換
  - 新增 `/help` 指令

**不動：**
- `scripts/run_live.py`
- `src/btc_predictor/infrastructure/store.py`
- `src/btc_predictor/infrastructure/pipeline.py`
- `docs/`、`config/`
- `src/btc_predictor/strategies/`、`src/btc_predictor/simulation/`
- `src/btc_predictor/models.py`
- `/health`、`/models`、`/pause`、`/resume` 的邏輯不動
- 不新增測試檔案

---

## 不要做的事

- **不要把 `model` 參數也改成 `Choice`**（策略是動態載入的，不能 hardcode）
- **不要移除 `model` 參數接受手動輸入的能力**（autocomplete 是建議，不是強制）
- **不要修改 `/predict` 和 `/stats` 的核心邏輯**（只改簽名和參數解包方式）
- **不要動態讀取 command tree 來生成 `/help` 內容**（hardcode 即可）
- 不要修改 DB schema
- 不要引入新的 pip 套件
- 不要新增測試檔案（純 UI 層改動，無邏輯分支）

---

## 驗收標準

```bash
# 1. TIMEFRAME_CHOICES 常數存在
grep 'TIMEFRAME_CHOICES' src/btc_predictor/discord_bot/bot.py

# 2. /predict 使用 choices
grep -A2 'name="predict"' src/btc_predictor/discord_bot/bot.py | grep -i 'choice'

# 3. /stats 使用 autocomplete
grep 'autocomplete' src/btc_predictor/discord_bot/bot.py

# 4. /help 指令存在
grep 'name="help"' src/btc_predictor/discord_bot/bot.py

# 5. model_autocomplete 方法存在
grep 'model_autocomplete' src/btc_predictor/discord_bot/bot.py

# 6. 所有 6 個指令在 help embed 中被提及
for cmd in health models predict stats pause resume; do
  grep -q "/$cmd" src/btc_predictor/discord_bot/bot.py && echo "$cmd: ✅" || echo "$cmd: ❌"
done
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