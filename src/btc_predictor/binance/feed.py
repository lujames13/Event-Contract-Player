"""
btc_predictor/binance/feed.py
-----------------------------
BinanceFeed: Pure data source (DataPipeline の WebSocket 部分を抽出).

職責:
- Binance WebSocket 接続と指数退避再接続
- 起動時の REST API 歴史データ補填
- 1m K 線確定時にすべての登録済み callback に pd.DataFrame を配信
- 複数の subscriber をサポート (callback list)。Polymarket 系が将来 subscribe 可能。

**不可** 以下の操作:
- Strategy predict の呼び出し
- DataStore への PredictionSignal / SimulatedTrade の保存
- Discord 通知
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Awaitable, Callable, List

import pandas as pd
from binance import AsyncClient, BinanceSocketManager

logger = logging.getLogger(__name__)

# Type alias for callback: receives a pd.DataFrame and returns an awaitable.
DataCallback = Callable[[pd.DataFrame], Awaitable[None]]


class BinanceFeed:
    """Pure Binance WebSocket data source.

    Fetches 1-minute OHLCV K-lines from Binance and delivers confirmed
    (closed) candles to all registered callbacks as a pd.DataFrame.

    Supports multiple subscribers via :meth:`register_callback` so that
    both the Binance execution pipeline and (future) Polymarket pipelines
    can consume the same feed independently.
    """

    def __init__(
        self,
        symbol: str,
        store,  # DataStore — injected to read/write OHLCV, kept as Any to avoid circular import
    ) -> None:
        self.symbol = symbol
        self.store = store
        self._callbacks: List[DataCallback] = []
        self._client: AsyncClient | None = None
        self._bm: BinanceSocketManager | None = None
        self.is_running: bool = False
        # interval -> last received datetime
        self._last_kline_time: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_callback(self, callback: DataCallback) -> None:
        """Register an async callback to be called on each confirmed K-line.

        The callback will receive the latest OHLCV DataFrame (up to 500
        1-minute candles, ascending order).  Multiple callbacks are
        supported; calling order is registration order.

        Args:
            callback: ``async def func(ohlcv: pd.DataFrame) -> None``
        """
        self._callbacks.append(callback)
        logger.debug(f"BinanceFeed: registered callback {callback!r} (total: {len(self._callbacks)})")

    async def start(self) -> None:
        """Start the feed: backfill → health checker → WebSocket loop."""
        self.is_running = True

        # 1. Backfill historical data
        try:
            await self._backfill_historical_data()
        except Exception as e:
            logger.error(f"BinanceFeed startup backfill error: {e}", exc_info=True)

        # 2. Background health-check task
        asyncio.create_task(self._health_check())

        # 3. WebSocket loop with exponential backoff reconnection
        reconnect_delay = 5
        while self.is_running:
            try:
                self._client = await AsyncClient.create()
                self._bm = BinanceSocketManager(self._client)

                logger.info(f"BinanceFeed: Connecting WebSocket for {self.symbol}…")
                reconnect_delay = 5  # reset on successful connection
                await self._handle_kline_stream("1m")
            except Exception as e:
                if not self.is_running:
                    break
                logger.error(
                    f"BinanceFeed WebSocket error: {e}. Reconnecting in {reconnect_delay}s…",
                    exc_info=True,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 300)
            finally:
                if self._client:
                    try:
                        await self._client.close_connection()
                    except Exception:
                        pass

    async def stop(self) -> None:
        """Signal the feed to stop and close the WebSocket client."""
        self.is_running = False
        if self._client:
            try:
                await self._client.close_connection()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _backfill_historical_data(self) -> None:
        """Fill any gap between the last stored candle and now via REST API."""
        logger.info("BinanceFeed: Checking for missing historical data…")
        latest_df = await asyncio.to_thread(
            self.store.get_latest_ohlcv, self.symbol, "1m", limit=1
        )

        now_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ts_ms: int | None = None

        if not latest_df.empty:
            latest_ts_ms = int(latest_df.index[0].timestamp() * 1000)
            # If latest candle is more than 5 minutes old, backfill the gap.
            if now_ts_ms - latest_ts_ms > 300_000:
                start_ts_ms = latest_ts_ms + 60_000  # start from the next minute
        else:
            # No local data at all — seed with last 100 minutes.
            start_ts_ms = now_ts_ms - (100 * 60 * 1_000)

        if start_ts_ms is None:
            logger.info("BinanceFeed: Historical data is up-to-date, no backfill needed.")
            return

        logger.info(
            f"BinanceFeed: Backfilling data since "
            f"{datetime.fromtimestamp(start_ts_ms / 1000, tz=timezone.utc)}"
        )
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        temp_client = await AsyncClient.create(api_key, api_secret)
        try:
            klines = await temp_client.get_historical_klines(
                self.symbol, "1m", start_str=start_ts_ms
            )
            if klines:
                logger.info(f"BinanceFeed: Fetched {len(klines)} historical klines. Saving…")
                df = pd.DataFrame(
                    klines,
                    columns=[
                        "open_time", "open", "high", "low", "close", "volume",
                        "close_time", "quote_volume", "count",
                        "taker_buy_base", "taker_buy_quote", "ignore",
                    ],
                )
                df = df[["open_time", "open", "high", "low", "close", "volume", "close_time"]]
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col])
                await asyncio.to_thread(self.store.save_ohlcv, df, self.symbol, "1m")
                logger.info(f"BinanceFeed: Successfully backfilled {len(df)} 1m candles.")
            else:
                logger.info("BinanceFeed: No missing historical data to backfill.")
        except Exception as e:
            logger.error(f"BinanceFeed: Failed to backfill historical data: {e}", exc_info=True)
        finally:
            await temp_client.close_connection()

    async def _health_check(self) -> None:
        """Heartbeat monitor: force reconnect if no data received for > 3 minutes."""
        while self.is_running:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            for interval, last_time in list(self._last_kline_time.items()):
                if now - last_time > timedelta(minutes=3):
                    logger.warning(
                        f"BinanceFeed: No {interval} data for >3 min. Forcing reconnect…"
                    )
                    if self._client:
                        try:
                            await self._client.close_connection()
                        except Exception:
                            pass

    async def _handle_kline_stream(self, interval: str) -> None:
        """Listen to the kline WebSocket stream and deliver confirmed candles."""
        self._last_kline_time[interval] = datetime.now(timezone.utc)

        async with self._bm.kline_socket(symbol=self.symbol, interval=interval) as stream:
            while self.is_running:
                try:
                    res = await stream.recv()
                    if not res:
                        break

                    self._last_kline_time[interval] = datetime.now(timezone.utc)
                    kline = res["k"]

                    if kline["x"]:  # confirmed (closed) candle
                        closed_at = datetime.fromtimestamp(
                            kline["t"] / 1000, tz=timezone.utc
                        )
                        logger.info(
                            f"BinanceFeed: [{interval}] Kline closed at {closed_at}"
                        )

                        # Persist the new candle
                        df_row = pd.DataFrame(
                            [
                                {
                                    "open_time": kline["t"],
                                    "open": float(kline["o"]),
                                    "high": float(kline["h"]),
                                    "low": float(kline["l"]),
                                    "close": float(kline["c"]),
                                    "volume": float(kline["v"]),
                                    "close_time": kline["T"],
                                }
                            ]
                        )
                        await asyncio.to_thread(
                            self.store.save_ohlcv, df_row, self.symbol, interval
                        )

                        # Fetch full OHLCV window and deliver to subscribers
                        ohlcv_df = await asyncio.to_thread(
                            self.store.get_latest_ohlcv, self.symbol, "1m", limit=500
                        )
                        await self._dispatch(ohlcv_df)

                except Exception as e:
                    if not self.is_running:
                        break
                    logger.error(f"BinanceFeed: Error in {interval} stream: {e}", exc_info=True)
                    raise  # re-raise to break gather and trigger reconnection

    async def _dispatch(self, ohlcv: pd.DataFrame) -> None:
        """Call every registered callback with the latest OHLCV DataFrame."""
        for callback in self._callbacks:
            try:
                await callback(ohlcv)
            except Exception as e:
                logger.error(
                    f"BinanceFeed: Error in callback {callback!r}: {e}", exc_info=True
                )
