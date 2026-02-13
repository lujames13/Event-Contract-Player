import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from btc_predictor.backtest.engine import run_backtest
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from unittest.mock import MagicMock, patch

class MockStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "mock_strategy"
    
    @property
    def requires_fitting(self) -> bool:
        return True
    
    def fit(self, ohlcv, timeframe_minutes):
        pass
    
    def predict(self, ohlcv, timeframe_minutes):
        # Always predict higher with 0.7 confidence
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            timeframe_minutes=timeframe_minutes, # type: ignore
            direction="higher",
            confidence=0.7,
            current_price=float(ohlcv['close'].iloc[-1])
        )

@pytest.fixture
def dummy_ohlcv():
    # 70 days of 1m data (to cover 60d train + 7d test)
    # Actually, 1m data is too large for simple testing. Let's use 1h data for a dummy run.
    # Total minutes = 70 * 24 * 60 = 100,800
    start = datetime(2025, 1, 1)
    indices = [start + timedelta(minutes=i) for i in range(100801)]
    df = pd.DataFrame({
        'open': np.linspace(90000, 100000, len(indices)),
        'high': np.linspace(90000, 100000, len(indices)) + 10,
        'low': np.linspace(90000, 100000, len(indices)) - 10,
        'close': np.linspace(90000, 100000, len(indices)),
        'volume': 100
    }, index=indices)
    return df

def test_run_backtest_basic(dummy_ohlcv):
    strategy = MockStrategy()
    
    # Mock load_constants to return some payout ratio
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
    
    with patch("btc_predictor.backtest.engine.load_constants", return_value=mock_constants), \
         patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
         
        trades = run_backtest(
            strategy,
            dummy_ohlcv,
            timeframe_minutes=10,
            train_days=60,
            test_days=7
        )
        
        # 10 days of test data (7 + 3) = 14400 minutes
        # Frequency is 10 minutes -> 1440 predictions
        assert len(trades) == 1440
        
        # Check first trade
        t0 = trades[0]
        assert t0.strategy_name == "mock_strategy"
        assert t0.direction == "higher"
        assert t0.confidence == 0.7
        # In a rising market (np.linspace), higher should win
        assert t0.result == "win"
        assert t0.pnl > 0
