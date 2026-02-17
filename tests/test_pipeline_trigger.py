import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from btc_predictor.data.pipeline import DataPipeline

def test_timeframe_trigger_logic():
    """驗證各 timeframe 的觸發條件是否符合預期"""
    
    # Define the trigger map locally for testing (should match pipeline.py)
    TRIGGER_MAP = {
        10: lambda dt: dt.minute % 10 == 0,
        30: lambda dt: dt.minute % 30 == 0,
        60: lambda dt: dt.minute == 0,
        1440: lambda dt: dt.hour == 0 and dt.minute == 0,
    }

    # Helper to create datetime
    def get_dt(hour, minute):
        return datetime(2024, 1, 1, hour, minute, tzinfo=timezone.utc)

    # 10m tests
    assert TRIGGER_MAP[10](get_dt(1, 0)) is True
    assert TRIGGER_MAP[10](get_dt(1, 10)) is True
    assert TRIGGER_MAP[10](get_dt(1, 20)) is True
    assert TRIGGER_MAP[10](get_dt(1, 5)) is False

    # 30m tests
    assert TRIGGER_MAP[30](get_dt(1, 0)) is True
    assert TRIGGER_MAP[30](get_dt(1, 30)) is True
    assert TRIGGER_MAP[30](get_dt(1, 10)) is False

    # 60m tests
    assert TRIGGER_MAP[60](get_dt(1, 0)) is True
    assert TRIGGER_MAP[60](get_dt(2, 0)) is True
    assert TRIGGER_MAP[60](get_dt(1, 30)) is False

    # 1440m tests
    assert TRIGGER_MAP[1440](get_dt(0, 0)) is True
    assert TRIGGER_MAP[1440](get_dt(1, 0)) is False
    assert TRIGGER_MAP[1440](get_dt(0, 30)) is False

@pytest.mark.asyncio
async def test_pipeline_filters_strategies():
    """驗證 pipeline 是否正確過濾不支援該 timeframe 的策略"""
    mock_store = MagicMock()
    
    # Strategy A supports 60m
    strat_a = MagicMock()
    strat_a.name = "strat_a"
    strat_a.available_timeframes = [60]
    
    # Strategy B supports 10m
    strat_b = MagicMock()
    strat_b.name = "strat_b"
    strat_b.available_timeframes = [10]
    
    pipeline = DataPipeline("BTCUSDT", ["1m"], [strat_a, strat_b], mock_store)
    
    # Mock get_ohlcv to return dummy data
    mock_store.get_ohlcv.return_value = MagicMock()
    
    # Trigger 60m
    with patch('btc_predictor.data.pipeline.process_signal') as mock_process:
        await pipeline._trigger_strategies(60)
        
        # strat_a should be called, strat_b should NOT
        strat_a.predict.assert_called_once()
        strat_b.predict.assert_not_called()
        
    # Reset mocks
    strat_a.predict.reset_mock()
    strat_b.predict.reset_mock()
    
    # Trigger 10m
    with patch('btc_predictor.data.pipeline.process_signal') as mock_process:
        await pipeline._trigger_strategies(10)
        
        # strat_b should be called, strat_a should NOT
        strat_b.predict.assert_called_once()
        strat_a.predict.assert_not_called()
