# ARCHITECTURE.md 建議修改

> 此文件列出 ARCHITECTURE.md 需要新增或修改的段落。
> 由架構師審核後，交給 coding agent 執行更新。

---

## 修改 1：系統總覽圖更新

**位置：** `## 系統總覽` 的 ASCII 架構圖

**原因：** 原圖只顯示單策略流程，需反映多模型同時運行的架構。

**替換為：**

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Pipeline Layer                       │
│  Binance WebSocket (1m OHLCV stream)                        │
│  Binance REST API (歷史回填)                                 │
│  [未來] Fear & Greed · DXY · CryptoBERT                     │
└──────────────┬──────────────────────────────────────────────┘
               │ OHLCV DataFrame（共用，只生成一次）
               ▼
┌─────────────────────────────────────────────────────────────┐
│              Strategy Registry (多模型並行)                   │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ xgboost_v1   │ │ lgbm_v1      │ │ mlp_v1       │  ...   │
│  │ (BaseStrategy)│ │ (BaseStrategy)│ │ (BaseStrategy)│        │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘        │
│         │                │                │                 │
│         ▼                ▼                ▼                 │
│    PredictionSignal PredictionSignal PredictionSignal        │
└──────────────┬──────────────────────────────────────────────┘
               │ List[PredictionSignal]
               ▼
┌─────────────────────────────────────────────────────────────┐
│               Decision & Simulation Layer                   │
│  每個 signal 獨立進行：                                      │
│  信心度 ≥ 閾值? → 風控檢查 → SimulatedTrade → SQLite        │
│  統計計算（per strategy × timeframe）                        │
└──────────┬─────────────────────────┬────────────────────────┘
           │                         │
           ▼                         ▼
   CLI 統計報表 / 回測          Discord Bot
   (scripts/backtest.py)       /predict  /stats  /models
                               自動通知（高信心 + 到期結果）
```

---

## 修改 2：新增 Strategy Registry 概念

**位置：** `## 策略基類` 之後新增一個段落

**新增內容：**

```markdown
## Strategy Registry（多模型管理）

系統透過 Strategy Registry 管理多個同時運行的策略。

### 註冊方式

策略透過目錄結構自動發現：

```
src/btc_predictor/strategies/
├── base.py                    # BaseStrategy 基類
├── registry.py                # ★ 策略自動發現與註冊
├── xgboost_v1/                # 每個策略一個目錄
│   ├── __init__.py
│   ├── strategy.py            # 必須有一個繼承 BaseStrategy 的 class
│   ├── features.py            # 策略專屬的特徵工程
│   └── model.py               # 策略專屬的模型邏輯
├── xgboost_v2/
├── lgbm_v1/
├── mlp_v1/
└── ...
```

### Registry 介面

```python
# src/btc_predictor/strategies/registry.py

class StrategyRegistry:
    """自動發現並管理所有策略。"""

    def discover_strategies(self, strategies_dir: Path) -> List[BaseStrategy]:
        """掃描目錄，載入所有繼承 BaseStrategy 的策略。"""
        ...

    def get_strategy(self, name: str) -> BaseStrategy:
        """根據名稱取得策略實例。"""
        ...

    def list_strategies(self) -> List[str]:
        """列出所有已註冊的策略名稱。"""
        ...
```

### 模型檔案位置

已訓練的模型檔案存放在：

```
models/
├── xgboost_v1/
│   ├── 10m.pkl
│   ├── 30m.pkl
│   ├── 60m.pkl
│   └── 1440m.pkl
├── lgbm_v1/
│   ├── 10m.pkl
│   └── ...
└── ...
```

策略載入時自動從對應目錄讀取模型。若模型檔不存在，策略標記為「未訓練」，不參與預測。
```

---

## 修改 3：Discord Bot 介面定義

**位置：** 文件末尾新增段落

**新增內容：**

```markdown
## Discord Bot 指令介面（Gate 2）

### /predict [timeframe]

回傳所有已載入模型對當前市場的預測。

```
📊 BTC 預測結果 (10m)
時間: 2026-02-15 14:30 UTC
當前價格: $97,234.56

┌──────────────┬──────────┬────────────┬──────────┐
│ 策略          │ 方向     │ Confidence │ 下注建議  │
├──────────────┼──────────┼────────────┼──────────┤
│ xgboost_v1   │ 🟢 Higher │ 0.72       │ 12 USDT  │
│ lgbm_v1      │ 🔴 Lower  │ 0.65       │ 8 USDT   │
│ mlp_v1       │ 🟢 Higher │ 0.58       │ —(< 閾值) │
└──────────────┴──────────┴────────────┴──────────┘
```

### /stats [model_name]

不指定 model_name → 摘要對比：

```
📈 模型表現總覽 (Live 模擬)

┌──────────────┬──────┬────────┬────────┬────────┐
│ 策略          │ TF   │ DA     │ Trades │ PnL    │
├──────────────┼──────┼────────┼────────┼────────┤
│ xgboost_v1   │ 10m  │ 52.3%  │ 142    │ -23.5  │
│ xgboost_v1   │ 30m  │ 55.1%  │ 89     │ +12.4  │
│ lgbm_v1      │ 10m  │ 51.8%  │ 138    │ -31.2  │
│ ...          │ ...  │ ...    │ ...    │ ...    │
└──────────────┴──────┴────────┴────────┴────────┘
```

### /models

列出所有已載入模型及狀態。

### 自動通知

**高信心預測通知：**
```
🔔 交易信號
策略: xgboost_v2 | 方向: 🟢 Higher | Confidence: 0.78
Timeframe: 30m | 下注: 15 USDT
當前價格: $97,234.56
到期時間: 2026-02-15 15:00 UTC
```

**到期結果通知：**
```
✅ 交易結果: WIN
策略: xgboost_v2 | 方向: 🟢 Higher (30m)
開盤: $97,234.56 → 收盤: $97,456.78
PnL: +12.75 USDT
```
```

---

## 修改 4：backtest CLI 指令更新

**位置：** AGENTS.md 的 `## 常用指令` 段落

**新增 / 修改：**

```bash
# 訓練指定策略的指定 timeframe
uv run python scripts/train_model.py --strategy <strategy_name> --timeframe <10|30|60|1440>

# 訓練指定策略的所有 timeframe
uv run python scripts/train_model.py --strategy <strategy_name> --all

# 回測指定策略
uv run python scripts/backtest.py --strategy <strategy_name> --timeframe <10|30|60|1440>

# 批量回測所有策略 × 所有 timeframe
uv run python scripts/backtest_all.py
```

注意：`scripts/train_model.py` 是通用訓練入口，取代策略專屬的 `train_xgboost_model.py`。
每個策略的訓練邏輯封裝在策略自己的 `fit()` 方法中。