import pytest
import pandas as pd
import numpy as np
from btc_predictor.infrastructure.store import DataStore
from btc_predictor.models import SimulatedTrade
from datetime import datetime, timezone, timedelta
import os
import uuid

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

def test_trade_deduplication(temp_db):
    store = DataStore(temp_db)
    now = datetime.now(timezone.utc)
    
    trade = SimulatedTrade(
        id="t1",
        strategy_name="test_strat",
        direction="higher",
        confidence=0.8,
        timeframe_minutes=10,
        bet_amount=10.0,
        open_time=now,
        open_price=50000.0,
        expiry_time=now + timedelta(minutes=10)
    )
    
    # 1. Save trade
    store.save_simulated_trade(trade)
    
    # 2. Check exists
    assert store.check_trade_exists("test_strat", 10, now) == True
    assert store.check_trade_exists("test_strat", 10, now + timedelta(seconds=1)) == False
    assert store.check_trade_exists("other_strat", 10, now) == False

def test_atomic_update_trade(temp_db):
    store = DataStore(temp_db)
    now = datetime.now(timezone.utc)
    
    trade = SimulatedTrade(
        id="t1",
        strategy_name="test_strat",
        direction="higher",
        confidence=0.8,
        timeframe_minutes=10,
        bet_amount=10.0,
        open_time=now,
        open_price=50000.0,
        expiry_time=now + timedelta(minutes=10)
    )
    store.save_simulated_trade(trade)
    
    # 1. First update - should succeed (returns True)
    success = store.update_simulated_trade("t1", 51000.0, "win", 10.0)
    assert success == True
    
    # Verify result
    with store._get_connection() as conn:
        res = conn.execute("SELECT result, pnl FROM simulated_trades WHERE id='t1'").fetchone()
        assert res[0] == "win"
        assert res[1] == 10.0
        
    # 2. Second update - should fail (returns False) because close_price IS NOT NULL
    success2 = store.update_simulated_trade("t1", 52000.0, "win", 20.0)
    assert success2 == False
    
    # Verify not changed
    with store._get_connection() as conn:
        res = conn.execute("SELECT pnl FROM simulated_trades WHERE id='t1'").fetchone()
        assert res[0] == 10.0 # Still 10.0
