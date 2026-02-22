import pytest
from unittest.mock import AsyncMock, patch
from btc_predictor.polymarket.gamma_client import GammaClient
from btc_predictor.polymarket.clob_client import CLOBClient
import httpx

@pytest.fixture
def gamma_client():
    return GammaClient()

@pytest.fixture
def clob_client():
    return CLOBClient()

@pytest.mark.asyncio
async def test_gamma_fetch_events_success(gamma_client):
    mock_response = [
        {"title": "Bitcoin Price at 12:00", "slug": "btc-1200", "markets": []},
        {"title": "Ethereum Price at 12:00", "slug": "eth-1200", "markets": []}
    ]
    
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        
        events = await gamma_client.fetch_events(query="Bitcoin")
        
        assert len(events) == 1
        assert events[0]["title"] == "Bitcoin Price at 12:00"
        mock_get.assert_called_once()

@pytest.mark.asyncio
async def test_gamma_fetch_events_timeout(gamma_client):
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout")):
        events = await gamma_client.fetch_events()
        assert events == []

@pytest.mark.asyncio
async def test_clob_get_markets_success(clob_client):
    mock_response = {"data": [{"condition_id": "0x123", "question": "BTC Up?"}]}
    
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status = MagicMock()
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        
        markets = await clob_client.get_markets()
        
        assert len(markets) == 1
        assert markets[0]["condition_id"] == "0x123"

@pytest.mark.asyncio
async def test_clob_get_price(clob_client):
    mock_book = {
        "bids": [{"price": "0.48", "size": "100"}],
        "asks": [{"price": "0.52", "size": "100"}]
    }
    
    with patch.object(CLOBClient, "get_orderbook", new_callable=AsyncMock) as mock_book_call:
        mock_book_call.return_value = mock_book
        
        price = await clob_client.get_price("token_123")
        
        assert price == pytest.approx(0.5)
