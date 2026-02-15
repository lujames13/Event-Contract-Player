import pandas as pd
import numpy as np
from typing import List, Dict, Any
from btc_predictor.models import SimulatedTrade

def calculate_backtest_stats(trades: List[SimulatedTrade], test_days: int = 7) -> Dict[str, Any]:
    """
    Calculate various statistics from a list of simulated trades.
    """
    if not trades:
        return {}
        
    # Handle both SimulatedTrade objects and dicts
    if isinstance(trades[0], dict):
        df = pd.DataFrame(trades)
    else:
        df = pd.DataFrame([vars(t) for t in trades])
    # Ensure open_time is datetime
    if not pd.api.types.is_datetime64_any_dtype(df['open_time']):
        df['open_time'] = pd.to_datetime(df['open_time'])
    
    # 1. Total Accuracy (DA)
    df['is_win'] = df['result'] == 'win'
    total_da = df['is_win'].mean()
    
    # Accuracy by direction
    higher_da = df[df['direction'] == 'higher']['is_win'].mean() if not df[df['direction'] == 'higher'].empty else 0.0
    lower_da = df[df['direction'] == 'lower']['is_win'].mean() if not df[df['direction'] == 'lower'].empty else 0.0
    
    # 2. PnL Stats
    cumulative_pnl = df['pnl'].cumsum()
    total_pnl = df['pnl'].sum()
    
    # 3. Maximum Drawdown (MDD)
    running_max = cumulative_pnl.cummax()
    drawdowns = running_max - cumulative_pnl
    mdd = drawdowns.max()
    
    # 4. Sharpe Ratio (Trade-based)
    pnl_std = df['pnl'].std()
    sharpe = (df['pnl'].mean() / pnl_std) if pnl_std > 0 else 0.0
    
    # 5. Max Consecutive Losses
    is_lose = df['result'] == 'lose'
    consecutive = is_lose.groupby((is_lose != is_lose.shift()).cumsum()).cumsum()
    max_consecutive_losses = consecutive.max()
    
    # 6. Confidence Calibration
    buckets = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    df['conf_bucket'] = pd.cut(df['confidence'], bins=buckets)
    calibration = df.groupby('conf_bucket', observed=False)['is_win'].agg(['mean', 'count']).to_dict('index')
    calibration = {str(k): v for k, v in calibration.items()}

    # 7. Inverted DA
    inverted_da = 1.0 - total_da
    
    # 8. Per-fold DA
    min_time = df['open_time'].min()
    # Group by test_days window
    df['fold'] = ((df['open_time'] - min_time).dt.total_seconds() // (test_days * 24 * 3600)).astype(int)
    per_fold_da = df.groupby('fold')['is_win'].mean().tolist()
    
    return {
        "total_trades": len(df),
        "total_da": float(total_da),
        "inverted_da": float(inverted_da),
        "per_fold_da": [float(x) for x in per_fold_da],
        "higher_da": float(higher_da),
        "lower_da": float(lower_da),
        "total_pnl": float(total_pnl),
        "mdd": float(mdd),
        "sharpe": float(sharpe),
        "max_consecutive_losses": int(max_consecutive_losses),
        "calibration": calibration,
        "cumulative_pnl": cumulative_pnl.tolist()
    }
