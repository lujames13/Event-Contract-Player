import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from btc_predictor.data.store import DataStore
from btc_predictor.simulation.settler import settle_pending_trades
from dataclasses import dataclass
from typing import Optional

@dataclass
class MockTrade:
    id: str
    strategy_name: str
    direction: str
    confidence: float
    timeframe_minutes: int
    bet_amount: float
    open_time: datetime
    open_price: float
    expiry_time: datetime
    features_used: Optional[dict] = None

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_settler.db"
    return str(db_file)

@pytest.mark.asyncio
async def test_settle_trades_flat_price(temp_db):
    store = DataStore(temp_db)
    
    # 1. Prepare pending trades with flat prices
    # Use a fixed UTC time for reliability
    expiry = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    # Trade 1: higher, flat -> lose
    trade_higher = MockTrade(
        id="T1", strategy_name="S1", direction="higher", confidence=0.7,
        timeframe_minutes=60, bet_amount=10.0, open_time=expiry - timedelta(hours=1),
        open_price=50000.0, expiry_time=expiry
    )
    
    # Trade 2: lower, flat -> lose (THIS IS THE BUG FIX VERIFICATION)
    trade_lower = MockTrade(
        id="T2", strategy_name="S1", direction="lower", confidence=0.7,
        timeframe_minutes=60, bet_amount=10.0, open_time=expiry - timedelta(hours=1),
        open_price=50000.0, expiry_time=expiry
    )
    
    # Trade 3: higher, win
    trade_higher_win = MockTrade(
        id="T3", strategy_name="S1", direction="higher", confidence=0.7,
        timeframe_minutes=60, bet_amount=10.0, open_time=expiry - timedelta(hours=1),
        open_price=49000.0, expiry_time=expiry
    )
    
    # Trade 4: lower, win
    trade_lower_win = MockTrade(
        id="T4", strategy_name="S1", direction="lower", confidence=0.7,
        timeframe_minutes=60, bet_amount=10.0, open_time=expiry - timedelta(hours=1),
        open_price=51000.0, expiry_time=expiry
    )
    
    store.save_simulated_trade(trade_higher)
    store.save_simulated_trade(trade_lower)
    store.save_simulated_trade(trade_higher_win)
    store.save_simulated_trade(trade_lower_win)
    
    # 2. Add OHLCV data for expiry time
    expiry_ms = int(expiry.timestamp() * 1000)
    ohlcv_df = pd.DataFrame({
        "open_time": [expiry_ms],
        "open": [50000.0],
        "high": [50000.0],
        "low": [50000.0],
        "close": [50000.0],
        "volume": [1.0],
        "close_time": [expiry_ms + 59999]
    })
    store.save_ohlcv(ohlcv_df, "BTCUSDT", "1m")
    
    # Mock datetime.now to be after expiry
    import btc_predictor.simulation.settler
    from unittest.mock import patch
    
    with patch('btc_predictor.simulation.settler.datetime') as mock_datetime:
        mock_datetime.now.return_value = expiry + timedelta(minutes=5)
        mock_datetime.fromisoformat.side_effect = lambda x: datetime.fromisoformat(x)
        
        # 3. Settle
        await settle_pending_trades(store)
    
    # 4. Check results
    with store._get_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM simulated_trades", conn)
        
    t1 = df[df['id'] == "T1"].iloc[0]
    t2 = df[df['id'] == "T2"].iloc[0]
    t3 = df[df['id'] == "T3"].iloc[0]
    t4 = df[df['id'] == "T4"].iloc[0]
    
    assert t1['result'] == "lose", "Higher on flat should be lose"
    assert t2['result'] == "lose", "Lower on flat should be lose (Fixed Bug)"
    assert t3['result'] == "win", "Higher on lower price should be win"
    assert t4['result'] == "win", "Lower on higher price should be win"
    
    assert t1['pnl'] == -10.0
    assert t2['pnl'] == -10.0
    assert t3['pnl'] == pytest.approx(10.0 * (1.85 - 1))
    assert t4['pnl'] == pytest.approx(10.0 * (1.85 - 1))
