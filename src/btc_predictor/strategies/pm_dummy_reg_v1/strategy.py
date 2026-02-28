import pandas as pd
from typing import List
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal

class DummyRegressionStrategy(BaseStrategy):
    SCALE_FACTOR = 5.0

    @property
    def name(self) -> str:
        return "pm_dummy_reg_v1"

    @property
    def requires_fitting(self) -> bool:
        return False

    @property
    def available_timeframes(self) -> List[int]:
        return [5, 15]

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        pass

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        if ohlcv.empty:
            raise ValueError("OHLCV data is empty")
        
        # dummy logic: simple moving average crossover difference as "predicted change"
        if len(ohlcv) < 5:
            predicted_change_pct = 0.1 # default slightly higher to avoid 0
        else:
            recent_close = ohlcv["close"].iloc[-1]
            ma5 = ohlcv["close"].iloc[-5:].mean()
            predicted_change_pct = (recent_close - ma5) / ma5 * 100
            
        if predicted_change_pct == 0.0:
            predicted_change_pct = 0.01

        direction = "higher" if predicted_change_pct > 0 else "lower"
        confidence = 0.99
        
        return PredictionSignal(
            strategy_name=self.name,
            direction=direction, # type: ignore
            confidence=confidence,
            timeframe_minutes=timeframe_minutes,
            current_price=float(ohlcv["close"].iloc[-1]),
            timestamp=ohlcv.index[-1], # type: ignore
            features_used=["dummy_feature"],
            alpha=float(predicted_change_pct) # Store regression output here
        )
