import sqlite3
import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path
from datetime import datetime, timezone

def run_validation():
    db_path = Path("data/btc_predictor.db").resolve()
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
        
    # Read-only connection to avoid locking
    target_uri = f"file:{db_path}?mode=ro"
    
    query = """
    SELECT 
        s.strategy_name, 
        s.timeframe_minutes, 
        o.pnl, 
        s.is_correct 
    FROM pm_orders o 
    JOIN prediction_signals s ON o.signal_id = s.id 
    WHERE s.strategy_name LIKE 'pm_%' 
      AND o.pnl IS NOT NULL
    """
    
    with sqlite3.connect(target_uri, uri=True) as conn:
        df = pd.read_sql_query(query, conn)
        
    if df.empty:
        print("No settled Polymarket orders found in the database.")
        _write_markdown_report([], "No settled Polymarket orders found.")
        return
        
    results = []
        
    groups = df.groupby(['strategy_name', 'timeframe_minutes'])
    for (strategy, tf), group in groups:
        n = len(group)
        wins = sum(group['pnl'] > 0)
        da = wins / n if n > 0 else 0
        total_pnl = group['pnl'].sum()
        avg_pnl = group['pnl'].mean() if n > 0 else 0
        
        # Win rate tests
        if n > 0:
            binom_res = stats.binomtest(wins, n, p=0.5, alternative='greater')
            da_pvalue = binom_res.pvalue
            ci_low = binom_res.proportion_ci(confidence_level=0.95, method='exact').low
            ci_high = binom_res.proportion_ci(confidence_level=0.95, method='exact').high
        else:
            da_pvalue = 1.0
            ci_low = 0
            ci_high = 0
            
        # PnL tests
        # We need at least 2 samples for a t-test
        if n >= 2:
            pnl_array = group['pnl'].values
            # Default is 2-sided, but ttest_1samp has 'alternative' in scipy 1.6+
            t_stat, pnl_pvalue = stats.ttest_1samp(pnl_array, popmean=0, alternative='greater')
            # If standard deviation is 0 and mean is not > 0, p-value might be nan
            if np.isnan(pnl_pvalue):
                pnl_pvalue = 1.0 if avg_pnl <= 0 else 0.0
        else:
            pnl_pvalue = 1.0
            t_stat = 0.0
            
        # Gate 3 condition
        passed = (n >= 200) and (da_pvalue < 0.05) and (pnl_pvalue < 0.05)
        
        results.append({
            'strategy': strategy,
            'timeframe': tf,
            'n': n,
            'wins': wins,
            'da': da,
            'ci_low': ci_low,
            'ci_high': ci_high,
            'da_pvalue': da_pvalue,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'pnl_pvalue': pnl_pvalue,
            'passed': passed
        })

    # Output to stdout
    print("="*60)
    print(" Polymarket Gate 3 Validation ".center(60, '='))
    print("="*60)
    
    for r in results:
        status_tag = "🟢 [GATE 3 PASSED]" if r['passed'] else "⏳ [WAITING]"
        data_tag = "INSUFFICIENT_DATA" if r['n'] < 200 else "READY"
        
        print(f"\nStrategy: {r['strategy']} | Timeframe: {r['timeframe']}m")
        print(f"- Sample Size: {r['n']:>4} / 200 [{data_tag}]")
        print(f"- DA (Win Rate): {r['da']*100:.2f}% (95% CI Lower: {r['ci_low']*100:.2f}%)")
        print(f"- DA p-value:    {r['da_pvalue']:.4f}")
        print(f"- Total PnL:     {r['total_pnl']:+.4f} (Avg: {r['avg_pnl']:+.4f})")
        print(f"- PnL p-value:   {r['pnl_pvalue']:.4f}")
        print(f"- Status:        {status_tag}")
        
    print("\n" + "="*60)
    
    _write_markdown_report(results)

def _write_markdown_report(results, error_msg=None):
    report_dir = Path("reports/polymarket")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "PM-gate3-validation.md"
    
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    lines = [
        "# Polymarket Gate 3 Validation Report",
        "",
        f"*Generated at: {now}*",
        ""
    ]
    
    if error_msg:
        lines.append(f"**Status:** {error_msg}")
    else:
        lines.append("## Overview")
        lines.append("This report automatically validates whether the paper trading signals accumulated for Polymarket strategies satisfy statistical significance to proceed to Gate 4 (Live Trading).")
        lines.append("")
        
        any_passed = any(r['passed'] for r in results)
        global_status = "🟢 AT LEAST ONE STRATEGY PASSED" if any_passed else "⏳ WAITING FOR MORE DATA / BETTER PERFORMANCE"
        lines.append(f"**Global Status:** {global_status}")
        lines.append("")
        
        lines.append("## Detailed Results")
        lines.append("")
        
        for r in results:
            status = "🟢 **[GATE 3 PASSED]**" if r['passed'] else "⏳ **[WAITING]**"
            progress = f"{r['n']} / 200" if r['n'] < 200 else f"{r['n']} (Met minimum 200)"
            
            lines.append(f"### {r['strategy']} ({r['timeframe']}m)")
            lines.append("")
            lines.append(f"**Status:** {status}")
            lines.append("")
            lines.append(f"- **Sample Size (N):** {progress}")
            lines.append(f"- **Directional Accuracy (DA):** {r['da']*100:.2f}%")
            lines.append(f"  - 95% CI Lower Bound: {r['ci_low']*100:.2f}%")
            lines.append(f"  - p-value (H0: DA <= 50%): `{r['da_pvalue']:.4f}`")
            lines.append(f"- **Profit and Loss (PnL):**")
            lines.append(f"  - Total PnL: {r['total_pnl']:+.4f}")
            lines.append(f"  - Avg PnL per trade: {r['avg_pnl']:+.4f}")
            lines.append(f"  - p-value (H0: Avg PnL <= 0): `{r['pnl_pvalue']:.4f}`")
            lines.append("")
            
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
        
    print(f"Report written to: {report_path}")

if __name__ == "__main__":
    run_validation()
