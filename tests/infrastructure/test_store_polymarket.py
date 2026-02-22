import pytest
import os
from datetime import datetime, timezone, timedelta
from src.btc_predictor.infrastructure.store import DataStore
from src.btc_predictor.models import PolymarketOrder

@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_pm.db"
    return DataStore(str(db_file))

def test_pm_markets_crud(temp_store):
    # Test save_pm_market (Insert)
    market = {
        "slug": "btc-5m-test",
        "condition_id": "cond123",
        "up_token_id": "token_up",
        "down_token_id": "token_down",
        "start_time": datetime.utcnow().isoformat(),
        "end_time": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
        "price_to_beat": 50000.0
    }
    
    temp_store.save_pm_market(market)
    
    # Verify insert
    m = temp_store.get_active_pm_market(5)
    assert m is not None
    assert m["slug"] == "btc-5m-test"
    assert m["price_to_beat"] == 50000.0
    
    # Test Update (UPSERT)
    market["price_to_beat"] = 51000.0
    temp_store.save_pm_market(market)
    
    m = temp_store.get_active_pm_market(5)
    assert m["price_to_beat"] == 51000.0

def test_pm_orders_crud(temp_store):
    # Setup a signal first if needed (though pm_orders references it, 
    # SQLite doesn't strictly enforce FB unless specified, and the schema uses REFERENCES)
    
    order = PolymarketOrder(
        signal_id="sig_123",
        order_id="order_pm_456",
        token_id="token_up",
        side="BUY",
        price=0.5,
        size=100.0,
        order_type="GTC",
        status="OPEN",
        placed_at=datetime.utcnow()
    )
    
    temp_store.save_pm_order(order)
    
    # Verify order exists
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT * FROM pm_orders WHERE order_id = ?", ("order_pm_456",)).fetchone()
        assert row is not None
        assert row[7] == "OPEN" # status column index 7 based on schema
    
    # Update order
    filled_at = datetime.utcnow()
    temp_store.update_pm_order(
        "order_pm_456", 
        status="FILLED", 
        filled_at=filled_at, 
        fill_price=0.5, 
        fill_size=100.0
    )
    
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT * FROM pm_orders WHERE order_id = ?", ("order_pm_456",)).fetchone()
        assert row[7] == "FILLED"
        assert row[10] == 0.5 # fill_price
