import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional, List

def get_signal_dataframe(
    db_path: str = "data/btc_predictor.db",
    strategy_name: Optional[str] = None,
    timeframe_minutes: Optional[int] = None,
    settled_only: bool = True,
    days: Optional[int] = None,
) -> pd.DataFrame:
    """
    從 prediction_signals 表萃取數據。
    回傳 DataFrame：columns 至少含 id, strategy_name, timestamp, timeframe_minutes,
    direction, confidence, current_price, expiry_time, actual_direction,
    close_price, is_correct, traded, trade_id
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return pd.DataFrame()
    
    query = "SELECT * FROM prediction_signals WHERE 1=1"
    params = []
    
    if settled_only:
        query += " AND actual_direction IS NOT NULL"
    
    if strategy_name:
        query += " AND strategy_name = ?"
        params.append(strategy_name)
        
    if timeframe_minutes:
        query += " AND timeframe_minutes = ?"
        params.append(timeframe_minutes)
        
    if days:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            query += " AND timestamp >= ?"
            params.append(cutoff.isoformat())
        except Exception:
            pass
            
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except sqlite3.OperationalError:
        df = pd.DataFrame()
    finally:
        conn.close()

    if df.empty:
        return pd.DataFrame()

    for col in ['timestamp', 'expiry_time', 'created_at']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True).astype('datetime64[ns, UTC]')
            
    df = df.sort_values('timestamp').reset_index(drop=True)
    return df

def get_trade_dataframe(
    db_path: str = "data/btc_predictor.db",
    strategy_name: Optional[str] = None,
    days: Optional[int] = None,
) -> pd.DataFrame:
    """
    從 pm_orders JOIN prediction_signals 萃取交易數據。
    回傳 DataFrame：columns 含 order info + signal info + pnl
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return pd.DataFrame()
        
    query = """
        SELECT o.*, s.strategy_name, s.timestamp, s.timeframe_minutes, 
               s.direction, s.confidence, s.current_price, s.expiry_time,
               s.actual_direction, s.close_price as signal_close_price, s.is_correct, s.alpha
        FROM pm_orders o
        JOIN prediction_signals s ON o.signal_id = s.id
        WHERE 1=1
    """
    params = []
    
    if strategy_name:
        query += " AND s.strategy_name = ?"
        params.append(strategy_name)
        
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query += " AND o.placed_at >= ?"
        params.append(cutoff.isoformat())
        
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except sqlite3.OperationalError:
        df = pd.DataFrame()
    finally:
        conn.close()
        
    if df.empty:
        return pd.DataFrame()
        
    for col in ['timestamp', 'expiry_time', 'placed_at', 'filled_at', 'created_at']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True).astype('datetime64[ns, UTC]')
            
    if 'placed_at' in df.columns:
        df = df.sort_values('placed_at').reset_index(drop=True)
    return df

def get_market_context(
    db_path: str = "data/btc_predictor.db",
    timestamps: Optional[List[datetime]] = None,
) -> pd.DataFrame:
    """
    從 ohlcv 表取得每個 timestamp 附近的市場狀態。
    columns: timestamp, volatility_5m, volume_5m, price_change_1h
    用於分析模型在不同市場條件下的表現。
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return pd.DataFrame(columns=["timestamp", "volatility_5m", "volume_5m", "price_change_1h"])
    
    try:
        df = pd.read_sql_query("SELECT * FROM ohlcv WHERE interval = '1m'", conn)
    except sqlite3.OperationalError:
        df = pd.DataFrame()
    finally:
        conn.close()
        
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "volatility_5m", "volume_5m", "price_change_1h"])
        
    df['timestamp'] = pd.to_datetime(df['close_time'], unit='ms', utc=True).astype('datetime64[ns, UTC]')
    df = df.sort_values('timestamp')
    
    df['volatility_5m'] = df['close'].pct_change().rolling(5).std()
    df['volume_5m'] = df['volume'].rolling(5).sum()
    df['price_change_1h'] = df['close'].pct_change(60)
    
    res = df[["timestamp", "volatility_5m", "volume_5m", "price_change_1h"]].dropna()
    return res.reset_index(drop=True)

def join_signals_with_context(
    signals_df: pd.DataFrame,
    context_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    將 signal DataFrame 與市場 context join 起來。
    純函數，不讀 DB。
    """
    if signals_df.empty:
        return signals_df
    if context_df.empty:
        # append empty columns
        signals_df = signals_df.copy()
        for col in ["volatility_5m", "volume_5m", "price_change_1h"]:
            signals_df[col] = float('nan')
        return signals_df
        
    sorted_signals = signals_df.sort_values("timestamp")
    sorted_context = context_df.sort_values("timestamp")
    
    return pd.merge_asof(
        sorted_signals, 
        sorted_context,
        on="timestamp",
        direction="backward"
    ).sort_index()
