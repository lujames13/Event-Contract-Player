import pandas as pd
import numpy as np
from typing import Tuple, List

def generate_window_features(df: pd.DataFrame, window_size: int = 30) -> Tuple[np.ndarray, pd.DatetimeIndex]:
    """
    Generate normalized raw window input for CNN/LSTM from OHLCV data.
    Feature Set B for PM baseline models.
    
    Args:
        df: DataFrame with datetime index and columns: open, high, low, close, volume.
            Index must be monotonic increasing.
        window_size: Length of the raw window.
        
    Returns:
        X: numpy array of shape (num_samples, window_size, 5) containing normalized O,H,L,C,V
        valid_indices: DatetimeIndex of the timestamps for each sample (the time 't' corresponding to the last candle in the window).
    """
    if df.empty or len(df) < window_size:
        return np.array([]), pd.DatetimeIndex([])
        
    # ensure sorted
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
        
    cols = ['open', 'high', 'low', 'close', 'volume']
    data = df[cols].values
    
    num_samples = len(data) - window_size + 1
    
    # Create sliding windows
    shape = (num_samples, window_size, len(cols))
    strides = (data.strides[0], data.strides[0], data.strides[1])
    windows = np.lib.stride_tricks.as_strided(data, shape=shape, strides=strides).copy()
    
    # Normalize: price and volume
    first_closes = windows[:, 0, 3].reshape(-1, 1, 1)  # close is index 3
    # avoid division by zero
    first_closes = np.where(first_closes == 0, 1e-8, first_closes)
    prices = windows[:, :, :4] / first_closes
    
    first_volumes = windows[:, 0, 4].reshape(-1, 1, 1)
    # add small epsilon to avoid div by zero
    volumes = windows[:, :, 4:5] / (first_volumes + 1e-8)
    
    X_norm = np.concatenate([prices, volumes], axis=2)
    
    valid_indices = df.index[window_size - 1:]
    
    return X_norm, valid_indices

def get_window_columns() -> List[str]:
    return ['open', 'high', 'low', 'close', 'volume']
