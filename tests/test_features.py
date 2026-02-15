import pytest
import pandas as pd
import numpy as np
from btc_predictor.strategies.xgboost_v1.features import generate_features, get_feature_columns

@pytest.fixture
def sample_ohlcv():
    """Create a 1m frequency sample OHLCV dataframe."""
    periods = 100
    times = pd.date_range("2025-01-01", periods=periods, freq="1min")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(periods))
    df = pd.DataFrame({
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.random.rand(periods) * 1000
    }, index=times)
    return df

def test_generate_features_basic(sample_ohlcv):
    feat = generate_features(sample_ohlcv)
    
    # Check if all expected features are present
    cols = get_feature_columns()
    for col in cols:
        assert col in feat.columns, f"Feature {col} missing"
        
    # Check for NaN handling
    # RSI(14) should have 14 NaNs at the beginning
    assert np.isnan(feat['rsi_14'].iloc[0])
    assert not np.isnan(feat['rsi_14'].iloc[14])
    
    # Check time features
    # 2025-01-01 00:00:00 is Wednesday (day 2 in pandas 0-6)
    # Actually let's check hour
    assert feat.index[0].hour == 0
    assert feat.iloc[0]['hour_sin'] == pytest.approx(0.0)
    assert feat.iloc[0]['hour_cos'] == pytest.approx(1.0)

def test_no_lookahead_bias(sample_ohlcv):
    # This is a basic check. Modifying the last row should NOT affect previous features.
    feat1 = generate_features(sample_ohlcv)
    
    modified_ohlcv = sample_ohlcv.copy()
    modified_ohlcv.iloc[-1, modified_ohlcv.columns.get_loc('close')] *= 2
    
    feat2 = generate_features(modified_ohlcv)
    
    # All rows except the last one should be identical
    pd.testing.assert_frame_equal(feat1.iloc[:-1], feat2.iloc[:-1])

def test_volume_features(sample_ohlcv):
    feat = generate_features(sample_ohlcv)
    
    # vol_ratio_5m: volume / mean(volume last 5)
    expected_vol_ratio = sample_ohlcv['volume'].iloc[4] / sample_ohlcv['volume'].iloc[0:5].mean()
    assert feat.iloc[4]['vol_ratio_5m'] == pytest.approx(expected_vol_ratio)

def test_bb_features(sample_ohlcv):
    feat = generate_features(sample_ohlcv)
    
    # bb_pct_b should be between 0 and 1 if price is within bands, but can be outside
    # Just check it's calculated
    assert not feat['bb_pct_b'].isna().all()
    # Check distance
    assert feat['bb_dist'].iloc[20] == pytest.approx((feat['close'].iloc[20] - feat['bb_middle'].iloc[20]) / feat['bb_middle'].iloc[20])
