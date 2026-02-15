import pandas as pd
import numpy as np
import talib
from typing import List

def generate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate optimized feature set for LGBM v2.
    """
    if df.empty:
        return df.copy()
        
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        
    # Check if features already generated (for efficiency)
    if 'rsi_14' in df.columns and 'vol_60m' in df.columns:
        return df
        
    feat = df.copy()
    
    # Base return
    feat['ret_1m'] = feat['close'].pct_change(1)
    
    # Top returns
    for n in [30, 60]:
        feat[f'ret_{n}m'] = feat['close'].pct_change(n)
        
    # Top volatilities
    for n in [10, 30, 60]:
        feat[f'vol_{n}m'] = feat['ret_1m'].rolling(window=n).std()

    close = feat['close'].values
    high = feat['high'].values
    low = feat['low'].values
    volume = feat['volume'].values

    # TA Indicators
    feat['rsi_14'] = talib.RSI(close, timeperiod=14)
    macd, macdsignal, macdhist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    feat['macd'] = macd
    feat['macd_signal'] = macdsignal
    feat['macd_hist'] = macdhist
    
    upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    feat['bb_upper'] = upper
    feat['bb_middle'] = middle
    feat['bb_lower'] = lower
    feat['atr_14'] = talib.ATR(high, low, close, timeperiod=14)

    # Distances
    bb_range = feat['bb_upper'] - feat['bb_lower']
    feat['bb_pct_b'] = (feat['close'] - feat['bb_lower']) / bb_range.replace(0, np.nan)
    feat['bb_dist'] = (feat['close'] - feat['bb_middle']) / feat['bb_middle']

    # Time
    hours = feat.index.hour
    days = feat.index.dayofweek
    feat['hour_sin'] = np.sin(2 * np.pi * hours / 24)
    feat['hour_cos'] = np.cos(2 * np.pi * hours / 24)
    feat['day_sin'] = np.sin(2 * np.pi * days / 7)

    # Volume
    obv = talib.OBV(close, volume)
    feat['obv'] = obv
    feat['obv_ret_5m'] = pd.Series(obv, index=feat.index).pct_change(5)

    return feat

def get_feature_columns() -> List[str]:
    """
    Returns the selected top features for LGBM v2.
    """
    return [
        'obv', 'vol_60m', 'vol_30m', 'vol_10m', 
        'hour_cos', 'hour_sin', 'day_sin',
        'bb_upper', 'bb_lower', 'bb_middle', 
        'ret_60m', 'ret_30m', 
        'atr_14', 'macd_signal', 'macd', 'macd_hist', 
        'rsi_14', 'bb_pct_b', 'bb_dist', 'obv_ret_5m'
    ]
