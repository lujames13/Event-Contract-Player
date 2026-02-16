import json
import argparse
import numpy as np
import os
from typing import Dict, Any

def analyze_report(report_path: str):
    if not os.path.exists(report_path):
        print(f"Error: Report {report_path} not found.")
        return

    with open(report_path, 'r') as f:
        data = json.load(f)

    stats = data.get('stats', {})
    trades = data.get('trades', [])
    
    total_trades = stats.get('total_trades', 0)
    higher_da = stats.get('higher_da', 0)
    lower_da = stats.get('lower_da', 0)
    per_fold_da = np.array(stats.get('per_fold_da', []))
    
    # Calculate counts from trades
    higher_trades = sum(1 for t in trades if t.get('direction') == 'higher')
    lower_trades = sum(1 for t in trades if t.get('direction') == 'lower')
    
    # Analysis
    da_diff = abs(higher_da - lower_da)
    trade_ratio_higher = higher_trades / total_trades if total_trades > 0 else 0
    trade_ratio_lower = lower_trades / total_trades if total_trades > 0 else 0
    
    fold_mean = np.mean(per_fold_da) if len(per_fold_da) > 0 else 0
    fold_std = np.std(per_fold_da) if len(per_fold_da) > 0 else 0
    fold_min = np.min(per_fold_da) if len(per_fold_da) > 0 else 0
    fold_max = np.max(per_fold_da) if len(per_fold_da) > 0 else 0
    
    breakeven = 0.5405 # for 60m
    folds_above_be = np.sum(per_fold_da > breakeven)
    
    # Worst 3 folds
    worst_3_folds = sorted(per_fold_da)[:3]
    
    # Trimmed mean (remove best and worst)
    if len(per_fold_da) > 2:
        trimmed_folds = sorted(per_fold_da)[1:-1]
        trimmed_mean = np.mean(trimmed_folds)
    else:
        trimmed_mean = fold_mean

    output = []
    output.append(f"Gate 1 Robustness Analysis: {report_path}")
    output.append("=" * 50)
    output.append(f"Total Trades: {total_trades}")
    output.append(f"Higher Trades: {higher_trades} ({trade_ratio_higher:.2%})")
    output.append(f"Lower Trades: {lower_trades} ({trade_ratio_lower:.2%})")
    output.append(f"Higher DA: {higher_da:.4f}")
    output.append(f"Lower DA: {lower_da:.4f}")
    output.append(f"DA Bias (abs diff): {da_diff:.4f}")
    
    if da_diff > 0.10:
        output.append("  ⚠️ WARNING: Directional bias > 10%")
    
    if max(trade_ratio_higher, trade_ratio_lower) > 0.60:
        output.append("  ⚠️ WARNING: Trade ratio bias > 60:40")
        
    output.append("-" * 30)
    output.append(f"Per-fold DA Stats (N={len(per_fold_da)}):")
    output.append(f"  Mean: {fold_mean:.4f}")
    output.append(f"  Std:  {fold_std:.4f}")
    output.append(f"  Min:  {fold_min:.4f}")
    output.append(f"  Max:  {fold_max:.4f}")
    output.append(f"  Folds above breakeven ({breakeven}): {folds_above_be}/{len(per_fold_da)}")
    output.append(f"  Worst 3 folds DA: {[f'{x:.4f}' for x in worst_3_folds]}")
    output.append(f"  Trimmed Mean DA (excl. 1 best/worst): {trimmed_mean:.4f}")
    
    if fold_std > 0.10:
        output.append("  ⚠️ WARNING: Fold σ > 10% (High volatility)")
    elif fold_std > 0.05:
        output.append("  💡 NOTE: Fold σ between 5% and 10%")
        
    if trimmed_mean < breakeven:
        output.append(f"  ⚠️ WARNING: Trimmed mean DA < breakeven ({breakeven})")
    
    report_text = "\n".join(output)
    print(report_text)
    
    analysis_path = "reports/gate1_robustness_analysis.txt"
    with open(analysis_path, "w") as f:
        f.write(report_text)
    print(f"\nAnalysis saved to {analysis_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=str, required=True, help="Path to backtest report JSON")
    args = parser.parse_args()
    
    analyze_report(args.report)
