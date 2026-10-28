"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_config():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["cutoff_time"] == "09:00"
    assert data["delivery_start_date"] == "2026-01-02"
    assert data["delivery_end_date"] == "2026-02-01"
    assert "Option A" in data["resolution_alignment"]


def test_get_comparison_valid_day():
    response = client.get("/api/comparison?date=2026-01-02")
    assert response.status_code == 200
    data = response.json()
    assert data["delivery_date"] == "2026-01-02"
    assert data["total_slots"] == 48
    assert data["evaluated_slots"] == 48
    assert len(data["slots"]) == 48
    # Check first slot
    s0 = data["slots"][0]
    assert s0["start_time"] == "2026-01-02T00:00:00Z"
    assert s0["settlement_period"] == 1
    assert s0["status"] == "EVALUATED"
    assert s0["forecast_generation_mw"] is not None
    assert s0["actual_generation_mw"] is not None
    assert s0["lead_time_hours"] is not None


def test_get_comparison_invalid_date():
    response = client.get("/api/comparison?date=not-a-date")
    assert response.status_code == 400


def test_get_metrics_overall():
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_slots"] == 1488
    assert data["evaluated_slots"] == 1488
    assert data["mae_mw"] > 0
    assert data["recommended_buffer_mw"] > 0
    assert "bias_corrected" in data
    bc = data["bias_corrected"]
    assert bc["mean_bias_subtracted_mw"] == data["bias_mw"]
    assert bc["mae_mw"] > 0
    assert "In-sample" in bc["explanation"]


def test_get_metrics_daily():
    response = client.get("/api/metrics/daily")
    assert response.status_code == 200
    days = response.json()
    assert len(days) == 31
    assert days[0]["delivery_date"] == "2026-01-02"
    assert days[-1]["delivery_date"] == "2026-02-01"
    for d in days:
        assert d["evaluated_slots"] == 48
        assert d["mae_mw"] > 0


def test_get_metrics_by_hour():
    response = client.get("/api/metrics/by-hour")
    assert response.status_code == 200
    hours = response.json()
    assert len(hours) == 24
    for h in hours:
        assert 0 <= h["hour"] <= 23
        assert h["evaluated_slots"] > 0
        assert h["mae_mw"] > 0


def test_get_metrics_horizon():
    response = client.get("/api/metrics/horizon")
    assert response.status_code == 200
    horizon = response.json()
    assert len(horizon) == 8
    assert horizon[0]["bucket_label"] == "0h - 6h"
    assert horizon[-1]["bucket_label"] == "42h - 48h"
    # Verification of monotonic accuracy: 0-6h MAE should be lower than 42-48h MAE
    assert horizon[0]["mae_mw"] < horizon[-1]["mae_mw"]


def test_get_metrics_histogram():
    response = client.get("/api/metrics/histogram?bins=16")
    assert response.status_code == 200
    bins = response.json()
    assert len(bins) == 16
    total_count = sum(b["count"] for b in bins)
    assert total_count == 1488


def test_export_csv():
    response = client.get("/api/export/csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.strip().split("\n")
    # Header + 1488 data rows = 1489 lines
    assert len(lines) == 1489
    header = lines[0]
    assert "start_time" in header
    assert "forecast_generation_mw" in header
    assert "actual_generation_mw" in header
    assert "error_mw" in header
    assert "lead_time_hours" in header
