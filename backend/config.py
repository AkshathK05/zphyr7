"""Configuration settings for Elexon BMRS Wind Backtest application."""

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """Application and backtest configuration with environment variable support."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Elexon API base configuration
    elexon_base_url: str = Field(
        default="https://data.elexon.co.uk/bmrs/api/v1",
        description="Base URL for Elexon BMRS Insights Solution API"
    )

    # Historical scope for decision days and delivery days
    decision_start_date: str = Field(
        default="2026-01-01",
        description="First decision day (YYYY-MM-DD)"
    )
    decision_end_date: str = Field(
        default="2026-01-31",
        description="Last decision day (YYYY-MM-DD)"
    )
    delivery_start_date: str = Field(
        default="2026-01-02",
        description="First delivery day (YYYY-MM-DD)"
    )
    delivery_end_date: str = Field(
        default="2026-02-01",
        description="Last delivery day (YYYY-MM-DD)"
    )

    # Lookback window for fetching forecasts published before the first decision cutoff
    forecast_fetch_start: str = Field(
        default="2025-12-28T00:00:00Z",
        description="ISO UTC start timestamp to fetch WINDFOR forecasts"
    )
    forecast_fetch_end: str = Field(
        default="2026-01-31T23:59:59Z",
        description="ISO UTC end timestamp to fetch WINDFOR forecasts"
    )

    # Core auction cutoff time (UTC) on day D-1
    cutoff_time: str = Field(
        default="09:00",
        description="Daily cutoff time (HH:MM UTC) on decision day D-1"
    )

    # Local SQLite cache path
    db_path: str = Field(
        default=str(BASE_DIR / "data" / "bmrs_cache.db"),
        description="Filesystem path to local SQLite database cache"
    )

    # HTTP client parameters
    http_timeout_seconds: float = Field(default=30.0, description="HTTP request timeout")
    max_retries: int = Field(default=4, description="Max retries for Elexon requests")
    backoff_factor: float = Field(default=1.5, description="Exponential backoff factor")

settings = Settings()
