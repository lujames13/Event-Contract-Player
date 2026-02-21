"""
tests/test_binance/test_pipeline_trigger.py
-------------------------------------------
Unit tests for BinanceLivePipeline strategy-triggering logic and
BinanceFeed trigger-map correctness.

Migration note: previously tested DataPipeline from
btc_predictor.infrastructure.pipeline. Now tests the refactored
BinanceLivePipeline from btc_predictor.binance.pipeline.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from btc_predictor.binance.pipeline import BinanceLivePipeline, TRIGGER_MAP


def test_timeframe_trigger_logic():
    """驗證各 timeframe 的觸發條件是否符合預期"""

    def get_dt(hour: int, minute: int) -> datetime:
        return datetime(2024, 1, 1, hour, minute, tzinfo=timezone.utc)

    # 10m tests
    assert TRIGGER_MAP[10](get_dt(1, 9)) is True
    assert TRIGGER_MAP[10](get_dt(1, 19)) is True
    assert TRIGGER_MAP[10](get_dt(1, 59)) is True
    assert TRIGGER_MAP[10](get_dt(1, 0)) is False

    # 30m tests
    assert TRIGGER_MAP[30](get_dt(1, 29)) is True
    assert TRIGGER_MAP[30](get_dt(1, 59)) is True
    assert TRIGGER_MAP[30](get_dt(1, 0)) is False

    # 60m tests
    assert TRIGGER_MAP[60](get_dt(1, 59)) is True
    assert TRIGGER_MAP[60](get_dt(2, 59)) is True
    assert TRIGGER_MAP[60](get_dt(1, 0)) is False

    # 1440m tests
    assert TRIGGER_MAP[1440](get_dt(23, 59)) is True
    assert TRIGGER_MAP[1440](get_dt(0, 0)) is False
    assert TRIGGER_MAP[1440](get_dt(0, 59)) is False


@pytest.mark.asyncio
async def test_pipeline_filters_strategies():
    """驗證 BinanceLivePipeline 是否正確過濾不支援該 timeframe 的策略"""
    import pandas as pd

    mock_store = MagicMock()
    # save_prediction_signal returns a string id
    mock_store.save_prediction_signal.return_value = "signal-id-123"

    # Strategy A supports 60m
    strat_a = MagicMock()
    strat_a.name = "strat_a"
    strat_a.available_timeframes = [60]
    # predict returns a MagicMock signal
    strat_a.predict.return_value = MagicMock()

    # Strategy B supports 10m
    strat_b = MagicMock()
    strat_b.name = "strat_b"
    strat_b.available_timeframes = [10]
    strat_b.predict.return_value = MagicMock()

    pipeline = BinanceLivePipeline(
        strategies=[strat_a, strat_b],
        store=mock_store,
    )

    # Build a minimal DataFrame with a 60m-trigger timestamp (minute=59)
    idx = pd.DatetimeIndex(
        [datetime(2024, 1, 1, 1, 59, tzinfo=timezone.utc)], name="open_time"
    )
    ohlcv_60 = pd.DataFrame(
        {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
        index=idx,
    )

    with patch(
        "btc_predictor.binance.pipeline.process_signal", return_value=None
    ) as mock_process:
        await pipeline._trigger_strategies(ohlcv_60, 60)

        # strat_a (60m) should be called; strat_b (10m) must NOT
        strat_a.predict.assert_called_once()
        strat_b.predict.assert_not_called()

    # Reset mocks
    strat_a.predict.reset_mock()
    strat_b.predict.reset_mock()

    # Build a DataFrame with a 10m-trigger timestamp (minute=9)
    idx2 = pd.DatetimeIndex(
        [datetime(2024, 1, 1, 1, 9, tzinfo=timezone.utc)], name="open_time"
    )
    ohlcv_10 = pd.DataFrame(
        {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
        index=idx2,
    )

    with patch(
        "btc_predictor.binance.pipeline.process_signal", return_value=None
    ) as mock_process:
        await pipeline._trigger_strategies(ohlcv_10, 10)

        # strat_b (10m) should be called; strat_a (60m) must NOT
        strat_b.predict.assert_called_once()
        strat_a.predict.assert_not_called()


@pytest.mark.asyncio
async def test_process_new_data_dispatches_correct_timeframes():
    """驗證 process_new_data 能根據時間戳自動決定要觸發哪些 timeframe"""
    import pandas as pd

    mock_store = MagicMock()
    mock_store.save_prediction_signal.return_value = "sig-abc"

    strat = MagicMock()
    strat.name = "strat_multi"
    strat.available_timeframes = [10, 30, 60]
    strat.predict.return_value = MagicMock()

    pipeline = BinanceLivePipeline(strategies=[strat], store=mock_store)

    # minute=29 → should trigger 30m (and also 10m? no: (29+1)%10 = 0 → yes, 10m too)
    # Actually minute=29: (29+1)%10 = 0 (triggers 10m), (29+1)%30 = 0 (triggers 30m), not 60m
    idx = pd.DatetimeIndex(
        [datetime(2024, 1, 1, 1, 29, tzinfo=timezone.utc)], name="open_time"
    )
    ohlcv = pd.DataFrame(
        {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
        index=idx,
    )

    with patch(
        "btc_predictor.binance.pipeline.process_signal", return_value=None
    ):
        await pipeline.process_new_data(ohlcv)

    # strat supports 10m and 30m → predict should be called twice (once per triggered timeframe)
    assert strat.predict.call_count == 2
