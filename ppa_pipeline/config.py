from dataclasses import dataclass
from pathlib import Path
import os

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PARQUET_DIR = DATA_DIR / "parquet"
DUCKDB_PATH = DATA_DIR / "ppa_market.duckdb"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
PARQUET_DIR.mkdir(parents=True, exist_ok=True)

# Market Configuration
DEFAULT_BIDDING_ZONE = "DE-LU"
DEFAULT_TIMEZONE = "Europe/Berlin"

# SMARD Bundesnetzagentur Filter Codes
SMARD_FILTERS = {
    # Wholesale Day-Ahead Electricity Prices (EUR/MWh)
    "day_ahead_price": {
        "filter": 4169,
        "region": "DE-LU",
        "resolution": "hour",
        "column": "price_eur_mwh"
    },
    # Realized Generation (MWh)
    "solar_generation": {
        "filter": 4068,
        "region": "DE",
        "resolution": "hour",
        "column": "solar_mwh"
    },
    "wind_onshore_generation": {
        "filter": 4069,
        "region": "DE",
        "resolution": "hour",
        "column": "wind_onshore_mwh"
    },
    "wind_offshore_generation": {
        "filter": 4070,
        "region": "DE",
        "resolution": "hour",
        "column": "wind_offshore_mwh"
    },
    "total_grid_load": {
        "filter": 410,
        "region": "DE",
        "resolution": "hour",
        "column": "total_load_mwh"
    },
    # Day-Ahead Generation Forecasts (MWh)
    "solar_forecast": {
        "filter": 125,
        "region": "DE",
        "resolution": "hour",
        "column": "solar_forecast_mwh"
    },
    "wind_onshore_forecast": {
        "filter": 123,
        "region": "DE",
        "resolution": "hour",
        "column": "wind_onshore_forecast_mwh"
    },
    "wind_offshore_forecast": {
        "filter": 124,
        "region": "DE",
        "resolution": "hour",
        "column": "wind_offshore_forecast_mwh"
    }
}

# Representative German benchmark coordinates for renewable asset modeling
@dataclass(frozen=True)
class BenchmarkSite:
    site_id: str
    name: str
    technology: str
    latitude: float
    longitude: float
    state: str

GERMAN_BENCHMARK_SITES = [
    BenchmarkSite(
        site_id="brandenburg_solar",
        name="Brandenburg Solar Hub",
        technology="solar",
        latitude=52.41,
        longitude=12.55,
        state="Brandenburg"
    ),
    BenchmarkSite(
        site_id="bavaria_solar",
        name="Bavaria Solar Cluster",
        technology="solar",
        latitude=48.79,
        longitude=11.42,
        state="Bayern"
    ),
    BenchmarkSite(
        site_id="schleswig_wind",
        name="Schleswig-Holstein Wind Corridor",
        technology="wind_onshore",
        latitude=54.32,
        longitude=9.69,
        state="Schleswig-Holstein"
    ),
    BenchmarkSite(
        site_id="lower_saxony_wind",
        name="Lower Saxony Wind Belt",
        technology="wind_onshore",
        latitude=53.14,
        longitude=8.21,
        state="Niedersachsen"
    ),
    BenchmarkSite(
        site_id="north_sea_offshore",
        name="German Bight Offshore Cluster",
        technology="wind_offshore",
        latitude=54.50,
        longitude=7.00,
        state="North Sea"
    ),
]

# Weather Variables to extract from ERA5 / Open-Meteo
WEATHER_HOURLY_VARIABLES = [
    "temperature_2m",
    "surface_solar_radiation",
    "direct_normal_irradiance",
    "global_tilted_irradiance",
    "cloud_cover",
    "wind_speed_10m",
    "wind_speed_100m",
    "wind_direction_100m",
    "wind_gusts_10m",
    "surface_pressure"
]
