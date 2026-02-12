import os
import sys
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from binance.client import Client
import pandas as pd
from pathlib import Path

# Add src to sys.path to allow imports from btc_predictor
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.data.store import DataStore

def fetch_history(symbol: str, interval: str, start_str: str, end_str: str = None):
    load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    
    client = Client(api_key, api_secret)
    store = DataStore()
    
    print(f"Fetching {interval} klines for {symbol} from {start_str}...")
    
    # Simple way to get data without complex chunking logic
    # get_historical_klines already handles the looping internally.
    # The slowness is just the sheer volume of data for 1m.
    # We will just call it and let it finish.
    
    klines = client.get_historical_klines(
        symbol=symbol,
        interval=interval,
        start_str=start_str,
        end_str=end_str
    )
    
    if not klines:
        print(f"No data found for {symbol} {interval}")
        return

    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume", 
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ])
    
    # Convert types
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
    
    # Save to store
    store.save_ohlcv(df, symbol, interval)
    print(f"Saved {len(df)} rows for {interval} to database.")

def main():
    parser = argparse.ArgumentParser(description="Fetch historical BTC klines from Binance")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Symbol to fetch (default: BTCUSDT)")
    parser.add_argument("--intervals", nargs="+", default=["1m", "5m", "1h", "1d"], help="Intervals to fetch")
    parser.add_argument("--start", type=str, default="1 Jan, 2024", help="Start date (e.g., '1 Jan, 2024')")
    
    args = parser.parse_args()
    
    for interval in args.intervals:
        try:
            fetch_history(args.symbol, interval, args.start)
        except Exception as e:
            print(f"Error fetching {interval}: {e}")

if __name__ == "__main__":
    main()
