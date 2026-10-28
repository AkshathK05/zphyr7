"""CLI script to fetch Elexon BMRS datasets and rebuild local SQLite cache."""

import sys
import time
import json
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.config import settings
from backend.database import init_db, save_fuelhh_records, save_windfor_records, get_connection
from backend.fetcher import ElexonFetcher

def run_rebuild():
    """Fetch all configured BMRS data and populate SQLite database."""
    print("=" * 60)
    print("REBUILDING LOCAL ELEXON BMRS DATA CACHE")
    print(f"Target Database: {settings.db_path}")
    print(f"FUELHH Range: {settings.delivery_start_date} to {settings.delivery_end_date}")
    print(f"WINDFOR Range: {settings.forecast_fetch_start} to {settings.forecast_fetch_end}")
    print("=" * 60)

    start_time = time.time()
    init_db()

    fetcher = ElexonFetcher()

    # 1. Fetch FUELHH Actuals
    print("\n[1/2] Fetching actual wind generation (FUELHH)...")
    fuel_records = fetcher.fetch_fuelhh_actuals(
        settlement_date_from=settings.delivery_start_date,
        settlement_date_to=settings.delivery_end_date,
        fuel_type="WIND",
    )
    print(f"  Received {len(fuel_records)} FUELHH records from API.")
    saved_fuel = save_fuelhh_records(fuel_records)
    print(f"  Saved {saved_fuel} actual records into SQLite cache.")

    # 2. Fetch WINDFOR Forecasts
    print("\n[2/2] Fetching wind forecasts (WINDFOR)...")
    wind_records = fetcher.fetch_windfor_forecasts_range(
        start_time_iso=settings.forecast_fetch_start,
        end_time_iso=settings.forecast_fetch_end,
        chunk_days=5,
    )
    print(f"  Received {len(wind_records)} WINDFOR records from API.")
    saved_wind = save_windfor_records(wind_records)
    print(f"  Saved {saved_wind} forecast records into SQLite cache.")

    # 3. Query sample records from DB to verify
    print("\n" + "=" * 60)
    print("VERIFYING DATABASE CACHE SAMPLES")
    print("=" * 60)

    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Sample FUELHH
        cursor.execute("""
            SELECT dataset, start_time, publish_time, settlement_date, settlement_period, fuel_type, generation
            FROM fuelhh_actuals
            ORDER BY start_time ASC
            LIMIT 3
        """)
        fuel_samples = [dict(row) for row in cursor.fetchall()]
        print("\nSample FUELHH records in SQLite:")
        print(json.dumps(fuel_samples, indent=2))

        # Sample WINDFOR
        cursor.execute("""
            SELECT dataset, start_time, publish_time, generation
            FROM windfor_forecasts
            ORDER BY publish_time ASC, start_time ASC
            LIMIT 3
        """)
        wind_samples = [dict(row) for row in cursor.fetchall()]
        print("\nSample WINDFOR records in SQLite:")
        print(json.dumps(wind_samples, indent=2))

        # Totals
        cursor.execute("SELECT COUNT(*) FROM fuelhh_actuals")
        total_fuel = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM windfor_forecasts")
        total_wind = cursor.fetchone()[0]

    elapsed = time.time() - start_time
    print(f"\nCache rebuild complete in {elapsed:.2f}s!")
    print(f"Total FUELHH rows in DB: {total_fuel}")
    print(f"Total WINDFOR rows in DB: {total_wind}")

if __name__ == "__main__":
    run_rebuild()
