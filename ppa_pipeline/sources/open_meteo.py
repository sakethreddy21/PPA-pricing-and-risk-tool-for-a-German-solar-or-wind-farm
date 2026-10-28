import logging
from typing import List, Optional, Union
import openmeteo_requests
import requests_cache
from retry_requests import retry
import pandas as pd
from ppa_pipeline.config import BenchmarkSite, GERMAN_BENCHMARK_SITES, DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoClient:
    """Client for pulling historical ERA5 reanalysis & forecast weather data
    from Open-Meteo for German solar and wind sites.
    """

    def __init__(self, cache_dir: str = ".cache"):
        cache_session = requests_cache.CachedSession(cache_dir, expire_after=86400)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        self.client = openmeteo_requests.Client(session=retry_session)

    def fetch_site_weather(
        self,
        site: Union[BenchmarkSite, dict],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch hourly weather variables for a given site (BenchmarkSite or dict with lat, lon, id).
        Dates: YYYY-MM-DD
        """
        if isinstance(site, BenchmarkSite):
            site_id = site.site_id
            lat = site.latitude
            lon = site.longitude
        else:
            site_id = site.get("site_id", "custom_site")
            lat = site["latitude"]
            lon = site["longitude"]

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": [
                "temperature_2m",
                "direct_normal_irradiance",
                "global_tilted_irradiance",
                "cloud_cover",
                "wind_speed_10m",
                "wind_speed_100m",
                "wind_direction_100m",
                "wind_gusts_10m",
                "surface_pressure"
            ],
            "wind_speed_unit": "ms"
        }

        logger.info(f"Fetching Open-Meteo weather for {site_id} ({lat}, {lon}) [{start_date} to {end_date}]")
        try:
            responses = self.client.weather_api(ARCHIVE_API_URL, params=params)
        except Exception as e:
            logger.warning(f"Archive API request failed: {e}. Falling back to forecast/recent API...")
            responses = self.client.weather_api(FORECAST_API_URL, params=params)

        response = responses[0]
        hourly = response.Hourly()

        # Extract timestamps
        # Time starts at hourly.Time() (seconds UTC) with hourly.Interval() step
        time_index = pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left"
        )

        df = pd.DataFrame({
            "timestamp_utc": time_index,
            "location_id": site_id,
            "latitude": round(response.Latitude(), 4),
            "longitude": round(response.Longitude(), 4),
            "temperature_2m_c": hourly.Variables(0).ValuesAsNumpy(),
            "direct_normal_irradiance_wm2": hourly.Variables(1).ValuesAsNumpy(),
            "global_tilted_irradiance_wm2": hourly.Variables(2).ValuesAsNumpy(),
            "cloud_cover_pct": hourly.Variables(3).ValuesAsNumpy(),
            "wind_speed_10m_ms": hourly.Variables(4).ValuesAsNumpy(),
            "wind_speed_100m_ms": hourly.Variables(5).ValuesAsNumpy(),
            "wind_direction_100m_deg": hourly.Variables(6).ValuesAsNumpy(),
            "wind_gusts_10m_ms": hourly.Variables(7).ValuesAsNumpy(),
            "surface_pressure_hpa": hourly.Variables(8).ValuesAsNumpy(),
        })

        df["timestamp_cet"] = df["timestamp_utc"].dt.tz_convert(DEFAULT_TIMEZONE).dt.strftime("%Y-%m-%d %H:%M:%S")
        return df

    def fetch_all_benchmark_sites(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch weather for all preconfigured German solar and wind benchmark sites."""
        dfs = []
        for site in GERMAN_BENCHMARK_SITES:
            try:
                site_df = self.fetch_site_weather(site, start_date, end_date)
                dfs.append(site_df)
            except Exception as e:
                logger.error(f"Failed to fetch weather for {site.site_id}: {e}")

        if not dfs:
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True)
