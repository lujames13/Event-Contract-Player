import asyncio
import pandas as pd
import logging
from datetime import datetime, timezone, timedelta
from binance import AsyncClient, BinanceSocketManager
from btc_predictor.data.store import DataStore
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.simulation.engine import process_signal
from typing import List, Any

logger = logging.getLogger(__name__)

class DataPipeline:
    def __init__(self, symbol: str, intervals: List[str], strategies: List[BaseStrategy], store: DataStore, bot: Any = None):
        self.symbol = symbol
        self.intervals = intervals
        self.strategies = strategies
        self.store = store
        self.bot = bot
        self.client = None
        self.bm = None
        self.is_running = False
        self.last_kline_time = {} # interval -> datetime

    async def start(self):
        self.is_running = True
        
        # 1. Backfill historical data on startup
        try:
            await self._backfill_historical_data()
        except Exception as e:
            logger.error(f"Startup backfill error: {e}")
        
        # 2. Start health check task
        asyncio.create_task(self._health_check())
        
        # 3. Start kline streams with reconnection logic
        reconnect_delay = 5
        while self.is_running:
            try:
                self.client = await AsyncClient.create()
                self.bm = BinanceSocketManager(self.client)
                
                tasks = []
                for interval in self.intervals:
                    tasks.append(self._handle_kline_stream(interval))
                
                logger.info(f"Connecting to WebSocket streams for {self.symbol}...")
                reconnect_delay = 5 # Reset delay on successful connection
                await asyncio.gather(*tasks)
            except Exception as e:
                if not self.is_running:
                    break
                logger.error(f"WebSocket connection error: {e}. Reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 300)
            finally:
                if self.client:
                    await self.client.close_connection()

    async def _backfill_historical_data(self):
        """啟動時回填最近缺失的 K 線"""
        logger.info("Checking for missing historical data...")
        # Check latest 1m ohlcv in store
        latest_df = self.store.get_latest_ohlcv(self.symbol, "1m", limit=1)
        
        start_ts_ms = None
        now_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        if not latest_df.empty:
            latest_ts_ms = int(latest_df.index[0].timestamp() * 1000)
            # If latest is more than 5 mins ago, backfill
            if now_ts_ms - latest_ts_ms > 300000:
                start_ts_ms = latest_ts_ms + 60000 # Start from next minute
        else:
            # If no data at all, fetch last 100 minutes
            start_ts_ms = now_ts_ms - (100 * 60 * 1000)
            
        if start_ts_ms:
            logger.info(f"Backfilling data since {datetime.fromtimestamp(start_ts_ms/1000, tz=timezone.utc)}")
            temp_client = await AsyncClient.create()
            try:
                klines = await temp_client.get_historical_klines(
                    self.symbol, "1m", start_str=start_ts_ms
                )
                if klines:
                    # kline format: [startTime, open, high, low, close, volume, closeTime, ...]
                    df = pd.DataFrame(klines, columns=[
                        "open_time", "open", "high", "low", "close", "volume", 
                        "close_time", "quote_volume", "count", "taker_buy_base", 
                        "taker_buy_quote", "ignore"
                    ])
                    # Keep only required columns
                    df = df[["open_time", "open", "high", "low", "close", "volume", "close_time"]]
                    # Convert to numeric
                    for col in ["open", "high", "low", "close", "volume"]:
                        df[col] = pd.to_numeric(df[col])
                    
                    self.store.save_ohlcv(df, self.symbol, "1m")
                    logger.info(f"Successfully backfilled {len(df)} 1m K-lines.")
            except Exception as e:
                logger.error(f"Failed to backfill historical data: {e}")
            finally:
                await temp_client.close_connection()

    async def _health_check(self):
        """心跳監控：如果超過 3 分鐘沒收到資料，主動重連"""
        while self.is_running:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            for interval, last_time in list(self.last_kline_time.items()):
                if now - last_time > timedelta(minutes=3):
                    logger.warning(f"No data received for {interval} in last 3 minutes. Triggering reconnection...")
                    if self.client:
                        # This should break the current streams and trigger reconnection in start()
                        await self.client.close_connection()

    async def _handle_kline_stream(self, interval: str):
        self.last_kline_time[interval] = datetime.now(timezone.utc)
        
        async with self.bm.kline_socket(symbol=self.symbol, interval=interval) as stream:
            while self.is_running:
                try:
                    res = await stream.recv()
                    if not res:
                        break
                        
                    self.last_kline_time[interval] = datetime.now(timezone.utc)
                    
                    kline = res['k']
                    if kline['x']: # 'x' means kline is closed
                        logger.info(f"[{interval}] Kline closed at {datetime.fromtimestamp(kline['t']/1000, tz=timezone.utc)}")
                        
                        df_row = pd.DataFrame([{
                            "open_time": kline['t'],
                            "open": float(kline['o']),
                            "high": float(kline['h']),
                            "low": float(kline['l']),
                            "close": float(kline['c']),
                            "volume": float(kline['v']),
                            "close_time": kline['T']
                        }])
                        self.store.save_ohlcv(df_row, self.symbol, interval)
                        
                        if interval == "1m":
                            current_ts_ms = kline['t']
                            current_dt = datetime.fromtimestamp(current_ts_ms / 1000, tz=timezone.utc)
                            
                            # Explicit trigger map for each timeframe
                            TRIGGER_MAP = {
                                10: lambda dt: dt.minute % 10 == 0,
                                30: lambda dt: dt.minute % 30 == 0,
                                60: lambda dt: dt.minute == 0,
                                1440: lambda dt: dt.hour == 0 and dt.minute == 0,
                            }
                            
                            for timeframe, trigger_fn in TRIGGER_MAP.items():
                                if trigger_fn(current_dt):
                                    await self._trigger_strategies(timeframe)
                except Exception as e:
                    if not self.is_running:
                        break
                    logger.error(f"Error in {interval} stream: {e}")
                    raise # Rethrow to break gather and trigger reconnection

    async def _trigger_strategies(self, timeframe: int):
        df = self.store.get_ohlcv(self.symbol, "1m", limit=500)
        
        for strategy in self.strategies:
            # Only trigger if the strategy supports this timeframe
            if timeframe not in strategy.available_timeframes:
                continue
                
            try:
                # 1. Prediction
                signal = strategy.predict(df, timeframe)
                
                # 2. Simulation Engine (saves to DB, returns trade if allowed)
                trade = process_signal(signal, self.store)
                
                # 3. Discord Notification
                if trade and self.bot:
                    await self.bot.send_signal(trade)
            except Exception as e:
                logger.error(f"Error triggering strategy {strategy.name} for {timeframe}m: {e}")

    async def stop(self):
        self.is_running = False
        if self.client:
            await self.client.close_connection()
