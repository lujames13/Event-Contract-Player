import pytest
import pandas as pd
import numpy as np
from btc_predictor.infrastructure.labeling import add_regression_labels

# Review tests for task-spec-g3.12
# Focus: regression labeling edge cases (gaps, timeline exact matching)

def test_regression_labeling_with_gaps():
    """
    Test timeframe extraction over missing timestamps (gaps).
    If t+N is missing, it should correctly assign NaN, without shifting wrongly.
    """
    # Create an index with a gap
    # 00:00, 00:01, 00:02, 00:04 (00:03 is missing)
    times = [
        pd.Timestamp("2024-01-01 00:00:00"),
        pd.Timestamp("2024-01-01 00:01:00"),
        pd.Timestamp("2024-01-01 00:02:00"),
        pd.Timestamp("2024-01-01 00:04:00"),
    ]
    df = pd.DataFrame({"class": "test", "close": [100.0, 101.0, 102.0, 104.0]}, index=pd.DatetimeIndex(times))
    
    # Test 1m horizon:
    # 00:00 -> +1m is 00:01 (price 101). Change: (101-100)/100 * 100 = 1.0
    # 00:02 -> +1m is 00:03 (missing). Change: NaN
    df_1m = add_regression_labels(df, timeframe_minutes=1)
    
    assert "price_change_pct" in df_1m.columns
    assert df_1m.loc[times[0], "price_change_pct"] == pytest.approx(1.0)
    assert np.isnan(df_1m.loc[times[2], "price_change_pct"])
    
    # Test 2m horizon:
    # 00:02 -> +2m is 00:04 (price 104). Change: (104-102)/102 * 100 = 1.96078
    df_2m = add_regression_labels(df, timeframe_minutes=2)
    assert df_2m.loc[times[2], "price_change_pct"] == pytest.approx(1.96078, rel=1e-4)

def test_add_regression_labels_zero_price():
    """
    Test division by zero or extreme cases gracefully if close price is 0.
    In real crypto it's unlikely, but robust calculation should generate inf or nan.
    """
    times = [
        pd.Timestamp("2024-01-01 00:00:00"),
        pd.Timestamp("2024-01-01 00:01:00")
    ]
    df = pd.DataFrame({"close": [0.0, 100.0]}, index=pd.DatetimeIndex(times))
    df_ret = add_regression_labels(df, timeframe_minutes=1)
    
    # 0.0 to 100.0 => (100 - 0) / 0 = inf
    assert np.isinf(df_ret.loc[times[0], "price_change_pct"]) or np.isnan(df_ret.loc[times[0], "price_change_pct"])
