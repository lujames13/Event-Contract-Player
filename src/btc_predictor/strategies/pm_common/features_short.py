import pandas as pd
import numpy as np
import talib
from typing import List

def generate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate short-term features from OHLCV data.
    Feature Set A for PM baseline models.
    """
    if df.empty:
        return df.copy()
        
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        
    feat = df.copy()
    
    # --- 1. Short-term Momentum ---
    for n in [1, 2, 3, 5]:
        feat[f'ret_{n}m'] = feat['close'].pct_change(n)
        
    # --- 2. Short-term Volatility ---
    for n in [3, 5, 10]:
        feat[f'vol_{n}m'] = feat['ret_1m'].rolling(window=n).std()

    close = feat['close'].values
    high = feat['high'].values
    low = feat['low'].values
    volume = feat['volume'].values

    # --- 3. Short RSI ---
    feat['rsi_7'] = talib.RSI(close, timeperiod=7)
    
    # --- 4. Short EMA ---
    feat['ema_3'] = talib.EMA(close, timeperiod=3)
    feat['ema_8'] = talib.EMA(close, timeperiod=8)
    feat['ema_13'] = talib.EMA(close, timeperiod=13)
    
    # --- 5. EMA Cross ---
    feat['ema_3_8_diff'] = feat['ema_3'] - feat['ema_8']
    feat['ema_8_13_diff'] = feat['ema_8'] - feat['ema_13']
    
    # --- 6. Short Bollinger Bands ---
    upper, middle, lower = talib.BBANDS(close, timeperiod=10, nbdevup=2, nbdevdn=2, matype=0)
    feat['bb_upper_10'] = upper
    feat['bb_middle_10'] = middle
    feat['bb_lower_10'] = lower
    
    # --- 7. BB Derived ---
    bb_range = feat['bb_upper_10'] - feat['bb_lower_10']
    
    with np.errstate(divide='ignore', invalid='ignore'):
        bb_pct_b = (feat['close'] - feat['bb_lower_10']) / bb_range
        bb_dist = (feat['close'] - feat['bb_middle_10']) / feat['bb_middle_10']
        
    feat['bb_pct_b_10'] = bb_pct_b.replace([np.inf, -np.inf], np.nan)
    feat['bb_dist_10'] = bb_dist.replace([np.inf, -np.inf], np.nan)
    
    # --- 8. Short ATR ---
    feat['atr_7'] = talib.ATR(high, low, close, timeperiod=7)
    
    # --- 9. Volume Pulse ---
    for n in [3, 5]:
        with np.errstate(divide='ignore', invalid='ignore'):
            feat[f'vol_ratio_{n}m'] = feat['volume'] / feat['volume'].rolling(window=n).mean()
        feat[f'vol_ratio_{n}m'] = feat[f'vol_ratio_{n}m'].replace([np.inf, -np.inf], np.nan)
        
    # --- 10. Candle Formations ---
    body = np.abs(feat['close'] - feat['open'])
    rng = feat['high'] - feat['low']
    with np.errstate(divide='ignore', invalid='ignore'):
        body_ratio = body / rng
        range_pct = rng / feat['close']
    feat['candle_body_ratio'] = body_ratio.replace([np.inf, -np.inf], np.nan)
    feat['candle_range_pct'] = range_pct.replace([np.inf, -np.inf], np.nan)
    
    # --- 11. OBV Momentum ---
    obv = talib.OBV(close, volume)
    feat['obv'] = obv
    feat['obv_ret_3m'] = pd.Series(obv, index=feat.index).pct_change(3)
    
    # --- 12. Time ---
    hours = feat.index.hour
    days = feat.index.dayofweek
    
    feat['hour_sin'] = np.sin(2 * np.pi * hours / 24)
    feat['hour_cos'] = np.cos(2 * np.pi * hours / 24)
    feat['day_sin'] = np.sin(2 * np.pi * days / 7)
    feat['day_cos'] = np.cos(2 * np.pi * days / 7)
    
    return feat

def get_feature_columns() -> List[str]:
    return [
        'ret_1m', 'ret_2m', 'ret_3m', 'ret_5m',
        'vol_3m', 'vol_5m', 'vol_10m',
        'rsi_7',
        'ema_3', 'ema_8', 'ema_13',
        'ema_3_8_diff', 'ema_8_13_diff',
        'bb_upper_10', 'bb_middle_10', 'bb_lower_10',
        'bb_pct_b_10', 'bb_dist_10',
        'atr_7',
        'vol_ratio_3m', 'vol_ratio_5m',
        'candle_body_ratio', 'candle_range_pct',
        'obv', 'obv_ret_3m',
        'hour_sin', 'hour_cos', 'day_sin', 'day_cos'
    ]
