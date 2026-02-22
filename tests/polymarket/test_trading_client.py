import os
import pytest
from unittest.mock import patch, MagicMock
from src.btc_predictor.polymarket.trading_client import TradeCLOBClient

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("POLYMARKET_API_KEY_DEV", "test_api_key")
    monkeypatch.setenv("POLYMARKET_SECRET_DEV", "dGVzdHNlY3JldDEyMzQ=")
    monkeypatch.setenv("POLYMARKET_PASSPHRASE_DEV", "test_passphrase")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY_DEV", "0x" + "0" * 63 + "1")
    monkeypatch.setenv("POLYMARKET_ADDRESS", "0x0000000000000000000000000000000000000000")
    
@pytest.fixture
def client(mock_env):
    return TradeCLOBClient(env="DEV")

def test_client_init(mock_env):
    with pytest.raises(ValueError):
        TradeCLOBClient(env="INVALID")
    
    cl = TradeCLOBClient(env="DEV")
    assert cl.env == "DEV"
    assert cl.client.host == "https://clob.polymarket.com"
    assert cl.client.chain_id == 137

@patch("py_clob_client.http_helpers.helpers._http_client.request")
def test_create_and_post_order(mock_request, client):
    # Mock tick size to avoid another HTTP request during the test
    client.client.get_tick_size = MagicMock(return_value="0.01")
    client.client.get_neg_risk = MagicMock(return_value=False)

    
    # Mock response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "orderID": "12345"}
    mock_request.return_value = mock_resp

    res = client.create_and_post_order(
        token_id="123456789",
        price=0.5,
        size=10,
        side="BUY"
    )

    assert res == {"success": True, "orderID": "12345"}
    mock_request.assert_called()
    
    # Verify the last call was to the order endpoint
    call_args = mock_request.call_args
    assert call_args is not None
    kwargs = call_args.kwargs
    method = kwargs.get("method")
    url = kwargs.get("url")
    headers = kwargs.get("headers", {})
    json_data = kwargs.get("json", {})
    
    assert method == "POST"
    assert "order" in url or "submit" in url # Depending on specific endpoint
    
    # py-clob-client uses POLY_API_KEY, not POLYMARKET-API-KEY
    # We check that some level 2 auth headers exist
    auth_keys = [k for k in headers.keys() if "API" in k.upper() or "POLY" in k.upper()]
    assert len(auth_keys) > 0, f"Headers missing auth: {headers}"
    
    import json
    if "content" in kwargs:
        json_data = json.loads(kwargs["content"].decode("utf-8"))
    
    assert "order" in json_data
    order = json_data["order"]
    assert str(order["tokenId"]) == "123456789"
    assert "side" in order
    # side can be 0 or 1 depending on EIP-712 struct or Enum mappings.
    # usually 0 = BUY, 1 = SELL. py-clob-client uses '0' for BUY.
    if isinstance(order["side"], str):
        assert order["side"].upper() == "BUY" or order["side"] == "0"
    else:
        assert order["side"] == 0

@patch("py_clob_client.http_helpers.helpers._http_client.request")
def test_cancel_order(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_request.return_value = mock_resp

    res = client.cancel_order("test_order_id")
    assert res == {"success": True}

    call_args = mock_request.call_args
    kwargs = call_args.kwargs
    
    assert kwargs.get("method") in ["DELETE", "POST"]
    auth_keys = [k for k in kwargs.get("headers", {}) if "API" in k.upper() or "POLY" in k.upper()]
    assert len(auth_keys) > 0
    
@patch("py_clob_client.http_helpers.helpers._http_client.request")
def test_get_open_orders(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # py-clob-client uses 'next_cursor' loop which terminates when cursor is "LTE="
    mock_resp.json.return_value = {
        "next_cursor": "LTE=", 
        "data": [{"id": "1"}, {"id": "2"}]
    }
    mock_request.return_value = mock_resp

    orders = client.get_open_orders()
    assert len(orders) == 2
    assert orders[0]["id"] == "1"

    kwargs = mock_request.call_args.kwargs
    assert kwargs.get("method") == "GET"
    auth_keys = [k for k in kwargs.get("headers", {}) if "API" in k.upper() or "POLY" in k.upper()]
    assert len(auth_keys) > 0

@patch("py_clob_client.http_helpers.helpers._http_client.request")
def test_get_order_status(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "test_order_id", "status": "OPEN"}
    mock_request.return_value = mock_resp

    status = client.get_order_status("test_order_id")
    assert status["status"] == "OPEN"
    
    kwargs = mock_request.call_args.kwargs
    assert kwargs.get("method") == "GET"
    assert "test_order_id" in kwargs.get("url")
