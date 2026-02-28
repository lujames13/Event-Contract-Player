import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
from scipy.stats import spearmanr
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

def compute_regression_stats(trades: List[SimulatedTrade], predictions: List[Tuple[float, float]] = None) -> Dict[str, Any]:
    """
    Compute regression specific stats if predicted_change_pct and actual_change_pct exist.
    """
    if not trades:
        return {}

    # Extract pred/actual pairs
    if predictions is None:
        predictions = []
        for t in trades:
            td = t if isinstance(t, dict) else vars(t)
            fu = td.get('features_used', {})
            if 'predicted_change_pct' in fu and 'actual_change_pct' in fu:
                predictions.append((fu['predicted_change_pct'], fu['actual_change_pct']))

    if not predictions:
        return {}

    df_pred = pd.DataFrame(predictions, columns=["predicted", "actual"])
    # Some trades might not have pnl/direction directly in predictions list
    # So we'll join it with trades info
    df_trades = pd.DataFrame([t if isinstance(t, dict) else vars(t) for t in trades])
    if 'predicted_change_pct' in df_pred.columns:
        pass # Not applicable, we just built it
    
    # We actually need is_win and pnl associated with each prediction.
    # If trades and predictions have the same length and order, we can combine:
    if len(df_pred) == len(df_trades):
        df_pred['is_win'] = df_trades['result'] == 'win'
        df_pred['pnl'] = df_trades['pnl']
    else:
        # We rely on extraction from trades
        pred_extract = []
        for t in trades:
            td = t if isinstance(t, dict) else vars(t)
            fu = td.get('features_used', {})
            if 'predicted_change_pct' in fu and 'actual_change_pct' in fu:
                pred_extract.append({
                    "predicted": fu['predicted_change_pct'],
                    "actual": fu['actual_change_pct'],
                    "is_win": td['result'] == 'win',
                    "pnl": td['pnl']
                })
        df_pred = pd.DataFrame(pred_extract)

    if df_pred.empty:
        return {}

    mae = (df_pred["predicted"] - df_pred["actual"]).abs().mean()
    rmse = np.sqrt(((df_pred["predicted"] - df_pred["actual"]) ** 2).mean())
    direction_da = np.sign(df_pred["predicted"]) == np.sign(df_pred["actual"])
    direction_da_mean = direction_da.mean()
    
    rho, p_val = spearmanr(df_pred["predicted"].abs(), df_pred["is_win"])
    
    # top quartile
    df_pred["abs_pred"] = df_pred["predicted"].abs()
    q75 = df_pred["abs_pred"].quantile(0.75)
    top_q = df_pred[df_pred["abs_pred"] >= q75]
    top_quartile_da = top_q["is_win"].mean() if not top_q.empty else 0.0
    top_quartile_pnl = top_q["pnl"].sum() if not top_q.empty else 0.0
    
    # alpha curve (4 buckets)
    try:
        df_pred["bucket"] = pd.qcut(df_pred["abs_pred"], 4, labels=["Q4_lowest", "Q3", "Q2", "Q1_highest"])
    except ValueError:
        # Fallback if too few unique values
        df_pred["bucket"] = "Q1_highest"
        
    alpha_curve = []
    if "bucket" in df_pred.columns:
        for b in ["Q4_lowest", "Q3", "Q2", "Q1_highest"]:
            b_df = df_pred[df_pred["bucket"] == b]
            if not b_df.empty:
                alpha_curve.append({
                    "bucket": b,
                    "da": float(b_df["is_win"].mean()),
                    "pnl": float(b_df["pnl"].sum()),
                    "n": len(b_df)
                })

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "direction_da": float(direction_da_mean),
        "magnitude_da_correlation": {
            "spearman_rho": float(rho) if not np.isnan(rho) else 0.0,
            "p_value": float(p_val) if not np.isnan(p_val) else 1.0
        },
        "top_quartile_da": float(top_quartile_da),
        "top_quartile_pnl": float(top_quartile_pnl),
        "alpha_curve": alpha_curve
    }
