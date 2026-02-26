import os
from typing import Dict, Any, List, Optional
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType, OpenOrderParams

class TradeCLOBClient:
    """
    Polymarket CLOB Trading Client responsible for managing the connection,
    EIP-712 signing, and submitting orders to the order book.
    """

    HOST_MAPPING = {
        "DEV": "https://clob.polymarket.com", # Note: Using prod url as placeholder, real DEV URL could differ
        "STAGE": "https://clob.polymarket.com",
        "PROD": "https://clob.polymarket.com"
    }
    
    CHAIN_ID_MAPPING = {
        "DEV": 137, # Polygon mainnet
        "STAGE": 137,
        "PROD": 137
    }

    def __init__(self, env: str = "PROD"):
        """
        初始化 TradeCLOBClient 並設定金鑰

        Args:
            env: 運行環境 ('DEV', 'STAGE', 'PROD')
        """
        self.env = env.upper()
        if self.env not in self.HOST_MAPPING:
            raise ValueError(f"Unknown environment: {env}. Must be one of {list(self.HOST_MAPPING.keys())}")
        
        # Load API keys from environment
        host = self.HOST_MAPPING[self.env]
        chain_id = self.CHAIN_ID_MAPPING[self.env]
        
        api_key = os.getenv(f"POLYMARKET_API_KEY_{self.env}")
        api_secret = os.getenv(f"POLYMARKET_SECRET_{self.env}")
        api_passphrase = os.getenv(f"POLYMARKET_PASSPHRASE_{self.env}")
        funder_address = os.getenv("POLYMARKET_ADDRESS")
        
        if not all([api_key, api_secret, api_passphrase, funder_address]):
            import logging
            logging.getLogger(__name__).warning(f"Missing Polymarket credentials for env {self.env}. Client might not be able to trade.")
            
        creds = None
        if api_key and api_secret and api_passphrase:
            creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
        
        # Setup Webshare Proxy if available
        p_addr = os.getenv("WEBSHARE_PROXY_ADDRESS")
        p_port = os.getenv("WEBSHARE_PROXY_PORT")
        p_user = os.getenv("WEBSHARE_PROXY_USERNAME")
        p_pass = os.getenv("WEBSHARE_PROXY_PASSWORD")
        
        if p_addr and p_port and p_user and p_pass:
            proxy_url = f"http://{p_user}:{p_pass}@{p_addr}:{p_port}"
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["http_proxy"] = proxy_url
            os.environ["https_proxy"] = proxy_url
            import logging
            logging.getLogger(__name__).info(f"Configured HTTP proxy: {p_addr}:{p_port}")
            
        # Note: Depending on the key type, we may need a private key to sign the L1 requests.
        # But `py_clob_client` usually creates credentials automatically when API Keys are provided.
        self.client = ClobClient(
            host=host,
            key=os.getenv(f"POLYMARKET_PRIVATE_KEY_{self.env}"), # Some versions use this
            chain_id=chain_id,
            creds=creds,
            signature_type=2, # Essential for Proxy Wallets
            funder=funder_address
        )
        
        if not creds and os.getenv(f"POLYMARKET_PRIVATE_KEY_{self.env}"):
            import logging
            logging.getLogger(__name__).info("No API credentials provided, deriving API key from private key...")
            creds = self.client.derive_api_key()
            
        self.client.set_api_creds(creds)

    def create_and_post_order(self, token_id: str, price: float, size: float, side: str) -> Dict[str, Any]:
        """
        建立並發送 Maker/Limit Order (GTC)。
        
        Args:
            token_id: 投注目標的 Token ID
            price: 小數點報價 (例如 0.5)
            size: 下單數量
            side: 'BUY' 或 'SELL'
            
        Returns:
            API response payload, potentially containing the order_id.
        """
        side_upper = side.upper()
        if side_upper not in ["BUY", "SELL"]:
            raise ValueError("Side must be 'BUY' or 'SELL'")
            
        order_args = OrderArgs(
            price=price,
            size=size,
            side=side_upper,
            token_id=token_id
        )
        # Using py_clob_client to sign and post the order automatically
        resp = self.client.create_and_post_order(order_args)
        return resp

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        撤銷指定訂單
        
        Args:
            order_id: The ID of the order to cancel
            
        Returns:
            The API response for the cancellation
        """
        return self.client.cancel(order_id)

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        查詢當前帳戶所有未完全成交的訂單
        
        Returns:
            A list of order objects.
        """
        # OpenOrderParams usually allows fetching open orders without specific filters.
        # But sometimes it needs arguments to just fetch everything. 
        # Using typical defaults.
        resp = self.client.get_orders(params=OpenOrderParams())
        # The typical response is a paginated list or list
        if isinstance(resp, list):
            return resp
        elif hasattr(resp, 'get') and 'orders' in resp:
            return resp['orders']
        return resp

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        查詢特定訂單的狀態
        
        Args:
            order_id: Order ID to query
            
        Returns:
            The comprehensive status and details of the order.
        """
        return self.client.get_order(order_id)
