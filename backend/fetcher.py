"""Elexon BMRS API client with robust retries, rate-limiting, and error handling."""

import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
from backend.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ElexonFetcher:
    """HTTP client responsible for pulling FUELHH and WINDFOR streams from Elexon BMRS."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.elexon_base_url).rstrip("/")
        self.timeout = timeout or settings.http_timeout_seconds
        self.max_retries = max_retries or settings.max_retries
        self.backoff_factor = backoff_factor or settings.backoff_factor
        self.headers = {
            "User-Agent": "ElexonWindBacktest/1.0",
            "Accept": "application/json",
        }

    def _get_with_retry(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Perform a GET request against Elexon BMRS with exponential backoff on transient errors."""
        url = f"{self.base_url}{endpoint}"
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Fetching {endpoint} (attempt {attempt}/{self.max_retries}) params: {params}")
                with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and "data" in data:
                        return data["data"]
                    return []
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_exception = exc
                wait_time = self.backoff_factor ** attempt
                logger.warning(f"Request to {url} failed: {exc}. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)

        logger.error(f"Exceeded max retries ({self.max_retries}) for {url}")
        raise RuntimeError(f"Failed to fetch data from {url} after {self.max_retries} attempts: {last_exception}")

    def fetch_fuelhh_actuals(
        self,
        settlement_date_from: str,
        settlement_date_to: str,
        fuel_type: str = "WIND",
    ) -> List[Dict[str, Any]]:
        """
        Fetch outturn generation from /datasets/FUELHH/stream.
        
        Args:
            settlement_date_from: Start settlement date (YYYY-MM-DD).
            settlement_date_to: End settlement date (YYYY-MM-DD).
            fuel_type: Target fuel type filter (default 'WIND').

        Returns:
            List of raw FUELHH record dictionaries.
        """
        params = {
            "settlementDateFrom": settlement_date_from,
            "settlementDateTo": settlement_date_to,
            "fuelType": fuel_type,
        }
        return self._get_with_retry("/datasets/FUELHH/stream", params)

    def fetch_windfor_forecasts_chunk(
        self,
        publish_from: str,
        publish_to: str,
    ) -> List[Dict[str, Any]]:
        """
        Fetch wind forecasts from /datasets/WINDFOR/stream for a publish time window.
        
        Args:
            publish_from: ISO 8601 UTC string (e.g. 2026-01-01T00:00:00Z).
            publish_to: ISO 8601 UTC string (e.g. 2026-01-05T00:00:00Z).

        Returns:
            List of raw WINDFOR record dictionaries.
        """
        params = {
            "publishDateTimeFrom": publish_from,
            "publishDateTimeTo": publish_to,
        }
        return self._get_with_retry("/datasets/WINDFOR/stream", params)

    def fetch_windfor_forecasts_range(
        self,
        start_time_iso: str,
        end_time_iso: str,
        chunk_days: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Fetch wind forecasts across a wide range by chunking into smaller date intervals.

        Args:
            start_time_iso: Range start (ISO 8601 UTC).
            end_time_iso: Range end (ISO 8601 UTC).
            chunk_days: Size of each chunk window in days.

        Returns:
            Combined list of all WINDFOR records.
        """
        # Parse ISO strings
        clean_start = start_time_iso.replace("Z", "+00:00")
        clean_end = end_time_iso.replace("Z", "+00:00")
        cur_dt = datetime.fromisoformat(clean_start)
        final_dt = datetime.fromisoformat(clean_end)

        all_records: List[Dict[str, Any]] = []

        while cur_dt < final_dt:
            next_dt = min(cur_dt + timedelta(days=chunk_days), final_dt)
            p_from = cur_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            p_to = next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            logger.info(f"Fetching WINDFOR chunk: {p_from} -> {p_to}")
            chunk = self.fetch_windfor_forecasts_chunk(p_from, p_to)
            all_records.extend(chunk)
            cur_dt = next_dt

        return all_records
