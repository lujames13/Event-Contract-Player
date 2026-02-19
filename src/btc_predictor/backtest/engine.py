import pandas as pd
import numpy as np
import uuid
import copy
from datetime import timedelta
from typing import List, Optional, Tuple
from joblib import Parallel, delayed
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import SimulatedTrade, PredictionSignal
from btc_predictor.simulation.risk import calculate_bet
from btc_predictor.utils.config import load_constants

def _process_fold(
    fold_start: pd.Timestamp,
    fold_end: pd.Timestamp,
    train_days: int,
    ohlcv: pd.DataFrame,
    strategy: BaseStrategy,
    timeframe_minutes: int,
    payout_ratio: float
) -> List[SimulatedTrade]:
    """Process a single walk-forward fold."""
    # Create a local copy of the strategy to avoid state sharing
    local_strategy = copy.deepcopy(strategy)
    
    # 1. Prepare data for this fold (train + test)
    # Ensure we include enough lookback for features (e.g. 14 days for safety)
    train_start = fold_start - timedelta(days=train_days)
    # Add a safety margin for indicators that might need historical data beyond train_days
    # For now, we take from train_start to fold_end (which is non-inclusive in testing)
    fold_data = ohlcv[(ohlcv.index >= train_start) & (ohlcv.index <= fold_end)].copy()
    
    # 2. Fit strategy if needed
    if local_strategy.requires_fitting:
        train_data = fold_data[fold_data.index < fold_start]
        local_strategy.fit(train_data, timeframe_minutes)
        
    # 3. Predict on test data
    # test_data_window excludes the fold_end (as predictions are for periods finishing AT or BEFORE fold_end)
    test_data_window = fold_data[(fold_data.index >= fold_start) & (fold_data.index < fold_end)]
    
    # We simulate non-overlapping trades by stepping by timeframe_minutes.
    test_timestamps = test_data_window.index[::timeframe_minutes]
    
    fold_trades = []
    for ts in test_timestamps:
        # Each prediction uses data up to current timestamp
        # Since fold_data is local and small, this is fast and thread-safe.
        data_up_to_ts = fold_data.loc[:ts]
        
        signal = local_strategy.predict(data_up_to_ts, timeframe_minutes)
        
        # 4. Risk check & Bet calculation
        bet = calculate_bet(signal.confidence, timeframe_minutes)
        
        if bet > 0:
            # 5. Create trade record
            expiry_time = ts + timedelta(minutes=timeframe_minutes)
            
            # Look up settlement price in fold_data
            if expiry_time in fold_data.index:
                close_price = float(fold_data.loc[expiry_time, 'close'])
                open_price = float(fold_data.loc[ts, 'close'])
                
                # Result logic: higher wins if close > open
                if signal.direction == "higher":
                    is_win = close_price > open_price
                else:
                    is_win = close_price < open_price
                    
                result = "win" if is_win else "lose"
                pnl = bet * (payout_ratio - 1) if is_win else -bet
                
                trade = SimulatedTrade(
                    id=str(uuid.uuid4()),
                    strategy_name=local_strategy.name,
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
                fold_trades.append(trade)
    
    return fold_trades

def run_backtest(
    strategy: BaseStrategy,
    ohlcv: pd.DataFrame,
    timeframe_minutes: int,
    train_days: int = 60,
    test_days: int = 7,
    step_days: Optional[int] = None,
    n_jobs: int = -2 # Use all but one core by default
) -> List[SimulatedTrade]:
    """
    Run a walk-forward backtest using parallel processing for folds.
    
    Args:
        strategy: The strategy to test.
        ohlcv: Full OHLCV data.
        timeframe_minutes: The contract timeframe.
        train_days: Initial training window size.
        test_days: Testing window size.
        step_days: How many days to step forward.
        n_jobs: Number of parallel jobs (-1: all, -2: all but one).
    """
    if step_days is None:
        step_days = test_days
        
    constants = load_constants()
    payout_ratios = constants.get("event_contract", {}).get("payout_ratio", {})
    payout_ratio = payout_ratios.get(timeframe_minutes, 1.85)
    
    # 1. Start time of the first test window
    start_time = ohlcv.index[0] + timedelta(days=train_days)
    end_time = ohlcv.index[-1]
    
    # 2. Generate all folds first
    folds = []
    current_test_start = start_time
    while current_test_start < end_time:
        current_test_end = current_test_start + timedelta(days=test_days)
        if current_test_end > end_time:
            current_test_end = end_time
            
        folds.append((current_test_start, current_test_end))
        current_test_start += timedelta(days=step_days)

    print(f"[{strategy.name}] Starting parallel walk-forward backtest ({len(folds)} folds, n_jobs={n_jobs})...")
    
    # 3. Parallelize over folds
    results = Parallel(n_jobs=n_jobs, backend="threading")(
        delayed(_process_fold)(
            f_start, f_end, train_days, ohlcv, strategy, timeframe_minutes, payout_ratio
        ) for f_start, f_end in folds
    )
    
    # 4. Flatten the list of lists of trades
    trades = [trade for sublist in results for trade in sublist]
    
    return trades
