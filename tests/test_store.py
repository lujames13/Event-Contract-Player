import pytest
import pandas as pd
import numpy as np
from btc_predictor.data.store import DataStore
from datetime import datetime
import os

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_btc.db"
    return str(db_file)

def test_store_ohlcv(temp_db):
    store = DataStore(temp_db)
    
    # Create sample data
    data = {
        "open_time": [1704067200000, 1704067260000],
        "open": [42000.0, 42100.0],
        "high": [42200.0, 42300.0],
        "low": [41900.0, 42000.0],
        "close": [42100.0, 42200.0],
        "volume": [1.5, 2.0],
        "close_time": [1704067259999, 1704067319999]
    }
    df = pd.DataFrame(data)
    
    store.save_ohlcv(df, "BTCUSDT", "1m")
    
    # Retrieve
    retrieved_df = store.get_ohlcv("BTCUSDT", "1m")
    assert len(retrieved_df) == 2
    assert retrieved_df.iloc[0]["close"] == 42100.0
    assert "BTCUSDT" in retrieved_df["symbol"].values

def test_store_upsert(temp_db):
    store = DataStore(temp_db)
    
    data = {
        "open_time": [1704067200000],
        "open": [42000.0],
        "high": [42200.0],
        "low": [41900.0],
        "close": [42100.0],
        "volume": [1.5],
        "close_time": [1704067259999]
    }
    df = pd.DataFrame(data)
    store.save_ohlcv(df, "BTCUSDT", "1m")
    
    # Update same record
    df["close"] = 42500.0
    store.save_ohlcv(df, "BTCUSDT", "1m")
    
    retrieved_df = store.get_ohlcv("BTCUSDT", "1m")
    assert len(retrieved_df) == 1
    assert retrieved_df.iloc[0]["close"] == 42500.0
