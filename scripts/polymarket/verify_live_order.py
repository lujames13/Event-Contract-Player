import os
import sys
import logging
from typing import Dict, Any

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.btc_predictor.polymarket.trading_client import TradeCLOBClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """
    Integration test connecting to Polymarket with real credentials.
    We test building the payload and creating an extreme price order,
    and then quickly canceling it.
    """
    env = os.getenv("POLYMARKET_ENV", "PROD")
    logger.info(f"Initializing TradeCLOBClient for {env} environment...")
    
    try:
        client = TradeCLOBClient(env=env)
    except Exception as e:
        logger.error(f"Failed to initialize client: {e}")
        return

    logger.info("Checking API authentication and fetching open orders...")
    try:
        open_orders = client.get_open_orders()
        logger.info(f"Successfully fetched {len(open_orders)} open orders.")
    except Exception as e:
        logger.error(f"Failed to fetch open orders: {e}")
        return
        
    # Send a tiny unfillable limit order to test signatures
    # Use standard BTC 5m token if we have a valid token_id, 
    # but for testing any valid token_id will do. We need a valid token ID.
    # To reliably do this, we can pick a known token or we might fail on token_id validation.
    # Since this is a live script, we assume the user provides a token_id.
    token_id = os.getenv("TEST_TOKEN_ID")
    if not token_id:
        logger.warning("TEST_TOKEN_ID environment variable is not set. Skipping the order placement and cancellation test.")
        logger.info("To fully test EIP-712 signing, please provide a valid token ID using 'export TEST_TOKEN_ID=\"your_token_id\"'.")
        return
        
    price = 0.01  # Absurdly low price to ensure it does not fill
    size = 5.0    # 5 shares
    side = "BUY"
    
    logger.info(f"Attempting to place test limit order: {side} {size} @ {price} for token_id: {token_id}")
    try:
        order_resp = client.create_and_post_order(
            token_id=token_id,
            price=price,
            size=size,
            side=side
        )
        logger.info(f"Order placement response: {order_resp}")
        
        # Determine how to extract order_id
        order_id = None
        if isinstance(order_resp, dict):
            if "orderID" in order_resp:
                order_id = order_resp["orderID"]
            elif "success" in order_resp and order_resp["success"] is True and "orderID" in order_resp:
                 order_id = order_resp["orderID"]
            elif isinstance(order_resp.get("order"), dict) and "id" in order_resp["order"]:
                order_id = order_resp["order"]["id"]
            else:
                 logger.warning("Could not extract order_id from response. Full response: " + str(order_resp))

        elif hasattr(order_resp, 'orderID'):
            order_id = order_resp.orderID
        else:
             logger.warning("Could not extract order_id from response. Type is " + str(type(order_resp)))
    
        if order_id:
            logger.info(f"Order placed successfully. Order ID: {order_id}. Immediately canceling...")
            try:
                # In some versions, cancel_order takes { 'orderID': order_id } ?? Wait, the signature says (self, order_id).
                cancel_resp = client.cancel_order(order_id)
                logger.info(f"Cancellation response: {cancel_resp}")
            except Exception as e:
                logger.error(f"Failed to cancel order: {e}. Please MANUALLY cancel it on Polymarket!")
        else:
            logger.warning("Did not receive a valid order ID. Cancellation skipped.")
            
    except Exception as e:
        logger.error(f"Failed to place order: {e}")

if __name__ == "__main__":
    main()
