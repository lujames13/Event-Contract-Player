# Review tests for task-spec-g4.1
# Focus: Error handling, environment configuration, side mapping, and GTC default behavior.

import os
import pytest
from unittest.mock import patch, MagicMock
from btc_predictor.polymarket.trading_client import TradeCLOBClient

@pytest.fixture
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("POLYMARKET_API_KEY_PROD", "prod_key")
    # Base64 for 'prod_secret' is 'cHJvZF9zZWNyZXQ='
    monkeypatch.setenv("POLYMARKET_SECRET_PROD", "cHJvZF9zZWNyZXQ=") 
    monkeypatch.setenv("POLYMARKET_PASSPHRASE_PROD", "prod_pass")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY_PROD", "0x" + "a" * 64)
    monkeypatch.setenv("POLYMARKET_ADDRESS", "0x" + "b" * 40)

def test_environment_variable_routing(mock_env_vars):
    """
    Test that the client correctly routes to the specific environment variables.
    """
    with patch("btc_predictor.polymarket.trading_client.ClobClient") as MockClob:
        client = TradeCLOBClient(env="PROD")
        
        # Verify the client initialization
        assert client.env == "PROD"
        
        # Check if ClobClient was initialized with variables from the PROD env
        args, kwargs = MockClob.call_args
        assert kwargs.get("host") == "https://clob.polymarket.com"
        assert kwargs.get("key") == "0x" + "a" * 64
        assert kwargs.get("funder") == "0x" + "b" * 40
        
        creds = kwargs.get("creds")
        assert creds.api_key == "prod_key"
        # Secret is decoded internally by ApiCreds so we don't assert its raw value if it's opaque
        assert creds.api_passphrase == "prod_pass"

def test_side_input_flexibility(mock_env_vars):
    """
    Test that 'buy', 'Sell', etc., are handled correctly.
    """
    with patch("btc_predictor.polymarket.trading_client.ClobClient"):
        client = TradeCLOBClient(env="PROD")
        client.client.create_and_post_order = MagicMock()
        
        # Test lowercase buy
        client.create_and_post_order("t1", 0.5, 10, "buy")
        called_args = client.client.create_and_post_order.call_args_list[0][0][0]
        assert called_args.side == "BUY"
        
        # Test mixed case Sell
        client.create_and_post_order("t1", 0.5, 10, "Sell")
        called_args = client.client.create_and_post_order.call_args_list[1][0][0]
        assert called_args.side == "SELL"

def test_missing_credentials_warning(caplog, monkeypatch):
    """
    Ensure the client warns when credentials are missing.
    """
    import logging
    # Clear env vars
    for key in ["POLYMARKET_API_KEY_PROD", "POLYMARKET_SECRET_PROD", "POLYMARKET_PASSPHRASE_PROD"]:
        monkeypatch.delenv(key, raising=False)
        
    with patch("btc_predictor.polymarket.trading_client.ClobClient"):
        client = TradeCLOBClient(env="PROD")
        assert "Missing Polymarket credentials for env PROD" in caplog.text

def test_cancel_order_passthrough(mock_env_vars):
    """
    Ensure cancel_order correctly passes the order_id to the SDK.
    """
    with patch("btc_predictor.polymarket.trading_client.ClobClient") as MockClob:
        mock_clob_instance = MagicMock()
        MockClob.return_value = mock_clob_instance
        
        client = TradeCLOBClient(env="PROD")
        mock_clob_instance.cancel.return_value = {"status": "canceled"}
        
        resp = client.cancel_order("order_999")
        mock_clob_instance.cancel.assert_called_once_with("order_999")
        assert resp == {"status": "canceled"}
