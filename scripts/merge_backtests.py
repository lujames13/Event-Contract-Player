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
    
    args = parser.parse_args()
    
    report_dir = Path(args.dir)
    pattern = f"backtest_{args.strategy}_{args.timeframe}m_*.json"
    
    all_trades = []
    files_processed = 0
    
    # Sort files by creation time to find the newest ones if there were multiple runs
    # Actually, we want to pick files that were generated in the current run.
    # We can filter by time if needed, but for now we'll just take all matching files 
    # that contain the 'trades' key and sort them by open_time.
    
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
    
    # Convert to DataFrame to sort and remove potential overlaps if any
    df = pd.DataFrame(all_trades)
    
    # Convert string dates back to objects if needed for stats (though stats.py handles strings/objects via vars())
    # Actually, stats.py uses vars(t) which might fail on dict.
    # We need to mock the SimulatedTrade object or modify stats.py to handle dicts.
    
    # Let's modify calculate_backtest_stats to handle DataFrame directly or list of dicts.
    # Looking at stats.py, it does: df = pd.DataFrame([vars(t) for t in trades])
    # If we pass a list of dicts, it's safer to have calculate_backtest_stats handle it.
    
    # For now, let's just use the logic from stats.py directly here to generate the final report.
    
    df['open_time'] = pd.to_datetime(df['open_time'])
    df = df.sort_values('open_time').drop_duplicates(subset=['open_time'])
    
    print(f"Final unique trades count: {len(df)}")
    
    # Calculate stats manually using the same logic as stats.py
    df['is_win'] = df['result'] == 'win'
    total_da = df['is_win'].mean()
    higher_da = df[df['direction'] == 'higher']['is_win'].mean() if not df[df['direction'] == 'higher'].empty else 0.0
    lower_da = df[df['direction'] == 'lower']['is_win'].mean() if not df[df['direction'] == 'lower'].empty else 0.0
    
    cumulative_pnl = df['pnl'].cumsum()
    total_pnl = df['pnl'].sum()
    running_max = cumulative_pnl.cummax()
    drawdowns = running_max - cumulative_pnl
    mdd = drawdowns.max()
    
    pnl_std = df['pnl'].std()
    sharpe = (df['pnl'].mean() / pnl_std) if pnl_std > 0 else 0.0
    
    is_lose = df['result'] == 'lose'
    consecutive = is_lose.groupby((is_lose != is_lose.shift()).cumsum()).cumsum()
    max_consecutive_losses = consecutive.max()
    
    buckets = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    df['conf_bucket'] = pd.cut(df['confidence'], bins=buckets)
    calibration = df.groupby('conf_bucket', observed=False)['is_win'].agg(['mean', 'count']).to_dict('index')
    calibration = {str(k): v for k, v in calibration.items()}
    
    final_stats = {
        "total_trades": len(df),
        "total_da": float(total_da),
        "higher_da": float(higher_da),
        "lower_da": float(lower_da),
        "total_pnl": float(total_pnl),
        "mdd": float(mdd),
        "sharpe": float(sharpe),
        "max_consecutive_losses": int(max_consecutive_losses),
        "calibration": calibration,
        "cumulative_pnl": cumulative_pnl.tolist()
    }
    
    # Output
    print("\n" + "="*40)
    print(f" MERGED BACKTEST REPORT: {args.strategy} {args.timeframe}m ")
    print("="*40)
    print(f"Total Trades:       {final_stats['total_trades']}")
    print(f"Total DA (Acc):     {final_stats['total_da']:.2%}")
    print(f"Higher DA:          {final_stats['higher_da']:.2%}")
    print(f"Lower DA:           {final_stats['lower_da']:.2%}")
    print(f"Total PnL (USDT):   {final_stats['total_pnl']:.2f}")
    print(f"Max Drawdown:       {final_stats['mdd']:.2f}")
    print(f"Sharpe Ratio:       {final_stats['sharpe']:.2f}")
    print(f"Max Consecutive L:  {final_stats['max_consecutive_losses']}")
    print("="*40)
    
    output_path = args.output if args.output else report_dir / f"final_backtest_{args.strategy}_{args.timeframe}m.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_stats, f, indent=4)
    print(f"Final report saved to {output_path}")

if __name__ == "__main__":
    main()
