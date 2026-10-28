"""Export all evaluated settlement slots across the backtest period to CSV."""

import sys
import csv
from pathlib import Path
from datetime import date, timedelta

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.config import settings
from backend.database import get_connection
from backend.processing import align_and_join_day
from backend.metrics import compute_bias_corrected_spread
import numpy as np

def export_all_slots_csv(output_path: str = None):
    out_file = Path(output_path or (Path(settings.db_path).parent / "evaluated_slots_january_2026.csv"))
    out_file.parent.mkdir(parents=True, exist_ok=True)

    start_d = date.fromisoformat(settings.delivery_start_date)
    end_d = date.fromisoformat(settings.delivery_end_date)

    conn = get_connection()
    all_slots = []
    cur_d = start_d
    while cur_d <= end_d:
        res = align_and_join_day(delivery_date=cur_d.isoformat(), cutoff_time=settings.cutoff_time, conn=conn)
        for s in res.slots:
            if s.status == "EVALUATED":
                all_slots.append(s)
        cur_d += timedelta(days=1)
    conn.close()

    print(f"Exporting {len(all_slots)} evaluated slots to {out_file}...")

    fieldnames = [
        "start_time",
        "settlement_date",
        "settlement_period",
        "forecast_generation_mw",
        "actual_generation_mw",
        "error_mw",
        "forecast_publish_time",
        "actual_publish_time",
        "lead_time_hours",
    ]

    with open(out_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in all_slots:
            writer.writerow({
                "start_time": s.start_time,
                "settlement_date": s.settlement_date,
                "settlement_period": s.settlement_period,
                "forecast_generation_mw": s.forecast_generation_mw,
                "actual_generation_mw": s.actual_generation_mw,
                "error_mw": s.error_mw,
                "forecast_publish_time": s.forecast_publish_time,
                "actual_publish_time": s.actual_publish_time,
                "lead_time_hours": s.lead_time_hours,
            })

    # Verification of all 4 bias-corrected metrics computed from this exact CSV dataset
    errors = np.array([s.error_mw for s in all_slots], dtype=float)
    bc = compute_bias_corrected_spread(errors)

    print("\n" + "=" * 65)
    print("BIAS-CORRECTED METRICS VERIFICATION (FROM EXPORTED DATASET)")
    print("=" * 65)
    print(f"Total Evaluated Slots:      {len(all_slots)}")
    print(f"Mean Bias Subtracted:       {bc.mean_bias_subtracted_mw:+,.2f} MW")
    print(f"1. Bias-Corrected MAE:      {bc.mae_mw:,.2f} MW")
    print(f"2. Bias-Corrected P10:      {bc.p10_mw:+,.2f} MW")
    print(f"3. Bias-Corrected P50:      {bc.p50_mw:+,.2f} MW")
    print(f"4. Bias-Corrected P90:      {bc.p90_mw:+,.2f} MW")
    print(f"Recommended Residual Buffer: {bc.recommended_buffer_mw:,.1f} MW")
    print("=" * 65)
    print(f"CSV file written successfully to: {out_file.resolve()}\n")

if __name__ == "__main__":
    export_all_slots_csv()
