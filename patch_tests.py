import sqlite3
from pathlib import Path

def patch_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS prediction_signals (id INTEGER PRIMARY KEY, timestamp TEXT, actual_direction TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS simulated_trades (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

