import json
import pandas as pd
from pathlib import Path
import sys
import argparse
from datetime import datetime

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.backtest.stats import calculate_backtest_stats

def main():
    parser = argparse.ArgumentParser(description="Merge segmented backtest reports")
    parser.add_argument("--strategy", type=str, required=True, help="Strategy name")
    parser.add_argument("--timeframe", type=int, required=True, help="Timeframe (10, 30, 60, 1440)")
    parser.add_argument("--dir", type=str, default="reports", help="Directory with report files")
    parser.add_argument("--output", type=str, help="Output filename")
    parser.add_argument("--test-days", type=int, default=7, help="Test window in days")
    
    args = parser.parse_args()
    
    report_dir = Path(args.dir)
    pattern = f"backtest_{args.strategy}_{args.timeframe}m_*.json"
    
    all_trades = []
    files_processed = 0
    
    for file_path in report_dir.glob(pattern):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'trades' in data:
                all_trades.extend(data['trades'])
                files_processed += 1
                print(f"Loaded {len(data['trades'])} trades from {file_path}")
    
    if not all_trades:
        print("No trades found to merge.")
        return
        
    print(f"Total trades collected: {len(all_trades)} from {files_processed} files.")
    
    # Sort and remove potential overlaps
    df = pd.DataFrame(all_trades)
    df['open_time'] = pd.to_datetime(df['open_time'])
    df = df.sort_values('open_time').drop_duplicates(subset=['open_time'])
    
    unique_trades = df.to_dict('records')
    print(f"Final unique trades count: {len(unique_trades)}")
    
    # Use centralized stats calculation
    final_stats = calculate_backtest_stats(unique_trades, test_days=args.test_days)
    
    # Output
    print("\n" + "="*40)
    print(f" MERGED BACKTEST REPORT: {args.strategy} {args.timeframe}m ")
    print("="*40)
    print(f"Total Trades:       {final_stats['total_trades']}")
    print(f"Total DA (Acc):     {final_stats['total_da']:.2%}")
    print(f"Inverted DA:        {final_stats.get('inverted_da', 0.0):.2%}")
    print(f"Higher DA:          {final_stats['higher_da']:.2%}")
    print(f"Lower DA:           {final_stats['lower_da']:.2%}")
    print(f"Total PnL (USDT):   {final_stats['total_pnl']:.2f}")
    print(f"Max Drawdown:       {final_stats['mdd']:.2f}")
    print(f"Sharpe Ratio:       {final_stats['sharpe']:.2f}")
    print(f"Max Consecutive L:  {final_stats['max_consecutive_losses']}")
    print("="*40)
    
    output_path = args.output if args.output else report_dir / f"merged_backtest_{args.strategy}_{args.timeframe}m.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_stats, f, indent=4)
    print(f"Final report saved to {output_path}")

if __name__ == "__main__":
    main()
