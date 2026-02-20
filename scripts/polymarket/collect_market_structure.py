import requests
import json
import logging
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
CLOB_BASE_URL = "https://clob.polymarket.com"

def fetch_gamma_events(query: str = "Bitcoin Up or Down") -> List[Dict[str, Any]]:
    """Fetch events from Gamma API with a specific query."""
    url = f"{GAMMA_BASE_URL}/events"
    params = {
        "tag_id": 1312, # Crypto Prices
        "active": "true",
        "closed": "false",
        "limit": 50
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        # Filter by title contains Bitcoin
        return [e for e in events if query.lower() in e.get('title', '').lower()]
    except Exception as e:
        logger.error(f"Error fetching Gamma events: {e}")
        return []

def fetch_closed_events(query: str = "Bitcoin Up or Down") -> List[Dict[str, Any]]:
    """Fetch recently closed events for resolution analysis."""
    url = f"{GAMMA_BASE_URL}/events"
    params = {
        "tag_id": 1312,
        "active": "true",
        "closed": "true",
        "limit": 50
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        return [e for e in events if query.lower() in e.get('title', '').lower()]
    except Exception as e:
        logger.error(f"Error fetching Gamma events: {e}")
        return []

def fetch_gamma_markets_by_tag(tag_id: int = 100512) -> List[Dict[str, Any]]:
    """Fetch markets by tag ID. 100512 is often used for Crypto/BTC markets."""
    url = f"{GAMMA_BASE_URL}/markets"
    params = {
        "tag_id": tag_id,
        "limit": 100,
        "closed": "true"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching Gamma markets: {e}")
        return []

def fetch_clob_market(condition_id: str) -> Dict[str, Any]:
    """Fetch market details from CLOB API."""
    url = f"{CLOB_BASE_URL}/markets/{condition_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching CLOB market {condition_id}: {e}")
        return {}

def analyze_lifecycle(market: Dict[str, Any]):
    """Print interesting timing info about a market."""
    mq = market.get('question', '')
    cid = market.get('condition_id', '')
    start_date = market.get('start_date')
    end_date = market.get('end_date')
    created_at = market.get('created_at')
    
    logger.info(f"Market: {mq}")
    logger.info(f"  Condition ID: {cid}")
    logger.info(f"  Created At: {created_at}")
    logger.info(f"  Start Date: {start_date}")
    logger.info(f"  End Date:   {end_date}")
    
    if created_at and start_date:
        try:
            # Polymarket use ISO formats
            c = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            s = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            logger.info(f"  Lead time (creation to start): {s - c}")
        except:
            pass

def main():
    parser = argparse.ArgumentParser(description="Collect Polymarket market structure data.")
    parser.add_argument("--slug", type=str, default="bitcoin-price-at-", help="Slug to filter by")
    args = parser.parse_args()

    logger.info(f"Collecting market data for slug: {args.slug}")
    
    # 1. Fetch active events
    events = fetch_gamma_events()
    logger.info(f"Found {len(events)} active Bitcoin 5m events.")
    
    # 2. Fetch closed events for resolution checking
    closed_events = fetch_closed_events()
    logger.info(f"Found {len(closed_events)} recently closed Bitcoin 5m events.")
    
    all_events = events + closed_events
    market_data = []
    
    for event in all_events:
        event_slug = event.get('slug', '')
        markets = event.get('markets', [])
        logger.info(f"Event: {event.get('title')} ({event_slug}) with {len(markets)} markets")
        
        for m in markets:
            # Cross valid with CLOB
            cid = m.get('condition_id')
            if cid:
                clob_info = fetch_clob_market(cid)
                m['clob_info'] = clob_info
            
            market_data.append(m)

    # Save raw data for analysis
    output_file = "reports/polymarket/market_structure_raw.json"
    with open(output_file, "w") as f:
        json.dump(market_data, f, indent=2)
    logger.info(f"Raw market data saved to {output_file}")

if __name__ == "__main__":
    main()
