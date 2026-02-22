# Review tests for task-spec-g3.4
# Focus: Market selection logic, UPSERT robustness, and timeframe matching slack.

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from src.btc_predictor.polymarket.tracker import PolymarketTracker
from src.btc_predictor.infrastructure.store import DataStore
from src.btc_predictor.models import PolymarketOrder

@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_review_pm.db"
    return DataStore(str(db_file))

@pytest.fixture
def mock_gamma():
    client = MagicMock()
    client.get_active_5m_btc_markets = AsyncMock()
    return client

@pytest.mark.asyncio
async def test_get_active_market_selection(temp_store):
    """Verify that get_active_pm_market returns the SOONEST to expire market."""
    now = datetime.now(timezone.utc)
    
    # Market A: expires in 5 mins
    market_a = {
        "slug": "soon",
        "condition_id": "c1",
        "up_token_id": "u1",
        "down_token_id": "d1",
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(minutes=5)).isoformat(),
        "price_to_beat": 50000.0
    }
    
    # Market B: expires in 10 mins
    market_b = {
        "slug": "later",
        "condition_id": "c2",
        "up_token_id": "u2",
        "down_token_id": "d2",
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(minutes=10)).isoformat(),
        "price_to_beat": 50000.0
    }
    
    temp_store.save_pm_market(market_a)
    temp_store.save_pm_market(market_b)
    
    # Should get 'soon' for 5m timeframe (duration matches)
    res = temp_store.get_active_pm_market(5)
    assert res is not None
    assert res["slug"] == "soon"
    
    # Should get 'later' for 10m timeframe
    res = temp_store.get_active_pm_market(10)
    assert res is not None
    assert res["slug"] == "later"

@pytest.mark.asyncio
async def test_tracker_timeframe_slack(mock_gamma, temp_store):
    """Verify tracker handles slight duration mismatches (slack)."""
    tracker = PolymarketTracker(mock_gamma, temp_store)
    now = datetime.now(timezone.utc)
    
    # 5m market with 295s duration (close enough)
    raw_markets = [
        {
            "slug": "slack-5m",
            "conditionId": "c_slack",
            "startDate": now.isoformat(),
            "endDate": (now + timedelta(seconds=295)).isoformat(),
            "line": "60000.0",
            "tokens": [{"tokenId": "u"}, {"tokenId": "d"}]
        }
    ]
    mock_gamma.get_active_5m_btc_markets.return_value = raw_markets
    
    await tracker.sync_active_markets(timeframes=[5])
    
    # Store's get_active_pm_market also has duration logic, let's check if it finds it
    res = temp_store.get_active_pm_market(5)
    assert res is not None
    assert res["slug"] == "slack-5m"

@pytest.mark.asyncio
async def test_upsert_preserves_outcome(temp_store):
    """Verify UPSERT doesn't overwrite outcome with NULL if it's already set."""
    now = datetime.now(timezone.utc)
    market = {
        "slug": "test-upsert",
        "condition_id": "c1",
        "up_token_id": "u1",
        "down_token_id": "d1",
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(minutes=5)).isoformat(),
        "price_to_beat": 50000.0,
        "outcome": "UP"
    }
    
    temp_store.save_pm_market(market)
    
    # Sync again with new data but NO outcome
    market_new = market.copy()
    market_new["price_to_beat"] = 51000.0
    market_new["outcome"] = None
    
    temp_store.save_pm_market(market_new)
    
    # Verify outcome is still "UP"
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT outcome, price_to_beat FROM pm_markets WHERE slug = ?", ("test-upsert",)).fetchone()
        assert row[0] == "UP"
        assert row[1] == 51000.0

@pytest.mark.asyncio
async def test_update_order_multiple_fields(temp_store):
    """Verify update_pm_order handles multiple fields correctly."""
    order = PolymarketOrder(
        signal_id="s1",
        order_id="o1",
        token_id="t1",
        side="BUY",
        price=0.5,
        size=10.0,
        order_type="GTC",
        status="OPEN",
        placed_at=datetime.now(timezone.utc)
    )
    temp_store.save_pm_order(order)
    
    temp_store.update_pm_order(
        "o1", 
        status="FILLED",
        fill_price=0.49,
        fill_size=10.0,
        filled_at=datetime.now(timezone.utc)
    )
    
    with temp_store._get_connection() as conn:
        row = conn.execute("SELECT status, fill_price, fill_size FROM pm_orders WHERE order_id = 'o1'").fetchone()
        assert row[0] == "FILLED"
        assert row[1] == 0.49
        assert row[2] == 10.0
