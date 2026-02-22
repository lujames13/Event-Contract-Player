import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from src.btc_predictor.polymarket.tracker import PolymarketTracker

@pytest.fixture
def mock_gamma():
    client = MagicMock()
    client.get_active_5m_btc_markets = AsyncMock()
    return client

@pytest.fixture
def mock_store():
    store = MagicMock()
    return store

@pytest.mark.asyncio
async def test_tracker_sync_logic(mock_gamma, mock_store):
    tracker = PolymarketTracker(mock_gamma, mock_store)
    
    # Setup mock raw data
    now = datetime.now(timezone.utc)
    raw_markets = [
        {
            "slug": "btc-5m-match",
            "conditionId": "cond_5m",
            "startDate": now.isoformat(),
            "endDate": (now + timedelta(minutes=5)).isoformat(),
            "line": "60000.0",
            "tokens": [{"tokenId": "up_5m"}, {"tokenId": "down_5m"}]
        },
        {
            "slug": "btc-1h-no-match",
            "startDate": now.isoformat(),
            "endDate": (now + timedelta(minutes=60)).isoformat(),
            "line": "61000.0",
            "tokens": [{"tokenId": "up_1h"}, {"tokenId": "down_1h"}]
        },
        {
            "slug": "btc-invalid-tokens",
            "startDate": now.isoformat(),
            "endDate": (now + timedelta(minutes=15)).isoformat(),
            "tokens": [{"tokenId": "only_one"}]
        }
    ]
    mock_gamma.get_active_5m_btc_markets.return_value = raw_markets
    
    # Run sync for 5m and 15m
    await tracker.sync_active_markets(timeframes=[5, 15])
    
    # Verify save_pm_market was called only for the 5m match
    assert mock_store.save_pm_market.call_count == 1
    args, _ = mock_store.save_pm_market.call_args
    market_data = args[0]
    assert market_data["slug"] == "btc-5m-match"
    assert market_data["up_token_id"] == "up_5m"

def test_get_active_market_delegation(mock_gamma, mock_store):
    tracker = PolymarketTracker(mock_gamma, mock_store)
    mock_store.get_active_pm_market.return_value = {"slug": "found"}
    
    res = tracker.get_active_market(5)
    assert res["slug"] == "found"
    mock_store.get_active_pm_market.assert_called_with(5)
