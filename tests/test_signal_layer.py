import pytest
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta
from btc_predictor.infrastructure.store import DataStore
from btc_predictor.models import PredictionSignal
from btc_predictor.simulation.settler import settle_pending_signals
import uuid
import os

@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_signals.db"
    store = DataStore(db_path=str(db_file))
    return store

def test_save_prediction_signal(temp_store):
    signal = PredictionSignal(
        strategy_name="test_strat",
        timestamp=datetime.now(timezone.utc),
        timeframe_minutes=60,
        direction="higher",
        confidence=0.75,
        current_price=50000.0,
        features_used={"feat1": 1.0}
    )
    
    signal_id = temp_store.save_prediction_signal(signal)
    assert isinstance(signal_id, str)
    
    # Check if saved
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT * FROM prediction_signals WHERE id = ?", (signal_id,)).fetchone()
        assert row is not None
        assert row[1] == "test_strat"
        assert row[3] == 60
        assert row[4] == "higher"
        assert row[5] == 0.75
        assert row[6] == 50000.0
        # Expiry Check
        expiry_dt = datetime.fromisoformat(row[7])
        expected_expiry = signal.timestamp + timedelta(minutes=60)
        assert abs((expiry_dt - expected_expiry).total_seconds()) < 1.0

def test_signal_not_traded_by_default(temp_store):
    signal = PredictionSignal(
        strategy_name="test_strat",
        timestamp=datetime.now(timezone.utc),
        timeframe_minutes=60,
        direction="higher",
        confidence=0.75,
        current_price=50000.0
    )
    signal_id = temp_store.save_prediction_signal(signal)
    
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT traded, trade_id FROM prediction_signals WHERE id = ?", (signal_id,)).fetchone()
        assert row[0] == 0
        assert row[1] is None

def test_update_signal_traded(temp_store):
    signal = PredictionSignal(
        strategy_name="test_strat",
        timestamp=datetime.now(timezone.utc),
        timeframe_minutes=60,
        direction="higher",
        confidence=0.75,
        current_price=50000.0
    )
    signal_id = temp_store.save_prediction_signal(signal)
    trade_id = str(uuid.uuid4())
    
    temp_store.update_signal_traded(signal_id, trade_id)
    
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT traded, trade_id FROM prediction_signals WHERE id = ?", (signal_id,)).fetchone()
        assert row[0] == 1
        assert row[1] == trade_id

def test_get_unsettled_signals(temp_store):
    now = datetime.now(timezone.utc)
    
    # 1. Unsettled but not yet expired
    s1 = PredictionSignal("s1", now, 60, "higher", 0.7, 50000.0)
    s1_id = temp_store.save_prediction_signal(s1)
    
    # 2. Unsettled and expired
    s2 = PredictionSignal("s2", now - timedelta(minutes=70), 60, "higher", 0.8, 50000.0)
    s2_id = temp_store.save_prediction_signal(s2)
    
    # 3. Settled and expired
    s3 = PredictionSignal("s3", now - timedelta(minutes=70), 60, "higher", 0.9, 50000.0)
    id3 = temp_store.save_prediction_signal(s3)
    temp_store.settle_signal(id3, "higher", 51000.0, True)

    all_unsettled = temp_store.get_unsettled_signals()
    # Should contain s1 (unsettled, not expired) and s2 (unsettled, expired)
    assert len(all_unsettled) == 2
    assert s2_id in all_unsettled['id'].values
    assert s1_id in all_unsettled['id'].values
    assert id3 not in all_unsettled['id'].values

def test_settle_signal_correct(temp_store):
    signal = PredictionSignal("s1", datetime.now(timezone.utc), 60, "higher", 0.7, 50000.0)
    id = temp_store.save_prediction_signal(signal)
    
    temp_store.settle_signal(id, "higher", 51000.0, True)
    
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT actual_direction, close_price, is_correct FROM prediction_signals WHERE id = ?", (id,)).fetchone()
        assert row[0] == "higher"
        assert row[1] == 51000.0
        assert row[2] == 1

def test_settle_signal_incorrect(temp_store):
    signal = PredictionSignal("s1", datetime.now(timezone.utc), 60, "higher", 0.7, 50000.0)
    id = temp_store.save_prediction_signal(signal)
    
    # Predicted higher, but actual was lower
    temp_store.settle_signal(id, "lower", 49000.0, False)
    
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT is_correct FROM prediction_signals WHERE id = ?", (id,)).fetchone()
        assert row[0] == 0

@pytest.mark.asyncio
async def test_settle_pending_signals(temp_store):
    now = datetime.now(timezone.utc)
    # Expired 10m ago
    ts = now - timedelta(minutes=70)
    signal = PredictionSignal("test_strat", ts, 60, "higher", 0.7, 50000.0)
    id = temp_store.save_prediction_signal(signal)
    
    # Create matching OHLCV candle for expiry
    expiry_ms = int((ts + timedelta(minutes=60)).timestamp() * 1000)
    df_ohlcv = pd.DataFrame([{
        "open_time": expiry_ms,
        "open": 50000.0,
        "high": 51500.0,
        "low": 49500.0,
        "close": 51000.0,
        "volume": 100.0,
        "close_time": expiry_ms + 59999
    }])
    temp_store.save_ohlcv(df_ohlcv, "BTCUSDT", "1m")
    
    count = await settle_pending_signals(temp_store)
    assert count == 1
    
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT actual_direction, is_correct FROM prediction_signals WHERE id = ?", (id,)).fetchone()
        assert row[0] == "higher"
        assert row[1] == 1

def test_signal_layer_stats(temp_store):
    # Save 3 signals
    id1 = temp_store.save_prediction_signal(PredictionSignal("s1", datetime.now(timezone.utc), 10, "higher", 0.6, 1.0))
    id2 = temp_store.save_prediction_signal(PredictionSignal("s2", datetime.now(timezone.utc), 10, "higher", 0.6, 1.0))
    id3 = temp_store.save_prediction_signal(PredictionSignal("s3", datetime.now(timezone.utc), 10, "higher", 0.6, 1.0))
    
    # Settle 2, 1 correct
    temp_store.settle_signal(id1, "higher", 1.1, True)
    temp_store.settle_signal(id2, "lower", 0.9, False)
    
    stats = temp_store.get_signal_stats()
    assert stats['total'] == 3
    assert stats['settled'] == 2
    assert stats['correct'] == 1
    assert stats['accuracy'] == pytest.approx(0.5)
