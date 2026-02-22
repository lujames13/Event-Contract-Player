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
                    -- Polymarket 擴展欄位
                    market_slug       TEXT,
                    market_price_up   FLOAT,
                    alpha             FLOAT,
                    order_type        TEXT,
                    -- 與 Execution Layer 的關聯
                    traded            BOOLEAN NOT NULL DEFAULT 0,
                    trade_id          TEXT,                 -- FK to simulated_trades.id（如有）
                    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)

            # Safe alter tables for backward compatibility
            try:
                conn.execute("ALTER TABLE prediction_signals ADD COLUMN market_slug TEXT;")
                conn.execute("ALTER TABLE prediction_signals ADD COLUMN market_price_up FLOAT;")
                conn.execute("ALTER TABLE prediction_signals ADD COLUMN alpha FLOAT;")
                conn.execute("ALTER TABLE prediction_signals ADD COLUMN order_type TEXT;")
            except sqlite3.OperationalError:
                pass

            
            # Create indexing for faster retrieval if needed
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_time ON ohlcv (open_time);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_unsettled ON prediction_signals(expiry_time) WHERE actual_direction IS NULL;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_strategy ON prediction_signals(strategy_name, timeframe_minutes);")

            # Polymarket Markets
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pm_markets (
                    slug            TEXT PRIMARY KEY,
                    condition_id    TEXT NOT NULL,
                    up_token_id     TEXT NOT NULL,
                    down_token_id   TEXT NOT NULL,
                    start_time      TEXT NOT NULL,
                    end_time        TEXT NOT NULL,
                    price_to_beat   REAL,
                    outcome         TEXT,
                    close_price     REAL,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)

            # Polymarket Orders
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pm_orders (
                    order_id        TEXT PRIMARY KEY,
                    signal_id       TEXT REFERENCES prediction_signals(id),
                    token_id        TEXT NOT NULL,
                    side            TEXT NOT NULL,
                    price           REAL NOT NULL,
                    size            REAL NOT NULL,
                    order_type      TEXT NOT NULL,
                    status          TEXT NOT NULL,
                    placed_at       TEXT NOT NULL,
                    filled_at       TEXT,
                    fill_price      REAL,
                    fill_size       REAL,
                    pnl             REAL,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)
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

    def check_trade_exists(self, strategy_name: str, timeframe_minutes: int, open_time: datetime) -> bool:
        """Check if a trade already exists for the given strategy and time."""
        open_time_str = open_time.isoformat() if isinstance(open_time, datetime) else open_time
        with self._get_connection() as conn:
            # Check for exact match on strategy, timeframe, and open time
            count = conn.execute("""
                SELECT COUNT(*) FROM simulated_trades 
                WHERE strategy_name = ? 
                AND timeframe_minutes = ? 
                AND open_time = ?
            """, (strategy_name, timeframe_minutes, open_time_str)).fetchone()[0]
            return count > 0

    def update_simulated_trade(self, trade_id: str, close_price: float, result: str, pnl: float) -> bool:
        """
        Update a trade with settlement results.
        Returns True if the update was successful (row modified), False otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE simulated_trades 
                SET close_price = ?, result = ?, pnl = ?
                WHERE id = ? AND close_price IS NULL
            """, (close_price, result, pnl, trade_id))
            return cursor.rowcount > 0

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
        
        market_slug = getattr(signal, 'market_slug', None)
        market_price_up = getattr(signal, 'market_price_up', None)
        alpha = getattr(signal, 'alpha', None)
        order_type = getattr(signal, 'order_type', None)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO prediction_signals (
                    id, strategy_name, timestamp, timeframe_minutes, direction,
                    confidence, current_price, expiry_time,
                    market_slug, market_price_up, alpha, order_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id, 
                signal.strategy_name,
                signal.timestamp.isoformat() if isinstance(signal.timestamp, datetime) else signal.timestamp,
                signal.timeframe_minutes,
                signal.direction,
                signal.confidence,
                signal.current_price,
                expiry_time.isoformat() if isinstance(expiry_time, datetime) else expiry_time,
                market_slug,
                market_price_up,
                alpha,
                order_type
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

    def get_settled_signals(
        self,
        strategy_name: str | None = None,
        timeframe_minutes: int | None = None
    ) -> pd.DataFrame:
        """
        取得已結算的 prediction signals。

        Args:
            strategy_name: 篩選策略（None = 全部）
            timeframe_minutes: 篩選 timeframe（None = 全部）

        Returns:
            DataFrame with columns: id, strategy_name, timestamp, timeframe_minutes,
            direction, confidence, current_price, expiry_time,
            actual_direction, close_price, is_correct, traded, trade_id
        """
        query = "SELECT * FROM prediction_signals WHERE actual_direction IS NOT NULL"
        params = []

        if strategy_name:
            query += " AND strategy_name = ?"
            params.append(strategy_name)

        if timeframe_minutes:
            query += " AND timeframe_minutes = ?"
            params.append(timeframe_minutes)

        query += " ORDER BY timestamp ASC"

        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

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

    # --- Polymarket Methods ---

    def save_pm_market(self, market: dict | Any):
        """
        Save or update a Polymarket market configuration.
        Supports both dict and potential future dataclass.
        """
        if hasattr(market, '__dataclass_fields__'):
            # Convert dataclass to dict if needed, but for now assuming dict or simple attr access
            m = {
                "slug": market.slug,
                "condition_id": market.condition_id,
                "up_token_id": market.up_token_id,
                "down_token_id": market.down_token_id,
                "start_time": market.start_time,
                "end_time": market.end_time,
                "price_to_beat": market.price_to_beat,
                "outcome": getattr(market, 'outcome', None),
                "close_price": getattr(market, 'close_price', None)
            }
        else:
            m = market

        query = """
            INSERT INTO pm_markets (
                slug, condition_id, up_token_id, down_token_id, 
                start_time, end_time, price_to_beat, outcome, close_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                condition_id = excluded.condition_id,
                up_token_id = excluded.up_token_id,
                down_token_id = excluded.down_token_id,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                price_to_beat = excluded.price_to_beat,
                outcome = COALESCE(excluded.outcome, outcome),
                close_price = COALESCE(excluded.close_price, close_price)
        """
        with self._get_connection() as conn:
            conn.execute(query, (
                m["slug"], m["condition_id"], m["up_token_id"], m["down_token_id"],
                m["start_time"], m["end_time"], m.get("price_to_beat"), 
                m.get("outcome"), m.get("close_price")
            ))

    def get_active_pm_market(self, timeframe_minutes: int) -> Optional[dict]:
        """
        Get the most recent active market for a specific timeframe.
        'Active' means end_time > now and outcome is NULL.
        """
        now_str = datetime.utcnow().isoformat()
        
        # Approximate timeframe matching via slug or price_to_beat isn't perfect, 
        # normally we'd need a 'timeframe' column, but we can filter by end_time - start_time
        # or just rely on the fact that tracker only syncs what we tell it.
        # For now, let's use a simple query that looks for unclosed markets.
        
        query = """
            SELECT * FROM pm_markets
            WHERE end_time > ? AND outcome IS NULL
            ORDER BY end_time ASC
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (now_str,)).fetchall()
            
            # Filter by timeframe in python for simplicity if needed, 
            # or just return the first one that fits the end_time alignment.
            # BTC 5m markets usually end on multiples of 5m.
            for row in rows:
                m = dict(row)
                start_dt = datetime.fromisoformat(m["start_time"].replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(m["end_time"].replace('Z', '+00:00'))
                duration = (end_dt - start_dt).total_seconds() / 60
                if abs(duration - timeframe_minutes) < 1: # Slack for 1 sec
                    return m
        return None

    def save_pm_order(self, order: Any):
        """Save a PolymarketOrder dataclass to the database."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO pm_orders (
                    order_id, signal_id, token_id, side, price, size,
                    order_type, status, placed_at, filled_at, fill_price, fill_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.order_id, order.signal_id, order.token_id, 
                order.side, order.price, order.size,
                order.order_type, order.status,
                order.placed_at.isoformat() if isinstance(order.placed_at, datetime) else order.placed_at,
                order.filled_at.isoformat() if isinstance(order.filled_at, datetime) else order.filled_at,
                order.fill_price, order.fill_size
            ))

    def update_pm_order(self, order_id: str, status: str, **kwargs):
        """Update an existing Polymarket order status and other fields."""
        fields = ["status = ?"]
        params = [status]
        
        for k, v in kwargs.items():
            if k in ['filled_at', 'fill_price', 'fill_size', 'pnl']:
                fields.append(f"{k} = ?")
                if k == 'filled_at' and isinstance(v, datetime):
                    params.append(v.isoformat())
                else:
                    params.append(v)
        
        params.append(order_id)
        query = f"UPDATE pm_orders SET {', '.join(fields)} WHERE order_id = ?"
        
        with self._get_connection() as conn:
            conn.execute(query, params)

    def save_polymarket_execution_context(self, signal: Any, trade: Any, order: Any) -> None:
        """
        Atomically save a prediction signal and (if applicable) its corresponding 
        SimulatedTrade and PolymarketOrder within a single database transaction. 
        """
        import json
        
        timestamp_dt = signal.timestamp
        if isinstance(timestamp_dt, pd.Timestamp):
            timestamp_dt = timestamp_dt.to_pydatetime()
            
        expiry_time = timestamp_dt + timedelta(minutes=signal.timeframe_minutes)
        
        signal_id = str(uuid.uuid4())
        market_slug = getattr(signal, 'market_slug', None)
        market_price_up = getattr(signal, 'market_price_up', None)
        alpha = getattr(signal, 'alpha', None)
        order_type_signal = getattr(signal, 'order_type', None)

        with self._get_connection() as conn:
            # 1. Save Prediction Signal
            conn.execute("""
                INSERT INTO prediction_signals (
                    id, strategy_name, timestamp, timeframe_minutes, direction,
                    confidence, current_price, expiry_time, traded, trade_id,
                    market_slug, market_price_up, alpha, order_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id, 
                signal.strategy_name,
                timestamp_dt.isoformat(),
                signal.timeframe_minutes,
                signal.direction,
                signal.confidence,
                signal.current_price,
                expiry_time.isoformat(),
                1 if trade else 0,
                trade.id if trade else None,
                market_slug,
                market_price_up,
                alpha,
                order_type_signal
            ))

            if trade and order:
                # 2. Save SimulatedTrade
                order.signal_id = signal_id
                
                features_json = json.dumps(getattr(trade, 'features_used', {}))
                op_time = trade.open_time.isoformat() if isinstance(trade.open_time, datetime) else trade.open_time
                exp_time = trade.expiry_time.isoformat() if isinstance(trade.expiry_time, datetime) else trade.expiry_time
                
                conn.execute("""
                    INSERT INTO simulated_trades (
                        id, strategy_name, direction, confidence, timeframe_minutes,
                        bet_amount, open_time, open_price, expiry_time, features_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade.id, trade.strategy_name, trade.direction, trade.confidence,
                    trade.timeframe_minutes, trade.bet_amount, op_time, trade.open_price, exp_time, features_json
                ))

                # 3. Save PolymarketOrder
                pl_time = order.placed_at.isoformat() if isinstance(order.placed_at, datetime) else order.placed_at
                conn.execute("""
                    INSERT INTO pm_orders (
                        order_id, signal_id, token_id, side, price, size,
                        order_type, status, placed_at, filled_at, fill_price, fill_size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order.order_id, order.signal_id, order.token_id, 
                    order.side, order.price, order.size,
                    order.order_type, order.status, pl_time, None, None, None
                ))
