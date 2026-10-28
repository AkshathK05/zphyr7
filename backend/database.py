"""Database management and SQLite cache persistence."""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from backend.config import settings

def get_connection(db_path: str = None, read_only: bool = False) -> sqlite3.Connection:
    """Open a SQLite connection with row factory configured."""
    target_path = Path(db_path or settings.db_path)
    if read_only and target_path.exists():
        uri_path = f"file:{target_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True)
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = None) -> None:
    """Initialize database tables and performance indices if not already present."""
    target_path = Path(db_path or settings.db_path)
    if target_path.exists():
        # Database already created, skip writes on serverless/read-only environments
        return

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Table for actual generation outturn (FUELHH)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fuelhh_actuals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset TEXT NOT NULL,
                start_time TEXT NOT NULL,
                publish_time TEXT NOT NULL,
                settlement_date TEXT NOT NULL,
                settlement_period INTEGER NOT NULL,
                fuel_type TEXT NOT NULL,
                generation REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(start_time, fuel_type)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fuelhh_start_time ON fuelhh_actuals(start_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fuelhh_settlement_date ON fuelhh_actuals(settlement_date);")

        # Table for wind generation forecasts (WINDFOR)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS windfor_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset TEXT NOT NULL,
                start_time TEXT NOT NULL,
                publish_time TEXT NOT NULL,
                generation REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(start_time, publish_time)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_windfor_start_time ON windfor_forecasts(start_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_windfor_publish_time ON windfor_forecasts(publish_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_windfor_target_publish ON windfor_forecasts(start_time, publish_time);")
        
        conn.commit()

def save_fuelhh_records(records: List[Dict[str, Any]], db_path: str = None) -> int:
    """Insert or replace FUELHH records in SQLite cache."""
    if not records:
        return 0
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO fuelhh_actuals (
                dataset, start_time, publish_time, settlement_date, settlement_period, fuel_type, generation
            ) VALUES (
                :dataset, :startTime, :publishTime, :settlementDate, :settlementPeriod, :fuelType, :generation
            )
            ON CONFLICT(start_time, fuel_type) DO UPDATE SET
                generation = excluded.generation,
                publish_time = excluded.publish_time,
                settlement_date = excluded.settlement_date,
                settlement_period = excluded.settlement_period
        """, records)
        conn.commit()
        return len(records)

def save_windfor_records(records: List[Dict[str, Any]], db_path: str = None) -> int:
    """Insert or replace WINDFOR records in SQLite cache."""
    if not records:
        return 0
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO windfor_forecasts (
                dataset, start_time, publish_time, generation
            ) VALUES (
                :dataset, :startTime, :publishTime, :generation
            )
            ON CONFLICT(start_time, publish_time) DO UPDATE SET
                generation = excluded.generation
        """, records)
        conn.commit()
        return len(records)
