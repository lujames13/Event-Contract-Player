import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
from src.btc_predictor.models import SimulatedTrade
from src.btc_predictor.discord_bot.bot import EventContractBot

@pytest.fixture
def mock_bot():
    bot = EventContractBot(channel_id=123, guild_id=456)
    bot.target_channel = AsyncMock()
    bot.store = MagicMock()
    bot.paused = False
    return bot

@pytest.mark.asyncio
async def test_send_signal_embed(mock_bot):
    trade = SimulatedTrade(
        id="test-uuid",
        strategy_name="test_strat",
        direction="higher",
        confidence=0.65,
        timeframe_minutes=60,
        bet_amount=10.0,
        open_time=datetime.now(timezone.utc),
        open_price=100000.0,
        expiry_time=datetime.now(timezone.utc)
    )
    
    await mock_bot.send_signal(trade)
    
    assert mock_bot.target_channel.send.called
    call_args = mock_bot.target_channel.send.call_args
    embed = call_args[1]['embed']
    
    assert "test_strat" in embed.title
    assert "HIGHER" in embed.title
    assert "0.6500" in embed.description
    assert "✅ 10.0 USDT" in embed.description
    assert "🎯 閾值:      0.591（已超過）" in embed.description

@pytest.mark.asyncio
async def test_send_settlement_embed(mock_bot):
    trade = SimulatedTrade(
        id="test-uuid",
        strategy_name="test_strat",
        direction="lower",
        confidence=0.55,
        timeframe_minutes=10,
        bet_amount=5.0,
        open_time=datetime.now(timezone.utc),
        open_price=100000.0,
        expiry_time=datetime.now(timezone.utc),
        close_price=99000.0,
        result="win",
        pnl=4.0
    )
    
    # Mock store response
    mock_bot.store.get_strategy_summary.return_value = {
        'strategy_name': 'test_strat',
        'total_trades': 100,
        'settled_trades': 80,
        'wins': 50,
        'da': 0.625,
        'total_pnl': 25.5
    }
    
    await mock_bot.send_settlement(trade)
    
    assert mock_bot.target_channel.send.called
    call_args = mock_bot.target_channel.send.call_args
    embed = call_args[1]['embed']
    
    assert "WIN" in embed.title
    assert "test_strat" in embed.title
    assert "LOWER" in embed.title
    assert "**+4.00** USDT" in embed.description
    assert "📊 累計: 100 筆 | DA 62.5% | PnL +25.50" in embed.description

@pytest.mark.asyncio
async def test_send_signal_pm_embed(mock_bot):
    trade = SimulatedTrade(
        id="pm-test-uuid",
        strategy_name="pm_v1",
        direction="higher",
        confidence=0.8,
        timeframe_minutes=5,
        bet_amount=20.0,
        open_time=datetime.now(timezone.utc),
        open_price=50000.0,
        expiry_time=datetime.now(timezone.utc)
    )
    
    # Mock DataStore and async asyncio.to_thread behaviors since the function awaits a def fetch_pm_info
    mock_conn = MagicMock()
    mock_bot.store._get_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = (0.3, "btc-up", 0.5, "GTC")
    
    await mock_bot.send_signal(trade)
    
    assert mock_bot.target_channel.send.called
    call_args = mock_bot.target_channel.send.call_args
    embed = call_args[1]['embed']
    
    assert "pm_v1" in embed.title
    assert "Alpha: 0.30000" in embed.description
    assert "PM Price: 0.5000" in embed.description
    assert "Order: GTC" in embed.description
