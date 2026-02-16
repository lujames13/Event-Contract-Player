import json
import glob
import os
import numpy as np

def get_stats(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    stats = data.get('stats', {})
    per_fold_da = stats.get('per_fold_da', [])
    fold_sigma = np.std(per_fold_da) if per_fold_da else 0.0
    return {
        "da": stats.get("total_da", 0),
        "inv_da": stats.get("inverted_da", 0),
        "sharpe": stats.get("sharpe", 0),
        "trades": stats.get("total_trades", 0),
        "pnl": "✅" if stats.get("total_pnl", 0) > 0 else "❌",
        "fold_sigma": fold_sigma
    }

def generate_row(rank, exp, strategy, s):
    da_str = f"**{s['da']:.2%}**" if s['da'] > 0.5405 else f"{s['da']:.2%}"
    # Special case for 10m breakeven 55.56%
    return f"| {rank} | {exp} | {strategy} | {da_str} | {s['inv_da']:.2%} | {s['fold_sigma']:.2%} | {s['sharpe']:.2f} | {s['trades']} | {s['pnl']} | 2026-02-16 |"

# Collect all latest reports
files = glob.glob("reports/backtest_*.json") + glob.glob("reports/final_backtest_*.json")
# Group by strategy and timeframe
latest_reports = {} # (strategy, tf) -> file
for f in files:
    parts = os.path.basename(f).split('_')
    # backtest_lgbm_v2_60m_DATE.json -> strategy=lgbm_v2, tf=60
    # final_backtest_lgbm_v1_10m.json -> strategy=lgbm_v1, tf=10
    if parts[0] == 'backtest':
        # Find where the timeframe (e.g. '10m', '30m') is
        m_idx = -1
        for i, p in enumerate(parts):
            if p.endswith('m') and p[:-1].isdigit():
                m_idx = i
                break
        if m_idx != -1:
            strategy = "_".join(parts[1:m_idx])
            tf = parts[m_idx].replace('m', '')
        else:
            continue
    elif parts[0] == 'final':
        # final_backtest_strategy_tfm.json
        m_idx = -1
        for i, p in enumerate(parts):
            if p.endswith('m') and p[:-1].isdigit():
                m_idx = i
                break
        if m_idx != -1:
            strategy = "_".join(parts[2:m_idx])
            tf = parts[m_idx].replace('m', '')
        else:
            continue
    
    key = (strategy, tf)
    if key not in latest_reports or os.path.getctime(f) > os.path.getctime(latest_reports[key]):
        latest_reports[key] = f

# Generate 10m table
print("### 10m")
tf = "10"
res = []
for (strategy, tf_key), f in latest_reports.items():
    if tf_key == tf:
        states = get_stats(f)
        exp = ""
        if "xgboost_v1" in strategy: exp = "001"
        elif "xgboost_v2" in strategy: exp = "002"
        elif "lgbm_v1" in strategy and "tuned" not in strategy: exp = "004"
        elif "lgbm_v2" in strategy: exp = "005"
        elif "catboost_v1" in strategy: exp = "008"
        elif "mlp_v1" in strategy: exp = "007"
        elif "tuned" in strategy: exp = "006"
        res.append((strategy, states, exp))

res.sort(key=lambda x: x[1]['da'], reverse=True)
for i, (strat, s, exp) in enumerate(res):
    print(generate_row(i+1, exp, strat, s))

# Generate 30m table
print("\n### 30m")
tf = "30"
res = []
for (strategy, tf_key), f in latest_reports.items():
    if tf_key == tf:
        states = get_stats(f)
        exp = ""
        if "xgboost_v1" in strategy: exp = "001"
        elif "xgboost_v2" in strategy: exp = "002"
        elif "lgbm_v1" in strategy and "tuned" not in strategy: exp = "004"
        elif "lgbm_v2" in strategy: exp = "005"
        elif "catboost_v1" in strategy: exp = "008"
        elif "mlp_v1" in strategy: exp = "007"
        elif "tuned" in strategy: exp = "006"
        res.append((strategy, states, exp))

res.sort(key=lambda x: x[1]['da'], reverse=True)
for i, (strat, s, exp) in enumerate(res):
    print(generate_row(i+1, exp, strat, s))

# Generate 60m table
print("\n### 60m")
tf = "60"
res = []
for (strategy, tf_key), f in latest_reports.items():
    if tf_key == tf:
        states = get_stats(f)
        exp = ""
        if "xgboost_v1" in strategy: exp = "001"
        elif "xgboost_v2" in strategy: exp = "002"
        elif "lgbm_v1" in strategy and "tuned" not in strategy: exp = "004"
        elif "lgbm_v2" in strategy: exp = "005"
        elif "catboost_v1" in strategy: exp = "008"
        elif "mlp_v1" in strategy: exp = "007"
        elif "tuned" in strategy: exp = "006"
        res.append((strategy, states, exp))

res.sort(key=lambda x: x[1]['da'], reverse=True)
for i, (strat, s, exp) in enumerate(res):
    print(generate_row(i+1, exp, strat, s))
