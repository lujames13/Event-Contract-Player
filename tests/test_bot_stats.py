import pytest
import sqlite3
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from btc_predictor.data.store import DataStore
from btc_predictor.discord_bot.bot import EventContractCog

@pytest.fixture
def store(tmp_path):
    # Use temporary file to test SQL logic with real schema
    db_file = tmp_path / "test_bot_stats.db"
    return DataStore(str(db_file))

def test_get_strategy_detail_logic(store):
    # Setup mock data in memory DB
    with store._get_connection() as conn:
        # 1. basic win (Higher)
        conn.execute("""
            INSERT INTO simulated_trades (id, strategy_name, direction, confidence, timeframe_minutes, bet_amount, open_time, open_price, expiry_time, result, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("1", "lgbm_v2", "higher", 0.6, 60, 10, "2026-02-17T00:00:00Z", 50000, "2026-02-17T01:00:00Z", "win", 1.85))
        # 2. basic lose (Higher)
        conn.execute("""
            INSERT INTO simulated_trades (id, strategy_name, direction, confidence, timeframe_minutes, bet_amount, open_time, open_price, expiry_time, result, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("2", "lgbm_v2", "higher", 0.6, 60, 10, "2026-02-17T01:00:00Z", 50000, "2026-02-17T02:00:00Z", "lose", -1.0))
        # 3. basic win (Lower)
        conn.execute("""
            INSERT INTO simulated_trades (id, strategy_name, direction, confidence, timeframe_minutes, bet_amount, open_time, open_price, expiry_time, result, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("3", "lgbm_v2", "lower", 0.6, 60, 10, "2026-02-17T02:00:00Z", 50000, "2026-02-17T03:00:00Z", "win", 1.85))
        # 4. Pending trade
        conn.execute("""
            INSERT INTO simulated_trades (id, strategy_name, direction, confidence, timeframe_minutes, bet_amount, open_time, open_price, expiry_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("4", "lgbm_v2", "higher", 0.6, 60, 10, "2026-02-17T03:00:00Z", 50000, "2026-02-17T04:00:00Z"))

    detail = store.get_strategy_detail("lgbm_v2")
    
    assert detail['settled'] == 3
    assert detail['pending'] == 1
    assert detail['wins'] == 2
    assert detail['da'] == pytest.approx(2/3)
    assert detail['higher_total'] == 2
    assert detail['higher_wins'] == 1
    assert detail['higher_da'] == 0.5
    assert detail['lower_total'] == 1
    assert detail['lower_wins'] == 1
    assert detail['lower_da'] == 1.0
    assert detail['total_pnl'] == pytest.approx(1.85 - 1.0 + 1.85)
    
    # Max drawdown check
    # PNL sequence: 1.85 -> 0.85 -> 2.70
    # Cumulative: 1.85, 0.85, 2.70
    # Peak: 1.85, 1.85, 2.70
    # DD: 0, 1.0, 0
    assert detail['max_drawdown'] == pytest.approx(1.0)

@pytest.mark.asyncio
async def test_stats_command_summary():
    bot = MagicMock()
    bot.store = MagicMock()
    bot.pipeline = MagicMock()
    
    # Mock strategies
    s1 = MagicMock()
    s1.name = "lgbm_v2"
    s1.available_timeframes = [60]
    bot.pipeline.strategies = [s1]
    
    # Mock store response for detail (used in summary loop)
    # Using a helper to avoid repetitive code
    def mock_get_detail(name, tf):
        return {
            "settled": 10, "pending": 2, "wins": 6, "da": 0.6,
            "higher_total": 5, "higher_wins": 3, "higher_da": 0.6,
            "lower_total": 5, "lower_wins": 3, "lower_da": 0.6,
            "total_pnl": 5.0, "max_drawdown": 2.0
        }
    bot.store.get_strategy_detail.side_effect = mock_get_detail
    
    # Mock the direct connection used in the summary loop
    conn = MagicMock()
    bot.store._get_connection.return_value.__enter__.return_value = conn
    conn.execute.return_value.fetchall.return_value = [("lgbm_v2", 60)]
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # Test summary (no args)
    await cog.stats.callback(cog, interaction)
    
    interaction.followup.send.assert_called_once()
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert embed.title == "📊 交易統計摘要"
    assert "lgbm_v2" in embed.description
    assert "60m" in embed.description
    assert "60.0%" in embed.description
    assert "+5.00" in embed.description

@pytest.mark.asyncio
async def test_stats_command_detail():
    bot = MagicMock()
    bot.store = MagicMock()
    bot.pipeline = MagicMock()
    
    s1 = MagicMock()
    s1.name = "lgbm_v2"
    s1.available_timeframes = [60]
    bot.pipeline.strategies = [s1]
    
    bot.store.get_strategy_detail.return_value = {
        "settled": 45, "pending": 2, "wins": 25, "da": 0.553,
        "higher_total": 24, "higher_wins": 14, "higher_da": 0.583,
        "lower_total": 21, "lower_wins": 11, "lower_da": 0.524,
        "total_pnl": 1.82, "max_drawdown": 8.50
    }
    bot.store.get_daily_stats.return_value = {
        "daily_trades": 3, "daily_loss": 0.45, "consecutive_losses": 2
    }
    
    # Mock the direct connection used for daily PnL
    conn = MagicMock()
    bot.store._get_connection.return_value.__enter__.return_value = conn
    conn.execute.return_value.fetchone.return_value = [0.45]
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # Test detail
    await cog.stats.callback(cog, interaction, model="lgbm_v2")
    
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert "lgbm_v2 詳細統計" in embed.title
    assert "方向準確率: **55.3%**" in embed.description
    assert "Higher:   58.3%" in embed.description
    assert "Lower:    52.4%" in embed.description
    assert "總 PnL:     **+1.82**" in embed.description
    assert "最大回撤:   **8.50**" in embed.description
    assert "今日交易:   3 筆 | PnL: +0.45" in embed.description
    assert "連敗:       2" in embed.description
