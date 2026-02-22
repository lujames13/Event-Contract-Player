# Review tests for task-spec-g3.2
# Focus: Implementation integrity of pm_v1, labeling and backtest engine for Polymarket

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from btc_predictor.strategies.pm_v1.strategy import PMV1Strategy
from btc_predictor.infrastructure.labeling import add_direction_labels, calculate_single_label
from btc_predictor.backtest.engine import run_backtest
from btc_predictor.models import PredictionSignal, SimulatedTrade

def test_pm_v1_prediction_signal_contract():
    """Verify pm_v1 prediction signal matches ARCHITECTURE.md and models.py contract."""
    # Create dummy data: 2000 rows to ensure enough samples after dropna
    df = pd.DataFrame({
        "open": np.random.randn(2000) + 50000.0,
        "high": np.random.randn(2000) + 50100.0,
        "low": np.random.randn(2000) + 49900.0,
        "close": np.random.randn(2000) + 50000.0,
        "volume": np.random.rand(2000) * 10
    }, index=pd.date_range("2026-01-01", periods=2000, freq="1min"))
    
    strategy = PMV1Strategy()
    # Mocking fit to avoid actual training in test (but we need it to pass validation)
    strategy.fit(df, 5)
    
    signal = strategy.predict(df, 5)
    
    # 1. Type checks
    assert isinstance(signal, PredictionSignal)
    # This is a known flaw I found: strategy.py returns dict, but contract says list
    # I will assert it is a list to catch the flaw
    assert isinstance(signal.features_used, list), f"features_used should be list, got {type(signal.features_used)}"
    
    # 2. Polymarket field existence (even if None)
    assert hasattr(signal, "market_slug")
    assert hasattr(signal, "market_price_up")
    assert hasattr(signal, "alpha")

def test_labeling_ge_condition():
    """Verify labeling.py correctly handles >= condition (Flat close == Win for Up)."""
    df = pd.DataFrame({
        "close": [50000.0, 50000.0, 50100.0, 49900.0]
    }, index=pd.date_range("2026-01-01", periods=4, freq="1min"))
    
    # Case: close(t+1) == close(t)
    # Default condition ">" should be 0
    label_gt = calculate_single_label(df, df.index[0], 1, settlement_condition=">")
    assert label_gt == 0
    
    # Polymarket condition ">=" should be 1
    label_ge = calculate_single_label(df, df.index[0], 1, settlement_condition=">=")
    assert label_ge == 1
    
    # Bulk labeling
    labeled_df = add_direction_labels(df, 1, settlement_condition=">=")
    assert labeled_df.loc[df.index[0], "label"] == 1.0 # 50000 == 50000
    assert labeled_df.loc[df.index[1], "label"] == 1.0 # 50100 > 50000
    assert labeled_df.loc[df.index[2], "label"] == 0.0 # 49900 < 50100

def test_backtest_engine_polymarket_payout():
    """Verify backtest engine uses 2.0 payout and >= condition for polymarket platform."""
    # Create enough data for 1 train day + 1 test day
    # (1 + 1) * 1440 = 2880 mins
    df = pd.DataFrame({
        "open":  [50000.0] * 3000,
        "high":  [50000.0] * 3000,
        "low":   [50000.0] * 3000,
        "close": [50000.0] * 3000,
        "volume": [1.0] * 3000
    }, index=pd.date_range("2026-01-01", periods=3000, freq="1min"))
    
    class ConstantUpStrategy(PMV1Strategy):
        def predict(self, ohlcv, tf):
            return PredictionSignal(
                strategy_name="const_up",
                timestamp=ohlcv.index[-1],
                timeframe_minutes=tf,
                direction="higher",
                confidence=0.8,
                current_price=float(ohlcv['close'].iloc[-1]),
                features_used=[]
            )
        def fit(self, ohlcv, tf): pass
        @property
        def requires_fitting(self): return False
        @property
        def name(self): return "const_up"

    strategy = ConstantUpStrategy()
    
    # Run backtest with platform="polymarket"
    trades = run_backtest(
        strategy, 
        df, 
        timeframe_minutes=10, 
        train_days=1, 
        test_days=1, 
        platform="polymarket",
        n_jobs=1
    )
    
    assert len(trades) > 0
    for trade in trades:
        # Payout 2.0 means Win gives pnl = bet * (2.0 - 1) = bet
        if trade.result == "win":
            # payout_ratio 2.0 -> net profit is 100% of bet
            assert trade.pnl == pytest.approx(trade.bet_amount)
        
        # Verify result logic (since it's constant price, should all be wins for 'higher' with >=)
        if trade.close_price >= trade.open_price:
            assert trade.result == "win"
        else:
            assert trade.result == "lose"

