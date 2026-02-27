import pytest
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta
from btc_predictor.analytics.extractors import get_signal_dataframe, get_trade_dataframe, get_market_context, join_signals_with_context

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    
    conn.execute("""
        CREATE TABLE prediction_signals (
            id TEXT, strategy_name TEXT, timestamp TEXT, timeframe_minutes INTEGER,
            direction TEXT, confidence FLOAT, current_price FLOAT, expiry_time TEXT,
            actual_direction TEXT, close_price FLOAT, is_correct BOOLEAN,
            traded BOOLEAN, trade_id TEXT, alpha FLOAT, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE pm_orders (
            order_id TEXT, signal_id TEXT, placed_at TEXT, 
            pnl FLOAT
        )
    """)
    conn.execute("""
        CREATE TABLE ohlcv (
            symbol TEXT, interval TEXT, close_time INTEGER, 
            open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume FLOAT
        )
    """)
    
    now = datetime.now(timezone.utc)
    t1 = now - timedelta(hours=1)
    
    conn.execute("INSERT INTO prediction_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 ("s1", "pm_v1", t1.isoformat(), 5, "higher", 0.6, 50000, 
                  (t1 + timedelta(minutes=5)).isoformat(), "higher", 50100, True,
                  True, "o1", 0.03, t1.isoformat()))
                  
    conn.execute("INSERT INTO pm_orders VALUES (?, ?, ?, ?)",
                 ("o1", "s1", t1.isoformat(), 10.5))
                 
    conn.execute("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 ("BTCUSDT", "1m", int(t1.timestamp() * 1000), 50000, 50010, 49990, 50005, 1.5))
                 
    conn.commit()
    conn.close()
    return str(db_path)
    
def test_get_signal_dataframe(temp_db):
    df = get_signal_dataframe(temp_db, strategy_name="pm_v1", timeframe_minutes=5)
    assert not df.empty
    assert len(df) == 1
    assert df.iloc[0]['id'] == 's1'
    assert 'timestamp' in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df['timestamp'])
    
def test_get_signal_empty(temp_db):
    df = get_signal_dataframe(temp_db, strategy_name="nonexistent")
    assert df.empty
    
def test_get_trade_dataframe(temp_db):
    df = get_trade_dataframe(temp_db)
    assert not df.empty
    assert 'pnl' in df.columns
    assert df.iloc[0]['pnl'] == 10.5
    
def test_get_trade_empty(temp_db):
    df = get_trade_dataframe(temp_db, strategy_name="nonexistent")
    assert df.empty
    
def test_get_market_context(temp_db):
    df = get_market_context(temp_db)
    assert df.empty # Need at least 60 rows for price_change_1h if we dropna
    
def test_db_not_exist():
    df = get_signal_dataframe("nonexistent_db_path.db")
    assert df.empty

def test_join_signals_with_context():
    now = datetime.now(timezone.utc)
    signals = pd.DataFrame({"timestamp": [now]})
    context = pd.DataFrame({"timestamp": [now], "volatility_5m": [0.01], "volume_5m": [100.0], "price_change_1h": [0.05]})
    
    joined = join_signals_with_context(signals, context)
    assert not joined.empty
    assert "volatility_5m" in joined.columns
    assert joined.iloc[0]["volatility_5m"] == 0.01

def test_join_signals_with_empty_context():
    now = datetime.now(timezone.utc)
    signals = pd.DataFrame({"timestamp": [now]})
    context = pd.DataFrame()
    
    joined = join_signals_with_context(signals, context)
    assert not joined.empty
    assert "volatility_5m" in joined.columns
    assert pd.isna(joined.iloc[0]["volatility_5m"])
