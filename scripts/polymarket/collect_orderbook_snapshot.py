import os
import time
import json
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("collect_orderbook.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
GAMMA_API_URL = "https://gamma-api.polymarket.com/events"
CLOB_API_URL = "https://clob.polymarket.com/book"
BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
DATA_DIR = Path("data/polymarket")
DATA_FILE = DATA_DIR / "orderbook_snapshots.jsonl"

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_active_markets():
    """Fetch active BTC 5m and 15m markets."""
    params = {
        "tag_id": 1312,
        "active": "true",
        "closed": "false",
        "limit": 1000
    }
    try:
        resp = requests.get(GAMMA_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        
        btc_markets = []
        now = datetime.now(timezone.utc)
        for event in events:
            slug = event.get("slug", "").lower()
            if "btc-updown" in slug and ("-5m" in slug or "-15m" in slug):
                for market in event.get("markets", []):
                    if not market.get("active") or market.get("closed"):
                        continue
                    
                    # Filter for future/current markets
                    end_date_str = market.get("endDate")
                    if not end_date_str:
                        continue
                        
                    end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    if end_dt < now:
                        continue

                    tokens = json.loads(market.get("clobTokenIds", "[]"))
                    if not tokens:
                        continue
                        
                    # We usually track the 'Up' token for price probability
                    # outcomes[0] is 'Yes/Up', outcomes[1] is 'No/Down'
                    btc_markets.append({
                        "event_slug": slug,
                        "market_id": market.get("id"),
                        "condition_id": market.get("conditionId"),
                        "up_token_id": tokens[0],
                        "down_token_id": tokens[1] if len(tokens) > 1 else None,
                        "end_date": market.get("endDate"),
                        "timeframe": "5m" if "-5m" in slug else "15m"
                    })
        return btc_markets
    except Exception as e:
        logger.error(f"Error fetching active markets: {e}")
        return []

def get_order_book(token_id):
    """Fetch order book for a given token ID."""
    params = {"token_id": token_id}
    try:
        resp = requests.get(CLOB_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching order book for {token_id}: {e}")
        return None

def get_binance_price():
    """Fetch real-time BTC price from Binance."""
    try:
        resp = requests.get(BINANCE_API_URL, timeout=5)
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception as e:
        logger.error(f"Error fetching Binance price: {e}")
        return None

def walk_the_book(orders, target_usd):
    """Calculate average price for a target USD size by walking the book."""
    if not orders:
        return None
        
    filled_usd = 0.0
    total_shares = 0.0
    
    for order in orders:
        try:
            price = float(order.get("price"))
            size = float(order.get("size"))  # size is in shares
            
            # Polymarket price is 0-1. Cost to buy 'size' shares is price * size
            available_usd = price * size
            
            if filled_usd + available_usd >= target_usd:
                needed_usd = target_usd - filled_usd
                needed_shares = needed_usd / price
                total_shares += needed_shares
                filled_usd = target_usd
                break
            else:
                filled_usd += available_usd
                total_shares += size
        except (ValueError, TypeError):
            continue
            
    if filled_usd < target_usd:
        return None  # Insufficient depth
        
    avg_price = target_usd / total_shares
    return avg_price

def collect_snapshots(duration_hrs=2, interval_sec=5):
    ensure_data_dir()
    end_time = time.time() + duration_hrs * 3600
    
    logger.info(f"Starting collection for {duration_hrs} hours. Interval: {interval_sec}s")
    
    while time.time() < end_time:
        start_loop = time.time()
        
        markets = get_active_markets()
        binance_price = get_binance_price()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        for m in markets:
            book = get_order_book(m["up_token_id"])
            if not book:
                continue
                
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            
            # Sort orders (bids desc, asks asc)
            bids = sorted(bids, key=lambda x: float(x["price"]), reverse=True)
            asks = sorted(asks, key=lambda x: float(x["price"]))
            
            best_bid = float(bids[0]["price"]) if bids else None
            best_ask = float(asks[0]["price"]) if asks else None
            spread = (best_ask - best_bid) if best_bid and best_ask else None
            midpoint = (best_ask + best_bid) / 2 if best_bid and best_ask else None
            
            depth_50 = walk_the_book(asks, 50.0)
            depth_100 = walk_the_book(asks, 100.0)
            
            # Calculate market lifecycle stage (seconds since start)
            # Market ends at end_date. For 5m market, start is end_date - 5m
            try:
                end_dt = datetime.fromisoformat(m["end_date"].replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                delta = (now_dt - end_dt).total_seconds()
                # If delta is negative, we are before end_date
                # For a 5m cycle, it started at end_dt - 300s
                time_since_start = 300 + delta if m["timeframe"] == "5m" else 900 + delta
            except:
                time_since_start = None

            snapshot = {
                "type": "orderbook",
                "timestamp": timestamp,
                "market_slug": m["event_slug"],
                "market_id": m["market_id"],
                "timeframe": m["timeframe"],
                "lifecycle_sec": time_since_start,
                "binance_price": binance_price,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "midpoint": midpoint,
                "depth_at_50": depth_50,
                "depth_at_100": depth_100,
                "top_5_bids": bids[:5],
                "top_5_asks": asks[:5]
            }
            
            with open(DATA_FILE, "a") as f:
                f.write(json.dumps(snapshot) + "\n")
        
        # Sleep to maintain interval
        elapsed = time.time() - start_loop
        wait = max(0, interval_sec - elapsed)
        time.sleep(wait)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Collect Polymarket order book snapshots.")
    parser.add_argument("--duration", type=float, default=2.0, help="Duration in hours")
    parser.add_argument("--interval", type=int, default=5, help="Interval in seconds")
    
    args = parser.parse_args()
    try:
        collect_snapshots(duration_hrs=args.duration, interval_sec=args.interval)
    except KeyboardInterrupt:
        logger.info("Collection stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
