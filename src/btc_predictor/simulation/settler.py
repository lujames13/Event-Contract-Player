import time
import pandas as pd
import asyncio
from datetime import datetime, timezone
from btc_predictor.data.store import DataStore
from btc_predictor.utils.config import load_constants
from typing import Any

def settle_pending_trades(store: DataStore, client=None, bot: Any = None):
    """
    Check for pending trades and settle them if expiry time has passed.
    """
    pending = store.get_pending_trades()
    if pending.empty:
        return
        
    constants = load_constants()
    payout_ratios = constants.get("event_contract", {}).get("payout_ratio", {})
    
    now = datetime.now(timezone.utc)
    
    for _, row in pending.iterrows():
        expiry_dt = datetime.fromisoformat(row['expiry_time'])
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
            
        if now < expiry_dt:
            continue
            
        print(f"Settling trade {row['id']} (expiry: {row['expiry_time']})...")
        
        expiry_ms = int(expiry_dt.timestamp() * 1000)
        df_price = store.get_ohlcv("BTCUSDT", "1m", start_time=expiry_ms, end_time=expiry_ms)
        
        close_price = None
        if not df_price.empty:
            close_price = float(df_price['close'].iloc[0])
        elif client:
            try:
                klines = client.get_historical_klines(
                    "BTCUSDT", 
                    "1m", 
                    start_str=expiry_ms - 1000, 
                    end_str=expiry_ms + 1000
                )
                if klines:
                    close_price = float(klines[0][4])
            except Exception as e:
                print(f"Error fetching price from Binance: {e}")
                
        if close_price is not None:
            open_price = float(row['open_price'])
            direction = row['direction']
            
            if direction == "higher":
                is_win = close_price > open_price
            else:
                is_win = close_price <= open_price
                
            result = "win" if is_win else "lose"
            
            payout_ratio = payout_ratios.get(int(row['timeframe_minutes']), 1.85)
            bet = float(row['bet_amount'])
            pnl = bet * (payout_ratio - 1) if is_win else -bet
            
            store.update_simulated_trade(row['id'], close_price, result, float(pnl))
            print(f"Trade {row['id']} settled: {result} | PnL: {pnl}")
            
            # Discord Notification
            if bot:
                # Need to reconstruct a dummy trade object for the bot's send_settlement
                from dataclasses import dataclass
                @dataclass
                class DummyTrade:
                    strategy_name: str
                    timeframe_minutes: int
                    direction: str
                    open_price: float
                    close_price: float
                    result: str
                    pnl: float
                
                dt = DummyTrade(
                    strategy_name=row['strategy_name'],
                    timeframe_minutes=row['timeframe_minutes'],
                    direction=row['direction'],
                    open_price=open_price,
                    close_price=close_price,
                    result=result,
                    pnl=float(pnl)
                )
                # Since notify is async, we need to handle it.
                # In a sync function, we can use create_task if in loop.
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(bot.send_settlement(dt))
                except Exception as e:
                    print(f"Error sending Discord notification: {e}")
        else:
            print(f"Could not find price for {row['id']} at {row['expiry_time']}. Will retry.")
