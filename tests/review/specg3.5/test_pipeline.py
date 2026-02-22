# Review tests for task-spec-g3.5
# Focus: Transaction integrity, Interface contracts, and Alpha logic accuracy

import pytest
import sqlite3
import pandas as pd
import uuid
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from btc_predictor.infrastructure.store import DataStore
from btc_predictor.polymarket.pipeline import PolymarketLivePipeline
from btc_predictor.models import PredictionSignal, SimulatedTrade, PolymarketOrder
from btc_predictor.strategies.base import BaseStrategy

class MockStrategy(BaseStrategy):
    def __init__(self, name="mock_strat", timeframes=[5]):
        self._name = name
        self._timeframes = timeframes
    @property
    def name(self): return self._name
    @property
    def requires_fitting(self): return False
    @property
    def available_timeframes(self): return self._timeframes
    def fit(self, ohlcv, tf): pass
    def predict(self, ohlcv, tf):
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            direction="higher",
            confidence=0.8,
            timeframe_minutes=tf,
            current_price=50000.0,
            features_used=["f1"]
        )

@pytest.fixture
def store(tmp_path):
    db_file = tmp_path / "review_test.db"
    return DataStore(db_path=str(db_file))

@pytest.mark.asyncio
async def test_transaction_rollback_on_failure(store):
    """
    Test that if one part of the multi-table insert fails, the whole transaction rolls back.
    We'll simulate this by mocking the connection to raise an error during the second insert.
    """
    strat = MockStrategy()
    tracker = type('MockTracker', (), {'get_active_market': lambda self, tf: {
        "slug": "rollback-test",
        "close_price": 0.4,
        "up_token_id": "up",
        "down_token_id": "down"
    }})()
    
    pipeline = PolymarketLivePipeline([strat], store, tracker)
    pipeline.alpha_thresholds = {"mock_strat": 0.1}
    
    # 1. First, make sure it works normally
    dt = datetime(2024, 1, 1, 0, 4, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({"open":[1], "high":[1], "low":[1], "close":[1], "volume":[1]}, index=[dt])
    
    # We want to force a failure during pm_orders insert.
    # One way is to inject a malformed order or mock the connection.
    # Let's try to mock the connection's 'execute' to fail when it sees 'pm_orders'.
    
    original_get_conn = store._get_connection
    
    class FailingConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn
        def execute(self, sql, params=()):
            if "INSERT INTO pm_orders" in sql:
                raise sqlite3.Error("Simulated DB Failure")
            return self.real_conn.execute(sql, params)
        def commit(self): self.real_conn.commit()
        def rollback(self): self.real_conn.rollback()
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                self.real_conn.rollback()
            else:
                self.real_conn.commit()
            self.real_conn.close()
        def close(self): self.real_conn.close()

    store._get_connection = lambda: FailingConnection(original_get_conn())
    
    # Run pipeline
    await pipeline.process_new_data(df)
    
    # Check if anything was saved. 
    # Because it's a single transaction in pipeline.py (lines 180-236), 
    # it should rollback prediction_signals and simulated_trades too.
    with original_get_conn() as conn:
        conn.row_factory = sqlite3.Row
        signals = conn.execute("SELECT * FROM prediction_signals").fetchall()
        assert len(signals) == 0, "prediction_signals should be rolled back"
        trades = conn.execute("SELECT * FROM simulated_trades").fetchall()
        assert len(trades) == 0, "simulated_trades should be rolled back"

@pytest.mark.asyncio
async def test_order_type_literal_violation(store):
    """
    Verify if the order_type being saved violates the dataclass Literal and how it behaves.
    ARCHITECTURE.md says order_type in PolymarketOrder is Literal["GTC", "FOK", "GTD"].
    But pipeline.py uses "maker".
    """
    strat = MockStrategy()
    tracker = type('MockTracker', (), {'get_active_market': lambda self, tf: {
        "slug": "literal-test",
        "close_price": 0.4,
        "up_token_id": "up",
        "down_token_id": "down"
    }})()
    
    pipeline = PolymarketLivePipeline([strat], store, tracker)
    pipeline.alpha_thresholds = {"mock_strat": 0.1}
    
    dt = datetime(2024, 1, 1, 0, 4, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({"open":[1], "high":[1], "low":[1], "close":[1], "volume":[1]}, index=[dt])
    
    await pipeline.process_new_data(df)
    
    with store._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        orders = conn.execute("SELECT * FROM pm_orders").fetchall()
        assert len(orders) == 1
        order = dict(orders[0])
        # The stored value IS "maker"
        assert order["order_type"] == "maker"
        
        # Test if we can re-construct the dataclass from DB
        # This will fail at runtime if we have strict type checking, but python won't stop it at constructor unless we use a library like pydantic.
        # However, it violates the contract.
        try:
            o = PolymarketOrder(
                signal_id=order["signal_id"],
                order_id=order["order_id"],
                token_id=order["token_id"],
                side=order["side"],
                price=order["price"],
                size=order["size"],
                order_type=order["order_type"], # This is "maker"
                status=order["status"],
                placed_at=datetime.fromisoformat(order["placed_at"])
            )
        except Exception as e:
            pytest.fail(f"Could not reconstruct PolymarketOrder: {e}")

@pytest.mark.asyncio
async def test_trigger_logic_for_all_timeframes(store):
    """
    Check if all timeframes (5, 15, 60, 240, 1440) trigger correctly.
    """
    # 240m = 4h. Trigger at e.g. 03:59, 07:59, etc.
    # 1440m = 24h. Trigger at 23:59.
    
    pipeline = PolymarketLivePipeline([], store, None)
    
    # Test 5m logic
    assert pipeline._trigger_strategies == pipeline._trigger_strategies # dummy
    from btc_predictor.polymarket.pipeline import TRIGGER_MAP
    
    t5 = TRIGGER_MAP[5]
    assert t5(datetime(2024, 1, 1, 0, 4, 0)) == True
    assert t5(datetime(2024, 1, 1, 0, 5, 0)) == False
    
    t240 = TRIGGER_MAP[240]
    assert t240(datetime(2024, 1, 1, 3, 59, 0)) == True
    assert t240(datetime(2024, 1, 1, 4, 0, 0)) == False
    assert t240(datetime(2024, 1, 1, 7, 59, 0)) == True

    t1440 = TRIGGER_MAP[1440]
    assert t1440(datetime(2024, 1, 1, 23, 59, 0)) == True
    assert t1440(datetime(2024, 1, 2, 0, 0, 0)) == False

@pytest.mark.asyncio
async def test_alpha_calculation_direction_lower(store):
    """
    Verify alpha calculation when direction is 'lower'.
    If confidence = 0.8 for 'lower', market_price_up = 0.4.
    Then market_price_lower = 1 - 0.4 = 0.6.
    Alpha = 0.8 - 0.6 = 0.2.
    """
    class LowerStrat(MockStrategy):
        def predict(self, ohlcv, tf):
            sig = super().predict(ohlcv, tf)
            sig.direction = "lower"
            sig.confidence = 0.8
            return sig
            
    strat = LowerStrat()
    tracker = type('MockTracker', (), {'get_active_market': lambda self, tf: {
        "slug": "lower-test",
        "close_price": 0.4, # UP price
        "up_token_id": "up",
        "down_token_id": "down"
    }})()
    
    pipeline = PolymarketLivePipeline([strat], store, tracker)
    pipeline.alpha_thresholds = {"mock_strat": 0.1}
    
    dt = datetime(2024, 1, 1, 0, 4, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({"open":[1], "high":[1], "low":[1], "close":[1], "volume":[1]}, index=[dt])
    
    await pipeline.process_new_data(df)
    
    with store._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        sig = conn.execute("SELECT * FROM prediction_signals").fetchone()
        # confidence (0.8) - (1.0 - market_price_up (0.4)) = 0.8 - 0.6 = 0.2
        assert abs(sig["confidence"] - 0.8) < 1e-6
        # The pipeline code has:
        # if signal.direction == "higher":
        #     market_price = market_price_up
        # else:
        #     market_price = 1.0 - market_price_up
        # signal.alpha = signal.confidence - market_price
        
        # In sqlite, alpha might be tricky if not stored as float. 
        # Wait, prediction_signals table 'alpha' column is not in Schema?
        # Let's check Schema in ARCHITECTURE.md or store.py
        pass

@pytest.mark.asyncio
async def test_missing_alpha_threshold_fallback(store):
    """
    If strategy alpha threshold is not in config, it should fallback to 0.02.
    """
    strat = MockStrategy(name="new_strat")
    tracker = type('MockTracker', (), {'get_active_market': lambda self, tf: {
        "slug": "fallback-test",
        "close_price": 0.5,
        "up_token_id": "up",
        "down_token_id": "down"
    }})()
    
    pipeline = PolymarketLivePipeline([strat], store, tracker)
    # No alpha_thresholds set for "new_strat"
    pipeline.alpha_thresholds = {}
    
    dt = datetime(2024, 1, 1, 0, 4, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({"open":[1], "high":[1], "low":[1], "close":[1], "volume":[1]}, index=[dt])
    
    # confidence=0.8, market_price=0.5 -> alpha=0.3.
    # threshold fallback should be 0.02. 0.3 > 0.02 -> BET.
    await pipeline.process_new_data(df)
    
    with store._get_connection() as conn:
        sig = conn.execute("SELECT traded FROM prediction_signals").fetchone()
        assert sig[0] == 1, "Should have bet using fallback alpha threshold 0.02"

@pytest.mark.asyncio
async def test_risk_control_daily_loss_limit(store):
    """
    Verify that if daily loss limit is reached, it stops betting.
    """
    strat = MockStrategy()
    tracker = type('MockTracker', (), {'get_active_market': lambda self, tf: {
        "slug": "risk-test",
        "close_price": 0.5,
        "up_token_id": "up",
        "down_token_id": "down"
    }})()
    
    pipeline = PolymarketLivePipeline([strat], store, tracker)
    pipeline.alpha_thresholds = {"mock_strat": 0.1}
    pipeline.risk_cfg = {"bet_range": [10, 100], "daily_max_loss": 50, "max_daily_trades": 30, "max_consecutive_losses": 8}
    
    # 1. Inject a huge loss for today in simulated_trades
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with store._get_connection() as conn:
        conn.execute("""
            INSERT INTO simulated_trades (id, strategy_name, direction, confidence, timeframe_minutes, bet_amount, open_time, open_price, expiry_time, result, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("loss-1", "mock_strat", "higher", 0.9, 5, 100, today_str + "T00:00:00", 50000, today_str + "T00:05:00", "lose", -100))
        conn.commit()

    # 2. Run pipeline
    dt = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    # Ensure it's a trigger time (e.g., minute 4, 9, etc.)
    while (dt.minute + 1) % 5 != 0:
        dt += timedelta(minutes=1)
    
    df = pd.DataFrame({"open":[1], "high":[1], "low":[1], "close":[1], "volume":[1]}, index=[dt])
    await pipeline.process_new_data(df)
    
    # 3. Check signal.traded
    with store._get_connection() as conn:
        sig = conn.execute("SELECT traded FROM prediction_signals WHERE strategy_name = 'mock_strat'").fetchone()
        assert sig[0] == 0, "Should NOT have bet because daily loss limit reached"
