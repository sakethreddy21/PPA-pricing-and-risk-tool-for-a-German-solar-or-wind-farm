import logging
from pathlib import Path
from typing import Optional, Union
import duckdb
import pandas as pd
from ppa_pipeline.config import DUCKDB_PATH

logger = logging.getLogger(__name__)


class DuckDBManager:
    """Manages DuckDB database initialization, data insertion, upserts,
    and analytical views for PPA pricing and risk metrics.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = str(db_path or DUCKDB_PATH)
        self.conn = duckdb.connect(self.db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables and analytical views if they do not exist."""
        with self.conn.cursor() as cur:
            # 1. Market Day-Ahead Prices
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_prices (
                    timestamp_utc TIMESTAMP PRIMARY KEY,
                    timestamp_cet VARCHAR,
                    price_eur_mwh DOUBLE,
                    bidding_zone VARCHAR
                );
            """)

            # 2. Actual Generation & Grid Load
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_generation (
                    timestamp_utc TIMESTAMP PRIMARY KEY,
                    timestamp_cet VARCHAR,
                    solar_mwh DOUBLE,
                    wind_onshore_mwh DOUBLE,
                    wind_offshore_mwh DOUBLE,
                    total_load_mwh DOUBLE,
                    total_renewables_mwh DOUBLE
                );
            """)

            # 3. Generation Forecasts
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_forecasts (
                    timestamp_utc TIMESTAMP PRIMARY KEY,
                    timestamp_cet VARCHAR,
                    solar_forecast_mwh DOUBLE,
                    wind_onshore_forecast_mwh DOUBLE,
                    wind_offshore_forecast_mwh DOUBLE
                );
            """)

            # 4. Weather Timeseries
            cur.execute("""
                CREATE TABLE IF NOT EXISTS weather_timeseries (
                    timestamp_utc TIMESTAMP,
                    timestamp_cet VARCHAR,
                    location_id VARCHAR,
                    latitude DOUBLE,
                    longitude DOUBLE,
                    temperature_2m_c DOUBLE,
                    direct_normal_irradiance_wm2 DOUBLE,
                    global_tilted_irradiance_wm2 DOUBLE,
                    cloud_cover_pct DOUBLE,
                    wind_speed_10m_ms DOUBLE,
                    wind_speed_100m_ms DOUBLE,
                    wind_direction_100m_deg DOUBLE,
                    wind_gusts_10m_ms DOUBLE,
                    surface_pressure_hpa DOUBLE,
                    PRIMARY KEY (timestamp_utc, location_id)
                );
            """)

            # 5. Combined Analytical View for PPA Profiling
            cur.execute("""
                CREATE OR REPLACE VIEW v_ppa_market AS
                SELECT
                    p.timestamp_utc,
                    p.timestamp_cet,
                    p.price_eur_mwh,
                    p.bidding_zone,
                    g.solar_mwh,
                    g.wind_onshore_mwh,
                    g.wind_offshore_mwh,
                    (COALESCE(g.wind_onshore_mwh, 0) + COALESCE(g.wind_offshore_mwh, 0)) AS total_wind_mwh,
                    g.total_load_mwh,
                    g.total_renewables_mwh,
                    (p.price_eur_mwh * g.solar_mwh) AS solar_revenue_eur,
                    (p.price_eur_mwh * (COALESCE(g.wind_onshore_mwh, 0) + COALESCE(g.wind_offshore_mwh, 0))) AS wind_revenue_eur,
                    CASE WHEN p.price_eur_mwh < 0 THEN 1 ELSE 0 END AS is_negative_price,
                    CASE WHEN p.price_eur_mwh <= 0 THEN 1 ELSE 0 END AS is_zero_or_negative
                FROM market_prices p
                LEFT JOIN market_generation g ON p.timestamp_utc = g.timestamp_utc;
            """)

            # 6. Monthly PPA Capture Price & Capture Factor (Marktwertfaktor) View
            cur.execute("""
                CREATE OR REPLACE VIEW v_monthly_capture_metrics AS
                SELECT
                    STRFTIME(timestamp_utc, '%Y-%m') AS month,
                    COUNT(*) AS total_hours,
                    ROUND(AVG(price_eur_mwh), 2) AS baseload_price_eur_mwh,
                    ROUND(MIN(price_eur_mwh), 2) AS min_price_eur_mwh,
                    ROUND(MAX(price_eur_mwh), 2) AS max_price_eur_mwh,
                    SUM(is_negative_price) AS negative_price_hours,
                    ROUND(SUM(solar_revenue_eur) / NULLIF(SUM(solar_mwh), 0), 2) AS solar_capture_price_eur_mwh,
                    ROUND((SUM(solar_revenue_eur) / NULLIF(SUM(solar_mwh), 0)) / NULLIF(AVG(price_eur_mwh), 0), 4) AS solar_capture_factor,
                    ROUND(SUM(wind_revenue_eur) / NULLIF(SUM(total_wind_mwh), 0), 2) AS wind_capture_price_eur_mwh,
                    ROUND((SUM(wind_revenue_eur) / NULLIF(SUM(total_wind_mwh), 0)) / NULLIF(AVG(price_eur_mwh), 0), 4) AS wind_capture_factor,
                    ROUND(SUM(solar_mwh), 0) AS total_solar_mwh,
                    ROUND(SUM(total_wind_mwh), 0) AS total_wind_mwh
                FROM v_ppa_market
                GROUP BY STRFTIME(timestamp_utc, '%Y-%m')
                ORDER BY month;
            """)

        logger.info(f"Initialized DuckDB schema at {self.db_path}")

    def upsert_prices(self, df: pd.DataFrame) -> int:
        """Upsert day-ahead price records."""
        if df.empty:
            return 0
        df = df.copy()
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
        self.conn.register("df_prices", df)
        self.conn.execute("""
            INSERT OR REPLACE INTO market_prices
            SELECT timestamp_utc, timestamp_cet, price_eur_mwh, bidding_zone
            FROM df_prices;
        """)
        self.conn.unregister("df_prices")
        return len(df)

    def upsert_generation(self, df: pd.DataFrame) -> int:
        """Upsert realized generation and load records."""
        if df.empty:
            return 0
        df = df.copy()
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
        self.conn.register("df_gen", df)
        self.conn.execute("""
            INSERT OR REPLACE INTO market_generation
            SELECT timestamp_utc, timestamp_cet, solar_mwh, wind_onshore_mwh,
                   wind_offshore_mwh, total_load_mwh, total_renewables_mwh
            FROM df_gen;
        """)
        self.conn.unregister("df_gen")
        return len(df)

    def upsert_forecasts(self, df: pd.DataFrame) -> int:
        """Upsert generation forecast records."""
        if df.empty:
            return 0
        df = df.copy()
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
        self.conn.register("df_fc", df)
        self.conn.execute("""
            INSERT OR REPLACE INTO market_forecasts
            SELECT timestamp_utc, timestamp_cet, solar_forecast_mwh,
                   wind_onshore_forecast_mwh, wind_offshore_forecast_mwh
            FROM df_fc;
        """)
        self.conn.unregister("df_fc")
        return len(df)

    def upsert_weather(self, df: pd.DataFrame) -> int:
        """Upsert weather timeseries records."""
        if df.empty:
            return 0
        df = df.copy()
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
        self.conn.register("df_weather", df)
        self.conn.execute("""
            INSERT OR REPLACE INTO weather_timeseries
            SELECT timestamp_utc, timestamp_cet, location_id, latitude, longitude,
                   temperature_2m_c, direct_normal_irradiance_wm2, global_tilted_irradiance_wm2,
                   cloud_cover_pct, wind_speed_10m_ms, wind_speed_100m_ms, wind_direction_100m_deg,
                   wind_gusts_10m_ms, surface_pressure_hpa
            FROM df_weather;
        """)
        self.conn.unregister("df_weather")
        return len(df)

    def query(self, sql: str) -> pd.DataFrame:
        """Execute arbitrary SQL and return a Pandas DataFrame."""
        return self.conn.execute(sql).df()

    def get_table_counts(self) -> dict:
        """Return row counts for all tables."""
        tables = ["market_prices", "market_generation", "market_forecasts", "weather_timeseries"]
        counts = {}
        for t in tables:
            cnt = self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            counts[t] = cnt
        return counts

    def close(self) -> None:
        """Close connection."""
        self.conn.close()
