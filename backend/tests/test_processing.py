"""Unit tests for cutoff selection, Option A resolution alignment, and error calculation."""

import pytest
from datetime import datetime, timezone
from backend.processing import (
    compute_decision_cutoff,
    select_best_forecasts_for_slots,
    align_and_join_day,
)
from backend.database import get_connection

def test_compute_decision_cutoff():
    """Verify decision cutoff falls on D-1 at the configured UTC hour/minute."""
    cutoff = compute_decision_cutoff("2026-01-02", "09:00")
    expected = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    assert cutoff == expected

    # Test edge of month
    cutoff_first = compute_decision_cutoff("2026-01-01", "12:00")
    assert cutoff_first == datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_cutoff_boundary_conditions():
    """
    Test edge cases around the decision cutoff:
    - Forecast published EXACTLY at the cutoff: must be included (<= cutoff).
    - Forecast published 1 second after the cutoff: must be excluded (no lookahead).
    """
    cutoff = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    target_slot = "2026-01-02T10:00:00Z"

    forecasts = [
        # Exactly at cutoff (09:00:00Z)
        {
            "start_time": target_slot,
            "publish_time": "2026-01-01T09:00:00Z",
            "generation": 5000.0,
        },
        # 1 second after cutoff (09:00:01Z) - Lookahead violation
        {
            "start_time": target_slot,
            "publish_time": "2026-01-01T09:00:01Z",
            "generation": 9999.0,
        },
    ]

    selected = select_best_forecasts_for_slots(forecasts, cutoff)
    assert target_slot in selected
    # Must pick the one at 09:00:00Z, never the one at 09:00:01Z
    assert selected[target_slot]["publish_time"] == "2026-01-01T09:00:00Z"
    assert selected[target_slot]["generation"] == 5000.0


def test_latest_forecast_selection_before_cutoff():
    """
    When multiple forecasts are published before the cutoff, the latest one must be chosen.
    """
    cutoff = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    target_slot = "2026-01-02T12:00:00Z"

    forecasts = [
        {"start_time": target_slot, "publish_time": "2025-12-31T20:00:00Z", "generation": 3000.0},
        {"start_time": target_slot, "publish_time": "2026-01-01T04:30:00Z", "generation": 4000.0},
        {"start_time": target_slot, "publish_time": "2026-01-01T07:30:00Z", "generation": 4500.0}, # Latest <= 09:00
        {"start_time": target_slot, "publish_time": "2026-01-01T11:00:00Z", "generation": 6000.0}, # After cutoff
    ]

    selected = select_best_forecasts_for_slots(forecasts, cutoff)
    assert selected[target_slot]["publish_time"] == "2026-01-01T07:30:00Z"
    assert selected[target_slot]["generation"] == 4500.0


def test_per_target_hour_selection_when_latest_run_is_incomplete():
    """
    Confirm forecast selection is done strictly per target hour (startTime),
    NOT by selecting a single forecast run for the entire day.
    
    Scenario:
    - Run 1 published at 04:30 covers both 10:00 and 20:00.
    - Run 2 published at 07:30 covers ONLY 10:00 (incomplete run, e.g. aborted or short horizon).
    - Cutoff is 09:00.
    Expected:
    - 10:00 uses Run 2 (published 07:30, 5200 MW).
    - 20:00 falls back to Run 1 (published 04:30, 4800 MW), because Run 2 has no entry for 20:00.
    """
    cutoff = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    slot_10 = "2026-01-02T10:00:00Z"
    slot_20 = "2026-01-02T20:00:00Z"

    forecasts = [
        # Earlier Run 1 (04:30) covering both hours
        {"start_time": slot_10, "publish_time": "2026-01-01T04:30:00Z", "generation": 4000.0},
        {"start_time": slot_20, "publish_time": "2026-01-01T04:30:00Z", "generation": 4800.0},
        # Later Run 2 (07:30) covering ONLY slot_10
        {"start_time": slot_10, "publish_time": "2026-01-01T07:30:00Z", "generation": 5200.0},
    ]

    selected = select_best_forecasts_for_slots(forecasts, cutoff)

    assert selected[slot_10]["publish_time"] == "2026-01-01T07:30:00Z"
    assert selected[slot_10]["generation"] == 5200.0

    assert selected[slot_20]["publish_time"] == "2026-01-01T04:30:00Z"
    assert selected[slot_20]["generation"] == 4800.0


def test_lead_time_hours_calculation():
    """
    Verify lead_time_hours = (startTime - publishTime) in hours.
    """
    delivery_date = "2026-01-02"
    cutoff_time = "09:00"

    mock_forecasts = [
        # Forecast for 14:00 published on Jan 1 at 08:00 (30 hours prior)
        {"start_time": "2026-01-02T14:00:00Z", "publish_time": "2026-01-01T08:00:00Z", "generation": 6000.0}
    ]
    mock_actuals = [
        {"start_time": "2026-01-02T14:00:00Z", "generation": 5800.0},
        {"start_time": "2026-01-02T14:30:00Z", "generation": 5900.0},
    ]

    res = align_and_join_day(
        delivery_date=delivery_date,
        cutoff_time=cutoff_time,
        custom_actuals=mock_actuals,
        custom_forecasts=mock_forecasts,
    )

    s1 = next(s for s in res.slots if s.start_time == "2026-01-02T14:00:00Z")
    s2 = next(s for s in res.slots if s.start_time == "2026-01-02T14:30:00Z")

    # From 2026-01-01T08:00:00 to 2026-01-02T14:00:00 is exactly 30.0 hours
    assert s1.lead_time_hours == 30.0
    # From 2026-01-01T08:00:00 to 2026-01-02T14:30:00 is 30.5 hours
    assert s2.lead_time_hours == 30.5


def test_option_a_broadcast_maps_hourly_to_both_half_hours():
    """
    Option A requirement:
    One hourly forecast (e.g. 14:00) must map to both 14:00 and 14:30 half-hour slots.
    """
    delivery_date = "2026-01-02"
    cutoff_time = "09:00"

    # Single hourly forecast for 14:00
    mock_forecasts = [
        {
            "start_time": "2026-01-02T14:00:00Z",
            "publish_time": "2026-01-01T07:00:00Z",
            "generation": 8000.0,
        }
    ]

    # Actuals for both 14:00 and 14:30
    mock_actuals = [
        {
            "start_time": "2026-01-02T14:00:00Z",
            "publish_time": "2026-01-02T14:30:00Z",
            "generation": 7500.0,
        },
        {
            "start_time": "2026-01-02T14:30:00Z",
            "publish_time": "2026-01-02T15:00:00Z",
            "generation": 8200.0,
        },
    ]

    res = align_and_join_day(
        delivery_date=delivery_date,
        cutoff_time=cutoff_time,
        custom_actuals=mock_actuals,
        custom_forecasts=mock_forecasts,
    )

    # Find the two 14:xx slots
    slot_14_00 = next(s for s in res.slots if s.start_time == "2026-01-02T14:00:00Z")
    slot_14_30 = next(s for s in res.slots if s.start_time == "2026-01-02T14:30:00Z")

    # Both must receive the 8000 MW forecast
    assert slot_14_00.status == "EVALUATED"
    assert slot_14_00.forecast_generation_mw == 8000.0
    assert slot_14_00.actual_generation_mw == 7500.0
    assert slot_14_00.error_mw == 500.0 # 8000 - 7500

    assert slot_14_30.status == "EVALUATED"
    assert slot_14_30.forecast_generation_mw == 8000.0
    assert slot_14_30.actual_generation_mw == 8200.0
    assert slot_14_30.error_mw == -200.0 # 8000 - 8200


def test_missing_hourly_forecast_skips_both_half_hours():
    """
    Option A rule:
    If an hourly forecast is missing, both of its half-hour slots count as skipped.
    """
    delivery_date = "2026-01-02"
    cutoff_time = "09:00"

    # No forecast for 14:00 provided
    mock_forecasts = []

    # Actuals exist for 14:00 and 14:30
    mock_actuals = [
        {"start_time": "2026-01-02T14:00:00Z", "generation": 7500.0},
        {"start_time": "2026-01-02T14:30:00Z", "generation": 8200.0},
    ]

    res = align_and_join_day(
        delivery_date=delivery_date,
        cutoff_time=cutoff_time,
        custom_actuals=mock_actuals,
        custom_forecasts=mock_forecasts,
    )

    slot_14_00 = next(s for s in res.slots if s.start_time == "2026-01-02T14:00:00Z")
    slot_14_30 = next(s for s in res.slots if s.start_time == "2026-01-02T14:30:00Z")

    assert slot_14_00.status == "SKIPPED"
    assert "Missing forecast" in slot_14_00.skip_reason
    assert slot_14_00.error_mw is None

    assert slot_14_30.status == "SKIPPED"
    assert "Missing forecast" in slot_14_30.skip_reason
    assert slot_14_30.error_mw is None


def test_missing_actual_skips_only_that_slot():
    """
    If actual outturn is missing for 14:30 but present for 14:00:
    14:00 is evaluated, 14:30 is skipped.
    """
    delivery_date = "2026-01-02"
    cutoff_time = "09:00"

    mock_forecasts = [
        {"start_time": "2026-01-02T14:00:00Z", "publish_time": "2026-01-01T06:00:00Z", "generation": 5000.0}
    ]
    # Only 14:00 actual exists
    mock_actuals = [
        {"start_time": "2026-01-02T14:00:00Z", "generation": 4800.0}
    ]

    res = align_and_join_day(
        delivery_date=delivery_date,
        cutoff_time=cutoff_time,
        custom_actuals=mock_actuals,
        custom_forecasts=mock_forecasts,
    )

    slot_14_00 = next(s for s in res.slots if s.start_time == "2026-01-02T14:00:00Z")
    slot_14_30 = next(s for s in res.slots if s.start_time == "2026-01-02T14:30:00Z")

    assert slot_14_00.status == "EVALUATED"
    assert slot_14_00.error_mw == 200.0

    assert slot_14_30.status == "SKIPPED"
    assert "Missing actual" in slot_14_30.skip_reason
    assert slot_14_30.error_mw is None


def test_error_sign_definition():
    """
    Verify error = forecast - actual:
    Positive error means forecast > actual (wind underdelivered, utility was short).
    Negative error means forecast < actual (wind overdelivered, utility was long).
    """
    delivery_date = "2026-01-02"
    cutoff_time = "09:00"

    mock_forecasts = [
        {"start_time": "2026-01-02T01:00:00Z", "publish_time": "2026-01-01T08:00:00Z", "generation": 12000.0},
        {"start_time": "2026-01-02T02:00:00Z", "publish_time": "2026-01-01T08:00:00Z", "generation": 7000.0},
    ]
    mock_actuals = [
        {"start_time": "2026-01-02T01:00:00Z", "generation": 10000.0}, # FC > ACT (+2000)
        {"start_time": "2026-01-02T02:00:00Z", "generation": 8500.0},  # FC < ACT (-1500)
    ]

    res = align_and_join_day(
        delivery_date=delivery_date,
        cutoff_time=cutoff_time,
        custom_actuals=mock_actuals,
        custom_forecasts=mock_forecasts,
    )

    s1 = next(s for s in res.slots if s.start_time == "2026-01-02T01:00:00Z")
    s2 = next(s for s in res.slots if s.start_time == "2026-01-02T02:00:00Z")

    assert s1.error_mw == 2000.0  # Underdelivery: short
    assert s2.error_mw == -1500.0 # Overdelivery: long


def test_real_database_day_evaluation():
    """
    Integration test against local SQLite cache for 2026-01-02:
    - Verify all 48 slots are present.
    - Verify every evaluated slot uses a forecast published <= cutoff (2026-01-01 09:00:00 UTC).
    """
    cutoff_str = "09:00"
    delivery_date = "2026-01-02"
    cutoff_dt = compute_decision_cutoff(delivery_date, cutoff_str)

    res = align_and_join_day(delivery_date=delivery_date, cutoff_time=cutoff_str)

    assert res.total_slots == 48
    assert res.evaluated_slots == 48
    assert res.skipped_slots == 0
    assert len(res.slots) == 48

    for s in res.slots:
        assert s.status == "EVALUATED"
        assert s.forecast_generation_mw is not None
        assert s.actual_generation_mw is not None
        assert s.error_mw == round(s.forecast_generation_mw - s.actual_generation_mw, 2)
        
        # Rigorous check: no forecast published after cutoff!
        pub_dt = datetime.fromisoformat(s.forecast_publish_time.replace("Z", "+00:00"))
        assert pub_dt <= cutoff_dt, f"Lookahead violation! publishTime {s.forecast_publish_time} > cutoff {cutoff_dt}"
