import pytest
import pandas as pd
import numpy as np
import torch
from btc_predictor.strategies.mlp_v1.strategy import MLPStrategy
from btc_predictor.models import PredictionSignal

@pytest.fixture
def dummy_ohlcv():
    # MLP needs enough data for rolling 60 window normalization
    periods = 1000
    times = pd.date_range("2025-01-01", periods=periods, freq="1min")
    # Base price with random walk-like structure
    base = 100 + np.cumsum(np.random.randn(periods) * 0.1)
    df = pd.DataFrame({
        "open": base + np.random.randn(periods) * 0.01,
        "high": base + 0.5 + np.random.randn(periods) * 0.01,
        "low": base - 0.5 + np.random.randn(periods) * 0.01,
        "close": base + np.random.randn(periods) * 0.01,
        "volume": np.random.rand(periods) * 1000 + 100
    }, index=times)
    return df

def test_mlp_fit_predict(dummy_ohlcv):
    strategy = MLPStrategy()
    assert strategy.name == "mlp_v1"
    assert strategy.requires_fitting is True
    
    # Train
    strategy.fit(dummy_ohlcv, timeframe_minutes=10)
    
    # Predict
    signal = strategy.predict(dummy_ohlcv, timeframe_minutes=10)
    
    assert isinstance(signal, PredictionSignal)
    assert signal.strategy_name == "mlp_v1"
    assert signal.direction in ["higher", "lower"]
    assert 0.4 <= signal.confidence <= 1.0 # sigmoid can be anything, but strategy forces confidence >= 0.5 if we interpret prob correctly.
    # Actually strategy.py:
    # if prob_higher > 0.5: confidence = prob_higher
    # else: confidence = 1.0 - prob_higher
    # So confidence must be >= 0.5
    assert signal.confidence >= 0.5
    
    assert signal.current_price == dummy_ohlcv['close'].iloc[-1]

def test_mlp_device():
    strategy = MLPStrategy()
    # Check if device is correctly set
    expected_device = 'cuda' if torch.cuda.is_available() else 'cpu'
    assert str(strategy.device) == expected_device
