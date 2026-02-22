import logging
import httpx
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class GammaClient:
    """
    Client for Polymarket Gamma API.
    Used for retrieving market metadata and settlement info.
    """
    BASE_URL = "https://gamma-api.polymarket.com"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def fetch_events(self, query: str = "Bitcoin", active: bool = True, closed: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch events from Gamma API.
        """
        url = f"{self.BASE_URL}/events"
        params = {
            "tag_id": 1312, # Crypto Prices
            "active": "true" if active else "false",
            "closed": "true" if closed else "false",
            "limit": limit
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                events = resp.json()
                return [e for e in events if query.lower() in e.get('title', '').lower()]
        except httpx.TimeoutException:
            logger.warning("Gamma API timeout while fetching events", exc_info=True)
            return []
        except httpx.HTTPStatusError as e:
            logger.error(f"Gamma API error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Gamma events: {e}", exc_info=True)
            return []

    async def fetch_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch market details by condition ID.
        """
        url = f"{self.BASE_URL}/markets"
        params = {"condition_id": condition_id}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                markets = resp.json()
                return markets[0] if markets else None
        except httpx.TimeoutException:
            logger.warning(f"Gamma API timeout while fetching market {condition_id}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"Gamma API error for market {condition_id}: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Gamma market {condition_id}: {e}", exc_info=True)
            return None

    async def get_active_5m_btc_markets(self) -> List[Dict[str, Any]]:
        """
        Helper to get active Bitcoin 5m prediction markets.
        """
        events = await self.fetch_events(query="Bitcoin")
        markets = []
        for event in events:
            # Look for 5m in title or description if needed, 
            # but usually they are grouped in events
            for m in event.get('markets', []):
                markets.append(m)
        return markets
