import sqlite3
import pandas as pd
from pathlib import Path
from typing import List, Optional, Any
from datetime import datetime, timedelta
import uuid

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

            # Table for prediction signals (Signal Layer)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prediction_signals (
                    id                TEXT PRIMARY KEY,
                    strategy_name     TEXT NOT NULL,
                    timestamp         TEXT NOT NULL,       -- 預測時間 (ISO format, UTC)
                    timeframe_minutes INTEGER NOT NULL,
                    direction         TEXT NOT NULL,        -- 'higher' / 'lower'
                    confidence        FLOAT NOT NULL,
                    current_price     FLOAT NOT NULL,
                    expiry_time       TEXT NOT NULL,
                    -- 結算後填入
                    actual_direction  TEXT,                 -- NULL = 未結算, 'higher' / 'lower' / 'draw'
                    close_price       FLOAT,
                    is_correct        BOOLEAN,             -- NULL = 未結算
                    -- 與 Execution Layer 的關聯
                    traded            BOOLEAN NOT NULL DEFAULT 0,
                    trade_id          TEXT,                 -- FK to simulated_trades.id（如有）
                    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)
            
            # Create indexing for faster retrieval if needed
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_time ON ohlcv (open_time);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_unsettled ON prediction_signals(expiry_time) WHERE actual_direction IS NULL;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_strategy ON prediction_signals(strategy_name, timeframe_minutes);")
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

    def get_strategy_summary(self, strategy_name: str) -> dict:
        """回傳指定策略的累計統計摘要。"""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COALESCE(SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END), 0) as wins,
                    COALESCE(SUM(CASE WHEN result IS NOT NULL THEN 1 ELSE 0 END), 0) as settled,
                    COALESCE(SUM(pnl), 0) as total_pnl
                FROM simulated_trades
                WHERE strategy_name = ?
            """, (strategy_name,)).fetchone()
        
        total, wins, settled, pnl = row
        da = wins / settled if settled > 0 else 0.0
        return {
            "total_trades": total,
            "settled_trades": settled,
            "wins": wins,
            "da": da,
            "total_pnl": pnl
        }

    def get_strategy_detail(self, strategy_name: str, timeframe: int = None) -> dict:
        """回傳指定策略的詳細統計，包含方向分拆和 drawdown。"""
        base_where = "WHERE strategy_name = ? AND result IS NOT NULL"
        params = [strategy_name]
        if timeframe:
            base_where += " AND timeframe_minutes = ?"
            params.append(timeframe)

        with self._get_connection() as conn:
            row = conn.execute(f"""
                SELECT COUNT(*) as settled,
                    COALESCE(SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END), 0) as wins,
                    COALESCE(SUM(pnl), 0) as total_pnl
                FROM simulated_trades {base_where}
            """, params).fetchone()

            higher = conn.execute(f"""
                SELECT COUNT(*),
                    COALESCE(SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END), 0)
                FROM simulated_trades {base_where} AND direction = 'higher'
            """, params).fetchone()

            lower = conn.execute(f"""
                SELECT COUNT(*),
                    COALESCE(SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END), 0)
                FROM simulated_trades {base_where} AND direction = 'lower'
            """, params).fetchone()

            pending_where = "WHERE strategy_name = ? AND result IS NULL"
            pending_params = [strategy_name]
            if timeframe:
                pending_where += " AND timeframe_minutes = ?"
                pending_params.append(timeframe)
            pending = conn.execute(f"""
                SELECT COUNT(*) FROM simulated_trades {pending_where}
            """, pending_params).fetchone()[0]

            pnl_rows = conn.execute(f"""
                SELECT pnl FROM simulated_trades {base_where}
                ORDER BY open_time ASC
            """, params).fetchall()

        settled, wins, total_pnl = row
        da = wins / settled if settled > 0 else 0.0
        h_total, h_wins = higher
        l_total, l_wins = lower
        higher_da = h_wins / h_total if h_total > 0 else 0.0
        lower_da = l_wins / l_total if l_total > 0 else 0.0

        cumulative = peak = max_dd = 0.0
        for (p,) in pnl_rows:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return {
            "settled": settled, "pending": pending,
            "wins": wins, "da": da,
            "higher_total": h_total, "higher_wins": h_wins,
            "higher_da": higher_da,
            "lower_total": l_total, "lower_wins": l_wins,
            "lower_da": lower_da,
            "total_pnl": total_pnl, "max_drawdown": max_dd,
        }

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

    def get_table_counts(self) -> dict[str, int]:
        """回傳各 table 的 row count。"""
        with self._get_connection() as conn:
            ohlcv_count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
            trades_count = conn.execute("SELECT COUNT(*) FROM simulated_trades").fetchone()[0]
            signals_count = conn.execute("SELECT COUNT(*) FROM prediction_signals").fetchone()[0]
        return {
            "ohlcv": ohlcv_count, 
            "simulated_trades": trades_count,
            "prediction_signals": signals_count
        }

    # --- Signal Layer Methods ---

    def save_prediction_signal(self, signal: Any) -> str:
        """無條件儲存預測信號，回傳 signal_id。"""
        signal_id = str(uuid.uuid4())
        expiry_time = signal.timestamp + timedelta(minutes=signal.timeframe_minutes)
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO prediction_signals (
                    id, strategy_name, timestamp, timeframe_minutes, direction,
                    confidence, current_price, expiry_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id, 
                signal.strategy_name,
                signal.timestamp.isoformat() if isinstance(signal.timestamp, datetime) else signal.timestamp,
                signal.timeframe_minutes,
                signal.direction,
                signal.confidence,
                signal.current_price,
                expiry_time.isoformat() if isinstance(expiry_time, datetime) else expiry_time
            ))
        return signal_id

    def update_signal_traded(self, signal_id: str, trade_id: str) -> None:
        """標記 signal 已產生對應的 SimulatedTrade。"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE prediction_signals 
                SET traded = 1, trade_id = ? 
                WHERE id = ?
            """, (trade_id, signal_id))

    def get_unsettled_signals(self) -> pd.DataFrame:
        """取得尚未結算的 signals。"""
        query = """
            SELECT * FROM prediction_signals
            WHERE actual_direction IS NULL
            ORDER BY expiry_time ASC
        """
        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn)

    def settle_signal(self, signal_id: str, actual_direction: str, close_price: float, is_correct: bool) -> None:
        """寫入 signal 的實際結果。"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE prediction_signals
                SET actual_direction = ?, close_price = ?, is_correct = ?
                WHERE id = ?
            """, (actual_direction, close_price, is_correct, signal_id))

    def get_signal_stats(self) -> dict:
        """取得 Signal Layer 統計。"""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN actual_direction IS NOT NULL THEN 1 ELSE 0 END), 0) as settled,
                    COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) as correct
                FROM prediction_signals
            """).fetchone()
            
        total, settled, correct = row
        accuracy = correct / settled if settled > 0 else None
        return {
            "total": total,
            "settled": settled,
            "correct": correct,
            "accuracy": accuracy
        }
