import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from btc_predictor.discord_bot.bot import EventContractCog

@pytest.mark.asyncio
async def test_health_command_logic():
    # 1. Setup mocks
    bot = MagicMock()
    bot.paused = False
    bot.store = MagicMock()
    bot.pipeline = MagicMock()
    bot.pipeline.is_running = True
    bot.pipeline.trigger_count = 42
    bot.pipeline.strategies = [MagicMock(), MagicMock()]
    
    now = datetime.now(timezone.utc)
    bot.pipeline.last_kline_time = {"1m": now - timedelta(seconds=5)}
    bot.start_time = now - timedelta(hours=1, minutes=30)
    
    # Mock store response
    bot.store.get_table_counts = MagicMock(return_value={"ohlcv": 1000, "simulated_trades": 50})
    
    cog = EventContractCog(bot)
    
    # Mock interaction
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # 2. Execute
    with patch("btc_predictor.discord_bot.bot.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        mock_datetime.fromtimestamp = datetime.fromtimestamp
        mock_datetime.fromisoformat = datetime.fromisoformat
        # we need to make sure max() works with our mock
        await cog.health.callback(cog, interaction)
    
    # 3. Verify
    interaction.response.defer.assert_called_once()
    interaction.followup.send.assert_called_once()
    
    # Extract embed
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert embed.title == "🏥 系統健康檢查"
    
    # Check fields
    fields = {f.name: f.value for f in embed.fields}
    assert "🔌 WebSocket" in fields
    assert "✅ 連線中" in fields["🔌 WebSocket"]
    assert "5 秒前" in fields["🔌 WebSocket"]
    
    assert "📊 Pipeline" in fields
    assert "已觸發策略: 42 次" in fields["📊 Pipeline"]
    
    assert "🤖 策略數" in fields
    assert "2 個已載入" in fields["🤖 策略數"]
    
    assert "💾 DB" in fields
    assert "ohlcv: 1,000 筆" in fields["💾 DB"]
    assert "trades: 50 筆" in fields["💾 DB"]
    
    assert "⏱️ Uptime" in fields
    assert "0d 1h 30m" in fields["⏱️ Uptime"]

@pytest.mark.asyncio
async def test_health_command_no_pipeline():
    bot = MagicMock()
    bot.pipeline = None
    bot.store = None
    bot.start_time = None
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    
    await cog.health.callback(cog, interaction)
    
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    fields = {f.name: f.value for f in embed.fields}
    assert fields["🔌 WebSocket"] == "❌ 未連線"
    assert fields["📊 Pipeline"] == "❌ 未運行"
    assert fields["💾 DB"] == "❌ Store 未初始化"
    assert fields["⏱️ Uptime"] == "未知"
