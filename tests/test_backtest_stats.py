import pytest
from btc_predictor.backtest.stats import calculate_backtest_stats
from btc_predictor.models import SimulatedTrade
from datetime import datetime

def test_calculate_backtest_stats_basic():
    trades = [
        SimulatedTrade(id="1", strategy_name="s", direction="higher", confidence=0.7, 
                       timeframe_minutes=10, bet_amount=10, open_time=datetime.now(), 
                       open_price=100, expiry_time=datetime.now(), close_price=110, 
                       result="win", pnl=8.0),
        SimulatedTrade(id="2", strategy_name="s", direction="lower", confidence=0.6, 
                       timeframe_minutes=10, bet_amount=10, open_time=datetime.now(), 
                       open_price=100, expiry_time=datetime.now(), close_price=110, 
                       result="lose", pnl=-10.0),
        SimulatedTrade(id="3", strategy_name="s", direction="higher", confidence=0.8, 
                       timeframe_minutes=10, bet_amount=20, open_time=datetime.now(), 
                       open_price=100, expiry_time=datetime.now(), close_price=90, 
                       result="lose", pnl=-20.0),
        SimulatedTrade(id="4", strategy_name="s", direction="lower", confidence=0.9, 
                       timeframe_minutes=10, bet_amount=5, open_time=datetime.now(), 
                       open_price=100, expiry_time=datetime.now(), close_price=95, 
                       result="win", pnl=4.0),
    ]
    
    stats = calculate_backtest_stats(trades)
    
    assert stats["total_trades"] == 4
    # 2 wins out of 4
    assert stats["total_da"] == 0.5
    # Higher: 1 win, 1 loss -> 0.5
    # Lower: 1 win, 1 loss -> 0.5
    assert stats["higher_da"] == 0.5
    assert stats["lower_da"] == 0.5
    
    # PnL: 8 - 10 - 20 + 4 = -18
    assert stats["total_pnl"] == -18.0
    
    # Cumulative PnL: [8, -2, -22, -18]
    # MDD: Peek was 8, min after peak was -22. Drop = 30.
    assert stats["mdd"] == 30.0
    
    # Max consecutive losses: 2 (indices 1 and 2)
    assert stats["max_consecutive_losses"] == 2
    
    # Check if calibration exists
    assert stats["inverted_da"] == 0.5
    assert "per_fold_da" in stats
    assert stats["per_fold_da"] == [0.5]  # All within same fold by default if times are now

def test_calculate_backtest_stats_folds():
    from datetime import timedelta
    now = datetime(2026, 1, 1)
    trades = [
        # Fold 0
        SimulatedTrade(id="1", strategy_name="s", direction="higher", confidence=0.7, 
                       timeframe_minutes=10, bet_amount=10, open_time=now, 
                       result="win", pnl=8.0, open_price=100, expiry_time=now, close_price=110),
        # Fold 1 (7 days later)
        SimulatedTrade(id="2", strategy_name="s", direction="higher", confidence=0.7, 
                       timeframe_minutes=10, bet_amount=10, open_time=now + timedelta(days=8), 
                       result="lose", pnl=-10.0, open_price=100, expiry_time=now, close_price=90),
        # Fold 2 (14 days later)
        SimulatedTrade(id="3", strategy_name="s", direction="higher", confidence=0.7, 
                       timeframe_minutes=10, bet_amount=10, open_time=now + timedelta(days=15), 
                       result="win", pnl=8.0, open_price=100, expiry_time=now, close_price=110),
    ]
    
    stats = calculate_backtest_stats(trades, test_days=7)
    
    # DA of Fold 0: 1/1 = 1.0
    # DA of Fold 1: 0/1 = 0.0
    # DA of Fold 2: 1/1 = 1.0
    assert stats["per_fold_da"] == [1.0, 0.0, 1.0]
    assert stats["total_da"] == pytest.approx(0.666666, 0.001)
    assert stats["inverted_da"] == pytest.approx(0.333333, 0.001)
