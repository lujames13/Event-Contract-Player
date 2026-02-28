import pytest
import pandas as pd
import numpy as np
from btc_predictor.infrastructure.labeling import add_regression_labels

@pytest.fixture
def df_dummy():
    times = pd.date_range("2026-03-01 00:00:00", periods=20, freq="1min", tz="UTC")
    df = pd.DataFrame(index=times)
    df["close"] = np.linspace(100, 119, 20)  # 100, 101, ... 119
    return df

def test_add_regression_labels_5m(df_dummy):
    df_labeled = add_regression_labels(df_dummy, 5)
    
    assert "price_change_pct" in df_labeled.columns
    
    # At t=0 (close=100), t+5 (close=105)
    # label = (105 - 100) / 100 * 100 = 5.0
    assert df_labeled["price_change_pct"].iloc[0] == pytest.approx(5.0)
    
    # End of DataFrame should have NaN
    assert np.isnan(df_labeled["price_change_pct"].iloc[-5])
    assert np.isnan(df_labeled["price_change_pct"].iloc[-1])

def test_add_regression_labels_15m(df_dummy):
    df_labeled = add_regression_labels(df_dummy, 15)
    
    # At t=0 (close=100), t+15 (close=115)
    # label = (115 - 100) / 100 * 100 = 15.0
    assert df_labeled["price_change_pct"].iloc[0] == pytest.approx(15.0)
    
    # End of DataFrame should have NaN
    assert np.isnan(df_labeled["price_change_pct"].iloc[-15])

def test_add_regression_labels_empty():
    df = pd.DataFrame()
    df_labeled = add_regression_labels(df, 5)
    assert df_labeled.empty

def test_add_regression_labels_invalid_index():
    df = pd.DataFrame({"close": [1, 2, 3]})
    with pytest.raises(ValueError, match="DataFrame index must be a pd.DatetimeIndex"):
        add_regression_labels(df, 5)

def test_add_regression_labels_missing_data():
    times = pd.to_datetime(["2026-03-01 00:00:00", "2026-03-01 00:01:00", "2026-03-01 00:05:00"], utc=True)
    df = pd.DataFrame({"close": [100, 101, 105]}, index=times)
    
    # t=00:00:00, +5m = 00:05:00 (close=105) -> (105-100)/100*100 = 5.0
    # t=00:01:00, +5m = 00:06:00 (missing) -> NaN
    df_labeled = add_regression_labels(df, 5)
    assert df_labeled["price_change_pct"].iloc[0] == pytest.approx(5.0)
    assert np.isnan(df_labeled["price_change_pct"].iloc[1])
    assert np.isnan(df_labeled["price_change_pct"].iloc[2])
