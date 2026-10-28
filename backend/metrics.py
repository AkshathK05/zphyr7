"""Statistical metrics computation for wind generation backtesting."""

import math
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import numpy as np

from backend.processing import SlotComparison, DayComparisonResult

@dataclass
class BiasCorrectedMetrics:
    """In-sample bias-corrected error distribution (errors centered around 0)."""
    mean_bias_subtracted_mw: float
    mae_mw: float
    p10_mw: float
    p50_mw: float
    p90_mw: float
    recommended_buffer_mw: float
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class OverallMetrics:
    """Overall summary statistics across all evaluated slots."""
    total_slots: int
    evaluated_slots: int
    skipped_slots: int
    coverage_pct: float
    mae_mw: float
    bias_mw: float
    rmse_mw: float
    p10_mw: float
    p50_mw: float
    p90_mw: float
    min_error_mw: float
    max_error_mw: float
    std_error_mw: float
    recommended_buffer_mw: float
    headline_explanation: str
    bias_corrected: BiasCorrectedMetrics

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class HourlyMetric:
    """Error metrics aggregated by hour of the day (0-23)."""
    hour: int
    hour_label: str
    evaluated_slots: int
    mae_mw: float
    bias_mw: float
    rmse_mw: float
    p10_mw: float
    p50_mw: float
    p90_mw: float
    avg_forecast_mw: float
    avg_actual_mw: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class DailyMetric:
    """Error metrics for each delivery day in the backtest."""
    delivery_date: str
    decision_date: str
    cutoff_time: str
    evaluated_slots: int
    skipped_slots: int
    mae_mw: float
    bias_mw: float
    rmse_mw: float
    p10_mw: float
    p50_mw: float
    p90_mw: float
    max_shortfall_mw: float  # Maximum positive error (largest underdelivery)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class HorizonBucketMetric:
    """Metrics grouped by forecast horizon across all forecasts published prior to delivery."""
    bucket_label: str
    min_hours: float
    max_hours: float
    forecast_count: int
    mae_mw: float
    bias_mw: float
    rmse_mw: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class LeadTimeMetric:
    """Legacy alias / per-slot lead time metric."""
    bucket_label: str
    min_hours: float
    max_hours: float
    slot_count: int
    mae_mw: float
    bias_mw: float
    rmse_mw: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class HistogramBin:
    """A single bucket in the error distribution histogram."""
    bin_start_mw: float
    bin_end_mw: float
    count: int
    percentage: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_bias_corrected_spread(errors: np.ndarray) -> BiasCorrectedMetrics:
    """
    Compute in-sample bias-corrected metrics from a single array of raw signed errors:
    1. Computes mean bias.
    2. Subtracts mean bias: residual_errors = errors - mean_bias.
    3. Computes MAE, P10, P50, and P90 from residual_errors in one unified function.
    """
    if len(errors) == 0:
        return BiasCorrectedMetrics(
            mean_bias_subtracted_mw=0.0,
            mae_mw=0.0,
            p10_mw=0.0,
            p50_mw=0.0,
            p90_mw=0.0,
            recommended_buffer_mw=0.0,
            explanation="No errors available.",
        )

    mean_bias = float(np.mean(errors))
    residuals = errors - mean_bias

    bc_mae = float(np.mean(np.abs(residuals)))
    bc_p10 = float(np.percentile(residuals, 10))
    bc_p50 = float(np.percentile(residuals, 50))
    bc_p90 = float(np.percentile(residuals, 90))
    bc_buffer = round(max(0.0, bc_p90), 1)

    return BiasCorrectedMetrics(
        mean_bias_subtracted_mw=round(mean_bias, 2),
        mae_mw=round(bc_mae, 2),
        p10_mw=round(bc_p10, 2),
        p50_mw=round(bc_p50, 2),
        p90_mw=round(bc_p90, 2),
        recommended_buffer_mw=bc_buffer,
        explanation=(
            f"In-sample bias-corrected view (after subtracting mean bias of {mean_bias:+,.1f} MW): "
            f"residual MAE is {bc_mae:,.1f} MW, with an asymmetric spread of P10 = {bc_p10:+,.1f} MW "
            f"to P90 = {bc_p90:+,.1f} MW. Sizing an in-sample buffer against the residual volatility requires {bc_buffer:,.1f} MW."
        ),
    )


def calculate_overall_metrics(evaluated_slots: List[SlotComparison], total_slots_count: int) -> OverallMetrics:
    """
    Compute overall backtest metrics: MAE, Bias, RMSE, P10/P50/P90, recommended buffer,
    and in-sample bias-corrected spread via compute_bias_corrected_spread.
    """
    if not evaluated_slots:
        empty_bc = BiasCorrectedMetrics(
            mean_bias_subtracted_mw=0.0,
            mae_mw=0.0,
            p10_mw=0.0,
            p50_mw=0.0,
            p90_mw=0.0,
            recommended_buffer_mw=0.0,
            explanation="No data available for bias correction.",
        )
        return OverallMetrics(
            total_slots=total_slots_count,
            evaluated_slots=0,
            skipped_slots=total_slots_count,
            coverage_pct=0.0,
            mae_mw=0.0,
            bias_mw=0.0,
            rmse_mw=0.0,
            p10_mw=0.0,
            p50_mw=0.0,
            p90_mw=0.0,
            min_error_mw=0.0,
            max_error_mw=0.0,
            std_error_mw=0.0,
            recommended_buffer_mw=0.0,
            headline_explanation="No slots evaluated.",
            bias_corrected=empty_bc,
        )

    errors = np.array([s.error_mw for s in evaluated_slots if s.error_mw is not None], dtype=float)
    n = len(errors)
    skipped = total_slots_count - n

    mae = float(np.mean(np.abs(errors)))
    bias = float(np.mean(errors))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    p10 = float(np.percentile(errors, 10))
    p50 = float(np.percentile(errors, 50))
    p90 = float(np.percentile(errors, 90))
    min_err = float(np.min(errors))
    max_err = float(np.max(errors))
    std_err = float(np.std(errors, ddof=0))

    # P90 of signed error represents the 90th percentile shortfall
    recommended_buffer = round(max(0.0, p90), 1)

    headline = (
        f"On average the day-ahead forecast missed actual wind generation by {mae:,.1f} MW (MAE). "
        f"Overall bias was {bias:+,.1f} MW (forecasts systematically exceeded metered outturn; "
        f"a likely cause is curtailment / constraint actions on wind farms reducing metered output relative to forecast potential, "
        f"though verifying this requires out-of-scope constraint data). In 90% of half-hour slots, wind generation was no more "
        f"than {recommended_buffer:,.1f} MW below forecast. Sizing a safety buffer of {recommended_buffer:,.1f} MW "
        f"would have protected the utility against shortfall in 90% of settlement periods."
    )

    # Compute in-sample bias-corrected spread in unified function
    bias_corrected = compute_bias_corrected_spread(errors)

    return OverallMetrics(
        total_slots=total_slots_count,
        evaluated_slots=n,
        skipped_slots=skipped,
        coverage_pct=round((n / total_slots_count) * 100.0, 2) if total_slots_count > 0 else 0.0,
        mae_mw=round(mae, 2),
        bias_mw=round(bias, 2),
        rmse_mw=round(rmse, 2),
        p10_mw=round(p10, 2),
        p50_mw=round(p50, 2),
        p90_mw=round(p90, 2),
        min_error_mw=round(min_err, 2),
        max_error_mw=round(max_err, 2),
        std_error_mw=round(std_err, 2),
        recommended_buffer_mw=recommended_buffer,
        headline_explanation=headline,
        bias_corrected=bias_corrected,
    )

    return OverallMetrics(
        total_slots=total_slots_count,
        evaluated_slots=n,
        skipped_slots=skipped,
        coverage_pct=round((n / total_slots_count) * 100.0, 2) if total_slots_count > 0 else 0.0,
        mae_mw=round(mae, 2),
        bias_mw=round(bias, 2),
        rmse_mw=round(rmse, 2),
        p10_mw=round(p10, 2),
        p50_mw=round(p50, 2),
        p90_mw=round(p90, 2),
        min_error_mw=round(min_err, 2),
        max_error_mw=round(max_err, 2),
        std_error_mw=round(std_err, 2),
        recommended_buffer_mw=recommended_buffer,
        headline_explanation=headline,
        bias_corrected=bias_corrected,
    )


def calculate_hourly_metrics(evaluated_slots: List[SlotComparison]) -> List[HourlyMetric]:
    """Calculate error statistics aggregated by hour of the day (00:00 to 23:00)."""
    by_hour: Dict[int, List[SlotComparison]] = {h: [] for h in range(24)}

    for s in evaluated_slots:
        if s.error_mw is not None:
            # Parse hour from start_time string 'YYYY-MM-DDTHH:MM:SSZ'
            h = int(s.start_time[11:13])
            by_hour[h].append(s)

    results: List[HourlyMetric] = []
    for h in range(24):
        slots_h = by_hour[h]
        if not slots_h:
            results.append(HourlyMetric(
                hour=h,
                hour_label=f"{h:02d}:00",
                evaluated_slots=0,
                mae_mw=0.0,
                bias_mw=0.0,
                rmse_mw=0.0,
                p10_mw=0.0,
                p50_mw=0.0,
                p90_mw=0.0,
                avg_forecast_mw=0.0,
                avg_actual_mw=0.0,
            ))
            continue

        errors = np.array([s.error_mw for s in slots_h], dtype=float)
        fcs = np.array([s.forecast_generation_mw for s in slots_h], dtype=float)
        acts = np.array([s.actual_generation_mw for s in slots_h], dtype=float)

        results.append(HourlyMetric(
            hour=h,
            hour_label=f"{h:02d}:00",
            evaluated_slots=len(errors),
            mae_mw=round(float(np.mean(np.abs(errors))), 2),
            bias_mw=round(float(np.mean(errors)), 2),
            rmse_mw=round(float(np.sqrt(np.mean(errors ** 2))), 2),
            p10_mw=round(float(np.percentile(errors, 10)), 2),
            p50_mw=round(float(np.percentile(errors, 50)), 2),
            p90_mw=round(float(np.percentile(errors, 90)), 2),
            avg_forecast_mw=round(float(np.mean(fcs)), 1),
            avg_actual_mw=round(float(np.mean(acts)), 1),
        ))

    return results


def calculate_daily_metrics(days_results: List[DayComparisonResult]) -> List[DailyMetric]:
    """Calculate daily performance metrics across each delivery day in the backtest."""
    metrics: List[DailyMetric] = []

    for day in days_results:
        eval_slots = [s for s in day.slots if s.status == "EVALUATED" and s.error_mw is not None]
        if not eval_slots:
            metrics.append(DailyMetric(
                delivery_date=day.delivery_date,
                decision_date=day.decision_date,
                cutoff_time=day.cutoff_time,
                evaluated_slots=0,
                skipped_slots=day.skipped_slots,
                mae_mw=0.0,
                bias_mw=0.0,
                rmse_mw=0.0,
                p10_mw=0.0,
                p50_mw=0.0,
                p90_mw=0.0,
                max_shortfall_mw=0.0,
            ))
            continue

        errors = np.array([s.error_mw for s in eval_slots], dtype=float)
        max_shortfall = float(np.max(errors))

        metrics.append(DailyMetric(
            delivery_date=day.delivery_date,
            decision_date=day.decision_date,
            cutoff_time=day.cutoff_time,
            evaluated_slots=len(errors),
            skipped_slots=day.skipped_slots,
            mae_mw=round(float(np.mean(np.abs(errors))), 2),
            bias_mw=round(float(np.mean(errors)), 2),
            rmse_mw=round(float(np.sqrt(np.mean(errors ** 2))), 2),
            p10_mw=round(float(np.percentile(errors, 10)), 2),
            p50_mw=round(float(np.percentile(errors, 50)), 2),
            p90_mw=round(float(np.percentile(errors, 90)), 2),
            max_shortfall_mw=round(max(0.0, max_shortfall), 2),
        ))

    return metrics


def calculate_horizon_metrics(
    conn = None,
    delivery_start_date: Optional[str] = None,
    delivery_end_date: Optional[str] = None,
) -> List[HorizonBucketMetric]:
    """
    Score ALL forecasts published before each delivery slot, bucketed by lead time horizon:
    [0h - 6h), [6h - 12h), [12h - 18h), [18h - 24h), [24h - 30h), [30h - 36h), [36h - 42h), [42h - 48h].
    
    This avoids diurnal confounding with the fixed cutoff and evaluates how forecast
    accuracy improves monotonically as the delivery horizon nears.
    """
    from backend.config import settings
    from backend.database import get_connection

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    start_date = delivery_start_date or settings.delivery_start_date
    end_date = delivery_end_date or settings.delivery_end_date

    try:
        cursor = conn.cursor()
        # 1. Fetch actuals across delivery range
        cursor.execute("""
            SELECT start_time, generation FROM fuelhh_actuals
            WHERE settlement_date >= ? AND settlement_date <= ? AND fuel_type = 'WIND'
        """, (start_date, end_date))
        actuals = {r["start_time"]: float(r["generation"]) for r in cursor.fetchall()}

        if not actuals:
            return []

        # 2. Fetch all forecasts targeting dates within the delivery range
        start_bound = f"{start_date}T00:00:00Z"
        end_bound = f"{end_date}T23:59:59Z"
        cursor.execute("""
            SELECT start_time, publish_time, generation FROM windfor_forecasts
            WHERE start_time >= ? AND start_time <= ?
        """, (start_bound, end_bound))
        forecasts = cursor.fetchall()
    finally:
        if close_conn:
            conn.close()

    buckets = [
        ("0h - 6h", 0.0, 6.0),
        ("6h - 12h", 6.0, 12.0),
        ("12h - 18h", 12.0, 18.0),
        ("18h - 24h", 18.0, 24.0),
        ("24h - 30h", 24.0, 30.0),
        ("30h - 36h", 30.0, 36.0),
        ("36h - 42h", 36.0, 42.0),
        ("42h - 48h", 42.0, 48.0),
    ]

    bucket_errors: Dict[str, List[float]] = {b[0]: [] for b in buckets}

    # Match each hourly forecast to both :00 and :30 delivery actuals (Option A)
    from datetime import datetime
    for r in forecasts:
        fc_st = r["start_time"]
        fc_gen = float(r["generation"])
        fc_pt_dt = datetime.fromisoformat(r["publish_time"].replace("Z", "+00:00"))

        dt_00 = datetime.fromisoformat(fc_st.replace("Z", "+00:00"))
        dt_30 = dt_00.replace(minute=30)

        targets = [
            (dt_00.strftime("%Y-%m-%dT%H:%M:%SZ"), dt_00),
            (dt_30.strftime("%Y-%m-%dT%H:%M:%SZ"), dt_30),
        ]

        for slot_str, slot_dt in targets:
            act_gen = actuals.get(slot_str)
            if act_gen is not None:
                lead_h = (slot_dt - fc_pt_dt).total_seconds() / 3600.0
                if 0.0 <= lead_h <= 48.0:
                    err = fc_gen - act_gen
                    for label, min_h, max_h in buckets:
                        if min_h <= lead_h < max_h or (max_h == 48.0 and lead_h == 48.0):
                            bucket_errors[label].append(err)
                            break

    results: List[HorizonBucketMetric] = []
    for label, min_h, max_h in buckets:
        errs = np.array(bucket_errors[label], dtype=float)
        if len(errs) == 0:
            results.append(HorizonBucketMetric(
                bucket_label=label,
                min_hours=min_h,
                max_hours=max_h,
                forecast_count=0,
                mae_mw=0.0,
                bias_mw=0.0,
                rmse_mw=0.0,
            ))
        else:
            results.append(HorizonBucketMetric(
                bucket_label=label,
                min_hours=min_h,
                max_hours=max_h,
                forecast_count=len(errs),
                mae_mw=round(float(np.mean(np.abs(errs))), 2),
                bias_mw=round(float(np.mean(errs)), 2),
                rmse_mw=round(float(np.sqrt(np.mean(errs ** 2))), 2),
            ))

    return results


def calculate_lead_time_metrics(evaluated_slots: List[SlotComparison]) -> List[LeadTimeMetric]:
    """
    Group errors by forecast lead time into 6-hour buckets:
    [15h, 21h), [21h, 27h), [27h, 33h), [33h, 39h), [39h, 45h]
    """
    buckets = [
        ("15h - 20.5h", 15.0, 20.99),
        ("21h - 26.5h", 21.0, 26.99),
        ("27h - 32.5h", 27.0, 32.99),
        ("33h - 38.5h", 33.0, 38.99),
        ("39h - 44.5h", 39.0, 45.0),
    ]

    results: List[LeadTimeMetric] = []

    for label, min_h, max_h in buckets:
        matching = [
            s for s in evaluated_slots
            if s.lead_time_hours is not None and min_h <= s.lead_time_hours <= max_h and s.error_mw is not None
        ]

        if not matching:
            results.append(LeadTimeMetric(
                bucket_label=label,
                min_hours=min_h,
                max_hours=max_h,
                slot_count=0,
                mae_mw=0.0,
                bias_mw=0.0,
                rmse_mw=0.0,
            ))
            continue

        errors = np.array([s.error_mw for s in matching], dtype=float)
        results.append(LeadTimeMetric(
            bucket_label=label,
            min_hours=min_h,
            max_hours=max_h,
            slot_count=len(errors),
            mae_mw=round(float(np.mean(np.abs(errors))), 2),
            bias_mw=round(float(np.mean(errors)), 2),
            rmse_mw=round(float(np.sqrt(np.mean(errors ** 2))), 2),
        ))

    return results


def calculate_error_histogram(evaluated_slots: List[SlotComparison], num_bins: int = 16) -> List[HistogramBin]:
    """Compute histogram distribution of errors for frontend chart rendering."""
    errors = [s.error_mw for s in evaluated_slots if s.error_mw is not None]
    if not errors:
        return []

    counts, bin_edges = np.histogram(errors, bins=num_bins)
    total = len(errors)
    bins: List[HistogramBin] = []

    for i in range(len(counts)):
        bins.append(HistogramBin(
            bin_start_mw=round(float(bin_edges[i]), 1),
            bin_end_mw=round(float(bin_edges[i + 1]), 1),
            count=int(counts[i]),
            percentage=round((float(counts[i]) / total) * 100.0, 2),
        ))

    return bins
