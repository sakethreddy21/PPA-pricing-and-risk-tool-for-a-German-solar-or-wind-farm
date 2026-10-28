import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import requests
import pandas as pd
from ppa_pipeline.config import SMARD_FILTERS, DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

BASE_URL = "https://www.smard.de/app/chart_data"


class SmardClient:
    """Client for downloading German electricity market data from Bundesnetzagentur SMARD.
    No API token required.
    """

    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 15):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "PPA-Pricing-Tool/1.0 (Energy Market Analytics)"
        })
        self.timeout = timeout

    def _get_chunk_timestamps(self, filter_id: int, region: str, resolution: str = "hour") -> List[int]:
        """Fetch index of chunk timestamps available for a specific filter and region."""
        url = f"{BASE_URL}/{filter_id}/{region}/index_{resolution}.json"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("timestamps", [])
            logger.warning(f"Failed to fetch chunk index from {url}: status {resp.status_code}")
            return []
        except Exception as e:
            logger.warning(f"Exception fetching chunk index from {url}: {e}")
            return []

    def fetch_filter_series(
        self,
        filter_id: int,
        region: str,
        start_date: str,
        end_date: str,
        resolution: str = "hour"
    ) -> pd.DataFrame:
        """Fetch time series data for a specific filter between start_date and end_date (inclusive, YYYY-MM-DD)."""
        start_dt = pd.to_datetime(start_date, utc=True)
        # End of end_date day
        end_dt = pd.to_datetime(end_date, utc=True) + pd.Timedelta(days=1, microseconds=-1)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        chunk_timestamps = self._get_chunk_timestamps(filter_id, region, resolution)
        if not chunk_timestamps:
            logger.warning(f"No chunks found for filter {filter_id} ({region})")
            return pd.DataFrame(columns=["timestamp_utc", "timestamp_cet", "value"])

        # Filter chunks that overlap with our date range
        # Each chunk typically spans ~7 days (604,800,000 ms)
        chunk_span_ms = 7 * 24 * 3600 * 1000
        relevant_chunks = [
            ts for ts in chunk_timestamps
            if (ts + chunk_span_ms) >= start_ms and ts <= end_ms
        ]

        logger.info(f"Downloading {len(relevant_chunks)} chunks for filter {filter_id} ({region})")

        all_points = []
        for ts in relevant_chunks:
            url = f"{BASE_URL}/{filter_id}/{region}/{filter_id}_{region}_{resolution}_{ts}.json"
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code != 200:
                    continue
                series = r.json().get("series", [])
                for pt in series:
                    t_ms, val = pt[0], pt[1]
                    if start_ms <= t_ms <= end_ms:
                        all_points.append((t_ms, val))
            except Exception as e:
                logger.error(f"Error fetching chunk {ts}: {e}")

        if not all_points:
            return pd.DataFrame(columns=["timestamp_utc", "timestamp_cet", "value"])

        df = pd.DataFrame(all_points, columns=["timestamp_ms", "value"])
        df = df.drop_duplicates(subset=["timestamp_ms"]).sort_values("timestamp_ms")
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        df["timestamp_cet"] = df["timestamp_utc"].dt.tz_convert(DEFAULT_TIMEZONE).dt.strftime("%Y-%m-%d %H:%M:%S")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df[["timestamp_utc", "timestamp_cet", "value"]]

    def fetch_day_ahead_prices(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch German day-ahead wholesale electricity prices in EUR/MWh."""
        cfg = SMARD_FILTERS["day_ahead_price"]
        df = self.fetch_filter_series(
            filter_id=cfg["filter"],
            region=cfg["region"],
            start_date=start_date,
            end_date=end_date,
            resolution=cfg["resolution"]
        )
        df = df.rename(columns={"value": cfg["column"]})
        df["bidding_zone"] = cfg["region"]
        return df

    def fetch_generation_and_load(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch realized generation for Solar, Wind Onshore, Wind Offshore, and Total Grid Load.
        Returns a single merged hourly DataFrame.
        """
        targets = [
            ("solar_generation", "solar_mwh"),
            ("wind_onshore_generation", "wind_onshore_mwh"),
            ("wind_offshore_generation", "wind_offshore_mwh"),
            ("total_grid_load", "total_load_mwh"),
        ]

        merged_df = None
        for config_key, col_name in targets:
            cfg = SMARD_FILTERS[config_key]
            series_df = self.fetch_filter_series(
                filter_id=cfg["filter"],
                region=cfg["region"],
                start_date=start_date,
                end_date=end_date,
                resolution=cfg["resolution"]
            )
            series_df = series_df.rename(columns={"value": col_name})

            if merged_df is None:
                merged_df = series_df
            else:
                merged_df = pd.merge(
                    merged_df,
                    series_df[["timestamp_utc", col_name]],
                    on="timestamp_utc",
                    how="outer"
                )

        if merged_df is not None:
            merged_df = merged_df.sort_values("timestamp_utc").reset_index(drop=True)
            merged_df["total_renewables_mwh"] = (
                merged_df["solar_mwh"].fillna(0)
                + merged_df["wind_onshore_mwh"].fillna(0)
                + merged_df["wind_offshore_mwh"].fillna(0)
            )
            return merged_df
        return pd.DataFrame()

    def fetch_generation_forecasts(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch day-ahead forecasts for Solar, Wind Onshore, and Wind Offshore."""
        targets = [
            ("solar_forecast", "solar_forecast_mwh"),
            ("wind_onshore_forecast", "wind_onshore_forecast_mwh"),
            ("wind_offshore_forecast", "wind_offshore_forecast_mwh"),
        ]

        merged_df = None
        for config_key, col_name in targets:
            cfg = SMARD_FILTERS[config_key]
            series_df = self.fetch_filter_series(
                filter_id=cfg["filter"],
                region=cfg["region"],
                start_date=start_date,
                end_date=end_date,
                resolution=cfg["resolution"]
            )
            series_df = series_df.rename(columns={"value": col_name})

            if merged_df is None:
                merged_df = series_df
            else:
                merged_df = pd.merge(
                    merged_df,
                    series_df[["timestamp_utc", col_name]],
                    on="timestamp_utc",
                    how="outer"
                )

        return merged_df if merged_df is not None else pd.DataFrame()
