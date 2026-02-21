import requests
import json
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime, timezone
import math

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
TAG_5M = 1312  # Task spec specifically requested TAG 1312 (Crypto Prices)
DB_PATH = "data/btc_predictor.db"

def get_db_volatility(start_ts):
    # Retrieve BTC volatility from local sqlite `ohlcv` table for the 5 min window
    start_ms = start_ts * 1000
    end_ms = (start_ts + 300) * 1000
    
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT open, close FROM ohlcv WHERE symbol='BTCUSDT' AND interval='1m' AND open_time >= ? AND open_time < ? ORDER BY open_time",
            (start_ms, end_ms)
        )
        rows = cur.fetchall()
        conn.close()
        
        if not rows:
            return None
            
        first_open = rows[0][0]
        last_close = rows[-1][1]
        
        if first_open == 0:
            return None
            
        pct_change = abs(last_close - first_open) / first_open * 100
        return pct_change
    except Exception:
        return None

def fetch_closed_5m_btc_markets(limit=2000):
    markets = []
    offset = 0
    while len(markets) < limit:
        url = f"{GAMMA_API}/events"
        params = {
            "tag_id": TAG_5M,
            "closed": "true",
            "limit": 100,
            "offset": offset,
            "order": "createdAt",
            "ascending": "false"
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except:
            break
            
        if not data:
            break
            
        for m in data:
            slug = m.get("slug", "")
            if "btc-updown-5m" in slug.lower():
                markets.append(m)
                
        offset += 100
        print(f"Fetched {offset} events, found {len(markets)} BTC markets")
        
        if len(data) < 100:
            break
            
    return markets[:limit]

def get_market_price_history(token_id):
    url = f"{CLOB_API}/prices-history"
    try:
        resp = requests.get(url, params={"market": token_id, "interval": "1d"}, timeout=10)
        if resp.status_code == 200:
            hist = resp.json().get("history", [])
            if hist: return hist
    except:
        pass
    try:
        resp = requests.get(url, params={"market": token_id, "interval": "max"}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("history", [])
    except:
        pass
    return []

def calculate_95_ci(p, n):
    if n == 0: return 0.0
    return 1.96 * math.sqrt((p * (1 - p)) / n)

def get_timezone_group(ts):
    dt = datetime.fromtimestamp(ts, timezone.utc)
    hour = dt.hour
    if 0 <= hour < 8: return "Asia (00-08)"
    elif 8 <= hour < 16: return "Europe (08-16)"
    else: return "US (16-00)"

def get_volatility_group(pct_change):
    if pct_change is None: return "Unknown"
    if pct_change < 0.1: return "Low (<0.1%)"
    if pct_change <= 0.3: return "Mid (0.1-0.3%)"
    return "High (>0.3%)"

from concurrent.futures import ThreadPoolExecutor

def process_market(m):
    slug = m.get("slug", "")
    start_ts_val = slug.split('-')[-1]
    try:
        start_ts = int(start_ts_val)
    except:
        return None
        
    event_markets = m.get("markets", [])
    if not event_markets: return None
    target_market = event_markets[0]
    
    outcome_prices_str = target_market.get("outcomePrices")
    if not outcome_prices_str: return None
    try:
        outcome_prices = json.loads(outcome_prices_str)
        actual_up_won = 1 if float(outcome_prices[0]) > 0.5 else 0
    except:
        return None
        
    clob_token_ids = target_market.get("clobTokenIds")
    if not clob_token_ids: return None
    try:
        token_ids = json.loads(clob_token_ids)
        token_id = token_ids[0]
    except:
        return None
        
    if not token_id: return None
    
    history = get_market_price_history(token_id)
    if not history: return None
        
    valid_prices = [p for p in history if 0.01 <= float(p['p']) <= 0.99]
    if not valid_prices: return None
    
    candidates = [p for p in valid_prices if start_ts <= int(p['t']) <= start_ts + 240]
    if not candidates:
        prev = [p for p in valid_prices if int(p['t']) <= start_ts + 60]
        if prev:
            candidates = [prev[-1]]
            
    if not candidates: return None
        
    target_t = start_ts + 45
    best_price = min(candidates, key=lambda x: abs(int(x['t']) - target_t))
    mid_price = float(best_price['p'])
    
    pct_change = get_db_volatility(start_ts)
    
    return {
        "slug": slug,
        "start_ts": start_ts,
        "tz": get_timezone_group(start_ts),
        "vol_group": get_volatility_group(pct_change),
        "implied_prob": mid_price,
        "actual": actual_up_won
    }

def analyze_calibration():
    print("--- Polymarket 5m BTC Calibration Analysis ---")
    markets = fetch_closed_5m_btc_markets(limit=1000)
    print(f"Retrieved {len(markets)} closed 5m BTC markets.")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = executor.map(process_market, markets)
        for i, res in enumerate(futures):
            if i > 0 and i % 100 == 0:
                print(f"Processing market {i}/{len(markets)}...")
            if res:
                results.append(res)

    if not results:
        print("No usable mid-market data found.")
        return

    df = pd.DataFrame(results)
    print(f"\nCollected {len(df)} fully matched samples.")
    
    df['brier'] = (df['implied_prob'] - df['actual'])**2
    brier_score = df['brier'].mean()
    baseline_brier = ((0.5 - df['actual'])**2).mean()
    print(f"\nOverall Brier Score: {brier_score:.4f} (Baseline: {baseline_brier:.4f})")
    print(f"Total Sample Size: {len(df)}")
    
    bins = np.linspace(0, 1, 11)
    df['bucket_idx'] = np.digitize(df['implied_prob'], bins) - 1
    df['bucket_idx'] = df['bucket_idx'].clip(0, 9)
    df['expected'] = bins[df['bucket_idx']] + 0.05
    
    def print_calibration(df_subset, group_cols=None):
        if group_cols:
            calib = df_subset.groupby(group_cols + ['expected']).agg(N=('actual', 'count'), win_rate=('actual', 'mean')).reset_index()
        else:
            calib = df_subset.groupby('expected').agg(N=('actual', 'count'), win_rate=('actual', 'mean')).reset_index()
            
        calib['win_rate'] = calib['win_rate'].fillna(0).astype(float)
        calib['dev'] = calib['win_rate'] - calib['expected']
        calib['95_ci'] = calib.apply(lambda r: calculate_95_ci(r['win_rate'], r['N']), axis=1)
        
        formatters = {'expected': '{:.2%}'.format, 'win_rate': '{:.2%}'.format, 'dev': '{:+.2%}'.format, '95_ci': '+-{:.2%}'.format}
        print(calib.to_string(formatters=formatters))

    print("\n[Overall Calibration Curve]")
    print_calibration(df)
    
    print("\n[Calibration by Timezone]")
    print_calibration(df[df['expected'].between(0.2, 0.8)], ['tz'])
    
    print("\n[Calibration by Volatility]")
    print_calibration(df[df['expected'].between(0.2, 0.8)], ['vol_group'])
    
    print("\n[40-60% Deep Dive]")
    mid_range = df[(df['implied_prob'] >= 0.4) & (df['implied_prob'] <= 0.6)]
    if not mid_range.empty:
        print_calibration(mid_range)
    else:
        print("No samples in 40-60%.")

if __name__ == "__main__":
    analyze_calibration()
