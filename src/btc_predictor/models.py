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

@dataclass
class RealTrade:
    signal_id: str                  # 對應的 SimulatedTrade.id
    actual_open_price: float        # Binance App 顯示的 open price
    actual_close_price: float       # 到期後的 close price
    actual_pnl: float               # 真實盈虧
    slippage: float                 # actual_open_price vs signal.current_price 差異
    execution_delay_sec: int        # 收到 Discord 訊號到實際下單的秒數
