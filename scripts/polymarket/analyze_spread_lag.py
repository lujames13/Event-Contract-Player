import json
import pandas as pd
import numpy as np
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_FILE = Path("data/polymarket/orderbook_snapshots.jsonl")
OUTPUT_PATH = Path("reports/polymarket/PM-3-lite-spread-snapshot.md")

def analyze_snapshots():
    if not DATA_FILE.exists():
        logger.error(f"Data file {DATA_FILE} not found.")
        return

    logger.info(f"Reading {DATA_FILE}...")
    data = []
    with open(DATA_FILE, "r") as f:
        for line in f:
            try:
                data.append(json.loads(line))
            except:
                continue
    
    if not data:
        logger.warning("No data found in JSONL.")
        return

    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 1. Spread Analysis
    def get_spread_stats(sub_df):
        if sub_df.empty: return {}
        return {
            "Median": sub_df['spread'].median(),
            "Mean": sub_df['spread'].mean(),
            "P25": sub_df['spread'].quantile(0.25),
            "P75": sub_df['spread'].quantile(0.75)
        }

    stats_5m = get_spread_stats(df[df['timeframe'] == '5m'])
    stats_15m = get_spread_stats(df[df['timeframe'] == '15m'])

    # Spread by lifecycle
    def get_lifecycle_stats(sub_df):
        bins = [0, 60, 180, 240, 301]
        labels = ["0-60s", "60-180s", "180-240s", "last 60s"]
        sub_df['stage'] = pd.cut(sub_df['lifecycle_sec'], bins=bins, labels=labels)
        return sub_df.groupby('stage')['spread'].median()

    lifecycle_5m = get_lifecycle_stats(df[df['timeframe'] == '5m'])
    
    # 2. Depth Analysis
    def get_depth_stats(sub_df):
        if sub_df.empty: return (None, None)
        # Slippage = (Avg Price - Midpoint) / Midpoint
        slippage_50 = ((sub_df['depth_at_50'] - sub_df['midpoint']) / sub_df['midpoint']).mean()
        slippage_100 = ((sub_df['depth_at_100'] - sub_df['midpoint']) / sub_df['midpoint']).mean()
        return slippage_50, slippage_100

    slip50_5m, slip100_5m = get_depth_stats(df[df['timeframe'] == '5m'])
    slip50_15m, slip100_15m = get_depth_stats(df[df['timeframe'] == '15m'])

    # 3. Lag Analysis (Binance Lead)
    # This is tricky with 5s snapshots. We look for correlation lag.
    # We'll use cross-correlation of return signs if possible, 
    # but with 5s it's mostly 0.
    # Simplified: Find time difference between major Binance move and Midpoint move.
    lag_msg = "Binance price lead 策略在當前延遲下 [尚未具備足夠高頻數據判定]"
    
    # For reporting purposes, we calculate the naive lag if variance exists
    try:
        if len(df) > 10:
            df_sorted = df.sort_values('timestamp')
            # Calculate correlation at different lags
            corrs = []
            for lag in range(0, 5): # 0 to 20 seconds (lag * 5s)
                # Note: 5s is too coarse for sub-second lag, but we do our best
                c = df_sorted['binance_price'].corr(df_sorted['midpoint'].shift(-lag))
                corrs.append(c)
            best_lag_idx = np.nanargmax(corrs) if not np.isnan(corrs).all() else 0
            best_lag_sec = best_lag_idx * 5
            if best_lag_sec > 2:
                lag_msg = f"Binance price lead 可能可行 (Lag ~{best_lag_sec}s > 2s E2E)"
            else:
                lag_msg = f"Binance price lead 不可行 (Lag ~{best_lag_sec}s <= 2s E2E)"
    except:
        pass

    # Generate Report
    report = f"""# PM-3-lite: Order Book Spread Snapshot 分析

## 1. Spread 統計表

| 指標 | 5m Market | 15m Market |
|------|-----------|------------|
| Median Spread | {stats_5m.get('Median', 0):.4f} | {stats_15m.get('Median', 0):.4f} |
| Mean Spread | {stats_5m.get('Mean', 0):.4f} | {stats_15m.get('Mean', 0):.4f} |
| P25 / P75 Spread | {stats_5m.get('P25', 0):.4f} / {stats_5m.get('P75', 0):.4f} | {stats_15m.get('P25', 0):.4f} / {stats_15m.get('P75', 0):.4f} |
| Spread at 0-60s | {lifecycle_5m.get('0-60s', 0):.4f} | - |
| Spread at 60-180s | {lifecycle_5m.get('60-180s', 0):.4f} | - |
| Spread at 180-240s | {lifecycle_5m.get('180-240s', 0):.4f} | - |
| Spread at last 60s | {lifecycle_5m.get('last 60s', 0):.4f} | - |

## 2. Depth 統計 (Slippage)
- **$50 Order Size**: 
  - 5m: {slip50_5m*100 if slip50_5m else 0:.2f}%
  - 15m: {slip50_15m*100 if slip50_15m else 0:.2f}%
- **$100 Order Size**:
  - 5m: {slip100_5m*100 if slip100_5m else 0:.2f}%
  - 15m: {slip100_15m*100 if slip100_15m else 0:.2f}%

## 3. 結論
- **Typical Spread**: {stats_5m.get('Median', 0):.4f}
- **Total Cost (Spread + Taker Fee)**: 在 $50 order size 下約 {(stats_5m.get('Median', 0) + 0.0312)*100:.2f}% (含 3.12% fee)

## 4. Binance Price Lead 觀測 (PM-6.5)
- **Lag 分析**: {lag_msg}
- **結論**: 在 5s 採樣精度下，Lag 觀測受限。

"""
    with open(OUTPUT_PATH, "w") as f:
        f.write(report)
    logger.info(f"Report generated at {OUTPUT_PATH}")

if __name__ == "__main__":
    analyze_snapshots()
