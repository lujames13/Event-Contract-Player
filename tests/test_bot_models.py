import pytest
from unittest.mock import AsyncMock, MagicMock
from btc_predictor.discord_bot.bot import EventContractCog

@pytest.mark.asyncio
async def test_models_command_logic():
    # 1. Setup mocks
    bot = MagicMock()
    bot.pipeline = MagicMock()
    bot.store = MagicMock()
    
    # Mock strategies
    strategy1 = MagicMock()
    strategy1.name = "lgbm_v2"
    strategy1.available_timeframes = [60]
    
    strategy2 = MagicMock()
    strategy2.name = "catboost_v1"
    strategy2.available_timeframes = [10]
    
    bot.pipeline.strategies = [strategy1, strategy2]
    
    # Mock store response for get_strategy_summary
    def get_summary_side_effect(name):
        if name == "lgbm_v2":
            return {
                "total_trades": 47,
                "settled_trades": 47,
                "wins": 26,
                "da": 0.55319,
                "total_pnl": 1.8152
            }
        else: # catboost_v1
            return {
                "total_trades": 123,
                "settled_trades": 123,
                "wins": 66,
                "da": 0.53658,
                "total_pnl": -2.408
            }
    
    bot.store.get_strategy_summary.side_effect = get_summary_side_effect
    
    cog = EventContractCog(bot)
    
    # Mock interaction
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # 2. Execute
    await cog.models.callback(cog, interaction)
    
    # 3. Verify
    interaction.response.defer.assert_called_once()
    interaction.followup.send.assert_called_once()
    
    # Extract embed
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert embed.title == "🤖 已載入模型"
    assert len(embed.fields) == 2
    
    # Field 1: lgbm_v2
    assert embed.fields[0].name == "📈 lgbm_v2"
    assert "Timeframes: 60m" in embed.fields[0].value
    assert "Live 交易: 47 筆" in embed.fields[0].value
    assert "DA: 55.3%" in embed.fields[0].value
    assert "PnL: +1.82 USDT" in embed.fields[0].value  # Rounded
    
    # Field 2: catboost_v1
    assert embed.fields[1].name == "📈 catboost_v1"
    assert "Timeframes: 10m" in embed.fields[1].value
    assert "Live 交易: 123 筆" in embed.fields[1].value
    assert "DA: 53.7%" in embed.fields[1].value # Rounded
    assert "PnL: -2.41 USDT" in embed.fields[1].value # Rounded

@pytest.mark.asyncio
async def test_models_command_no_pipeline():
    bot = MagicMock()
    bot.pipeline = None
    bot.store = MagicMock()
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    
    await cog.models.callback(cog, interaction)
    
    interaction.followup.send.assert_called_with("無法取得模型清單（Pipeline 未連線）", ephemeral=True)

@pytest.mark.asyncio
async def test_models_command_no_trades():
    bot = MagicMock()
    bot.pipeline = MagicMock()
    bot.store = MagicMock()
    
    strategy = MagicMock()
    strategy.name = "new_model"
    strategy.available_timeframes = [30]
    bot.pipeline.strategies = [strategy]
    
    bot.store.get_strategy_summary.return_value = {
        "total_trades": 0,
        "settled_trades": 0,
        "wins": 0,
        "da": 0.0,
        "total_pnl": 0.0
    }
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    
    await cog.models.callback(cog, interaction)
    
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert "尚無結算紀錄" in embed.fields[0].value
