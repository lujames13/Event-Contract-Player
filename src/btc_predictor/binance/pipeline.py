"""
btc_predictor/binance/pipeline.py
----------------------------------
BinanceLivePipeline: Binance EC の実行・制御骨幹.

職責:
- StrategyRegistry と DataStore を保持する
- BinanceFeed から配信される pd.DataFrame を受け取る callback を実装する
  (`process_new_data`)
- 各ストラテジーの predict → PredictionSignal 保存 → 風控チェック →
  SimulatedTrade 保存を実行する
- Signal Settler の定期バックグラウンドタスクを管理する

**不可** 以下の操作:
- WebSocket / REST の接続管理 (それは BinanceFeed の責務)
- Polymarket 専用のロジック追加
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, List

import pandas as pd

from btc_predictor.infrastructure.store import DataStore
from btc_predictor.simulation.engine import process_signal
from btc_predictor.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

# Trigger map: timeframe_minutes -> predicate(datetime) -> bool
# A candle at minute M triggers timeframe T when the *next* candle would
# be the first of a new T-minute window.
# e.g. minute 9 triggers 10m because (9+1) % 10 == 0.
TRIGGER_MAP = {
    10: lambda dt: (dt.minute + 1) % 10 == 0,
    30: lambda dt: (dt.minute + 1) % 30 == 0,
    60: lambda dt: (dt.minute + 1) % 60 == 0,
    1440: lambda dt: dt.hour == 23 and dt.minute == 59,
}


class BinanceLivePipeline:
    """Binance live execution and control backbone.

    Consumes OHLCV DataFrames delivered by :class:`~btc_predictor.binance.feed.BinanceFeed`
    and orchestrates the full predict → risk → trade lifecycle for every
    registered strategy.

    Usage::

        feed = BinanceFeed(symbol, store)
        pipeline = BinanceLivePipeline(strategies, store, bot=bot)
        feed.register_callback(pipeline.process_new_data)

        await asyncio.gather(
            feed.start(),
            pipeline.run_settler(client),
        )
    """

    def __init__(
        self,
        strategies: List[BaseStrategy],
        store: DataStore,
        bot: Any = None,
    ) -> None:
        self.strategies = strategies
        self.store = store
        self.bot = bot
        self.trigger_count: int = 0
        # Optional back-reference to the BinanceFeed for forwarding read-only
        # status attributes (is_running, last_kline_time) that the Discord bot's
        # /health command accesses on `bot.pipeline`.
        self._feed: Any = None

    # ------------------------------------------------------------------
    # Feed status forwarding — keeps Discord bot compatibility
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Forward to the attached BinanceFeed's running state."""
        if self._feed is not None:
            return self._feed.is_running
        return False

    @property
    def last_kline_time(self) -> dict:
        """Forward to the attached BinanceFeed's kline timestamps."""
        if self._feed is not None:
            return self._feed._last_kline_time
        return {}

    # ------------------------------------------------------------------
    # Primary callback — invoked by BinanceFeed on every confirmed candle
    # ------------------------------------------------------------------

    async def process_new_data(self, ohlcv: pd.DataFrame) -> None:
        """Receive the latest OHLCV DataFrame and run strategy inference.

        Called by :class:`~btc_predictor.binance.feed.BinanceFeed` every
        time a 1-minute candle is confirmed. Determines which timeframe(s)
        should be triggered based on the timestamp of the latest row, then
        runs predict → signal → trade for each applicable strategy.

        Args:
            ohlcv: Cleaned OHLCV DataFrame (up to 500 rows, ascending).
                   Index is DatetimeTZDtype (UTC).
        """
        if ohlcv.empty:
            return

        # The last row represents the just-confirmed candle.
        latest_dt = ohlcv.index[-1]

        for timeframe, trigger_fn in TRIGGER_MAP.items():
            if trigger_fn(latest_dt):
                await self._trigger_strategies(ohlcv, timeframe)

    # ------------------------------------------------------------------
    # Settler background task
    # ------------------------------------------------------------------

    async def run_settler(self, client: Any, bot: Any = None) -> None:
        """Periodic background task that settles pending trades and signals.

        This coroutine is designed to be run alongside
        :meth:`~btc_predictor.binance.feed.BinanceFeed.start` via
        ``asyncio.gather``.

        Args:
            client: An authenticated :class:`binance.AsyncClient` instance
                    used to fetch closing prices when they are missing from
                    local SQLite.
            bot:    Optional Discord bot for settlement notifications. Falls
                    back to ``self.bot`` when *None* is passed.
        """
        from btc_predictor.binance.settler import settle_pending_trades, settle_pending_signals

        effective_bot = bot if bot is not None else self.bot

        while True:
            try:
                await settle_pending_trades(self.store, client, bot=effective_bot)
                await settle_pending_signals(self.store, client)
            except Exception as e:
                logger.error(f"BinanceLivePipeline settler error: {e}", exc_info=True)
            await asyncio.sleep(60)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _trigger_strategies(self, ohlcv: pd.DataFrame, timeframe: int) -> None:
        """Run predict → signal → trade for every strategy that supports *timeframe*.

        Args:
            ohlcv:     Latest OHLCV DataFrame (already fetched by the feed).
            timeframe: Timeframe in minutes (10 | 30 | 60 | 1440).
        """
        self.trigger_count += 1
        logger.info(f"BinanceLivePipeline: Triggering strategies for {timeframe}m…")

        for strategy in self.strategies:
            if timeframe not in strategy.available_timeframes:
                continue

            try:
                # 1. Prediction (CPU-intensive — offloaded to thread)
                signal = await asyncio.to_thread(strategy.predict, ohlcv, timeframe)

                # 2. Signal Layer: persist ALL signals unconditionally
                signal_id: str | None = None
                try:
                    signal_id = self.store.save_prediction_signal(signal)
                except Exception as e:
                    logger.error(
                        f"BinanceLivePipeline: Signal Layer save error for "
                        f"{strategy.name}: {e}",
                        exc_info=True,
                    )

                # 3. Execution Layer: risk check + SimulatedTrade creation
                trade = await asyncio.to_thread(process_signal, signal, self.store)

                # 4. Link signal to trade when applicable
                if signal_id and trade:
                    try:
                        self.store.update_signal_traded(signal_id, trade.id)
                    except Exception as e:
                        logger.error(
                            f"BinanceLivePipeline: Signal Layer update_traded error: {e}",
                            exc_info=True,
                        )

                # 5. Discord notification
                if trade and self.bot:
                    await self.bot.send_signal(trade)

            except Exception as e:
                logger.error(
                    f"BinanceLivePipeline: Error triggering {strategy.name} for "
                    f"{timeframe}m: {e}",
                    exc_info=True,
                )
