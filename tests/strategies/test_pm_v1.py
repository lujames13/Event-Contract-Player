import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from btc_predictor.strategies.pm_v1.strategy import PMV1Strategy
from btc_predictor.models import PredictionSignal

@pytest.fixture
def mock_ohlcv():
    dates = pd.date_range("2024-01-01", periods=1000, freq="1min")
    df = pd.DataFrame({
        "open": np.random.randn(1000) + 50000,
        "high": np.random.randn(1000) + 50100,
        "low": np.random.randn(1000) + 49900,
        "close": np.random.randn(1000) + 50000,
        "volume": np.random.rand(1000) * 10
    }, index=dates)
    return df

def test_pm_v1_strategy_integrity(mock_ohlcv):
    strategy = PMV1Strategy()
    
    # Mock model
    class MockModel:
        def predict_proba(self, X):
            return np.array([[0.4, 0.6]])
            
    strategy.models[5] = MockModel()
    
    signal = strategy.predict(mock_ohlcv, 5)
    
    # Verify PredictionSignal integrity
    assert isinstance(signal, PredictionSignal)
    assert signal.strategy_name == "pm_v1"
    assert signal.timeframe_minutes == 5
    assert signal.direction == "higher"
    assert signal.confidence == 0.6
    assert isinstance(signal.features_used, list)
    assert len(signal.features_used) > 0
    assert signal.market_slug is not None
    assert signal.market_price_up == 0.5
    assert signal.alpha == pytest.approx(0.1)

def test_pm_v1_available_timeframes():
    strategy = PMV1Strategy()
    strategy.models[5] = "mock"
    strategy.models[15] = "mock"
    
    assert set(strategy.available_timeframes) == {5, 15}
