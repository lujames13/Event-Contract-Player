import pandas as pd
import numpy as np
import pytest
from btc_predictor.strategies.pm_common.features_short import generate_features, get_feature_columns
from btc_predictor.strategies.pm_common.features_window import generate_window_features, get_window_columns

@pytest.fixture
def mock_ohlcv():
    dates = pd.date_range("2024-01-01 00:00:00", periods=100, freq="1min", tz="UTC")
    df = pd.DataFrame(index=dates)
    
    # Create simple trends
    df['open'] = np.linspace(100, 200, 100)
    df['high'] = df['open'] + np.random.uniform(0, 5, 100)
    df['low'] = df['open'] - np.random.uniform(0, 5, 100)
    df['close'] = df['open'] + np.random.uniform(-2, 2, 100)
    df['volume'] = np.random.uniform(10, 100, 100)
    return df

def test_generate_short_features(mock_ohlcv):
    feat_df = generate_features(mock_ohlcv)
    
    # Check shape is maintained
    assert len(feat_df) == len(mock_ohlcv)
    
    # Check all feature columns are present
    feature_cols = get_feature_columns()
    for col in feature_cols:
        assert col in feat_df.columns
        
    # Check returns are calculated correctly
    assert 'ret_1m' in feat_df.columns
    assert np.isnan(feat_df['ret_1m'].iloc[0])

def test_generate_window_features(mock_ohlcv):
    # Test typical window size
    window_size = 30
    X, valid_indices = generate_window_features(mock_ohlcv, window_size=window_size)
    
    # Check shape
    expected_samples = len(mock_ohlcv) - window_size + 1
    assert X.shape == (expected_samples, window_size, 5)
    assert len(valid_indices) == expected_samples
    
    # Check normalization: The first close of each window should map to 1.0 (approx) for close price
    # Wait, the close price is index 3. So X[:, 0, 3] should be all 1.0
    np.testing.assert_allclose(X[:, 0, 3], np.ones(expected_samples))
    
    # Volume normalization check
    # Depending on precision, we can use rtol
    # But because of epsilon, it might be slightly less than 1.0. Let's use atol.
    assert np.allclose(X[:, 0, 4], np.ones(expected_samples), atol=1e-5)
