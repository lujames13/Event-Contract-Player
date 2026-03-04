import json
import glob
import os
import re
from datetime import datetime

models = ["pm_xgb_reg_v1", "pm_lgbm_reg_v1", "pm_cb_reg_v1", "pm_mlp_reg_v1", "pm_tabnet_reg_v1", "pm_cnn_reg_v1", "pm_lstm_reg_v1"]

for tf in [5, 15]:
    print(f"\n### {tf}m\n")
    print("| 排名 | 實驗 | 策略 | MAE(%) | Dir DA | ρ(mag,DA) | Q1 DA | Sharpe | PnL | 樣本 | PnL ✓ | Train Win | 日期 |")
    print("|------|------|------|--------|--------|-----------|-------|--------|-----|------|------|-----------|------|")
    
    rows = []
    
    for m in models:
        # Find latest file
        pattern = f"reports/backtest_{m}_{tf}m_*.json"
        files = glob.glob(pattern)
        if not files:
            continue
        latest = max(files, key=os.path.getctime)
        with open(latest, 'r') as f:
            data = json.load(f)
            
        stats = data.get("stats", {})
        reg_stats = stats.get("regression_stats", {})
        
        mae = reg_stats.get("mae", 0.0)
        dir_da = float(stats.get("total_da", 0)) * 100
        rho = reg_stats.get("magnitude_da_correlation", {}).get("spearman_rho", 0.0)
        if rho is None: rho = 0.0
        q1_da = reg_stats.get("top_quartile_da", 0.0) * 100
        sharpe = stats.get("sharpe", 0.0)
        pnl = stats.get("total_pnl", 0.0)
        samples = stats.get("total_trades", 0)
        
        pnl_check = "✅" if pnl > 0 else "❌"
        date_str = datetime.today().strftime("%Y-%m-%d")
        
        rows.append((q1_da, f"| - | 001 | {m} | {mae:.4f} | {dir_da:.2f}% | {rho:.4f} | {q1_da:.2f}% | {sharpe:.2f} | {pnl:.2f} | {samples} | {pnl_check} | 60 | {date_str} |"))
        
    rows.sort(key=lambda x: x[0], reverse=True) # sort by Q1 DA
    for i, (_, row) in enumerate(rows):
        # Update rank
        row = row.replace("| - |", f"| {i+1} |", 1)
        print(row)
