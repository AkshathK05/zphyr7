"""Core business logic for cutoff selection, resolution alignment, and forecast-actual join."""

from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta, time, timezone
from typing import List, Optional, Dict, Any
import sqlite3

from backend.config import settings
from backend.database import get_connection

@dataclass
class SlotComparison:
    """Comparison record for a single half-hour settlement slot."""
    start_time: str                  # ISO UTC e.g. 2026-01-02T00:30:00Z
    settlement_date: str             # YYYY-MM-DD
    settlement_period: int           # 1 to 48
    forecast_generation_mw: Optional[float]
    actual_generation_mw: Optional[float]
    error_mw: Optional[float]        # forecast - actual (positive = overforecast / utility short)
    forecast_publish_time: Optional[str]
    actual_publish_time: Optional[str]
    lead_time_hours: Optional[float] # (start_time - forecast_publish_time) in hours
    status: str                      # 'EVALUATED' or 'SKIPPED'
    skip_reason: Optional[str] = None

@dataclass
class DayComparisonResult:
    """Full day evaluation outcome."""
    delivery_date: str
    decision_date: str
    cutoff_time: str
    cutoff_timestamp: str
    total_slots: int
    evaluated_slots: int
    skipped_slots: int
    slots: List[SlotComparison]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_utc_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp string to a timezone-aware UTC datetime."""
    clean = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_utc_timestamp(dt: datetime) -> str:
    """Format a datetime to standard ISO 8601 UTC string (YYYY-MM-DDTHH:MM:SSZ)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_decision_cutoff(delivery_date_str: str, cutoff_time_str: str = "09:00") -> datetime:
    """
    Compute decision cutoff datetime in UTC.
    For delivery day D, the decision day is D-1.
    Cutoff timestamp is (D-1) at cutoff_time_str UTC.
    
    Example:
        delivery_date = '2026-01-02', cutoff_time = '09:00'
        -> cutoff = 2026-01-01 09:00:00 UTC
    """
    delivery_d = date.fromisoformat(delivery_date_str)
    decision_d = delivery_d - timedelta(days=1)
    hour, minute = [int(p) for p in cutoff_time_str.split(":")]
    return datetime.combine(decision_d, time(hour, minute, 0), tzinfo=timezone.utc)


def generate_half_hour_slots_for_day(delivery_date_str: str) -> List[Dict[str, Any]]:
    """Generate all 48 half-hour settlement slots for a delivery day."""
    d = date.fromisoformat(delivery_date_str)
    slots = []
    current_dt = datetime.combine(d, time(0, 0, 0), tzinfo=timezone.utc)
    for period in range(1, 49):
        slots.append({
            "start_time": format_utc_timestamp(current_dt),
            "settlement_date": delivery_date_str,
            "settlement_period": period,
            # The corresponding hourly forecast slot (:00 of the same hour)
            "hourly_slot": format_utc_timestamp(current_dt.replace(minute=0, second=0)),
        })
        current_dt += timedelta(minutes=30)
    return slots


def select_best_forecasts_for_slots(
    raw_forecasts: List[Dict[str, Any]],
    cutoff_dt: datetime,
) -> Dict[str, Dict[str, Any]]:
    """
    Pure logic function:
    Given a list of forecast records, filter out any with publish_time > cutoff_dt (no lookahead).
    For each target slot (start_time), pick the forecast with the LATEST publish_time <= cutoff_dt.

    Args:
        raw_forecasts: List of dicts with 'start_time', 'publish_time', 'generation'.
        cutoff_dt: UTC datetime cutoff threshold.

    Returns:
        Dict mapping target start_time -> best forecast record dict.
    """
    # Group eligible forecasts by target start_time
    eligible_by_slot: Dict[str, List[Dict[str, Any]]] = {}

    for row in raw_forecasts:
        pub_dt = parse_utc_timestamp(row["publish_time"])
        # Core Rule: publish_time <= cutoff (NO LOOKAHEAD)
        if pub_dt <= cutoff_dt:
            st = row["start_time"]
            eligible_by_slot.setdefault(st, []).append((pub_dt, row))

    selected: Dict[str, Dict[str, Any]] = {}
    for st, entries in eligible_by_slot.items():
        # Pick the one with the maximum publish_time
        entries.sort(key=lambda item: item[0])
        selected[st] = entries[-1][1]

    return selected


def align_and_join_day(
    delivery_date: str,
    cutoff_time: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    custom_actuals: Optional[List[Dict[str, Any]]] = None,
    custom_forecasts: Optional[List[Dict[str, Any]]] = None,
) -> DayComparisonResult:
    """
    Evaluate one delivery day:
    1. Determine cutoff timestamp (D-1 at cutoff_time).
    2. Retrieve actuals and forecasts (from DB or in-memory lists).
    3. Select best forecast for each target hour slot (publish_time <= cutoff).
    4. Apply Option A: broadcast hourly forecast to both HH:00 and HH:30 half-hour slots.
    5. Join with actuals on start_time.
    6. Calculate error = forecast - actual (MW).
    7. Count and record evaluated vs skipped slots.
    """
    cutoff_str = cutoff_time or settings.cutoff_time
    cutoff_dt = compute_decision_cutoff(delivery_date, cutoff_str)
    cutoff_iso = format_utc_timestamp(cutoff_dt)
    decision_date = (date.fromisoformat(delivery_date) - timedelta(days=1)).isoformat()

    # 1. Fetch data
    actuals_map: Dict[str, Dict[str, Any]] = {}
    raw_forecasts: List[Dict[str, Any]] = []

    if custom_actuals is not None and custom_forecasts is not None:
        # In-memory data (useful for unit tests)
        for act in custom_actuals:
            actuals_map[act["start_time"]] = act
        raw_forecasts = custom_forecasts
    else:
        # SQLite cached data
        close_conn = False
        if conn is None:
            conn = get_connection()
            close_conn = True

        try:
            cursor = conn.cursor()
            # Fetch actuals for this delivery date
            cursor.execute("""
                SELECT dataset, start_time, publish_time, settlement_date, settlement_period, fuel_type, generation
                FROM fuelhh_actuals
                WHERE settlement_date = ? AND fuel_type = 'WIND'
            """, (delivery_date,))
            for r in cursor.fetchall():
                d = dict(r)
                actuals_map[d["start_time"]] = d

            # Fetch all forecasts targeting this delivery day
            # Target start_times for day D span from YYYY-MM-DDT00:00:00Z to YYYY-MM-DDT23:00:00Z
            day_start = f"{delivery_date}T00:00:00Z"
            day_end = f"{delivery_date}T23:59:59Z"
            cursor.execute("""
                SELECT dataset, start_time, publish_time, generation
                FROM windfor_forecasts
                WHERE start_time >= ? AND start_time <= ?
            """, (day_start, day_end))
            raw_forecasts = [dict(r) for r in cursor.fetchall()]
        finally:
            if close_conn:
                conn.close()

    # 2. Select best available forecast per target hour slot (publish_time <= cutoff)
    best_hourly_forecasts = select_best_forecasts_for_slots(raw_forecasts, cutoff_dt)

    # 3. Build comparison for all 48 half-hour slots (Option A alignment)
    slot_definitions = generate_half_hour_slots_for_day(delivery_date)
    slots_result: List[SlotComparison] = []
    evaluated_count = 0
    skipped_count = 0

    for slot_def in slot_definitions:
        st = slot_def["start_time"]
        hourly_st = slot_def["hourly_slot"]
        period = slot_def["settlement_period"]

        # Option A broadcast: hourly forecast applies to both HH:00 and HH:30
        matched_fc = best_hourly_forecasts.get(hourly_st)
        matched_act = actuals_map.get(st)

        fc_val = matched_fc["generation"] if matched_fc is not None else None
        act_val = matched_act["generation"] if matched_act is not None else None
        fc_pub = matched_fc["publish_time"] if matched_fc is not None else None
        act_pub = matched_act.get("publish_time") if matched_act is not None else None

        lead_hours = None
        if fc_pub is not None:
            fc_pub_dt = parse_utc_timestamp(fc_pub)
            slot_dt = parse_utc_timestamp(st)
            lead_hours = round((slot_dt - fc_pub_dt).total_seconds() / 3600.0, 2)

        if fc_val is None or act_val is None:
            # Missing value -> skip slot (no imputation)
            reasons = []
            if fc_val is None:
                reasons.append("Missing forecast <= cutoff")
            if act_val is None:
                reasons.append("Missing actual generation")

            slots_result.append(SlotComparison(
                start_time=st,
                settlement_date=delivery_date,
                settlement_period=period,
                forecast_generation_mw=None,
                actual_generation_mw=act_val,
                error_mw=None,
                forecast_publish_time=fc_pub,
                actual_publish_time=act_pub,
                lead_time_hours=lead_hours,
                status="SKIPPED",
                skip_reason=", ".join(reasons),
            ))
            skipped_count += 1
        else:
            # Both present -> Error = forecast - actual (MW)
            # Positive error = overforecast (utility was short)
            err = round(float(fc_val) - float(act_val), 2)
            slots_result.append(SlotComparison(
                start_time=st,
                settlement_date=delivery_date,
                settlement_period=period,
                forecast_generation_mw=float(fc_val),
                actual_generation_mw=float(act_val),
                error_mw=err,
                forecast_publish_time=fc_pub,
                actual_publish_time=act_pub,
                lead_time_hours=lead_hours,
                status="EVALUATED",
                skip_reason=None,
            ))
            evaluated_count += 1

    return DayComparisonResult(
        delivery_date=delivery_date,
        decision_date=decision_date,
        cutoff_time=cutoff_str,
        cutoff_timestamp=cutoff_iso,
        total_slots=len(slot_definitions),
        evaluated_slots=evaluated_count,
        skipped_slots=skipped_count,
        slots=slots_result,
    )
