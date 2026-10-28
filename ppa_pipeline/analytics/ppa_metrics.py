import logging
from typing import Dict, Any, Optional
import duckdb
import pandas as pd
from ppa_pipeline.storage.duckdb_manager import DuckDBManager

logger = logging.getLogger(__name__)


class PpaRiskAnalytics:
    """Computes key financial and volumetric risk metrics for German Solar and Wind PPAs."""

    def __init__(self, db: Optional[DuckDBManager] = None):
        self.db = db or DuckDBManager()

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Compute holistic PPA metrics across the entire loaded period."""
        query = """
        SELECT
            COUNT(*) AS total_hours,
            MIN(timestamp_utc) AS start_time,
            MAX(timestamp_utc) AS end_time,
            ROUND(AVG(price_eur_mwh), 2) AS baseload_price_eur_mwh,
            ROUND(MIN(price_eur_mwh), 2) AS min_price_eur_mwh,
            ROUND(MAX(price_eur_mwh), 2) AS max_price_eur_mwh,
            ROUND(STDDEV(price_eur_mwh), 2) AS price_volatility_eur_mwh,
            SUM(is_negative_price) AS negative_price_hours,
            ROUND(100.0 * SUM(is_negative_price) / COUNT(*), 2) AS pct_negative_hours,
            -- Solar capture metrics
            ROUND(SUM(solar_revenue_eur) / NULLIF(SUM(solar_mwh), 0), 2) AS solar_capture_price_eur_mwh,
            ROUND((SUM(solar_revenue_eur) / NULLIF(SUM(solar_mwh), 0)) / NULLIF(AVG(price_eur_mwh), 0), 4) AS solar_capture_factor,
            ROUND(SUM(solar_mwh), 0) AS total_solar_mwh,
            -- Wind onshore capture metrics
            ROUND(SUM(price_eur_mwh * wind_onshore_mwh) / NULLIF(SUM(wind_onshore_mwh), 0), 2) AS wind_onshore_capture_price_eur_mwh,
            ROUND((SUM(price_eur_mwh * wind_onshore_mwh) / NULLIF(SUM(wind_onshore_mwh), 0)) / NULLIF(AVG(price_eur_mwh), 0), 4) AS wind_onshore_capture_factor,
            ROUND(SUM(wind_onshore_mwh), 0) AS total_wind_onshore_mwh,
            -- Combined wind capture metrics
            ROUND(SUM(wind_revenue_eur) / NULLIF(SUM(total_wind_mwh), 0), 2) AS total_wind_capture_price_eur_mwh,
            ROUND((SUM(wind_revenue_eur) / NULLIF(SUM(total_wind_mwh), 0)) / NULLIF(AVG(price_eur_mwh), 0), 4) AS total_wind_capture_factor,
            ROUND(SUM(total_wind_mwh), 0) AS total_wind_mwh
        FROM v_ppa_market;
        """
        df = self.db.query(query)
        if df.empty or df.iloc[0]["total_hours"] == 0:
            return {}
        return df.iloc[0].to_dict()

    def get_monthly_capture_table(self) -> pd.DataFrame:
        """Return the monthly breakdown table of capture prices, factors, and negative hours."""
        query = "SELECT * FROM v_monthly_capture_metrics ORDER BY month;"
        return self.db.query(query)

    def get_solar_cannibalization_profile(self) -> pd.DataFrame:
        """Analyze hourly cannibalization: average price and generation by hour of the day."""
        query = """
        SELECT
            EXTRACT(HOUR FROM timestamp_utc) AS hour_of_day_utc,
            ROUND(AVG(price_eur_mwh), 2) AS avg_price_eur_mwh,
            ROUND(AVG(solar_mwh), 1) AS avg_solar_mwh,
            ROUND(AVG(wind_onshore_mwh), 1) AS avg_wind_onshore_mwh,
            SUM(is_negative_price) AS negative_price_occurrences
        FROM v_ppa_market
        GROUP BY EXTRACT(HOUR FROM timestamp_utc)
        ORDER BY hour_of_day_utc;
        """
        return self.db.query(query)

    def get_weather_price_correlation(self, location_id: Optional[str] = None) -> pd.DataFrame:
        """Calculate correlation between local weather drivers and wholesale electricity prices."""
        filter_clause = f"WHERE w.location_id = '{location_id}'" if location_id else ""
        query = f"""
        SELECT
            w.location_id,
            COUNT(*) AS sample_hours,
            ROUND(CORR(w.direct_normal_irradiance_wm2, p.price_eur_mwh), 3) AS corr_dni_vs_price,
            ROUND(CORR(w.global_tilted_irradiance_wm2, p.price_eur_mwh), 3) AS corr_solar_irradiance_vs_price,
            ROUND(CORR(w.wind_speed_100m_ms, p.price_eur_mwh), 3) AS corr_wind_speed_100m_vs_price,
            ROUND(CORR(w.temperature_2m_c, p.price_eur_mwh), 3) AS corr_temp_vs_price
        FROM weather_timeseries w
        JOIN market_prices p ON w.timestamp_utc = p.timestamp_utc
        {filter_clause}
        GROUP BY w.location_id;
        """
        return self.db.query(query)
