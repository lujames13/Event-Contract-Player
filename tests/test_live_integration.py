import pytest
import pandas as pd
import numpy as np
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from btc_predictor.data.store import DataStore
from btc_predictor.strategies.xgboost_v1.strategy import XGBoostDirectionStrategy
from btc_predictor.simulation.engine import process_signal
from btc_predictor.simulation.settler import settle_pending_trades
from btc_predictor.models import PredictionSignal, SimulatedTrade

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "integration_test.db"
    return str(db_file)

@pytest.fixture
def sample_data():
    """Create 500 minutes of dummy data for BTCUSDT 1m"""
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    data = []
    current_price = 50000.0
    for i in range(500):
        ts = int((now - timedelta(minutes=500-i)).timestamp() * 1000)
        # Random walk
        change = np.random.normal(0, 10)
        open_p = current_price
        close_p = open_p + change
        data.append({
            "open_time": ts,
            "open": open_p,
            "high": max(open_p, close_p) + 5,
            "low": min(open_p, close_p) - 5,
            "close": close_p,
            "volume": 1.0,
            "close_time": ts + 59999
        })
        current_price = close_p
    return pd.DataFrame(data)

@pytest.mark.asyncio
async def test_end_to_end_pipeline(temp_db, sample_data):
    store = DataStore(temp_db)
    
    # 1. Save historical data
    store.save_ohlcv(sample_data, "BTCUSDT", "1m")
    
    # 2. Load XGBoost strategy (since we have its model)
    model_path = Path("models/xgboost_v1/10m.pkl")
    if not model_path.exists():
        pytest.skip("XGBoost 10m model not found, skipping integration test.")
        
    strategy = XGBoostDirectionStrategy(model_path=str(model_path))
    assert 10 in strategy.available_timeframes
    
    # 3. Simulate trigger prediction
    df = store.get_ohlcv("BTCUSDT", "1m", limit=500)
    timeframe = 10
    
    # Prediction
    signal = strategy.predict(df, timeframe)
    assert isinstance(signal, PredictionSignal)
    assert signal.strategy_name == "xgboost_v1"
    assert signal.timeframe_minutes == 10
    assert signal.direction in ["higher", "lower"]
    assert 0.0 <= signal.confidence <= 1.0
    
    # 4. Engine Processing (Risk Control should allow it if we haven't traded)
    trade = process_signal(signal, store)
    
    if trade is None:
        # If risk control blocked it (e.g. low confidence), we manually force one for testing settlement
        import uuid
        trade = SimulatedTrade(
            id=str(uuid.uuid4()),
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            confidence=signal.confidence,
            timeframe_minutes=signal.timeframe_minutes,
            bet_amount=10.0,
            open_time=signal.timestamp,
            open_price=signal.current_price,
            expiry_time=signal.timestamp + timedelta(minutes=timeframe)
        )
        store.save_simulated_trade(trade)
    
    assert isinstance(trade, SimulatedTrade)
    
    # Verify written to DB
    pending = store.get_pending_trades()
    assert not pending.empty
    assert trade.id in pending['id'].values
    
    # 5. Settlement
    # Add a candle for the expiry time
    expiry_ms = int(trade.expiry_time.timestamp() * 1000)
    
    # Simulate a win
    target_price = trade.open_price + 100 if trade.direction == "higher" else trade.open_price - 100
    
    ohlcv_expiry = pd.DataFrame([{
        "open_time": expiry_ms,
        "open": target_price,
        "high": target_price + 5,
        "low": target_price - 5,
        "close": target_price,
        "volume": 1.0,
        "close_time": expiry_ms + 59999
    }])
    store.save_ohlcv(ohlcv_expiry, "BTCUSDT", "1m")
    
    # Run settlement (mocking time to be after expiry)
    import btc_predictor.simulation.settler
    from unittest.mock import patch
    
    with patch('btc_predictor.simulation.settler.datetime') as mock_dt:
        mock_dt.now.return_value = trade.expiry_time + timedelta(minutes=1)
        # We need to mock fromisoformat too because it's called in settler.py
        mock_dt.fromisoformat.side_effect = lambda x: datetime.fromisoformat(x)
        
        await settle_pending_trades(store)
    
    # 6. Verify result
    with store._get_connection() as conn:
        res_df = pd.read_sql_query("SELECT * FROM simulated_trades WHERE id = ?", conn, params=[trade.id])
    
    assert not res_df.empty
    assert res_df.iloc[0]['result'] == "win"
    assert res_df.iloc[0]['close_price'] == target_price
    assert res_df.iloc[0]['pnl'] > 0
