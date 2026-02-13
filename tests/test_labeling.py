import pytest
import pandas as pd
import numpy as np
from btc_predictor.data.labeling import add_direction_labels, calculate_single_label

@pytest.fixture
def sample_data():
    """Create a 1m frequency sample dataframe."""
    times = pd.date_range("2025-01-01", periods=20, freq="1min")
    prices = [100, 101, 102, 101, 100, 99, 98, 99, 101, 103, 
              105, 104, 103, 104, 105, 106, 107, 106, 105, 104]
    df = pd.DataFrame({"close": prices}, index=times)
    return df

def test_add_direction_labels_standard(sample_data):
    # Predicted 5m ahead
    df_labeled = add_direction_labels(sample_data, timeframe_minutes=5)
    
    # Check index 0: price=100, price at T+5m (index 5) is 99. 99 < 100 -> label 0
    assert df_labeled.iloc[0]["label"] == 0
    
    # Check index 5: price=99, price at T+5m (index 10) is 105. 105 > 99 -> label 1
    assert df_labeled.iloc[5]["label"] == 1
    
    # Last 5 rows should be NaN because we don't have enough data
    assert np.isnan(df_labeled.iloc[-1]["label"])
    assert np.isnan(df_labeled.iloc[-5]["label"])
    # Index 14 (T+5m = Index 19) should have a label
    assert not np.isnan(df_labeled.iloc[14]["label"])

def test_add_direction_labels_flat_price():
    times = pd.date_range("2025-01-01", periods=10, freq="1min")
    # Price is flat at 100
    df = pd.DataFrame({"close": [100.0] * 10}, index=times)
    
    df_labeled = add_direction_labels(df, timeframe_minutes=5)
    
    # close_price (100) > open_price (100) is False -> label 0
    assert df_labeled.iloc[0]["label"] == 0
    assert df_labeled.iloc[2]["label"] == 0

def test_add_direction_labels_with_gaps():
    times = pd.to_datetime([
        "2025-01-01 00:00:00",
        "2025-01-01 00:01:00",
        "2025-01-01 00:05:00", # Gap here
        "2025-01-01 00:06:00"
    ])
    df = pd.DataFrame({"close": [100, 101, 105, 106]}, index=times)
    
    # Label 5m ahead
    df_labeled = add_direction_labels(df, timeframe_minutes=5)
    
    # 00:00:00 + 5m = 00:05:00. Price at 00:05:00 is 105. 105 > 100 -> label 1
    assert df_labeled.loc[pd.Timestamp("2025-01-01 00:00:00"), "label"] == 1
    
    # 00:01:00 + 5m = 00:06:00. Price at 00:06:00 is 106. 106 > 101 -> label 1
    assert df_labeled.loc[pd.Timestamp("2025-01-01 00:01:00"), "label"] == 1
    
    # 00:05:00 + 5m = 00:10:00. No data -> NaN
    assert np.isnan(df_labeled.loc[pd.Timestamp("2025-01-01 00:05:00"), "label"])

def test_calculate_single_label(sample_data):
    open_time = pd.Timestamp("2025-01-01 00:00:00")
    label = calculate_single_label(sample_data, open_time, timeframe_minutes=5)
    assert label == 0 # 100 -> 99
    
    label = calculate_single_label(sample_data, open_time, timeframe_minutes=10)
    assert label == 1 # 100 -> 105
    
    # Invalid open_time
    assert calculate_single_label(sample_data, pd.Timestamp("2024-12-31"), 5) is None
    
    # Missing expiry data
    assert calculate_single_label(sample_data, open_time, timeframe_minutes=100) is None
