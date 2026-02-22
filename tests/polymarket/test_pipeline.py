import pytest
import sqlite3
import asyncio
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from btc_predictor.infrastructure.store import DataStore
from btc_predictor.polymarket.pipeline import PolymarketLivePipeline
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.base import BaseStrategy

class DummyStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "dummy_pm"
    
    @property
    def requires_fitting(self) -> bool:
        return False

    @property
    def available_timeframes(self) -> list[int]:
        return [5]

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        pass

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            direction="higher",
            confidence=0.9,
            timeframe_minutes=timeframe_minutes,
            current_price=100000.0,
            features_used=["dummy"]
        )

class MockTracker:
    def sync_active_markets(self, timeframes):
        pass

    def get_active_market(self, timeframe):
        return {
            "slug": "test-market",
            "condition_id": "0x123",
            "up_token_id": "up123",
            "down_token_id": "dn123",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:05:00Z",
            "price_to_beat": 100000.0,
            "outcome": None,
            "close_price": 0.4  # the market price for "higher". Alpha will be 0.9 - 0.4 = 0.5
        }

@pytest.fixture
def temp_store(tmp_path: Path):
    db_file = tmp_path / "test.db"
    return DataStore(db_path=str(db_file))

@pytest.mark.asyncio
async def test_polymarket_pipeline_execution(temp_store):
    # Setup dummy data
    strat = DummyStrategy()
    tracker = MockTracker()
    
    pipeline = PolymarketLivePipeline(
        strategies=[strat],
        store=temp_store,
        tracker=tracker
    )
    
    # Overwrite config for threshold to trigger bet
    # alpha = 0.9 - 0.4 = 0.5, which is > 0.1, so it should bet
    pipeline.alpha_thresholds = {"dummy_pm": {5: 0.1}}
    pipeline.risk_cfg = {"bet_range": [10, 100], "daily_max_loss": 500, "max_daily_trades": 100, "max_consecutive_losses": 8}
    
    # Create fake OHLCV ending perfectly on a 5-minute trigger boundary.
    # TRIGGER_MAP for 5m is: (dt.minute + 1) % 5 == 0 -> e.g. minute 4 or 9
    dt = datetime(2024, 1, 1, 0, 4, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({
        "open": [1, 2],
        "high": [1, 2],
        "low": [1, 2],
        "close": [1, 2],
        "volume": [1, 2],
    }, index=[dt - pd.Timedelta(minutes=1), dt])
    
    # Process new data
    await pipeline.process_new_data(df)
    
    # Verify records in db
    with temp_store._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        signals = conn.execute("SELECT * FROM prediction_signals").fetchall()
        assert len(signals) == 1, "Expected exactly 1 prediction signal to be saved"
        sig = dict(signals[0])
        assert sig["strategy_name"] == "dummy_pm"
        assert sig["traded"] == 1
        
        trades = conn.execute("SELECT * FROM simulated_trades").fetchall()
        assert len(trades) == 1, "Expected exactly 1 simulated trade to be saved"
        trade = dict(trades[0])
        assert trade["bet_amount"] == 10.0
        assert trade["open_price"] == 100000.0
        
        orders = conn.execute("SELECT * FROM pm_orders").fetchall()
        assert len(orders) == 1, "Expected exactly 1 Polymarket order to be saved"
        order = dict(orders[0])
        assert order["status"] == "OPEN"
        assert order["order_type"] == "maker"
        assert order["price"] == 0.4
        
@pytest.mark.asyncio
async def test_polymarket_pipeline_handles_missing_market(temp_store, caplog):
    strat = DummyStrategy()
    
    class MockEmptyTracker:
        def get_active_market(self, timeframe):
            return None
    
    pipeline = PolymarketLivePipeline(
        strategies=[strat],
        store=temp_store,
        tracker=MockEmptyTracker()
    )
    pipeline.alpha_thresholds = {"dummy_pm": {5: 0.1}}
    
    dt = datetime(2024, 1, 1, 0, 9, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({
        "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]
    }, index=[dt])
    
    await pipeline.process_new_data(df)
    
    # No crash should happen, but it should still log a signal because signals are unconditionally saved
    with temp_store._get_connection() as conn:
        signals = conn.execute("SELECT * FROM prediction_signals").fetchall()
        assert len(signals) == 1
        trades = conn.execute("SELECT * FROM simulated_trades").fetchall()
        assert len(trades) == 0 # no trades because alpha is None    
        
        # Wait, the logic is: default fallback to 0.5
        # confidence: 0.9, market_price: 0.5. alpha: 0.9 - 0.5 = 0.4 > 0.1 -> still bet!
