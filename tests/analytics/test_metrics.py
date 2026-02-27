import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from btc_predictor.analytics.metrics import (
    compute_directional_accuracy, compute_pnl_metrics, compute_alpha_analysis,
    compute_temporal_patterns, compute_confidence_calibration, compute_drift_detection
)

def test_compute_da_empty():
    res = compute_directional_accuracy(pd.DataFrame())
    assert res['overall']['total'] == 0

def test_compute_da():
    df = pd.DataFrame({
        'is_correct': [True, False, True, True],
        'timeframe_minutes': [5, 5, 10, 10]
    })
    res = compute_directional_accuracy(df, groupby=['timeframe_minutes'])
    assert res['overall']['total'] == 4
    assert res['overall']['da'] == 0.75
    assert res['by_group']['5']['da'] == 0.5
    assert res['by_group']['10']['da'] == 1.0

def test_compute_pnl_empty():
    res = compute_pnl_metrics(pd.DataFrame())
    assert res['total_pnl'] == 0.0

def test_compute_pnl():
    df = pd.DataFrame({
        'pnl': [10.0, -5.0, 15.0],
        'placed_at': pd.date_range(start='2026-01-01', periods=3)
    })
    res = compute_pnl_metrics(df)
    assert res['total_pnl'] == 20.0
    assert res['total_trades'] == 3
    assert res['win_rate'] == pytest.approx(2/3)
    assert res['avg_win'] == 12.5
    assert res['avg_loss'] == -5.0
    assert res['profit_factor'] == 5.0

def test_compute_alpha_empty():
    res = compute_alpha_analysis(pd.DataFrame())
    assert res['distribution']['mean'] == 0.0

def test_compute_alpha():
    df = pd.DataFrame({
        'alpha': [0.01, 0.03, 0.06],
        'is_correct': [False, True, True],
        'pnl': [-5.0, 10.0, 15.0]
    })
    res = compute_alpha_analysis(df)
    assert res['distribution']['mean'] == pytest.approx(0.0333, abs=1e-3)
    
def test_compute_temporal_empty():
    res = compute_temporal_patterns(pd.DataFrame())
    assert res['recent_vs_all']['all_time']['total'] == 0

def test_compute_temporal():
    now = datetime.now(timezone.utc)
    df = pd.DataFrame({
        'timestamp': [now, now - timedelta(days=1), now - timedelta(days=10)],
        'is_correct': [True, False, True]
    })
    res = compute_temporal_patterns(df)
    assert res['recent_vs_all']['last_7d']['total'] == 2
    assert res['recent_vs_all']['last_30d']['total'] == 3

def test_compute_calibration_empty():
    res = compute_confidence_calibration(pd.DataFrame())
    assert res['brier_score'] == 0.0

def test_compute_calibration():
    df = pd.DataFrame({
        'confidence': [0.55, 0.65, 0.95],
        'is_correct': [True, False, True]
    })
    res = compute_confidence_calibration(df)
    assert res['brier_score'] > 0
    
def test_compute_drift_empty():
    res = compute_drift_detection(pd.DataFrame(), window_size=50)
    assert len(res['rolling_da']) == 0

def test_compute_drift():
    df = pd.DataFrame({
        'is_correct': [True] * 60 + [False] * 40
    })
    res = compute_drift_detection(df, window_size=50)
    assert len(res['rolling_da']) == 51
