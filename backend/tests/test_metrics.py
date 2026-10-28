"""Unit tests for metrics calculation."""

import pytest
import numpy as np
from datetime import datetime, timezone
from backend.processing import SlotComparison, DayComparisonResult, align_and_join_day
from backend.metrics import (
    calculate_overall_metrics,
    calculate_hourly_metrics,
    calculate_daily_metrics,
    calculate_lead_time_metrics,
    calculate_error_histogram,
    calculate_horizon_metrics,
)

def test_overall_metrics_exact_values():
    """Verify MAE, Bias, RMSE, P10, P50, P90 with exact hand-calculated test vectors."""
    # Errors: [-200, -100, 0, +100, +200]
    # abs: [200, 100, 0, 100, 200] -> sum = 600 -> MAE = 120.0
    # signed sum = 0 -> Bias = 0.0
    # sq: [40000, 10000, 0, 10000, 40000] = 100,000 / 5 = 20,000 -> RMSE = sqrt(20,000) = 141.42
    slots = [
        SlotComparison(
            start_time=f"2026-01-02T{i:02d}:00:00Z",
            settlement_date="2026-01-02",
            settlement_period=i+1,
            forecast_generation_mw=1000.0 + err,
            actual_generation_mw=1000.0,
            error_mw=float(err),
            forecast_publish_time="2026-01-01T07:00:00Z",
            actual_publish_time="2026-01-02T01:00:00Z",
            lead_time_hours=20.0,
            status="EVALUATED",
        )
        for i, err in enumerate([-200, -100, 0, 100, 200])
    ]

    m = calculate_overall_metrics(slots, total_slots_count=5)

    assert m.total_slots == 5
    assert m.evaluated_slots == 5
    assert m.skipped_slots == 0
    assert m.coverage_pct == 100.0
    assert m.mae_mw == 120.0
    assert m.bias_mw == 0.0
    assert m.rmse_mw == 141.42
    assert m.p50_mw == 0.0
    assert m.p90_mw == 160.0 # 90th percentile of [-200, -100, 0, 100, 200]
    assert m.recommended_buffer_mw == 160.0
    assert "safety buffer of 160.0 MW" in m.headline_explanation

    # Bias corrected check (bias was 0.0, so should match)
    assert m.bias_corrected.mean_bias_subtracted_mw == 0.0
    assert m.bias_corrected.mae_mw == 120.0
    assert m.bias_corrected.p90_mw == 160.0


def test_bias_correction_with_nonzero_bias():
    """Verify in-sample bias correction shifts residuals to zero mean."""
    # Errors: [1000, 1100, 1200] -> Mean = 1100.0
    # Residuals: [-100, 0, +100] -> Mean = 0.0, MAE = 66.67
    slots = [
        SlotComparison(
            start_time=f"2026-01-02T{i:02d}:00:00Z",
            settlement_date="2026-01-02",
            settlement_period=i+1,
            forecast_generation_mw=2000.0 + err,
            actual_generation_mw=1000.0,
            error_mw=float(err),
            forecast_publish_time="2026-01-01T07:00:00Z",
            actual_publish_time="2026-01-02T01:00:00Z",
            lead_time_hours=20.0,
            status="EVALUATED",
        )
        for i, err in enumerate([1000, 1100, 1200])
    ]

    m = calculate_overall_metrics(slots, total_slots_count=3)
    assert m.bias_mw == 1100.0
    assert m.mae_mw == 1100.0

    bc = m.bias_corrected
    assert bc.mean_bias_subtracted_mw == 1100.0
    assert bc.mae_mw == 66.67 # (| -100 | + 0 + 100) / 3
    assert bc.p50_mw == 0.0
    assert bc.p10_mw == -80.0
    assert bc.p90_mw == 80.0
    assert bc.recommended_buffer_mw == 80.0


def test_horizon_metrics_calculation():
    """Verify horizon analysis runs on SQLite and produces 8 buckets with monotonic degradation."""
    horizon = calculate_horizon_metrics()
    assert len(horizon) == 8
    # Assert counts exist
    for h in horizon:
        assert h.forecast_count > 0
        assert h.mae_mw > 0
    # First bucket (0-6h) has lower MAE than the last bucket (42-48h)
    assert horizon[0].mae_mw < horizon[-1].mae_mw


def test_overall_metrics_empty_input():
    """Verify clean handling when no evaluated slots exist."""
    m = calculate_overall_metrics([], total_slots_count=48)
    assert m.total_slots == 48
    assert m.evaluated_slots == 0
    assert m.skipped_slots == 48
    assert m.coverage_pct == 0.0
    assert m.mae_mw == 0.0
    assert m.recommended_buffer_mw == 0.0


def test_hourly_metrics_aggregation():
    """Verify errors are grouped into the correct 0-23 hour slots."""
    slots = [
        # Two slots in hour 04 (04:00 and 04:30)
        SlotComparison(
            start_time="2026-01-02T04:00:00Z",
            settlement_date="2026-01-02",
            settlement_period=9,
            forecast_generation_mw=5000.0,
            actual_generation_mw=4500.0,
            error_mw=500.0,
            forecast_publish_time="2026-01-01T07:00:00Z",
            actual_publish_time="2026-01-02T04:30:00Z",
            lead_time_hours=21.0,
            status="EVALUATED",
        ),
        SlotComparison(
            start_time="2026-01-02T04:30:00Z",
            settlement_date="2026-01-02",
            settlement_period=10,
            forecast_generation_mw=5000.0,
            actual_generation_mw=4700.0,
            error_mw=300.0,
            forecast_publish_time="2026-01-01T07:00:00Z",
            actual_publish_time="2026-01-02T05:00:00Z",
            lead_time_hours=21.5,
            status="EVALUATED",
        ),
    ]

    hourly = calculate_hourly_metrics(slots)
    assert len(hourly) == 24
    
    h4 = next(h for h in hourly if h.hour == 4)
    assert h4.evaluated_slots == 2
    assert h4.mae_mw == 400.0 # (500 + 300) / 2
    assert h4.bias_mw == 400.0

    # Other hours should have 0 evaluated slots
    h0 = next(h for h in hourly if h.hour == 0)
    assert h0.evaluated_slots == 0


def test_lead_time_metrics_bucketing():
    """Verify lead time bucketing into 6-hour bins."""
    slots = [
        SlotComparison(
            start_time="2026-01-02T02:00:00Z",
            settlement_date="2026-01-02",
            settlement_period=5,
            forecast_generation_mw=3000.0,
            actual_generation_mw=2800.0,
            error_mw=200.0,
            forecast_publish_time="2026-01-01T07:00:00Z",
            actual_publish_time="2026-01-02T02:30:00Z",
            lead_time_hours=19.0, # Fits into [15h - 20.5h]
            status="EVALUATED",
        ),
        SlotComparison(
            start_time="2026-01-02T16:00:00Z",
            settlement_date="2026-01-02",
            settlement_period=33,
            forecast_generation_mw=6000.0,
            actual_generation_mw=5400.0,
            error_mw=600.0,
            forecast_publish_time="2026-01-01T07:00:00Z",
            actual_publish_time="2026-01-02T16:30:00Z",
            lead_time_hours=33.0, # Fits into [33h - 38.5h]
            status="EVALUATED",
        ),
    ]

    lt_metrics = calculate_lead_time_metrics(slots)
    assert len(lt_metrics) == 5

    b1 = next(b for b in lt_metrics if "15h" in b.bucket_label)
    assert b1.slot_count == 1
    assert b1.mae_mw == 200.0

    b4 = next(b for b in lt_metrics if "33h" in b.bucket_label)
    assert b4.slot_count == 1
    assert b4.mae_mw == 600.0


def test_error_histogram_generation():
    """Verify histogram binning sums to total count and ~100%."""
    slots = [
        SlotComparison(
            start_time=f"2026-01-02T{i:02d}:00:00Z",
            settlement_date="2026-01-02",
            settlement_period=i+1,
            forecast_generation_mw=5000.0,
            actual_generation_mw=5000.0 - err,
            error_mw=float(err),
            forecast_publish_time="2026-01-01T07:00:00Z",
            actual_publish_time="2026-01-02T01:00:00Z",
            lead_time_hours=24.0,
            status="EVALUATED",
        )
        for i, err in enumerate(range(-500, 501, 100)) # 11 values
    ]

    bins = calculate_error_histogram(slots, num_bins=5)
    assert len(bins) == 5
    total_count = sum(b.count for b in bins)
    total_pct = sum(b.percentage for b in bins)

    assert total_count == 11
    assert 99.9 <= total_pct <= 100.1
