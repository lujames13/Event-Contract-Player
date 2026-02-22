import logging
import httpx
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class CLOBClient:
    """
    Client for Polymarket CLOB API (Read-only).
    Used for retrieving order book and current market prices.
    """
    BASE_URL = "https://clob.polymarket.com"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def get_markets(self) -> List[Dict[str, Any]]:
        """
        Fetch all available markets from CLOB.
        """
        url = f"{self.BASE_URL}/markets"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=self.timeout)
                resp.raise_for_status()
                # The response is a list of markets in the 'data' field sometimes, 
                # but based on vps_verify.py, it's often a list directly or in 'data'
                data = resp.json()
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                return data
        except httpx.TimeoutException:
            logger.warning("CLOB API timeout while fetching markets")
            return []
        except httpx.HTTPStatusError as e:
            logger.error(f"CLOB API error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching CLOB markets: {e}", exc_info=True)
            return []

    async def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch specific market details from CLOB.
        """
        url = f"{self.BASE_URL}/markets/{condition_id}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            logger.warning(f"CLOB API timeout while fetching market {condition_id}")
            return None
        except httpx.HTTPStatusError as e:
            # Polymarket returns 404 for non-existent markets
            if e.response.status_code != 404:
                logger.error(f"CLOB API error for market {condition_id}: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching CLOB market {condition_id}: {e}", exc_info=True)
            return None

    async def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """
        Fetch order book for a specific token.
        """
        url = f"{self.BASE_URL}/book"
        params = {"token_id": token_id}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            logger.warning(f"CLOB API timeout while fetching book for {token_id}")
            return {}
        except httpx.HTTPStatusError as e:
            logger.error(f"CLOB API error for book {token_id}: {e.response.status_code}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching CLOB book for {token_id}: {e}", exc_info=True)
            return {}

    async def get_price(self, token_id: str) -> Optional[float]:
        """
        Get the current mid price (roughly) from the order book.
        """
        book = await self.get_orderbook(token_id)
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        
        if not bids or not asks:
            return None
        
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        return (best_bid + best_ask) / 2.0
