import pytest
from datetime import datetime
from btc_predictor.models import SimulatedTrade
from btc_predictor.backtest.stats import compute_regression_stats

@pytest.fixture
def mock_trades():
    # 4 trades for proper quartile splitting
    return [
        SimulatedTrade(
            id="1", strategy_name="pm_test", direction="higher", confidence=0.0, timeframe_minutes=5,
            bet_amount=10.0, open_time=datetime.utcnow(), open_price=100.0, expiry_time=datetime.utcnow(),
            close_price=105.0, result="win", pnl=10.0,
            features_used={"predicted_change_pct": 5.0, "actual_change_pct": 5.0} # Q1 (highest) -> abs_pred=5.0
        ),
        SimulatedTrade(
            id="2", strategy_name="pm_test", direction="higher", confidence=0.0, timeframe_minutes=5,
            bet_amount=10.0, open_time=datetime.utcnow(), open_price=100.0, expiry_time=datetime.utcnow(),
            close_price=102.0, result="lose", pnl=-10.0,
            features_used={"predicted_change_pct": 3.0, "actual_change_pct": -2.0} # Q2 -> abs_pred=3.0
        ),
        SimulatedTrade(
            id="3", strategy_name="pm_test", direction="lower", confidence=0.0, timeframe_minutes=5,
            bet_amount=10.0, open_time=datetime.utcnow(), open_price=100.0, expiry_time=datetime.utcnow(),
            close_price=99.0, result="win", pnl=10.0,
            features_used={"predicted_change_pct": -2.0, "actual_change_pct": -1.0} # Q3 -> abs_pred=2.0
        ),
        SimulatedTrade(
            id="4", strategy_name="pm_test", direction="lower", confidence=0.0, timeframe_minutes=5,
            bet_amount=10.0, open_time=datetime.utcnow(), open_price=100.0, expiry_time=datetime.utcnow(),
            close_price=101.0, result="lose", pnl=-10.0,
            features_used={"predicted_change_pct": -1.0, "actual_change_pct": 1.0} # Q4 (lowest) -> abs_pred=1.0
        ),
    ]

def test_compute_regression_stats_with_features(mock_trades):
    stats = compute_regression_stats(mock_trades)
    
    # MAE = (|5-5| + |3--2| + |-2--1| + |-1-1|) / 4
    # MAE = (0 + 5 + 1 + 2) / 4 = 8 / 4 = 2.0
    assert stats["mae"] == pytest.approx(2.0)
    
    # direction DA
    # 1: pred +, actual + (True)
    # 2: pred +, actual - (False)
    # 3: pred -, actual - (True)
    # 4: pred -, actual + (False)
    # DA = 0.5
    assert stats["direction_da"] == pytest.approx(0.5)
    
    # top_quartile: 5.0 is the top 25%. It was a win, PnL=10.
    assert stats["top_quartile_da"] == pytest.approx(1.0)
    assert stats["top_quartile_pnl"] == pytest.approx(10.0)
    
    assert "alpha_curve" in stats
    assert len(stats["alpha_curve"]) == 4

def test_compute_regression_stats_empty():
    stats = compute_regression_stats([])
    assert stats == {}

def test_compute_regression_stats_no_regression_features():
    trades = [
        SimulatedTrade(
            id="1", strategy_name="pm_test", direction="higher", confidence=0.0, timeframe_minutes=5,
            bet_amount=10.0, open_time=datetime.utcnow(), open_price=100.0, expiry_time=datetime.utcnow(),
            close_price=105.0, result="win", pnl=10.0,
            features_used={} 
        )
    ]
    stats = compute_regression_stats(trades)
    assert stats == {}
