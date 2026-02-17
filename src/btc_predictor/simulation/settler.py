import time
import pandas as pd
import asyncio
import logging
from datetime import datetime, timezone
from btc_predictor.data.store import DataStore
from btc_predictor.utils.config import load_constants
from btc_predictor.models import SimulatedTrade
from typing import Any

logger = logging.getLogger(__name__)

async def settle_pending_trades(store: DataStore, client=None, bot: Any = None):
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
        try:
            expiry_str = row['expiry_time']
            expiry_dt = datetime.fromisoformat(expiry_str)
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                
            if now < expiry_dt:
                continue
                
            logger.info(f"Settling trade {row['id']} (expiry: {expiry_str})...")
            
            expiry_ms = int(expiry_dt.timestamp() * 1000)
            
            # 1. Try SQLite first
            # We look for a 1m candle starting at the exactly expiry minute
            df_price = store.get_ohlcv("BTCUSDT", "1m", start_time=expiry_ms, end_time=expiry_ms)
            
            close_price = None
            if not df_price.empty:
                close_price = float(df_price['close'].iloc[0])
                logger.debug(f"Found price in SQLite for trade {row['id']}")
                
            # 2. Try Binance REST API if not in SQLite
            if close_price is None and client:
                try:
                    # Determine if client is async or needs to_thread
                    if hasattr(client, 'get_klines') and asyncio.iscoroutinefunction(client.get_klines):
                        klines = await client.get_klines(
                            symbol="BTCUSDT",
                            interval="1m",
                            startTime=expiry_ms,
                            limit=1
                        )
                    else:
                        # Fallback for sync client
                        klines = await asyncio.to_thread(
                            client.get_klines,
                            symbol="BTCUSDT",
                            interval="1m",
                            startTime=expiry_ms,
                            limit=1
                        )
                    
                    if klines:
                        # kline format: [startTime, open, high, low, close, volume, closeTime, ...]
                        close_price = float(klines[0][4])
                        logger.info(f"Retrieved price from Binance REST API for trade {row['id']}: {close_price}")
                except Exception as e:
                    logger.error(f"Error fetching price from Binance for trade {row['id']}: {e}")
                    
            if close_price is not None:
                open_price = float(row['open_price'])
                direction = row['direction']
                
                if direction == "higher":
                    is_win = close_price > open_price   # 嚴格大於
                else:
                    is_win = close_price < open_price   # 嚴格小於
                    
                result = "win" if is_win else "lose"
                
                timeframe_minutes = int(row['timeframe_minutes'])
                payout_ratio = payout_ratios.get(timeframe_minutes, 1.85)
                bet = float(row['bet_amount'])
                pnl = bet * (payout_ratio - 1) if is_win else -bet
                
                store.update_simulated_trade(row['id'], close_price, result, float(pnl))
                logger.info(f"Trade {row['id']} settled: {result} | PnL: {pnl:.4f}")
                
                # Discord Notification
                if bot:
                    trade_obj = SimulatedTrade(
                        id=row['id'],
                        strategy_name=row['strategy_name'],
                        direction=row['direction'],
                        confidence=row['confidence'],
                        timeframe_minutes=timeframe_minutes,
                        bet_amount=bet,
                        open_time=datetime.fromisoformat(row['open_time']),
                        open_price=open_price,
                        expiry_time=expiry_dt,
                        close_price=close_price,
                        result=result,
                        pnl=float(pnl)
                    )
                    try:
                        await bot.send_settlement(trade_obj)
                    except Exception as e:
                        logger.error(f"Error sending Discord notification for {row['id']}: {e}")
            else:
                logger.warning(f"Could not find price for {row['id']} at {expiry_str}. Will retry.")
        except Exception as e:
            logger.error(f"Unexpected error settling trade {row['id']}: {e}", exc_info=True)
