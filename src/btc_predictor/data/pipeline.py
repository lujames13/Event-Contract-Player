import asyncio
import pandas as pd
from datetime import datetime, timezone
from binance import AsyncClient, BinanceSocketManager
from btc_predictor.data.store import DataStore
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.simulation.engine import process_signal
from typing import List, Any

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

    async def start(self):
        self.client = await AsyncClient.create()
        self.bm = BinanceSocketManager(self.client)
        self.is_running = True
        
        # Start kline streams for each interval
        tasks = []
        for interval in self.intervals:
            tasks.append(self._handle_kline_stream(interval))
            
        await asyncio.gather(*tasks)

    async def _handle_kline_stream(self, interval: str):
        async with self.bm.kline_socket(symbol=self.symbol, interval=interval) as stream:
            while self.is_running:
                try:
                    res = await stream.recv()
                    if not res:
                        break
                        
                    kline = res['k']
                    if kline['x']: # 'x' means kline is closed
                        print(f"[{interval}] Kline closed at {datetime.fromtimestamp(kline['t']/1000, tz=timezone.utc)}")
                        
                        # 1. Save to SQLite
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
                        
                        # 2. Trigger strategy prediction for specific timeframes
                        if interval == "1m":
                            current_ts_ms = kline['t']
                            current_dt = datetime.fromtimestamp(current_ts_ms / 1000, tz=timezone.utc)
                            
                            for timeframe in [10, 30, 60, 1440]:
                                if current_dt.minute % timeframe == 0:
                                    await self._trigger_strategies(timeframe)
                except Exception as e:
                    print(f"Error in {interval} stream: {e}")
                    await asyncio.sleep(5)

    async def _trigger_strategies(self, timeframe: int):
        df = self.store.get_ohlcv(self.symbol, "1m", limit=500)
        
        for strategy in self.strategies:
            try:
                # 1. Prediction
                signal = strategy.predict(df, timeframe)
                
                # 2. Simulation Engine (saves to DB, returns trade if allowed)
                trade = process_signal(signal, self.store)
                
                # 3. Discord Notification
                if trade and self.bot:
                    await self.bot.send_signal(trade)
            except Exception as e:
                print(f"Error triggering strategy {strategy.name}: {e}")

    async def stop(self):
        self.is_running = False
        if self.client:
            await self.client.close_connection()
