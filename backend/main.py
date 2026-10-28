"""FastAPI REST API application for Elexon BMRS Wind Backtest."""

import os
import io
import csv
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from fastapi import FastAPI, APIRouter, Query, HTTPException, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import get_connection, init_db
from backend.processing import align_and_join_day, DayComparisonResult
from backend.metrics import (
    calculate_overall_metrics,
    calculate_hourly_metrics,
    calculate_daily_metrics,
    calculate_horizon_metrics,
    calculate_error_histogram,
    OverallMetrics,
    HourlyMetric,
    DailyMetric,
    HorizonBucketMetric,
    HistogramBin,
)

# Initialize database tables if database does not already exist
init_db()

app = FastAPI(
    title="Elexon Wind Backtest API",
    description="GB Day-Ahead Market Wind Generation Forecast vs Actual Backtest API",
    version="1.0.0",
)

# Enable CORS for cross-origin local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define an APIRouter for all endpoints
router = APIRouter()


@router.get("/export/csv", tags=["Export"])
def export_csv_data(
    cutoff: Optional[str] = Query(None, description="Cutoff time in HH:MM UTC (default: 09:00)"),
) -> Response:
    """
    Export all evaluated settlement slots (1,488 rows) to CSV format
    with start_time, forecast_mw, actual_mw, error_mw, publish_time, lead_time_hours.
    """
    cutoff_val = cutoff or settings.cutoff_time
    start_d = date.fromisoformat(settings.delivery_start_date)
    end_d = date.fromisoformat(settings.delivery_end_date)

    conn = get_connection(read_only=True)
    try:
        all_slots = []
        cur_d = start_d
        while cur_d <= end_d:
            res = align_and_join_day(delivery_date=cur_d.isoformat(), cutoff_time=cutoff_val, conn=conn)
            for s in res.slots:
                if s.status == "EVALUATED":
                    all_slots.append(s)
            cur_d += timedelta(days=1)
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "start_time",
        "settlement_date",
        "settlement_period",
        "forecast_generation_mw",
        "actual_generation_mw",
        "error_mw",
        "forecast_publish_time",
        "actual_publish_time",
        "lead_time_hours",
    ])
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

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="elexon_wind_backtest_january_2026.csv"',
        },
    )


@router.get("/health", tags=["System"])
def health_check() -> Dict[str, str]:
    """Check API operational health status."""
    return {"status": "ok", "service": "elexon-wind-backtest"}


@router.get("/config", tags=["Configuration"])
def get_config() -> Dict[str, Any]:
    """Retrieve current backtest parameters and operating date ranges."""
    return {
        "elexon_base_url": settings.elexon_base_url,
        "cutoff_time": settings.cutoff_time,
        "decision_start_date": settings.decision_start_date,
        "decision_end_date": settings.decision_end_date,
        "delivery_start_date": settings.delivery_start_date,
        "delivery_end_date": settings.delivery_end_date,
        "resolution_alignment": "Option A (Hourly forecast broadcast across both HH:00 and HH:30 slots)",
    }


@router.get("/comparison", tags=["Backtest Evaluation"])
def get_day_comparison(
    date: str = Query(..., description="Delivery date (YYYY-MM-DD)", examples=["2026-01-02"]),
    cutoff: Optional[str] = Query(None, description="Cutoff time in HH:MM UTC (default: 09:00)", examples=["09:00"]),
) -> Dict[str, Any]:
    """
    Get 48 half-hour settlement slots for a single delivery day:
    forecast, actual outturn, error, publishTime, and lead time.
    """
    try:
        from datetime import date as dt_date
        dt_date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")

    cutoff_val = cutoff or settings.cutoff_time
    result = align_and_join_day(delivery_date=date, cutoff_time=cutoff_val)
    return result.to_dict()


@router.get("/metrics", tags=["Metrics"])
def get_overall_metrics(
    cutoff: Optional[str] = Query(None, description="Cutoff time in HH:MM UTC (default: 09:00)"),
) -> Dict[str, Any]:
    """
    Overall backtest summary metrics across all delivery days in the evaluation period:
    MAE, Bias, RMSE, P10/P50/P90, recommended buffer, and in-sample bias-corrected view.
    """
    cutoff_val = cutoff or settings.cutoff_time
    start_d = date.fromisoformat(settings.delivery_start_date)
    end_d = date.fromisoformat(settings.delivery_end_date)

    conn = get_connection(read_only=True)
    try:
        all_evaluated_slots = []
        total_slots = 0
        cur_d = start_d
        while cur_d <= end_d:
            res = align_and_join_day(delivery_date=cur_d.isoformat(), cutoff_time=cutoff_val, conn=conn)
            total_slots += res.total_slots
            all_evaluated_slots.extend([s for s in res.slots if s.status == "EVALUATED"])
            cur_d += timedelta(days=1)

        metrics = calculate_overall_metrics(all_evaluated_slots, total_slots)
        return metrics.to_dict()
    finally:
        conn.close()


@router.get("/metrics/daily", tags=["Metrics"])
def get_daily_metrics(
    cutoff: Optional[str] = Query(None, description="Cutoff time in HH:MM UTC (default: 09:00)"),
) -> List[Dict[str, Any]]:
    """Daily error metrics (MAE, Bias, RMSE, max shortfall) across every delivery day in the month."""
    cutoff_val = cutoff or settings.cutoff_time
    start_d = date.fromisoformat(settings.delivery_start_date)
    end_d = date.fromisoformat(settings.delivery_end_date)

    conn = get_connection(read_only=True)
    try:
        days_results = []
        cur_d = start_d
        while cur_d <= end_d:
            res = align_and_join_day(delivery_date=cur_d.isoformat(), cutoff_time=cutoff_val, conn=conn)
            days_results.append(res)
            cur_d += timedelta(days=1)

        daily = calculate_daily_metrics(days_results)
        return [d.to_dict() for d in daily]
    finally:
        conn.close()


@router.get("/metrics/by-hour", tags=["Metrics"])
def get_hourly_metrics(
    cutoff: Optional[str] = Query(None, description="Cutoff time in HH:MM UTC (default: 09:00)"),
) -> List[Dict[str, Any]]:
    """Metrics aggregated by hour of the day (00:00 to 23:00) across the entire backtest."""
    cutoff_val = cutoff or settings.cutoff_time
    start_d = date.fromisoformat(settings.delivery_start_date)
    end_d = date.fromisoformat(settings.delivery_end_date)

    conn = get_connection(read_only=True)
    try:
        all_evaluated_slots = []
        cur_d = start_d
        while cur_d <= end_d:
            res = align_and_join_day(delivery_date=cur_d.isoformat(), cutoff_time=cutoff_val, conn=conn)
            all_evaluated_slots.extend([s for s in res.slots if s.status == "EVALUATED"])
            cur_d += timedelta(days=1)

        hourly = calculate_hourly_metrics(all_evaluated_slots)
        return [h.to_dict() for h in hourly]
    finally:
        conn.close()


@router.get("/metrics/horizon", tags=["Metrics"])
def get_horizon_metrics() -> List[Dict[str, Any]]:
    """
    Horizon analysis: scores ALL forecasts published prior to delivery slots,
    grouped by lead time (0-6h, 6-12h, ... 42-48h).
    """
    horizon = calculate_horizon_metrics()
    return [h.to_dict() for h in horizon]


@router.get("/metrics/histogram", tags=["Metrics"])
def get_histogram_metrics(
    cutoff: Optional[str] = Query(None, description="Cutoff time in HH:MM UTC (default: 09:00)"),
    bins: int = Query(16, ge=5, le=50, description="Number of histogram bins"),
) -> List[Dict[str, Any]]:
    """Error distribution histogram bins showing frequencies and percentages."""
    cutoff_val = cutoff or settings.cutoff_time
    start_d = date.fromisoformat(settings.delivery_start_date)
    end_d = date.fromisoformat(settings.delivery_end_date)

    conn = get_connection(read_only=True)
    try:
        all_evaluated_slots = []
        cur_d = start_d
        while cur_d <= end_d:
            res = align_and_join_day(delivery_date=cur_d.isoformat(), cutoff_time=cutoff_val, conn=conn)
            all_evaluated_slots.extend([s for s in res.slots if s.status == "EVALUATED"])
            cur_d += timedelta(days=1)

        hist = calculate_error_histogram(all_evaluated_slots, num_bins=bins)
        return [b.to_dict() for b in hist]
    finally:
        conn.close()


# Mount the router both with prefix="/api" AND at root "/"
# This ensures that whether Vercel passes "/api/..." or strips the "/api" prefix,
# both paths match and work flawlessly.
app.include_router(router, prefix="/api")
app.include_router(router)
