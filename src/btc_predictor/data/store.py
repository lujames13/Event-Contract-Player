import sqlite3
import pandas as pd
from pathlib import Path
from typing import List, Optional

class DataStore:
    def __init__(self, db_path: str = "data/btc_predictor.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize SQLite tables based on ARCHITECTURE.md."""
        with self._get_connection() as conn:
            # Table for historical K-lines
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv (
                    symbol      TEXT NOT NULL,           -- e.g. "BTCUSDT"
                    interval    TEXT NOT NULL,           -- "1m" | "5m" | "1h" | "1d"
                    open_time   INTEGER NOT NULL,        -- Unix ms
                    open        REAL NOT NULL,
                    high        REAL NOT NULL,
                    low         REAL NOT NULL,
                    close       REAL NOT NULL,
                    volume      REAL NOT NULL,
                    close_time  INTEGER NOT NULL,        -- Unix ms
                    PRIMARY KEY (symbol, interval, open_time)
                ) WITHOUT ROWID;
            """)
            
            # Table for simulated trades
            conn.execute("""
                CREATE TABLE IF NOT EXISTS simulated_trades (
                    id                  TEXT PRIMARY KEY,
                    strategy_name       TEXT NOT NULL,
                    direction           TEXT NOT NULL,       -- "higher" | "lower"
                    confidence          REAL NOT NULL,
                    timeframe_minutes   INTEGER NOT NULL,
                    bet_amount          REAL NOT NULL,
                    open_time           TEXT NOT NULL,        -- ISO 8601 UTC
                    open_price          REAL NOT NULL,
                    expiry_time         TEXT NOT NULL,        -- ISO 8601 UTC
                    close_price         REAL,
                    result              TEXT,                 -- "win" | "lose"
                    pnl                 REAL,
                    features_used       TEXT                  -- JSON string
                );
            """)
            
            # Create indexing for faster retrieval if needed
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_time ON ohlcv (open_time);")
            conn.commit()

    def save_ohlcv(self, df: pd.DataFrame, symbol: str, interval: str):
        """
        Save OHLCV data to database. 
        Expected columns: open_time, open, high, low, close, volume, close_time
        """
        if df.empty:
            return

        # Ensure required columns exist
        required_cols = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Prepare for upsert
        df = df.copy()
        df["symbol"] = symbol
        df["interval"] = interval
        
        # We use sqlite3 with "REPLACE" or "INSERT OR IGNORE" to handle duplicates
        with self._get_connection() as conn:
            df[ ["symbol", "interval"] + required_cols ].to_sql(
                "ohlcv", 
                conn, 
                if_exists="append", 
                index=False,
                method=self._sqlite_upsert
            )

    def _sqlite_upsert(self, table, conn, keys, data_iter):
        """
        Custom method for to_sql to handle UPSERT in SQLite.
        """
        from sqlite3 import IntegrityError
        
        columns = ", ".join(keys)
        placeholders = ", ".join(["?"] * len(keys))
        sql = f"INSERT OR REPLACE INTO {table.name} ({columns}) VALUES ({placeholders})"
        conn.executemany(sql, data_iter)

    def get_ohlcv(
        self, 
        symbol: str, 
        interval: str, 
        start_time: Optional[int] = None, 
        end_time: Optional[int] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Retrieve OHLCV data from database.
        """
        query = "SELECT * FROM ohlcv WHERE symbol = ? AND interval = ?"
        params = [symbol, interval]

        if start_time:
            query += " AND open_time >= ?"
            params.append(start_time)
        if end_time:
            query += " AND open_time <= ?"
            params.append(end_time)

        query += " ORDER BY open_time ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        
        # Convert open_time to datetime index if desired, or keep as int
        # For consistency with BaseStrategy, we might want to return datetime index
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
            df.set_index('datetime', inplace=True)
            
        return df
