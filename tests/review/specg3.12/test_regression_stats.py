import pytest
import numpy as np
import math
from btc_predictor.backtest.stats import compute_regression_stats

# Review tests for task-spec-g3.12
# Focus: edge cases of stats computation (constant inputs, single entries)

def test_compute_stats_constant_inputs():
    """
    Test when all predicted values are equal, resulting in a pd.qcut ValueError.
    The fallback logic should activate and put everything into a single bucket.
    """
    # 4 predictions, all identical. DA is 50%
    predictions = [
        (1.0, 1.0), # win
        (1.0, 1.0), # win
        (1.0, -1.0), # lose
        (1.0, -1.0), # lose
    ]
    
    # We must mock trades to provide is_win and PnL, or supply is_win in df directly
    # `compute_regression_stats` needs is_win/pnl attached or extracted from trades.
    # The signature is compute_regression_stats(trades: List, predictions: List = None)
    dummy_trades = [
        {"result": "win", "pnl": 1.0, "features_used": {"predicted_change_pct": predictions[0][0], "actual_change_pct": predictions[0][1]}},
        {"result": "win", "pnl": 1.0, "features_used": {"predicted_change_pct": predictions[1][0], "actual_change_pct": predictions[1][1]}},
        {"result": "lose", "pnl": -1.0, "features_used": {"predicted_change_pct": predictions[2][0], "actual_change_pct": predictions[2][1]}},
        {"result": "lose", "pnl": -1.0, "features_used": {"predicted_change_pct": predictions[3][0], "actual_change_pct": predictions[3][1]}},
    ]
    
    stats = compute_regression_stats(dummy_trades)
    
    # MAE of pred=1.0 and act=1,-1 => |1-(1)|+|1-(1)|+|1-(-1)|+|1-(-1)| / 4 = 4/4 = 1.0
    assert stats["mae"] == 1.0
    
    # direction_da: sign(pred) == sign(act) -> 1==1, 1==1, 1!=-1, 1!=-1 => 2/4 = 0.5
    assert stats["direction_da"] == 0.5
    
    # The alpha curve should fallback to everything being Q1_highest
    alpha_curve = stats["alpha_curve"]
    assert len(alpha_curve) == 1
    assert alpha_curve[0]["bucket"] == "Q1_highest"
    assert alpha_curve[0]["da"] == 0.5
    assert alpha_curve[0]["pnl"] == 0.0
    assert alpha_curve[0]["n"] == 4

def test_spearman_correlation_no_variance():
    """
    Test Spearman correlation computation gracefully handles zero variance cases (producing nan output).
    The code explicitly returns 0.0/1.0 when nan.
    """
    # All predicted magitude is 1.0, thus no variance.
    # All is_win is true, thus no variance.
    dummy_trades = [
        {"result": "win", "pnl": 1.0, "features_used": {"predicted_change_pct": 1.0, "actual_change_pct": 1.0}},
        {"result": "win", "pnl": 1.0, "features_used": {"predicted_change_pct": 1.0, "actual_change_pct": 1.0}},
    ]
    
    stats = compute_regression_stats(dummy_trades)
    
    # spearman_rho handles NaN
    assert not math.isnan(stats["magnitude_da_correlation"]["spearman_rho"])
    assert stats["magnitude_da_correlation"]["spearman_rho"] == 0.0

def test_alpha_curve_four_buckets():
    """
    Test correct bucket allocation of alpha curve for unique values.
    """
    dummy_trades = [
        {"result": "lose", "pnl": -1.0, "features_used": {"predicted_change_pct": 0.1, "actual_change_pct": -0.1}}, # Q4
        {"result": "win",  "pnl": 1.0, "features_used": {"predicted_change_pct": 0.3, "actual_change_pct": 0.3}},  # Q3
        {"result": "win",  "pnl": 1.0, "features_used": {"predicted_change_pct": 0.6, "actual_change_pct": 0.6}},  # Q2
        {"result": "win",  "pnl": 1.0, "features_used": {"predicted_change_pct": 0.9, "actual_change_pct": 0.9}},  # Q1
    ]
    
    stats = compute_regression_stats(dummy_trades)
    alpha = stats["alpha_curve"]
    assert len(alpha) == 4
    
    buckets = {b["bucket"]: b["da"] for b in alpha}
    assert buckets["Q4_lowest"] == 0.0
    assert buckets["Q3"] == 1.0
    assert buckets["Q1_highest"] == 1.0
