import sqlite3
import pandas as pd
from pathlib import Path
from typing import List, Optional, Any
from datetime import datetime

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
            conn.execute("PRAGMA journal_mode=WAL;")
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
        
        # Convert open_time to datetime index
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
            df.set_index('datetime', inplace=True)
            
        return df

    def get_latest_ohlcv(
        self, 
        symbol: str, 
        interval: str, 
        limit: int
    ) -> pd.DataFrame:
        """
        Retrieve LATEST OHLCV data from database.
        """
        query = "SELECT * FROM ohlcv WHERE symbol = ? AND interval = ? ORDER BY open_time DESC LIMIT ?"
        params = [symbol, interval, limit]

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        
        # Convert open_time to datetime index and reverse to ASC
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
            df.set_index('datetime', inplace=True)
            df.sort_index(inplace=True)
            
        return df

    def save_simulated_trade(self, trade: Any):
        """Save a new simulated trade to the database."""
        import json
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO simulated_trades (
                    id, strategy_name, direction, confidence, timeframe_minutes,
                    bet_amount, open_time, open_price, expiry_time, features_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id, trade.strategy_name, trade.direction, trade.confidence,
                trade.timeframe_minutes, trade.bet_amount, 
                trade.open_time.isoformat() if isinstance(trade.open_time, datetime) else trade.open_time,
                trade.open_price,
                trade.expiry_time.isoformat() if isinstance(trade.expiry_time, datetime) else trade.expiry_time,
                json.dumps(getattr(trade, 'features_used', {}))
            ))

    def update_simulated_trade(self, trade_id: str, close_price: float, result: str, pnl: float):
        """Update a trade with settlement results."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE simulated_trades 
                SET close_price = ?, result = ?, pnl = ?
                WHERE id = ?
            """, (close_price, result, pnl, trade_id))

    def get_daily_stats(self, strategy_name: str, date_str: str) -> dict:
        """
        Get daily statistics for risk control.
        date_str should be YYYY-MM-DD (UTC).
        """
        query = """
            SELECT 
                SUM(CASE WHEN pnl < 0 THEN -pnl ELSE 0 END) as daily_loss,
                COUNT(*) as daily_trades
            FROM simulated_trades
            WHERE strategy_name = ? AND open_time LIKE ?
        """
        
        with self._get_connection() as conn:
            row = conn.execute(query, (strategy_name, f"{date_str}%")).fetchone()
            
            # For consecutive losses, we need the recent trades
            trades_query = """
                SELECT result FROM simulated_trades
                WHERE strategy_name = ? 
                ORDER BY open_time DESC
                LIMIT 20
            """
            recent_results = conn.execute(trades_query, (strategy_name,)).fetchall()
            
            consecutive_losses = 0
            for (res,) in recent_results:
                if res == 'lose':
                    consecutive_losses += 1
                elif res == 'win':
                    break
                else: # None (pending)
                    continue
            
            return {
                "daily_loss": row[0] if row[0] else 0.0,
                "daily_trades": row[1] if row[1] else 0,
                "consecutive_losses": consecutive_losses
            }

    def get_pending_trades(self) -> pd.DataFrame:
        """Retrieve trades that need settlement (close_price IS NULL)."""
        with self._get_connection() as conn:
            return pd.read_sql_query("""
                SELECT * FROM simulated_trades WHERE close_price IS NULL
                ORDER BY expiry_time ASC
            """, conn)
