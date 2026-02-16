import json
import glob
import os

def extract_stats():
    # Final reports or latest ones
    strategies = ["xgboost_v1", "xgboost_v2", "lgbm_v1", "lgbm_v1_tuned", "lgbm_v2", "mlp_v1", "catboost_v1"]
    timeframes = ["10", "30", "60"]
    
    results = {tf: [] for tf in timeframes}
    
    for strategy in strategies:
        for tf in timeframes:
            # Match backtest_strategy_tfm*.json and pick the latest
            pattern = f"reports/backtest_{strategy}_{tf}m*.json"
            files = glob.glob(pattern)
            if not files:
                # Also try reports/final_backtest_strategy_tfm.json or similar
                files = glob.glob(f"reports/final_backtest_{strategy}_{tf}m.json")
            
            if files:
                latest_file = max(files, key=os.path.getctime)
                with open(latest_file, 'r') as f:
                    data = json.load(f)
                    stats = data.get('stats', {})
                    # Fold sigma
                    per_fold_da = stats.get('per_fold_da', [])
                    fold_sigma = f"{np.std(per_fold_da):.2%}" if per_fold_da else "N/A"
                    
                    results[tf].append({
                        "strategy": strategy,
                        "da": f"{stats.get('total_da', 0):.2%}",
                        "inv_da": f"{stats.get('inverted_da', 0):.2%}",
                        "sharpe": f"{stats.get('sharpe', 0):.2f}",
                        "trades": stats.get('total_trades', 0),
                        "pnl": "✅" if stats.get('total_pnl', 0) > 0 else "❌",
                        "fold_sigma": fold_sigma,
                        "file": latest_file
                    })
    
    for tf, tf_results in results.items():
        print(f"\nTimeframe: {tf}m")
        print("| Strategy | DA | Inv. DA | Sharpe | Trades | Fold σ | PnL |")
        print("|----------|----|---------|--------|--------|--------|-----|")
        # Sort by DA descending
        sorted_results = sorted(tf_results, key=lambda x: float(x['da'].strip('%')), reverse=True)
        for r in sorted_results:
            print(f"| {r['strategy']} | {r['da']} | {r['inv_da']} | {r['sharpe']} | {r['trades']} | {r['fold_sigma']} | {r['pnl']} |")

if __name__ == "__main__":
    import numpy as np
    extract_stats()
