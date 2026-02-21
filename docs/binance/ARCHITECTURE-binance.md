# System Architecture

## 系統總覽

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
│  信心度 ≥ 閾值? → SimulatedTrade → SQLite        │
│  統計計算（per strategy × timeframe）                        │
└──────────┬─────────────────────────┬────────────────────────┘
           │                         │
           ▼                         ▼
   CLI 統計報表 / 回測          Discord Bot
   (scripts/backtest.py)       /predict  /stats  /models
                               自動通知（高信心 + 到期結果）
```

---

## 介面契約（Interface Contracts）

以下 dataclass 是跨模組溝通的契約。任何策略、引擎、bot 的實作都必須遵守。

### PredictionSignal

所有策略的統一輸出格式。

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

@dataclass
class PredictionSignal:
    strategy_name: str                                  # e.g. "nbeats_perceiver", "xgboost_v1"
    timestamp: datetime                                 # 預測產生時間 (UTC)
    timeframe_minutes: Literal[10, 30, 60, 1440]        # 到期時間框架
    direction: Literal["higher", "lower"]               # 預測方向
    confidence: float                                   # 0.0 ~ 1.0
    current_price: float                                # 預測時的 BTC index price
    features_used: dict = field(default_factory=dict)   # 可解釋性：驅動預測的關鍵特徵
```

### SimulatedTrade

模擬倉引擎的交易記錄。

```python
@dataclass
class SimulatedTrade:
    id: str                                             # UUID
    strategy_name: str
    direction: Literal["higher", "lower"]
    confidence: float
    timeframe_minutes: Literal[10, 30, 60, 1440]
    bet_amount: float                                   # 5–20 USDT
    open_time: datetime                                 # UTC
    open_price: float                                   # 開倉瞬間 BTC index price
    expiry_time: datetime                               # open_time + timeframe
    close_price: float | None = None                    # 到期時 BTC index price（回填）
    result: Literal["win", "lose"] | None = None        # 回填
    pnl: float | None = None                            # 模擬盈虧（回填）
    features_used: dict = field(default_factory=dict)   # 記錄當時使用的特徵 (JSON)
```

PnL 計算邏輯：
- Win: `pnl = bet_amount × (payout_ratio - 1)`（淨利）
- Lose: `pnl = -bet_amount`

### RealTrade (Phase 3)

真實交易記錄，用於比對模擬與真實表現。

```python
@dataclass
class RealTrade:
    signal_id: str                  # 對應的 SimulatedTrade.id
    actual_open_price: float        # Binance App 顯示的 open price
    actual_close_price: float       # 到期後的 close price
    actual_pnl: float               # 真實盈虧
    slippage: float                 # actual_open_price vs signal.current_price 差異
    execution_delay_sec: int        # 收到 Discord 訊號到實際下單的秒數
```

---

## 策略基類

所有策略必須繼承此基類，實作 `predict()` 方法。

```python
# src/btc_predictor/strategies/base.py

from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """所有預測策略的基類。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """策略唯一名稱，用於日誌和資料庫。"""
        ...

    @property
    @abstractmethod
    def requires_fitting(self) -> bool:
        """策略是否需要訓練。"""
        ...

    @property
    def available_timeframes(self) -> list[int]:
        """回傳此策略已有訓練模型的 timeframe list。"""
        ...

    @abstractmethod
    def fit(
        self,
        ohlcv: pd.DataFrame,
        timeframe_minutes: int,
    ) -> None:
        """
        根據歷史數據訓練模型。
        
        Args:
            ohlcv: 包含 open, high, low, close, volume 欄位的 DataFrame，
                   index 為 datetime (UTC)，按時間升序排列。
            timeframe_minutes: 訓練目標的到期時間框架。
        """
        ...

    @abstractmethod
    def predict(
        self,
        ohlcv: pd.DataFrame,
        timeframe_minutes: int,
    ) -> PredictionSignal:
        """
        輸入 OHLCV 數據，輸出預測信號。

        Args:
            ohlcv: 包含 open, high, low, close, volume 欄位的 DataFrame，
                   index 為 datetime (UTC)，按時間升序排列。
            timeframe_minutes: 預測的到期時間框架 (10 | 30 | 60 | 1440)。

        Returns:
            PredictionSignal，包含方向、信心度等資訊。
        """
        ...
```

---

## Strategy Registry（多模型管理）

系統透過 Strategy Registry 管理多個同時運行的策略。

### 策略目錄結構

```
src/btc_predictor/strategies/
├── base.py                    # BaseStrategy 基類
├── registry.py                # ★ 策略自動發現與註冊
├── xgboost_v1/                # 每個策略一個目錄
│   ├── __init__.py
│   ├── strategy.py            # 必須包含一個繼承 BaseStrategy 的 class
│   ├── features.py            # 策略專屬的特徵工程
│   └── model.py               # 策略專屬的模型邏輯
├── lgbm_v1/
└── ...
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
│   └── ...
└── ...
```

策略載入時自動從對應目錄讀取模型。若模型檔不存在，策略標記為「未訓練」，不參與預測。

### Registry 介面

```python
# src/btc_predictor/strategies/registry.py

class StrategyRegistry:
    """自動發現並管理所有策略。"""

    def discover(self, strategies_dir: Path, models_dir: Path) -> None:
        """掃描 strategies_dir 下的子目錄，載入繼承 BaseStrategy 的策略。"""
        ...

    def get(self, name: str) -> BaseStrategy:
        """根據名稱取得策略實例。"""
        ...

    def list_names(self) -> List[str]:
        """列出所有已註冊的策略名稱。"""
        ...

    def list_strategies(self) -> List[BaseStrategy]:
        """列出所有已註冊的策略實例。"""
        ...
```

---

## 資料層

### SQLite Schema

```sql
-- 歷史 K 線
CREATE TABLE ohlcv (
    symbol      TEXT NOT NULL,           -- e.g. "BTCUSDT"
    interval    TEXT NOT NULL,           -- "1m" | "5m" | "1h" | "1d"
    open_time   INTEGER NOT NULL,        -- Unix ms
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      REAL NOT NULL,
    close_time  INTEGER NOT NULL,        -- Unix ms
    PRIMARY KEY (symbol, interval, open_time)
);

-- 模擬交易
CREATE TABLE simulated_trades (
    id                  TEXT PRIMARY KEY,
    strategy_name       TEXT NOT NULL,
    direction           TEXT NOT NULL,       -- "higher" | "lower"
    confidence          REAL NOT NULL,
    timeframe_minutes   INTEGER NOT NULL,
    bet_amount          REAL NOT NULL,
    open_time           TEXT NOT NULL,        -- ISO 8601 UTC
    open_price          REAL NOT NULL,
    expiry_time         TEXT NOT NULL,        -- ISO 8601 UTC
    close_price         REAL,
    result              TEXT,                 -- "win" | "lose"
    pnl                 REAL,
    features_used       TEXT                  -- JSON string
);

-- 真實交易 (Phase 3)
CREATE TABLE real_trades (
    signal_id           TEXT PRIMARY KEY REFERENCES simulated_trades(id),
    actual_open_price   REAL NOT NULL,
    actual_close_price  REAL NOT NULL,
    actual_pnl          REAL NOT NULL,
    slippage            REAL NOT NULL,
    execution_delay_sec INTEGER NOT NULL
);

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

### Data Pipeline

```
Binance REST API  ──→  fetch_history.py  ──→  ohlcv table (歷史回填)
Binance WebSocket ──→  pipeline.py       ──→  ohlcv table (即時更新)
                                          ──→  predict() ──→ save_prediction_signal() ──→ prediction_signals 表（全量）
                                                  │
                                                  └──→ process_signal() ──→ [閾值 + 風控通過] ──→ simulated_trades 表
                                                            │                                          │
                                                            └── 更新 signal.traded = True ──────────────┘

Signal Settler（背景任務）：掃描 prediction_signals 中已到期但未結算的記錄，
查詢收盤價，填入 actual_direction、close_price、is_correct。

- **WebSocket 重連機制**：採指數退避（Exponential backoffs），初始 5 秒，最高 300 秒。
- **健康監控**：每 60 秒檢查一次心跳，若超過 3 分鐘未收 K 線則強制重連。
- **歷史回填**：啟動時自動比對 SQLite 與當前時間，若中斷超過 5 分鐘則透過 REST API 補足缺失 K 線。
- REST API：用於回填歷史數據（1m/5m/1h/1d）
- WebSocket：用於即時監聽，K 線收盤時觸發策略 inference
- 兩者寫入同一張 ohlcv table，用 `(symbol, interval, open_time)` 去重
- 模組路徑皆位於 `src/btc_predictor/` 下（src layout）

### DataStore 介面契約

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

def get_signal_stats(self) -> dict:
    """取得 Signal Layer 統計：{"total": int, "settled": int, "correct": int, "accuracy": float | None}"""

def get_settled_signals(
    self,
    strategy_name: str | None = None,
    timeframe_minutes: int | None = None
) -> pd.DataFrame:
    """取得已結算的 prediction signals，供校準分析使用。"""
```
```

---

## 風控邏輯

```python
# src/btc_predictor/simulation/risk.py
# 邏輯從 config/project_constants.yaml 讀取配置

def should_trade(daily_loss: float, consecutive_losses: int, daily_trades: int) -> bool:
    """檢查各項閾值是否允許繼續交易。"""
    ...

def calculate_bet(confidence: float, timeframe_minutes: int) -> float:
    """根據信心度與 timeframe 閾值計算下注金額。小於閾值返回 0。"""
    ...
```

---

## Phase 2+ 多模態特徵（依優先級逐步接入）

| 優先級 | 特徵 | GPU 需求 | 來源 |
|--------|------|---------|------|
| 1 | 技術指標 (RSI, MACD, BB, ATR) | 無 | 直接計算 |
| 2 | Fear & Greed Index | 無 | alternative.me API |
| 3 | DXY 美元指數 | 無 | Yahoo Finance API |
| 4 | CryptoBERT 情緒 | ~2GB VRAM | ElKulako/cryptobert (inference only) |
| 5 | 鏈上指標 (NVT, MVRV, SOPR) | 無 | Glassnode API (付費) |

---

## Discord Bot 指令介面（Gate 2）

### /predict [timeframe]
用當前市場數據跑所有已載入模型，回傳每個模型的預測方向 + confidence + 下注建議。

### /stats [model_name]
- 不指定 model_name → 顯示所有模型的摘要對比表（DA、Trades、PnL）
- 指定 model_name → 顯示該模型的詳細統計（含校準、drawdown）

### /models
列出所有已載入模型及其回測表現摘要 + live 運行狀態。

### 自動通知
- 當任何策略 confidence > threshold 時，自動發送「交易信號」通知
- 到期時自動發送結果通知（是否獲勝 + PnL）