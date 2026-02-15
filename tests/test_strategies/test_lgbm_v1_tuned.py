import pytest
import pandas as pd
import numpy as np
from btc_predictor.strategies.lgbm_v1_tuned.strategy import LGBMTunedStrategy
from btc_predictor.models import PredictionSignal
from datetime import datetime

@pytest.fixture
def dummy_ohlcv():
    periods = 200
    times = pd.date_range("2025-01-01", periods=periods, freq="30min")
    df = pd.DataFrame({
        "open": np.linspace(100, 200, periods),
        "high": np.linspace(101, 201, periods),
        "low": np.linspace(99, 199, periods),
        "close": np.linspace(100, 200, periods) + (np.random.rand(periods) - 0.5), # Upward trend with noise
        "volume": np.random.rand(periods) * 1000
    }, index=times)
    return df

def test_lgbm_tuned_fit_predict(dummy_ohlcv):
    strategy = LGBMTunedStrategy()
    assert strategy.name == "lgbm_v1_tuned"
    assert strategy.requires_fitting is True
    
    # Train
    strategy.fit(dummy_ohlcv, timeframe_minutes=30)
    
    # Predict
    signal = strategy.predict(dummy_ohlcv, timeframe_minutes=30)
    
    assert isinstance(signal, PredictionSignal)
    assert signal.strategy_name == "lgbm_v1_tuned"
    assert signal.direction in ["higher", "lower"]
    assert 0.5 <= signal.confidence <= 1.0
    assert signal.current_price == dummy_ohlcv['close'].iloc[-1]

def test_lgbm_tuned_no_model(dummy_ohlcv):
    strategy = LGBMTunedStrategy()
    with pytest.raises(ValueError, match="Model not trained"):
        strategy.predict(dummy_ohlcv, timeframe_minutes=30)
