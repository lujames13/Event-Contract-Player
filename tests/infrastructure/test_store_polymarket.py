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

def test_pm_strategy_stats(temp_store):
    from btc_predictor.models import PredictionSignal, SimulatedTrade
    now = datetime.now(timezone.utc)
    
    # Needs a prediction signal and a pm_order
    signal = PredictionSignal(
        strategy_name="pm_v1",
        timestamp=now - timedelta(minutes=10),
        timeframe_minutes=5,
        direction="higher",
        confidence=0.8,
        current_price=50000.0,
        market_slug="slug1",
        market_price_up=0.5,
        alpha=0.3,
        order_type="GTC"
    )
    
    trade = SimulatedTrade(
        id="t1",
        strategy_name="pm_v1",
        direction="higher",
        confidence=0.8,
        timeframe_minutes=5,
        bet_amount=10.0,
        open_time=now - timedelta(minutes=10),
        open_price=50000.0,
        expiry_time=now - timedelta(minutes=5)
    )
    
    order1 = PolymarketOrder(
        signal_id="will-be-linked", 
        order_id="o1",
        token_id="tok1",
        side="BUY",
        price=0.5,
        size=20,
        order_type="GTC",
        status="OPEN",
        placed_at=now - timedelta(minutes=10)
    )
    
    temp_store.save_polymarket_execution_context(signal, trade, order1)
    
    # Update order with win
    temp_store.update_pm_order("o1", status="FILLED", pnl=10.0)
    
    # Another order for loss
    signal2 = PredictionSignal(
        strategy_name="pm_v1",
        timestamp=now - timedelta(minutes=5),
        timeframe_minutes=5,
        direction="lower",
        confidence=0.9,
        current_price=50000.0,
    )
    trade2 = SimulatedTrade(
        id="t2", strategy_name="pm_v1", direction="lower", confidence=0.9, 
        timeframe_minutes=5, bet_amount=10, open_time=now - timedelta(minutes=5), open_price=50000.0, 
        expiry_time=now
    )
    order2 = PolymarketOrder(
        signal_id="will-be-linked", order_id="o2", token_id="tok2", side="BUY",
        price=0.5, size=20, order_type="GTC", status="OPEN", placed_at=now - timedelta(minutes=5)
    )
    temp_store.save_polymarket_execution_context(signal2, trade2, order2)
    temp_store.update_pm_order("o2", status="FILLED", pnl=-10.0)
    
    # Summary test
    summary = temp_store.get_pm_strategy_summary("pm_v1")
    assert summary["total_trades"] == 2
    assert summary["settled_trades"] == 2
    assert summary["wins"] == 1
    assert summary["da"] == 0.5
    assert summary["total_pnl"] == 0.0

    # Detail test
    detail = temp_store.get_pm_strategy_detail("pm_v1")
    assert detail["settled"] == 2
    assert detail["wins"] == 1
    assert detail["total_pnl"] == 0.0
    assert detail["higher_total"] == 1
    assert detail["higher_wins"] == 1
    assert detail["lower_total"] == 1
    assert detail["lower_wins"] == 0

    # Daily test
    date_str = now.strftime("%Y-%m-%d")
    daily = temp_store.get_pm_daily_stats("pm_v1", date_str)
    assert daily["daily_loss"] == 10.0
    assert daily["daily_trades"] == 2
    assert daily["consecutive_losses"] == 1
