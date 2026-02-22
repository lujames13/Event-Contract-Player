# Review tests for task-spec-g3.6
# Focus: DataStore PM extensions, Discord Bot routing and rendering, and Interface contract compliance.

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from discord import app_commands
from typing import get_args, Literal

from src.btc_predictor.models import PredictionSignal, PolymarketOrder, SimulatedTrade
from src.btc_predictor.infrastructure.store import DataStore
from src.btc_predictor.discord_bot.bot import EventContractCog, EventContractBot

@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "review_pm.db"
    return DataStore(str(db_file))

def test_prediction_signal_order_type_contract():
    # Verify PredictionSignal.order_type Literal args
    # Note: __annotations__ might be hidden or different depending on how it's defined
    # but we can check the class definition if needed.
    # Here we just verify it accepts the new values.
    sig = PredictionSignal(
        strategy_name="test",
        timestamp=datetime.now(timezone.utc),
        timeframe_minutes=10,
        direction="higher",
        confidence=0.5,
        current_price=50000.0,
        order_type="GTC"
    )
    assert sig.order_type == "GTC"
    
    # Check that PM order also has these
    order = PolymarketOrder(
        signal_id="s1", order_id="o1", token_id="t1", side="BUY",
        price=0.5, size=10, order_type="FOK", status="OPEN",
        placed_at=datetime.now(timezone.utc)
    )
    assert order.order_type == "FOK"

def test_store_get_pm_strategy_detail_timeframe_filtering(temp_store):
    now = datetime.now(timezone.utc)
    
    # Create signals and orders for different timeframes
    for tf in [5, 15]:
        sig = PredictionSignal(
            strategy_name="pm_v1",
            timestamp=now - timedelta(minutes=20),
            timeframe_minutes=tf,
            direction="higher",
            confidence=0.8,
            current_price=50000.0
        )
        trade = SimulatedTrade(
            id=f"t_{tf}", strategy_name="pm_v1", direction="higher", confidence=0.8,
            timeframe_minutes=tf, bet_amount=10, open_time=now - timedelta(minutes=20),
            open_price=50000.0, expiry_time=now - timedelta(minutes=20-tf)
        )
        order = PolymarketOrder(
            signal_id="linked", order_id=f"o_{tf}", token_id="tok", side="BUY",
            price=0.5, size=20, order_type="GTC", status="OPEN", placed_at=now - timedelta(minutes=20)
        )
        temp_store.save_polymarket_execution_context(sig, trade, order)
        temp_store.update_pm_order(f"o_{tf}", status="FILLED", pnl=10.0 if tf == 5 else -5.0)

    # Test all timeframes
    detail_all = temp_store.get_pm_strategy_detail("pm_v1")
    assert detail_all["settled"] == 2
    assert detail_all["total_pnl"] == 5.0 # 10 - 5
    
    # Test specific timeframe 5m
    detail_5 = temp_store.get_pm_strategy_detail("pm_v1", timeframe=5)
    assert detail_5["settled"] == 1
    assert detail_5["total_pnl"] == 10.0
    
    # Test specific timeframe 15m
    detail_15 = temp_store.get_pm_strategy_detail("pm_v1", timeframe=15)
    assert detail_15["settled"] == 1
    assert detail_15["total_pnl"] == -5.0

@pytest.mark.asyncio
async def test_bot_stats_routing_logic():
    bot = MagicMock()
    bot.store = MagicMock()
    pipeline = MagicMock()
    s1 = MagicMock()
    s1.name = "pm_v1"
    pipeline.strategies = [s1]
    bot.pipeline = pipeline
    
    cog = EventContractCog(bot)
    
    # Mock bot.store methods
    bot.store.get_pm_strategy_detail.return_value = {
        "settled": 1, "pending": 0, "wins": 1, "da": 1.0,
        "higher_total": 1, "higher_wins": 1, "higher_da": 1.0,
        "lower_total": 0, "lower_wins": 0, "lower_da": 0.0,
        "total_pnl": 10.0, "max_drawdown": 0.0
    }
    bot.store.get_pm_daily_stats.return_value = {
        "daily_loss": 0.0, "daily_trades": 1, "consecutive_losses": 0
    }
    
    # Mock connection execute for daily_pnl
    mock_conn = MagicMock()
    bot.store._get_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = (10.0,)
    
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # Call stats for pm_v1
    await cog.stats.callback(cog, interaction, model="pm_v1")
    
    # Verify get_pm_strategy_detail was called, not get_strategy_detail
    bot.store.get_pm_strategy_detail.assert_called_with("pm_v1", None)
    bot.store.get_strategy_detail.assert_not_called()
    
    # Verify SQL query used pm_orders
    args, _ = mock_conn.execute.call_args
    assert "pm_orders" in args[0]
    assert "prediction_signals" in args[0]

@pytest.mark.asyncio
async def test_bot_predict_alpha_none_handling():
    bot = MagicMock()
    bot.store = MagicMock()
    bot.pipeline = MagicMock()
    
    df = pd.DataFrame({"close": [50000]*2}, index=pd.date_range("2026-02-22", periods=2, freq="1min"))
    bot.store.get_latest_ohlcv.return_value = df
    
    s1 = MagicMock()
    s1.name = "pm_v1"
    s1.available_timeframes = [5]
    # Signal with alpha=None
    s1.predict.return_value = PredictionSignal(
        strategy_name="pm_v1",
        timestamp=df.index[-1],
        timeframe_minutes=5,
        direction="higher",
        confidence=0.8,
        current_price=50000.0,
        alpha=None,
        market_slug="slug1"
    )
    bot.pipeline.strategies = [s1]
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # Should not crash
    await cog.predict.callback(cog, interaction)
    
    interaction.followup.send.assert_called_once()
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    val = embed.fields[0].value
    assert "Alpha: **N/A**" in val

def test_store_get_pm_daily_stats_consecutive_losses(temp_store):
    now = datetime.now(timezone.utc)
    
    # Create 3 losses followed by 1 win
    results = [(-10.0, "lose"), (-5.0, "lose"), (-2.0, "lose"), (8.0, "win")]
    for i, (pnl, _) in enumerate(results):
        sig = PredictionSignal(
            strategy_name="pm_v1", timestamp=now - timedelta(minutes=10-i),
            timeframe_minutes=5, direction="higher", confidence=0.8, current_price=50000.0
        )
        trade = SimulatedTrade(
            id=f"t_{i}", strategy_name="pm_v1", direction="higher", confidence=0.8,
            timeframe_minutes=5, bet_amount=10, open_time=now - timedelta(minutes=10-i),
            open_price=50000.0, expiry_time=now - timedelta(minutes=5-i)
        )
        order = PolymarketOrder(
            signal_id="linked", order_id=f"o_{i}", token_id="tok", side="BUY",
            price=0.5, size=20, order_type="GTC", status="OPEN", placed_at=now - timedelta(minutes=10-i)
        )
        temp_store.save_polymarket_execution_context(sig, trade, order)
        temp_store.update_pm_order(f"o_{i}", status="FILLED", pnl=pnl)

    date_str = now.strftime("%Y-%m-%d")
    stats = temp_store.get_pm_daily_stats("pm_v1", date_str)
    
    # Recent is win (at index 3), so consecutive losses should be 0 or based on order.
    # The code says:
    # for (pnl,) in recent_results:
    #     if pnl < 0: consecutive_losses += 1
    #     elif pnl > 0: break
    # Since latest (i=3) is pnl=8.0 > 0, it breaks immediately.
    assert stats["consecutive_losses"] == 0
    
    # Now add another loss
    sig = PredictionSignal(
        strategy_name="pm_v1", timestamp=now,
        timeframe_minutes=5, direction="higher", confidence=0.8, current_price=50000.0
    )
    trade = SimulatedTrade(
        id="t_new", strategy_name="pm_v1", direction="higher", confidence=0.8,
        timeframe_minutes=5, bet_amount=10, open_time=now,
        open_price=50000.0, expiry_time=now + timedelta(minutes=5)
    )
    order = PolymarketOrder(
        signal_id="linked", order_id="o_new", token_id="tok", side="BUY",
        price=0.5, size=20, order_type="GTC", status="OPEN", placed_at=now
    )
    temp_store.save_polymarket_execution_context(sig, trade, order)
    temp_store.update_pm_order("o_new", status="FILLED", pnl=-1.0)
    
    stats = temp_store.get_pm_daily_stats("pm_v1", date_str)
    assert stats["consecutive_losses"] == 1
