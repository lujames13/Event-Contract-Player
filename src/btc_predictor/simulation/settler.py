import pandas as pd
import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from btc_predictor.infrastructure.store import DataStore
from btc_predictor.utils.config import load_constants
from btc_predictor.models import SimulatedTrade
from typing import Any

logger = logging.getLogger(__name__)

async def _get_close_price(store: DataStore, expiry_ms: int, client=None) -> Any:
    """Helper to fetch 1m close price from SQLite or Binance API."""
    # 1. Try SQLite first
    df_price = await asyncio.to_thread(
        store.get_ohlcv, "BTCUSDT", "1m", start_time=expiry_ms, end_time=expiry_ms
    )
    
    if not df_price.empty:
        return float(df_price['close'].iloc[0])
        
    # 2. Try Binance REST API if not in SQLite
    if client:
        try:
            if hasattr(client, 'get_klines') and asyncio.iscoroutinefunction(client.get_klines):
                klines = await client.get_klines(
                    symbol="BTCUSDT", interval="1m", startTime=expiry_ms, limit=1
                )
            else:
                klines = await asyncio.to_thread(
                    client.get_klines, symbol="BTCUSDT", interval="1m", startTime=expiry_ms, limit=1
                )
            
            if klines:
                return float(klines[0][4])
        except Exception as e:
            logger.error(f"Error fetching price from Binance for {expiry_ms}: {e}")
            
    return None

async def settle_pending_trades(store: DataStore, client=None, bot: Any = None):
    """
    Check for pending trades and settle them if expiry time has passed.
    """
    pending = await asyncio.to_thread(store.get_pending_trades)
    if pending.empty:
        return
        
    constants = await asyncio.to_thread(load_constants)
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
            close_price = await _get_close_price(store, expiry_ms, client)
                    
            if close_price is not None:
                open_price = float(row['open_price'])
                direction = row['direction']
                
                if direction == "higher":
                    is_win = close_price > open_price
                else:
                    is_win = close_price < open_price
                    
                result = "win" if is_win else "lose"
                
                timeframe_minutes = int(row['timeframe_minutes'])
                payout_ratio = payout_ratios.get(timeframe_minutes, 1.85)
                bet = float(row['bet_amount'])
                pnl = bet * (payout_ratio - 1) if is_win else -bet
                
                await asyncio.to_thread(
                    store.update_simulated_trade, row['id'], close_price, result, float(pnl)
                )
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
                        pnl=float(pnl),
                        features_used=json.loads(row['features_used']) if row['features_used'] else {}
                    )
                    try:
                        await bot.send_settlement(trade_obj)
                    except Exception as e:
                        logger.error(f"Error sending Discord notification for {row['id']}: {e}")
            else:
                logger.warning(f"Could not find price for {row['id']} at {expiry_str}. Will retry.")
        except Exception as e:
            logger.error(f"Unexpected error settling trade {row['id']}: {e}", exc_info=True)

async def settle_pending_signals(store: DataStore, client=None, max_age_hours: int = 24) -> int:
    """
    結算所有已到期但未結算的 prediction signals。
    """
    pending = await asyncio.to_thread(store.get_unsettled_signals)
    if pending.empty:
        return 0
        
    now = datetime.now(timezone.utc)
    max_age_dt = now - timedelta(hours=max_age_hours)
    count = 0
    
    for _, row in pending.iterrows():
        try:
            expiry_str = row['expiry_time']
            expiry_dt = datetime.fromisoformat(expiry_str)
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                
            if now < expiry_dt:
                continue
                
            if expiry_dt < max_age_dt:
                continue

            expiry_ms = int(expiry_dt.timestamp() * 1000)
            close_price = await _get_close_price(store, expiry_ms, client)
            
            if close_price is not None:
                open_price = float(row['current_price'])
                direction = row['direction']
                
                # Determine actual_direction
                if close_price > open_price:
                    actual_direction = 'higher'
                elif close_price < open_price:
                    actual_direction = 'lower'
                else:
                    actual_direction = 'draw'
                
                # Determine if correct
                # 平盤算錯，與 simulated_trades 一致
                is_correct = (direction == actual_direction)
                
                await asyncio.to_thread(
                    store.settle_signal, row['id'], actual_direction, close_price, is_correct
                )
                count += 1
                logger.debug(f"Signal {row['id']} settled: actual={actual_direction}, correct={is_correct}")
        except Exception as e:
            logger.error(f"Error settling signal {row['id']}: {e}")
            
    if count > 0:
        logger.info(f"Settled {count} prediction signals.")
    return count
