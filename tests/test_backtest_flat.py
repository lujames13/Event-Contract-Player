
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from btc_predictor.backtest.engine import run_backtest
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from unittest.mock import MagicMock, patch

class MockFlatStrategy(BaseStrategy):
    def __init__(self, direction):
        self.direction = direction

    @property
    def name(self) -> str:
        return f"mock_flat_{self.direction}"
    
    @property
    def requires_fitting(self) -> bool:
        return False
    
    def fit(self, ohlcv, timeframe_minutes):
        pass
    
    def predict(self, ohlcv, timeframe_minutes):
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            timeframe_minutes=timeframe_minutes, # type: ignore
            direction=self.direction,
            confidence=0.8,
            current_price=float(ohlcv['close'].iloc[-1]),
            features_used={}
        )

def test_flat_market_conditions():
    # Create data where price stays exactly the same
    # Use enough data to cover train_days=0 but loop logic needs > 0 samples
    start = datetime(2025, 1, 1)
    indices = [start + timedelta(minutes=i*10) for i in range(100)]
    
    df = pd.DataFrame({
        'open': [100.0] * 100,
        'high': [101.0] * 100,
        'low': [99.0] * 100,
        'close': [100.0] * 100,
        'volume': [1000] * 100
    }, index=indices)

    mock_constants = {
        "event_contract": {
            "payout_ratio": {10: 1.8},
        },
        "risk_control": {
            "bet_range": [5, 20],
        },
        "confidence_thresholds": {
            10: 0.6,
        }
    }

    # Patch both places where load_constants is used
    with patch("btc_predictor.backtest.engine.load_constants", return_value=mock_constants), \
         patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):

        # Test Higher Strategy: Expect LOSE on flat
        strategy_higher = MockFlatStrategy("higher")
        trades_higher = run_backtest(
            strategy_higher,
            df,
            timeframe_minutes=10,
            train_days=0, 
            test_days=1,
            step_days=1
        )
        
        # Should be some trades
        assert len(trades_higher) > 0
        for trade in trades_higher:
            assert trade.open_price == trade.close_price
            assert trade.result == "lose"
            assert trade.pnl < 0

        # Test Lower Strategy: Expect LOSE on flat
        strategy_lower = MockFlatStrategy("lower")
        trades_lower = run_backtest(
            strategy_lower,
            df,
            timeframe_minutes=10,
            train_days=0, 
            test_days=1,
            step_days=1
        )
        
        assert len(trades_lower) > 0
        for trade in trades_lower:
            assert trade.open_price == trade.close_price
            assert trade.result == "lose"
            assert trade.pnl < 0
