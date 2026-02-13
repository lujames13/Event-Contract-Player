import pytest
import pandas as pd
import numpy as np
from btc_predictor.strategies.xgboost_direction.strategy import XGBoostDirectionStrategy
from btc_predictor.strategies.xgboost_direction.model import train_model
from btc_predictor.strategies.xgboost_direction.features import get_feature_columns, generate_features
from btc_predictor.models import PredictionSignal

@pytest.fixture
def trained_strategy():
    # Create some dummy data to train a model
    periods = 100
    times = pd.date_range("2025-01-01", periods=periods, freq="1min")
    df = pd.DataFrame({
        "open": np.random.rand(periods) + 100,
        "high": np.random.rand(periods) + 101,
        "low": np.random.rand(periods) + 99,
        "close": np.random.rand(periods) + 100,
        "volume": np.random.rand(periods) * 1000
    }, index=times)
    
    # Generate labels (random for dummy)
    from btc_predictor.data.labeling import add_direction_labels
    df_with_labels = add_direction_labels(df, timeframe_minutes=5)
    
    # Generate features
    feat_df = generate_features(df_with_labels)
    
    # Train
    feature_cols = get_feature_columns()
    # Drop rows with NaNs (from indicators)
    train_df = feat_df.dropna(subset=feature_cols + ['label'])
    
    model = train_model(train_df[feature_cols], train_df['label'])
    
    return XGBoostDirectionStrategy(model=model), df

def test_strategy_predict(trained_strategy):
    strategy, df = trained_strategy
    
    signal = strategy.predict(df, timeframe_minutes=5)
    
    assert isinstance(signal, PredictionSignal)
    assert signal.strategy_name == "xgboost_v1"
    assert signal.direction in ["higher", "lower"]
    assert 0.5 <= signal.confidence <= 1.0
    assert signal.current_price == df['close'].iloc[-1]
    assert signal.timeframe_minutes == 5

def test_strategy_name(trained_strategy):
    strategy, _ = trained_strategy
    assert strategy.name == "xgboost_v1"
