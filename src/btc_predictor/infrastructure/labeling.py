import pandas as pd
import numpy as np
from typing import Optional

def add_direction_labels(
    df: pd.DataFrame, 
    timeframe_minutes: int,
    price_col: str = "close",
    settlement_condition: str = ">"
) -> pd.DataFrame:
    """
    Add direction labels for prediction.
    
    The label for timestamp 't' represents the price direction at 't + timeframe_minutes'.
    label = 1 (Higher) if price(t + timeframe_minutes) > price(t)
    label = 0 (Lower) if price(t + timeframe_minutes) <= price(t)
    
    Note: In Event Contracts, if the price is exactly the same, it's usually 
    considered a loss for both 'higher' and 'lower' bettors (depending on the 
    specific contract, but usually 'higher' means strictly higher). 
    According to PROGRESS.md, close_price == open_price is treated as 0 (lower/lose).
    
    Args:
        df: DataFrame with datetime index and price column.
            The index should be sorted and have a fixed frequency (e.g., 1m).
        timeframe_minutes: The prediction horizon in minutes.
        price_col: The column name to use for price comparison (default: "close").
        
    Returns:
        DataFrame with an additional 'label' column.
        Rows where the future price is not available will have NaN labels.
    """
    if df.empty:
        return df.copy()

    # Calculate frequency of the index in minutes
    # We assume the index is already pd.DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a pd.DatetimeIndex")
    
    # Calculate how many rows correspond to timeframe_minutes
    # For a 1m frequency, 10 minutes = 10 rows.
    # To be robust, we calculate the median difference between index timestamps.
    diffs = df.index.to_series().diff().dropna()
    if diffs.empty:
        # Only one row, can't determine frequency
        df_labeled = df.copy()
        df_labeled["label"] = np.nan
        return df_labeled

    # Use timestamp-based lookup to handle potential gaps in data
    # Calculate expiry_time for each row
    expiry_times = df.index + pd.Timedelta(minutes=timeframe_minutes)
    
    # Reindex to find prices at expiry_times
    # We only want to find prices that actually exist in the original index
    future_prices = df[price_col].reindex(expiry_times)
    future_prices.index = df.index # Reset index to match original df
    
    df_labeled = df.copy()
    
    # label = 1 if future_price > current_price (or >= depending on settlement_condition)
    # Note: We use .values for comparison to avoid index matching issues if any
    if settlement_condition == ">=":
        condition = (future_prices >= df_labeled[price_col])
    else:
        condition = (future_prices > df_labeled[price_col])
    df_labeled["label"] = condition.astype(float)
    
    # Mark rows where future_price is NaN as NaN label
    # This happens if expiry_time is not in the index (gap or end of data)
    df_labeled.loc[future_prices.isna(), "label"] = np.nan
    
    return df_labeled

def calculate_single_label(
    df: pd.DataFrame,
    open_time: pd.Timestamp,
    timeframe_minutes: int,
    price_col: str = "close",
    settlement_condition: str = ">"
) -> Optional[int]:
    """
    Calculate label for a specific open_time and timeframe.
    Used for evaluation or single signal checks.
    """
    if open_time not in df.index:
        return None
        
    expiry_time = open_time + pd.Timedelta(minutes=timeframe_minutes)
    
    if expiry_time not in df.index:
        return None
        
    open_price = df.loc[open_time, price_col]
    close_price = df.loc[expiry_time, price_col]
    
    if settlement_condition == ">=":
        return 1 if close_price >= open_price else 0
    else:
        return 1 if close_price > open_price else 0
