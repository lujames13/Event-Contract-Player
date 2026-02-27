import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any
from sklearn.linear_model import LinearRegression

def compute_directional_accuracy(
    df: pd.DataFrame,
    groupby: Optional[List[str]] = None,
) -> dict:
    if df.empty:
        return {"overall": {"total": 0, "correct": 0, "da": 0.0, "ci_95": 0.0}}
        
    def _calc_stats(sub_df):
        total = len(sub_df)
        if total == 0:
            return {"total": 0, "correct": 0, "da": 0.0, "ci_95": 0.0}
        # handle missing is_correct
        correct = int(sub_df['is_correct'].fillna(0).sum())
        da = correct / total
        ci_95 = 1.96 * np.sqrt(da * (1 - da) / total)
        return {
            "total": int(total),
            "correct": int(correct),
            "da": float(da),
            "ci_95": float(ci_95)
        }

    res = {"overall": _calc_stats(df)}
    
    if groupby:
        res["by_group"] = {}
        for keys, group in df.groupby(groupby):
            if isinstance(keys, tuple):
                key_str = "|".join(map(str, keys))
            else:
                key_str = str(keys)
            res["by_group"][key_str] = _calc_stats(group)
            
    return res

def compute_pnl_metrics(df: pd.DataFrame) -> dict:
    if df.empty or 'pnl' not in df.columns:
        return {
            "total_pnl": 0.0, "total_trades": 0, "win_rate": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "max_drawdown_pct": 0.0, "sharpe_like": 0.0,
            "daily_pnl": [], "cumulative_pnl": []
        }
        
    # Drop NaNs from pnl just in case
    df = df.dropna(subset=['pnl']).copy()
    if df.empty:
        return {
            "total_pnl": 0.0, "total_trades": 0, "win_rate": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "max_drawdown_pct": 0.0, "sharpe_like": 0.0,
            "daily_pnl": [], "cumulative_pnl": []
        }
        
    total_trades = len(df)
    total_pnl = df['pnl'].sum()
    wins = df[df['pnl'] > 0]
    losses = df[df['pnl'] < 0]
    
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0.0
    avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0.0
    sum_losses = abs(losses['pnl'].sum())
    profit_factor = wins['pnl'].sum() / sum_losses if sum_losses > 0 else float('inf')
    
    # max drawdown
    # Assuming df is sorted chronologically
    cum_pnl = df['pnl'].cumsum()
    running_max = cum_pnl.cummax()
    drawdowns = running_max - cum_pnl
    max_drawdown = float(drawdowns.max()) if not drawdowns.empty else 0.0
    
    # max drawdown pct: this requires starting capital, maybe use max_drawdown / running_max
    # Or just return 0 if starting capital is not known
    # Let's approximate starting cap as 1000 or ignore
    max_drawdown_pct = 0.0 # difficult to compute without starting equity

    # Sharpe-like (daily mean / std)
    if 'placed_at' in df.columns:
        date_col = 'placed_at'
    elif 'timestamp' in df.columns:
        date_col = 'timestamp'
    else:
        date_col = None
        
    daily_pnl = []
    sharpe_like = 0.0
    if date_col:
        dates = df[date_col].dt.date
        daily_sums = df.groupby(dates)['pnl'].sum()
        mean_daily = daily_sums.mean()
        std_daily = daily_sums.std()
        
        if std_daily and std_daily > 0:
            sharpe_like = (mean_daily / std_daily) * np.sqrt(365) # annualized
            
        daily_pnl = [{"date": str(k), "pnl": float(v)} for k, v in daily_sums.items()]
        
    cumulative = [{"trade_idx": int(i), "cum_pnl": float(val)} for i, val in enumerate(cum_pnl)]

    return {
        "total_pnl": float(total_pnl),
        "total_trades": int(total_trades),
        "win_rate": float(win_rate),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "profit_factor": float(profit_factor),
        "max_drawdown": float(max_drawdown),
        "max_drawdown_pct": float(max_drawdown_pct),
        "sharpe_like": float(sharpe_like),
        "daily_pnl": daily_pnl,
        "cumulative_pnl": cumulative,
    }

def compute_alpha_analysis(
    df: pd.DataFrame,
    buckets: Optional[List[float]] = None,
) -> dict:
    if buckets is None:
        buckets = [0, 0.02, 0.05, 0.10, 1.0]

    if df.empty or 'alpha' not in df.columns or 'is_correct' not in df.columns:
        return {
            "distribution": {"mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0},
            "by_bucket": [],
            "threshold_simulation": []
        }
        
    alpha_s = df['alpha'].dropna()
    if alpha_s.empty:
        return {
            "distribution": {"mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0},
            "by_bucket": [],
            "threshold_simulation": []
        }

    dist = {
        "mean": float(alpha_s.mean()),
        "median": float(alpha_s.median()),
        "std": float(alpha_s.std()),
        "min": float(alpha_s.min()),
        "max": float(alpha_s.max())
    }

    by_bucket = []
    for i in range(len(buckets)-1):
        low, high = buckets[i], buckets[i+1]
        mask = (df['alpha'] >= low) & (df['alpha'] < high)
        subset = df[mask]
        count = len(subset)
        if count == 0:
            continue
        corr = subset['is_correct'].sum()
        win_rate = corr / count
        avg_pnl = float(subset.get('pnl', pd.Series([0]*count)).mean())
        if pd.isna(avg_pnl):
            avg_pnl = 0.0
            
        by_bucket.append({
            "range": f"{low:.2f}-{high:.2f}",
            "count": int(count),
            "win_rate": float(win_rate),
            "avg_pnl": float(avg_pnl)
        })

    # Threshold simulation: 0.00 to 0.15 step 0.01
    simulations = []
    for t in np.arange(0.0, 0.16, 0.01):
        mask = df['alpha'] >= t
        subset = df[mask]
        trades = len(subset)
        if trades == 0:
            continue
        corr = subset['is_correct'].sum()
        win_rate = corr / trades
        total_pnl = float(subset.get('pnl', pd.Series([0]*trades)).sum())
        simulations.append({
            "threshold": float(t),
            "trades": int(trades),
            "win_rate": float(win_rate),
            "total_pnl": float(total_pnl)
        })

    return {
        "distribution": dist,
        "by_bucket": by_bucket,
        "threshold_simulation": simulations
    }

def compute_temporal_patterns(df: pd.DataFrame) -> dict:
    if df.empty or 'timestamp' not in df.columns or 'is_correct' not in df.columns:
        return {
            "by_hour": [],
            "by_weekday": [],
            "recent_vs_all": {
                "last_7d": {"total": 0, "da": 0.0},
                "last_30d": {"total": 0, "da": 0.0},
                "all_time": {"total": 0, "da": 0.0},
            }
        }
    
    df = df.copy()
    df['hour'] = df['timestamp'].dt.hour
    df['weekday'] = df['timestamp'].dt.day_name()
    
    by_hour = []
    for h in range(24):
        sub = df[df['hour'] == h]
        t = len(sub)
        da = float(sub['is_correct'].sum() / t) if t > 0 else 0.0
        by_hour.append({"hour": int(h), "total": int(t), "da": da})
        
    by_weekday = []
    for wd in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
        sub = df[df['weekday'] == wd]
        t = len(sub)
        da = float(sub['is_correct'].sum() / t) if t > 0 else 0.0
        by_weekday.append({"weekday": wd, "total": int(t), "da": da})
        
    max_ts = df['timestamp'].max()
    d7 = max_ts - pd.Timedelta(days=7)
    d30 = max_ts - pd.Timedelta(days=30)
    
    def _stat(s_df):
        t = len(s_df)
        da = float(s_df['is_correct'].sum() / t) if t > 0 else 0.0
        return {"total": int(t), "da": da}
        
    recent_vs_all = {
        "last_7d": _stat(df[df['timestamp'] >= d7]),
        "last_30d": _stat(df[df['timestamp'] >= d30]),
        "all_time": _stat(df)
    }

    return {
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "recent_vs_all": recent_vs_all
    }

def compute_confidence_calibration(df: pd.DataFrame) -> dict:
    if df.empty or 'confidence' not in df.columns or 'is_correct' not in df.columns:
        return {
            "buckets": [],
            "brier_score": 0.0,
            "baseline_brier": 0.0,
        }
        
    # Buckets: [0.50, 0.55), ... [0.95, 1.00]
    buckets_info = []
    bins = np.arange(0.5, 1.05, 0.05)
    for i in range(len(bins)-1):
        low, high = bins[i], bins[i+1]
        mask = (df['confidence'] >= low) & (df['confidence'] < high)
        if high == 1.0: # inclusive for rightmost
            mask = (df['confidence'] >= low) & (df['confidence'] <= 1.0)
            
        sub = df[mask]
        count = len(sub)
        if count == 0:
            continue
            
        expected = sub['confidence'].mean()
        actual = sub['is_correct'].mean()
        
        buckets_info.append({
            "expected": float(expected),
            "actual": float(actual),
            "count": int(count),
            "deviation": float(actual - expected)
        })
        
    # brier
    preds = df['confidence']
    acts = df['is_correct'].astype(float)
    brier = ((preds - acts)**2).mean()
    baseline_brier = ((acts.mean() - acts)**2).mean() # predicting the mean always
    
    return {
        "buckets": buckets_info,
        "brier_score": float(brier) if not pd.isna(brier) else 0.0,
        "baseline_brier": float(baseline_brier) if not pd.isna(baseline_brier) else 0.0,
    }

def compute_drift_detection(df: pd.DataFrame, window_size: int = 50) -> dict:
    if len(df) < window_size or 'is_correct' not in df.columns:
        return {
            "rolling_da": [],
            "trend_slope": 0.0,
            "is_degrading": False,
            "worst_window": {"start_idx": 0, "end_idx": 0, "da": 0.0},
            "best_window": {"start_idx": 0, "end_idx": 0, "da": 0.0},
        }

    # rolling da
    y = df['is_correct'].astype(float).values
    rolling_da = []
    for i in range(window_size, len(y) + 1):
        window_y = y[i-window_size:i]
        da = window_y.mean()
        rolling_da.append(da)
        
    rolling_da_out = [{"window_end_idx": int(i+window_size), "da": float(da)} for i, da in enumerate(rolling_da)]
        
    if len(rolling_da) > 1:
        X = np.arange(len(rolling_da)).reshape(-1, 1)
        mdl = LinearRegression().fit(X, rolling_da)
        slope = float(mdl.coef_[0])
    else:
        slope = 0.0
        
    best_idx = np.argmax(rolling_da)
    worst_idx = np.argmin(rolling_da)
    
    return {
        "rolling_da": rolling_da_out,
        "trend_slope": slope,
        "is_degrading": slope < -0.005, # < -0.5% per window
        "worst_window": {
            "start_idx": int(worst_idx), 
            "end_idx": int(worst_idx + window_size), 
            "da": float(rolling_da[worst_idx])
        },
        "best_window": {
            "start_idx": int(best_idx), 
            "end_idx": int(best_idx + window_size), 
            "da": float(rolling_da[best_idx])
        },
    }
