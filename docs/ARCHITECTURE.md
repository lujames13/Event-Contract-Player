# System Architecture

## 系統總覽

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Pipeline Layer                       │
│  Binance WebSocket (OHLCV stream) · Fear & Greed Index      │
│  [Phase 2+] CryptoBERT 情緒 · 鏈上指標 · DXY              │
└──────────────┬──────────────────────────────────────────────┘
               │ OHLCV DataFrame + 特徵
               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Prediction Engine Layer                      │
│  各策略繼承 BaseStrategy                                     │
│  每個策略獨立輸出 PredictionSignal                            │
└──────────────┬──────────────────────────────────────────────┘
               │ PredictionSignal
               ▼
┌─────────────────────────────────────────────────────────────┐
│               Decision & Simulation Layer                   │
│  信心度 ≥ 閾值? → SimulatedTrade → SQLite                   │
│  風控檢查 → 統計計算                                         │
└──────────┬─────────────────────────┬────────────────────────┘
           │                         │
           ▼                         ▼
   Phase 2: CLI 統計報表     Phase 3: Discord Bot → RealTrade
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
```

### Data Pipeline

```
Binance REST API  ──→  fetch_history.py  ──→  ohlcv table (歷史回填)
Binance WebSocket ──→  pipeline.py       ──→  ohlcv table (即時更新)
                                          ──→  觸發各策略 predict()
```

- REST API：用於回填歷史數據（1m/5m/1h/1d）
- WebSocket：用於即時監聽，K 線收盤時觸發策略 inference
- 兩者寫入同一張 ohlcv table，用 `(symbol, interval, open_time)` 去重
- 模組路徑皆位於 `src/btc_predictor/` 下（src layout）

---

## 風控邏輯

```python
# src/btc_predictor/simulation/risk.py

CONFIDENCE_THRESHOLDS = {10: 0.606, 30: 0.591, 60: 0.591, 1440: 0.591}
PAYOUT_RATIOS = {10: 1.80, 30: 1.85, 60: 1.85, 1440: 1.85}

def should_trade(daily_loss: float, consecutive_losses: int, daily_trades: int) -> bool:
    """檢查是否允許交易。"""
    if daily_loss >= 50:        return False   # daily_max_loss
    if consecutive_losses >= 8: return False   # 暫停 1 小時
    if daily_trades >= 30:      return False   # max_daily_trades
    return True

def calculate_bet(confidence: float, timeframe_minutes: int) -> float:
    """根據信心度計算下注金額。低於閾值返回 0。"""
    threshold = CONFIDENCE_THRESHOLDS[timeframe_minutes]
    if confidence < threshold:
        return 0.0
    return 5 + (confidence - threshold) / (1.0 - threshold) * 15
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