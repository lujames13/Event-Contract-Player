import pandas as pd
import numpy as np
import talib
from typing import List

def generate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate features for XGBoost model from OHLCV data.
    
    Args:
        df: DataFrame with datetime index and columns: open, high, low, close, volume.
            Index must be sorted.
            
    Returns:
        DataFrame with features. Original columns are preserved but might be 
        augmented with technical indicators.
    """
    if df.empty:
        return df.copy()
        
    # Ensure index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        
    # Optimization for backtesting: if features are already present, skip generation
    if 'rsi_14' in df.columns and 'macd' in df.columns:
        return df
        
    feat = df.copy()
    
    # --- 1. Basic Returns & Volatility ---
    # Returns for various horizons
    for n in [1, 3, 5, 10, 30, 60]:
        feat[f'ret_{n}m'] = feat['close'].pct_change(n)
        feat[f'log_ret_{n}m'] = np.log(feat['close'] / feat['close'].shift(n))
        
    # Volatility (Rolling Std of returns)
    for n in [5, 10, 30, 60]:
        feat[f'vol_{n}m'] = feat[f'ret_1m'].rolling(window=n).std()

    # --- 2. TA-Lib Indicators ---
    close = feat['close'].values
    high = feat['high'].values
    low = feat['low'].values
    volume = feat['volume'].values

    # RSI
    feat['rsi_14'] = talib.RSI(close, timeperiod=14)
    # MACD
    macd, macdsignal, macdhist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    feat['macd'] = macd
    feat['macd_signal'] = macdsignal
    feat['macd_hist'] = macdhist
    
    # Bollinger Bands
    upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    feat['bb_upper'] = upper
    feat['bb_middle'] = middle
    feat['bb_lower'] = lower
    
    # ATR
    feat['atr_14'] = talib.ATR(high, low, close, timeperiod=14)

    # --- 3. Derived Features ---
    # RSI distance from midpoint (50)
    feat['rsi_dist'] = feat['rsi_14'] - 50
    
    # MACD histogram slope (current - previous)
    feat['macd_hist_slope'] = feat['macd_hist'].diff()
    
    # BB %B: (price - lower) / (upper - lower)
    bb_range = feat['bb_upper'] - feat['bb_lower']
    feat['bb_pct_b'] = (feat['close'] - feat['bb_lower']) / bb_range.replace(0, np.nan)
    
    # Price relative to BB middle (percentage)
    feat['bb_dist'] = (feat['close'] - feat['bb_middle']) / feat['bb_middle']

    # --- 4. Time Features (Sin/Cos Encoding) ---
    hours = feat.index.hour
    days = feat.index.dayofweek
    
    feat['hour_sin'] = np.sin(2 * np.pi * hours / 24)
    feat['hour_cos'] = np.cos(2 * np.pi * hours / 24)
    feat['day_sin'] = np.sin(2 * np.pi * days / 7)
    feat['day_cos'] = np.cos(2 * np.pi * days / 7)

    # --- 5. Volume Features ---
    # Volume ratio vs rolling mean
    for n in [5, 10, 30]:
        feat[f'vol_ratio_{n}m'] = feat['volume'] / feat['volume'].rolling(window=n).mean()
        
    # OBV rate of change
    obv = talib.OBV(close, volume)
    feat['obv'] = obv
    feat['obv_ret_5m'] = pd.Series(obv, index=feat.index).pct_change(5)

    # --- 6. Rolling Z-Score Normalization (for MLP) ---
    feature_cols = get_feature_columns()
    for col in feature_cols:
        if col in feat.columns:
            # Skip sin/cos features
            if col.endswith('_sin') or col.endswith('_cos'):
                continue
            # Use window=60 as per requirement
            rolling = feat[col].rolling(window=60)
            feat[col] = (feat[col] - rolling.mean()) / rolling.std().replace(0, np.nan)
    
    # Fill remaining NaNs from rolling windows with 0 (or drop them later)
    # feat = feat.fillna(0) # Not here, let the fit() handle it

    return feat

def get_feature_columns() -> List[str]:
    """Returns a list of feature column names that should be used for training/prediction."""
    # This will be refined in Phase 2.3 Feature Selection
    # For now, we manually list the generated features, excluding original OHLCV and volume if desired, 
    # but often 'close' etc. are not great features themselves, but their returns are.
    
    cols = []
    for n in [1, 3, 5, 10, 30, 60]:
        cols.extend([f'ret_{n}m', f'log_ret_{n}m'])
    for n in [5, 10, 30, 60]:
        cols.append(f'vol_{n}m')
        
    cols.extend([
        'rsi_14', 'macd', 'macd_signal', 'macd_hist', 
        'bb_upper', 'bb_middle', 'bb_lower', 'atr_14',
        'rsi_dist', 'macd_hist_slope', 'bb_pct_b', 'bb_dist',
        'hour_sin', 'hour_cos', 'day_sin', 'day_cos',
        'obv', 'obv_ret_5m'
    ])
    
    for n in [5, 10, 30]:
        cols.append(f'vol_ratio_{n}m')
        
    return cols
