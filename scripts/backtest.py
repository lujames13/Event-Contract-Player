import argparse
import pandas as pd
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add src to sys.path to allow imports from btc_predictor
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.infrastructure.store import DataStore
from btc_predictor.backtest.engine import run_backtest
from btc_predictor.backtest.stats import calculate_backtest_stats
# from btc_predictor.strategies.xgboost_v1.strategy import XGBoostDirectionStrategy (Removed)
from btc_predictor.strategies.xgboost_v1.features import generate_features
from btc_predictor.strategies.registry import StrategyRegistry
STRATEGIES_DIR = "src/btc_predictor/strategies"
MODELS_DIR = "models"

def main():
    parser = argparse.ArgumentParser(description="BTC Predictor Backtest CLI")
    parser.add_argument("--strategy", type=str, required=True, help="Strategy name (e.g. xgboost_v1)")
    parser.add_argument("--timeframe", type=int, required=True, help="Timeframe in minutes (10, 30, 60, 1440)")
    parser.add_argument("--train-days", type=int, default=60, help="Initial training window in days")
    parser.add_argument("--test-days", type=int, default=7, help="Test window in days")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading symbol")
    parser.add_argument("--interval", type=str, default="1m", help="Data interval (1m, 5m, etc.)")
    parser.add_argument("--output", type=str, default="reports", help="Output directory for reports")
    parser.add_argument("--start-date", type=str, help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--n-jobs", type=int, default=-2, help="Parallel jobs (-1: all, -2: all-1)")
    parser.add_argument("--platform", type=str, default="binance", help="Trading platform (binance or polymarket)")
    
    args = parser.parse_args()
    
    # 1. Load Data
    print(f"Loading data for {args.symbol} {args.interval}...")
    store = DataStore()
    
    start_ms = None
    if args.start_date:
        # Subtract train_days to have enough data for the first training
        start_dt = datetime.strptime(args.start_date, "%Y-%m-%d") - timedelta(days=args.train_days)
        start_ms = int(start_dt.timestamp() * 1000)
    
    end_ms = None
    if args.end_date:
        end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")
        end_ms = int(end_dt.timestamp() * 1000)
        
    df = store.get_ohlcv(args.symbol, args.interval, start_time=start_ms, end_time=end_ms)
    
    if df.empty:
        print(f"No data found for {args.symbol} {args.interval} in database.")
        return
        
    print(f"Loaded {len(df)} rows. Range: {df.index[0]} to {df.index[-1]}")
    
    # Pre-calculate features to speed up backtest
    print("Pre-calculating features...")
    df = generate_features(df)
    
    # 2. Initialize Strategy
    try:
        registry = StrategyRegistry()
        registry.discover(STRATEGIES_DIR, MODELS_DIR)
        strategy = registry.get(args.strategy)
    except KeyError:
        print(f"Unknown strategy: {args.strategy}")
        print(f"Available strategies: {registry.list_names()}")
        return
        
    # 3. Run Backtest
    print(f"Starting walk-forward backtest for {args.strategy} ({args.timeframe}m)...")
    trades = run_backtest(
        strategy,
        df,
        timeframe_minutes=args.timeframe,
        train_days=args.train_days,
        test_days=args.test_days,
        n_jobs=args.n_jobs,
        platform=args.platform
    )
    
    if not trades:
        print("No trades generated during backtest.")
        return
        
    # 4. Calculate Stats
    stats = calculate_backtest_stats(trades, test_days=args.test_days)
    
    # 5. Output Report
    print("\n" + "="*40)
    print(f" BACKTEST REPORT: {args.strategy} {args.timeframe}m ")
    print("="*40)
    print(f"Total Trades:       {stats['total_trades']}")
    print(f"Total DA (Acc):     {stats['total_da']:.2%}")
    print(f"Higher DA:          {stats['higher_da']:.2%}")
    print(f"Lower DA:           {stats['lower_da']:.2%}")
    print(f"Total PnL (USDT):   {stats['total_pnl']:.2f}")
    print(f"Max Drawdown:       {stats['mdd']:.2f}")
    print(f"Sharpe Ratio:       {stats['sharpe']:.2f}")
    print(f"Max Consecutive L:  {stats['max_consecutive_losses']}")
    print("="*40)
    
    # Save to JSON
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"backtest_{args.strategy}_{args.timeframe}m_{timestamp}.json"
    report_path = output_dir / report_filename
    
    # Include raw trades for merging later if needed
    full_output = {
        "stats": stats,
        "trades": [vars(t) for t in trades]
    }
    
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(full_output, f, indent=4, default=str)
        
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    main()
