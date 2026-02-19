import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock
from discord import app_commands
from btc_predictor.discord_bot.bot import EventContractCog
from btc_predictor.models import PredictionSignal

@pytest.mark.asyncio
async def test_predict_command_success():
    bot = MagicMock()
    bot.store = MagicMock()
    bot.pipeline = MagicMock()
    
    # 1. Mock OHLCV data
    df = pd.DataFrame(
        {"close": [50000] * 10, "open": [50000] * 10},
        index=pd.date_range("2026-02-17 14:00", periods=10, freq="1min")
    )
    bot.store.get_latest_ohlcv.return_value = df
    
    # 2. Mock strategies
    s1 = MagicMock()
    s1.name = "lgbm_v2"
    s1.available_timeframes = [10, 60]
    
    # Mock strategy.predict
    def mock_predict(df_in, tf):
        if tf == 60:
            return PredictionSignal(
                strategy_name="lgbm_v2",
                timestamp=df_in.index[-1],
                timeframe_minutes=60,
                direction="higher",
                confidence=0.6234,
                current_price=50000.0
            )
        else:
            return PredictionSignal(
                strategy_name="lgbm_v2",
                timestamp=df_in.index[-1],
                timeframe_minutes=10,
                direction="lower",
                confidence=0.5101,
                current_price=50000.0
            )
            
    s1.predict.side_effect = mock_predict
    bot.pipeline.strategies = [s1]
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # Test predict (no args = all tfs)
    await cog.predict.callback(cog, interaction)
    
    interaction.followup.send.assert_called_once()
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert "即時預測" in embed.title
    assert "2026-02-17 14:09 UTC" in embed.title
    
    # Check fields (Order: 10m, then 60m)
    fields = embed.fields
    assert len(fields) == 2
    
    # 10m: lower, confidence=0.5101, threshold=0.52, 不下注
    assert "lgbm_v2 | 10m" in fields[0].name
    assert "LOWER" in fields[0].value
    assert "❌ 不下注" in fields[0].value

    # 60m: higher, confidence=0.6234, threshold=0.591, bet calculation
    assert "lgbm_v2 | 60m" in fields[1].name
    assert "HIGHER" in fields[1].value
    assert "0.6234" in fields[1].value
    assert "✅ 6.2 USDT" in fields[1].value 

@pytest.mark.asyncio
async def test_predict_command_filter_tf():
    bot = MagicMock()
    bot.store = MagicMock()
    bot.pipeline = MagicMock()
    
    df = pd.DataFrame(
        {"close": [50000] * 10},
        index=pd.date_range("2026-02-17 14:00", periods=10, freq="1min")
    )
    bot.store.get_latest_ohlcv.return_value = df
    
    s1 = MagicMock()
    s1.name = "lgbm_v2"
    s1.available_timeframes = [10, 60]
    s1.predict.return_value = PredictionSignal(
        strategy_name="lgbm_v2",
        timestamp=df.index[-1],
        timeframe_minutes=60,
        direction="higher",
        confidence=0.7,
        current_price=50000.0
    )
    bot.pipeline.strategies = [s1]
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # Test predict with tf filter
    choice = app_commands.Choice(name="1 小時", value=60)
    await cog.predict.callback(cog, interaction, timeframe=choice)
    
    interaction.followup.send.assert_called_once()
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert len(embed.fields) == 1
    assert "60m" in embed.fields[0].name

@pytest.mark.asyncio
async def test_predict_command_error_isolation():
    bot = MagicMock()
    bot.store = MagicMock()
    bot.pipeline = MagicMock()
    
    df = pd.DataFrame(
        {"close": [50000] * 10},
        index=pd.date_range("2026-02-17 14:00", periods=10, freq="1min")
    )
    bot.store.get_latest_ohlcv.return_value = df
    
    s1 = MagicMock()
    s1.name = "fail_strategy"
    s1.available_timeframes = [60]
    s1.predict.side_effect = Exception("Model failed")
    
    s2 = MagicMock()
    s2.name = "ok_strategy"
    s2.available_timeframes = [60]
    s2.predict.return_value = PredictionSignal(
        strategy_name="ok_strategy",
        timestamp=df.index[-1],
        timeframe_minutes=60,
        direction="higher",
        confidence=0.8,
        current_price=50000.0
    )
    
    bot.pipeline.strategies = [s1, s2]
    
    cog = EventContractCog(bot)
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    await cog.predict.callback(cog, interaction)
    
    args, kwargs = interaction.followup.send.call_args
    embed = kwargs.get('embed') or args[0]
    
    assert len(embed.fields) == 2
    assert "❌ 推理失敗: Model failed" in embed.fields[0].value
    assert "方向: **HIGHER**" in embed.fields[1].value
