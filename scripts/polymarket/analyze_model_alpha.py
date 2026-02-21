import os
import json
import sqlite3
import logging
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from btc_predictor.strategies.catboost_v1.strategy import CatBoostDirectionStrategy
from btc_predictor.strategies.lgbm_v2.strategy import LGBMDirectionStrategyV2
from btc_predictor.infrastructure.store import DataStore

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DB_PATH = "data/btc_predictor.db"

def fetch_closed_5m_btc_markets(limit=200):
    markets = []
    offset = 0
    while len(markets) < limit:
        url = f"{GAMMA_API}/events"
        params = {
            "tag_id": 1312,
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
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            break
            
        if not data:
            break
            
        for event in data:
            slug = event.get("slug", "")
            if "btc-updown-5m" in slug.lower():
                markets.append(event)
                
        offset += 100
        if len(data) < 100:
            break
            
    return markets[:limit]

def get_market_price_at_start(token_id, start_ts):
    """Get the last trade price before or at start_ts."""
    url = f"{CLOB_API}/prices-history"
    try:
        resp = requests.get(url, params={"market": token_id, "interval": "max"}, timeout=10)
        if resp.status_code == 200:
            history = resp.json().get("history", [])
            # History is usually sorted by time. Find the last price p where t <= start_ts
            valid_prices = [p for p in history if int(p['t']) <= start_ts]
            if valid_prices:
                return float(valid_prices[-1]['p'])
    except Exception as e:
        logger.error(f"Error fetching price history for {token_id}: {e}")
    return None

def get_ohlcv_before(start_ts, limit=500):
    """Fetch OHLCV data from SQLite before start_ts."""
    start_ms = start_ts * 1000
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        query = """
            SELECT open_time, open, high, low, close, volume 
            FROM ohlcv 
            WHERE symbol='BTCUSDT' AND interval='1m' AND open_time < ? 
            ORDER BY open_time DESC LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(start_ms, limit))
        conn.close()
        
        if df.empty:
            return None
            
        df = df.sort_values("open_time")
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df
    except Exception as e:
        logger.error(f"Error fetching OHLCV: {e}")
        return None

def analyze_model_alpha(limit=200):
    logger.info("Loading models...")
    catboost = CatBoostDirectionStrategy(model_path="models/catboost_v1")
    lgbm = LGBMDirectionStrategyV2(model_path="models/lgbm_v2")
    
    if not catboost.available_timeframes and not lgbm.available_timeframes:
        logger.error("No models available!")
        return
        
    logger.info(f"Fetching {limit} closed markets...")
    events = fetch_closed_5m_btc_markets(limit=limit)
    logger.info(f"Found {len(events)} markets.")
    
    results = []
    
    for i, event in enumerate(events):
        slug = event.get("slug", "")
        try:
            start_ts = int(slug.split('-')[-1])
        except:
            continue
            
        market = event.get("markets", [])[0]
        token_ids = json.loads(market.get("clobTokenIds", "[]"))
        if not token_ids: continue
        up_token_id = token_ids[0]
        
        # Outcome
        outcome_prices_str = market.get("outcomePrices")
        if not outcome_prices_str: continue
        outcome_prices = json.loads(outcome_prices_str)
        actual_up_won = 1 if float(outcome_prices[0]) > 0.5 else 0
        
        # Market price at start
        market_p_up = get_market_price_at_start(up_token_id, start_ts)
        if market_p_up is None: continue
        
        # Get OHLCV
        ohlcv = get_ohlcv_before(start_ts)
        if ohlcv is None or len(ohlcv) < 300:
            # Try fetching from Binance if not in DB
            # BUT we follow the rule: "Don't make external requests unless necessary"
            # Actually for analysis, we might need it. 
            # Given we have 1.6M rows, we probably have the data.
            continue
            
        # Inference
        row = {
            "slug": slug,
            "start_time": datetime.fromtimestamp(start_ts, timezone.utc).isoformat(),
            "market_p_up": market_p_up,
            "actual": actual_up_won
        }
        
        # CatBoost 10m
        if 10 in catboost.available_timeframes:
            sig = catboost.predict(ohlcv, 10)
            p_up = sig.confidence if sig.direction == "higher" else (1.0 - sig.confidence)
            row["catboost_p_up"] = p_up
            row["catboost_alpha"] = p_up - market_p_up
            row["catboost_correct"] = 1 if (p_up > 0.5) == actual_up_won else 0
            
        # LGBM 60m
        if 60 in lgbm.available_timeframes:
            sig = lgbm.predict(ohlcv, 60)
            p_up = sig.confidence if sig.direction == "higher" else (1.0 - sig.confidence)
            row["lgbm_p_up"] = p_up
            row["lgbm_alpha"] = p_up - market_p_up
            row["lgbm_correct"] = 1 if (p_up > 0.5) == actual_up_won else 0
            
        results.append(row)
        if (i+1) % 20 == 0:
            logger.info(f"Processed {i+1}/{len(events)} markets...")

    if not results:
        logger.warning("No results to analyze.")
        return

    df = pd.DataFrame(results)
    output_path = Path("reports/polymarket/PM-6-model-alpha-baseline.md")
    
    # Generate Report Content
    report = f"""# PM-6: Model Alpha vs Market Price Baseline 分析

## 1. 實驗設計
- **樣本數**: {len(df)} 個已結算 5m BTC 市場
- **評估模型**:
  - `catboost_v1` (10m model): 用於 5m 市場預測 (Timeframe Mismatch)
  - `lgbm_v2` (60m model): 用於 5m 市場預測 (Timeframe Mismatch)
- **Alpha 定義**: `Alpha = Model_P(Up) - Market_Implied_P(Up)`
- **分析焦點**: 不同 Alpha 區間下的模型勝率與 Net Edge

## 2. Alpha 分佈統計

| 指標 | CatBoost v1 (10m) | LGBM v2 (60m) |
|------|-------------------|----------------|
| Mean Alpha | {df['catboost_alpha'].mean():.2%} | {df['lgbm_alpha'].mean():.2%} |
| Median Alpha | {df['catboost_alpha'].median():.2%} | {df['lgbm_alpha'].median():.2%} |
| Std Dev | {df['catboost_alpha'].std():.2%} | {df['lgbm_alpha'].std():.2%} |
| |alpha| > 5% | {(df['catboost_alpha'].abs() > 0.05).mean():.2%} | {(df['lgbm_alpha'].abs() > 0.05).mean():.2%} |
| |alpha| > 10% | {(df['catboost_alpha'].abs() > 0.10).mean():.2%} | {(df['lgbm_alpha'].abs() > 0.10).mean():.2%} |

## 3. 條件勝率分析 (CatBoost v1 10m)

| Alpha Range | N | Model Win Rate | Market Implied WR | Net Edge | Taker BE (3.12%) | Maker BE (0%) |
|-------------|---|---------------|-------------------|----------|------------------|---------------|
"""

    def get_range_stats(data, col_alpha, col_correct):
        bins = [-float('inf'), -0.1, -0.05, 0, 0.05, 0.1, float('inf')]
        labels = ["alpha < -10%", "-10% ≤ alpha < -5%", "-5% ≤ alpha < 0%", "0% ≤ alpha < 5%", "5% ≤ alpha < 10%", "alpha ≥ 10%"]
        data['bucket'] = pd.cut(data[col_alpha], bins=bins, labels=labels)
        stats = data.groupby('bucket').agg(
            N=(col_alpha, 'count'),
            win_rate=(col_correct, 'mean'),
            market_wr=('market_p_up', 'mean')
        ).reset_index()
        return stats

    if 'catboost_alpha' in df.columns:
        cat_stats = get_range_stats(df, 'catboost_alpha', 'catboost_correct')
        for _, r in cat_stats.iterrows():
            net_edge = r['win_rate'] - r['market_wr']
            taker_be = "✅" if net_edge > 0.0312 else "❌"
            maker_be = "✅" if net_edge > 0 else "❌"
            report += f"| {r['bucket']} | {r['N']} | {r['win_rate']:.2%} | {r['market_wr']:.2%} | {net_edge:+.2%} | {taker_be} | {maker_be} |\n"

    report += """
## 4. 關鍵發現
1. **Timeframe Mismatch 影響**: 當前模型是針對 10m/60m 訓練的，但在 5m 市場上仍展現出一定的 Alpha 分佈。
2. **Net Edge 觀察**: 當 Alpha 絕對值較大時，模型的勝率是否能覆蓋 Taker Fee ({:.2%})。
3. **結算條件**: Polymarket 包含平盤 (>=)，這對 Up 方向有利。

## 5. 結論與優化方向
- **Alpha 現狀**: 量化模型與市場共識的偏離度。
- **Top 優化方向**:
  1. 針對 5m timeframe 訓練專屬模型。
  2. 調整 Label 生成邏輯以匹配 Polymarket 的 `>=` 規則（平盤 = Up）。
  3. 加入 Polymarket 專屬特徵（如 Order Book Imbalance, Funding Rate）。

""".format(0.0312)

    with open(output_path, "w") as f:
        f.write(report)
    logger.info(f"Report generated at {output_path}")

if __name__ == "__main__":
    analyze_model_alpha(limit=300)
