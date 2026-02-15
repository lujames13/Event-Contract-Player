import pandas as pd
import numpy as np
import uuid
from datetime import timedelta
from typing import List, Optional
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import SimulatedTrade, PredictionSignal
from btc_predictor.simulation.risk import calculate_bet
from btc_predictor.utils.config import load_constants

def run_backtest(
    strategy: BaseStrategy,
    ohlcv: pd.DataFrame,
    timeframe_minutes: int,
    train_days: int = 60,
    test_days: int = 7,
    step_days: Optional[int] = None
) -> List[SimulatedTrade]:
    """
    Run a walk-forward backtest.
    
    Args:
        strategy: The strategy to test.
        ohlcv: Full OHLCV data (e.g. 1m interval).
        timeframe_minutes: The contract timeframe.
        train_days: Initial training window size.
        test_days: Testing window size.
        step_days: How many days to step forward. Defaults to test_days.
    """
    if step_days is None:
        step_days = test_days
        
    constants = load_constants()
    payout_ratios = constants.get("event_contract", {}).get("payout_ratio", {})
    payout_ratio = payout_ratios.get(timeframe_minutes, 1.85)
    
    trades = []
    
    # Start time of the first test window
    start_time = ohlcv.index[0] + timedelta(days=train_days)
    end_time = ohlcv.index[-1]
    
    current_test_start = start_time
    
    while current_test_start < end_time:
        current_test_end = current_test_start + timedelta(days=test_days)
        if current_test_end > end_time:
            current_test_end = end_time
            
        # 1. Prepare training data (sliding window of train_days)
        train_start = current_test_start - timedelta(days=train_days)
        train_data = ohlcv[(ohlcv.index >= train_start) & (ohlcv.index < current_test_start)]
        
        # 2. Fit strategy if needed
        if strategy.requires_fitting:
            print(f"[{strategy.name}] Fitting on data before {current_test_start}...")
            strategy.fit(train_data, timeframe_minutes)
            
        # 3. Predict on test data
        test_data_window = ohlcv[(ohlcv.index >= current_test_start) & (ohlcv.index < current_test_end)]
        
        # We simulate non-overlapping trades by stepping by timeframe_minutes.
        test_timestamps = test_data_window.index[::timeframe_minutes]
        
        for i, ts in enumerate(test_timestamps):
            if i % 10 == 0:
                print(".", end="", flush=True)
            # Optimization: Slice only recent history (e.g. 7 days) to avoid copying full DataFrame
            # Boolean indexing or full slicing is O(N) copy.
            lookback_start = ts - timedelta(days=7)
            data_up_to_ts = ohlcv.loc[lookback_start:ts]
            
            signal = strategy.predict(data_up_to_ts, timeframe_minutes)
            
            # 4. Risk check & Bet calculation
            bet = calculate_bet(signal.confidence, timeframe_minutes)
            
            if bet > 0:
                # 5. Create trade record
                expiry_time = ts + timedelta(minutes=timeframe_minutes)
                
                # Look up settlement price
                if expiry_time in ohlcv.index:
                    close_price = float(ohlcv.loc[expiry_time, 'close'])
                    open_price = float(ohlcv.loc[ts, 'close'])
                    
                    # Result logic: higher wins if close > open
                    if signal.direction == "higher":
                        is_win = close_price > open_price      # 嚴格大於才算贏
                    else:
                        is_win = close_price < open_price      # 嚴格小於才算贏
                        
                    result = "win" if is_win else "lose"
                    pnl = bet * (payout_ratio - 1) if is_win else -bet
                    
                    trade = SimulatedTrade(
                        id=str(uuid.uuid4()),
                        strategy_name=strategy.name,
                        direction=signal.direction,
                        confidence=signal.confidence,
                        timeframe_minutes=timeframe_minutes, # type: ignore
                        bet_amount=float(bet),
                        open_time=ts,
                        open_price=open_price,
                        expiry_time=expiry_time,
                        close_price=close_price,
                        result=result, # type: ignore
                        pnl=float(pnl)
                    )
                    trades.append(trade)
                else:
                    # Expiry time beyond data range, ignore
                    pass
        
        # Move to next window
        current_test_start += timedelta(days=step_days)
        
    return trades
