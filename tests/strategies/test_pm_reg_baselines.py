import pandas as pd
import numpy as np
import pytest
import os
import shutil

from btc_predictor.strategies.pm_xgb_reg_v1.strategy import PMXGBRegV1Strategy
from btc_predictor.strategies.pm_lgbm_reg_v1.strategy import PMLGBMRegV1Strategy
from btc_predictor.strategies.pm_cb_reg_v1.strategy import PMCBRegV1Strategy
from btc_predictor.strategies.pm_mlp_reg_v1.strategy import PMMLPRegV1Strategy
from btc_predictor.strategies.pm_tabnet_reg_v1.strategy import PMTabNetRegV1Strategy
from btc_predictor.strategies.pm_cnn_reg_v1.strategy import PMCNNRegV1Strategy
from btc_predictor.strategies.pm_lstm_reg_v1.strategy import PMLSTMRegV1Strategy

@pytest.fixture(scope="module")
def sample_ohlcv():
    dates = pd.date_range("2024-01-01 00:00:00", periods=200, freq="1min", tz="UTC")
    df = pd.DataFrame(index=dates)
    
    np.random.seed(42)
    # create realistic looking prices
    df['open'] = np.linspace(100, 200, 200) + np.random.normal(0, 1, 200)
    df['high'] = df['open'] + np.random.uniform(0, 2, 200)
    df['low'] = df['open'] - np.random.uniform(0, 2, 200)
    df['close'] = df['open'] + np.random.normal(0, 0.5, 200)
    df['volume'] = np.random.uniform(10, 100, 200)
    return df

@pytest.mark.parametrize("strategy_class", [
    PMXGBRegV1Strategy,
    PMLGBMRegV1Strategy,
    PMCBRegV1Strategy,
    PMMLPRegV1Strategy,
    PMCNNRegV1Strategy,
    PMLSTMRegV1Strategy,
    PMTabNetRegV1Strategy
])
def test_regression_baseline_fit_predict(strategy_class, sample_ohlcv, tmp_path):
    strategy = strategy_class()
    timeframe = 5
    
    # Check requires_fitting
    assert strategy.requires_fitting
    
    # 1. Fit (CNN and LSTM need epochs to complete fast, we mock this by overriding kwargs or just relying on internal defaults for 200 samples)
    strategy.fit(sample_ohlcv, timeframe_minutes=timeframe)
    
    # 2. Predict
    prediction = strategy.predict(sample_ohlcv, timeframe_minutes=timeframe)
    assert prediction.direction in ["higher", "lower"]
    assert prediction.confidence >= 0
    assert prediction.alpha is not None
    assert prediction.strategy_name == strategy.name
    
    # 3. Save and Load
    model_path = str(tmp_path / f"{timeframe}m.pkl")
    strategy.save_model(timeframe, model_path)
    
    # Verify we can initialize a new one and load
    new_strategy = strategy_class(model_path=str(tmp_path))
    assert timeframe in new_strategy.available_timeframes
    
    new_pred = new_strategy.predict(sample_ohlcv, timeframe_minutes=timeframe)
    assert new_pred.direction in ["higher", "lower"]
