import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
import time

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# Tag ID for 5M Markets (found during investigation)
TAG_5M = 102892

def fetch_closed_5m_btc_markets(limit=500):
    markets = []
    offset = 0
    while len(markets) < limit:
        url = f"{GAMMA_API}/markets"
        params = {
            "tag_id": TAG_5M,
            "closed": "true",
            "limit": 100,
            "offset": offset,
            "order": "createdAt",
            "ascending": "false"
        }
        print(f"Fetching closed 5m markets offset {offset}...")
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
            
        for m in data:
            slug = m.get("slug", "")
            if "btc-updown-5m" in slug:
                markets.append(m)
        
        offset += 100
        if len(data) < 100:
            break
            
    return markets[:limit]

def get_market_price_history(token_id):
    url = f"{CLOB_API}/prices-history"
    params = {
        "market": token_id,
        "interval": "all",
        "fidelity": 1
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("history", [])
    except:
        return []

def analyze_calibration():
    print("--- Polymarket 5m BTC Calibration Analysis ---")
    markets = fetch_closed_5m_btc_markets(limit=500)
    print(f"Retrieved {len(markets)} closed 5m BTC markets.")
    
    results = []
    
    print(f"Starting loop over markets...")
    for i, m in enumerate(markets):
        slug = m.get("slug")
        if i % 50 == 0:
            print(f"Checking market {i}/{len(markets)}: {slug}")
        
        outcome_prices_str = m.get("outcomePrices")
        if not outcome_prices_str:
            continue
        try:
            outcome_prices = json.loads(outcome_prices_str)
        except:
            continue
            
        if len(outcome_prices) < 2:
            continue
            
        try:
            actual_up_won = 1 if float(outcome_prices[0]) > 0.5 else 0
        except:
            continue
            
        clob_token_ids = m.get("clobTokenIds")
        if not clob_token_ids:
            continue
        try:
            token_ids = json.loads(clob_token_ids)
            up_token_id = token_ids[0]
        except:
            continue
            
        history = get_market_price_history(up_token_id)
        if not history:
            continue
            
        valid_prices = [p for p in history if 0.01 < float(p['p']) < 0.99]
        if not valid_prices:
            continue
            
        mid_price = float(valid_prices[-1]['p'])
        
        results.append({
            "slug": slug,
            "implied_prob": mid_price,
            "actual": actual_up_won
        })
        
        if len(results) % 50 == 0:
            print(f"Processed {len(results)} markets...")

    if not results:
        print("No usable data found for calibration.")
        return

    df = pd.DataFrame(results)
    
    # Avoid categorical issues by using float midpoints directly
    bins = np.linspace(0, 1, 11)
    df['bucket_idx'] = np.digitize(df['implied_prob'], bins) - 1
    # Cap at 9 (for the 0.9-1.0 bucket)
    df['bucket_idx'] = df['bucket_idx'].clip(0, 9)
    df['expected'] = bins[df['bucket_idx']] + 0.05 # center of bucket
    
    calibration = df.groupby('expected', observed=False).agg(
        n=('actual', 'count'),
        actual_win_rate=('actual', 'mean')
    ).reset_index()
    
    calibration['actual_win_rate'] = calibration['actual_win_rate'].fillna(0).astype(float)
    calibration['deviation'] = calibration['actual_win_rate'] - calibration['expected']
    
    # Brier Score
    df['brier'] = (df['implied_prob'] - df['actual'])**2
    brier_score = df['brier'].mean()
    
    print("\n[Calibration Curve]")
    print(calibration.to_string())
    print(f"\nOverall Brier Score: {brier_score:.4f}")
    
    baseline_brier = ((0.5 - df['actual'])**2).mean()
    print(f"Baseline Brier Score (50% guess): {baseline_brier:.4f}")
    improvement = (baseline_brier - brier_score) / baseline_brier * 100
    print(f"Improvement over baseline: {improvement:.2f}%")
    
    if brier_score < 0.20:
        conclusion = "🟢 Good calibration, very low error."
    elif brier_score < 0.24:
        conclusion = "🟡 Moderate calibration, potential edge."
    else:
        conclusion = "🔴 Poor calibration or needs more data."
        
    print(f"\nConclusion: {conclusion}")

if __name__ == "__main__":
    analyze_calibration()
