import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from src.btc_predictor.polymarket.gamma_client import GammaClient
from src.btc_predictor.infrastructure.store import DataStore

logger = logging.getLogger(__name__)

class PolymarketTracker:
    """
    Tracks Polymarket market lifecycles and syncs them to DataStore.
    """
    def __init__(self, gamma_client: GammaClient, store: DataStore):
        self.gamma_client = gamma_client
        self.store = store

    async def sync_active_markets(self, timeframes: List[int] = [5, 15]):
        """
        Fetch active BTC markets from Gamma API and sync to DataStore.
        Filters markets by duration matching requested timeframes.
        """
        logger.info(f"Syncing active Polymarket BTC markets for timeframes: {timeframes}")
        raw_markets = await self.gamma_client.get_active_5m_btc_markets()
        
        synced_count = 0
        for m in raw_markets:
            try:
                # Parse start/end times to determine timeframe
                # Gamma returns ISO strings usually
                start_str = m.get("startDate") or m.get("start_time")
                end_str = m.get("endDate") or m.get("end_time")
                
                if not start_str or not end_str:
                    continue
                
                start_dt = self._parse_iso_datetime(start_str)
                end_dt = self._parse_iso_datetime(end_str)
                
                duration_min = round((end_dt - start_dt).total_seconds() / 60)
                
                # Check if it matches requested timeframes (with some slack)
                matched = False
                for tf in timeframes:
                    if abs(duration_min - tf) <= 1:
                        matched = True
                        break
                
                if not matched:
                    continue

                # Extract token IDs. Usually tokens[0] is 'Yes' (Up), tokens[1] is 'No' (Down)
                tokens = m.get("tokens", [])
                if len(tokens) < 2:
                    logger.warning(f"Market {m.get('slug')} has fewer than 2 tokens")
                    continue
                
                # Note: On Polymarket price markets, 'Yes' means 'At or above' (Up)
                # 'No' means 'Lower' (Down)
                up_token_id = tokens[0].get("tokenId")
                down_token_id = tokens[1].get("tokenId")
                
                if not up_token_id or not down_token_id:
                    continue

                market_data = {
                    "slug": m.get("slug"),
                    "condition_id": m.get("conditionId"),
                    "up_token_id": up_token_id,
                    "down_token_id": down_token_id,
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "price_to_beat": float(m.get("line")) if m.get("line") else None,
                    "outcome": m.get("outcome"),
                    "close_price": float(m.get("close_price")) if m.get("close_price") else None
                }
                
                self.store.save_pm_market(market_data)
                synced_count += 1
                
            except Exception as e:
                logger.error(f"Error processing market {m.get('slug')}: {e}", exc_info=True)

        logger.info(f"Successfully synced {synced_count} markets to DataStore.")

    def get_active_market(self, timeframe_minutes: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve the latest tradeable market for the given timeframe.
        """
        return self.store.get_active_pm_market(timeframe_minutes)

    def _parse_iso_datetime(self, dt_str: str) -> datetime:
        """Helper to parse ISO datetime strings, handling 'Z' suffix."""
        if dt_str.endswith('Z'):
            dt_str = dt_str.replace('Z', '+00:00')
        return datetime.fromisoformat(dt_str)
