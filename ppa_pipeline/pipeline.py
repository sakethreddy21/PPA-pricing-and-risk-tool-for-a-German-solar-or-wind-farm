import logging
from datetime import datetime, timedelta
from typing import List, Optional
from tabulate import tabulate
import pandas as pd

from ppa_pipeline.config import GERMAN_BENCHMARK_SITES
from ppa_pipeline.sources.smard import SmardClient
from ppa_pipeline.sources.entsoe import EntsoeClient
from ppa_pipeline.sources.open_meteo import OpenMeteoClient
from ppa_pipeline.storage.duckdb_manager import DuckDBManager
from ppa_pipeline.storage.parquet_export import ParquetStorage
from ppa_pipeline.analytics.ppa_metrics import PpaRiskAnalytics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ppa_pipeline")


def run_pipeline(
    start_date: str,
    end_date: str,
    use_entsoe: bool = False,
    sites: Optional[List] = None,
    export_parquet: bool = True
) -> dict:
    """Execute complete end-to-end data pipeline:
    1. Fetch German wholesale Day-Ahead Prices (SMARD or ENTSO-E)
    2. Fetch Realized Renewable Generation & Load (SMARD)
    3. Fetch Renewable Day-Ahead Forecasts (SMARD)
    4. Fetch ERA5 Weather Data (Open-Meteo)
    5. Clean & Store into DuckDB
    6. Export to Parquet
    7. Calculate and display PPA risk & capture metrics
    """
    logger.info("=" * 60)
    logger.info(f"STARTING PPA DATA PIPELINE: {start_date} to {end_date}")
    logger.info("=" * 60)

    db = DuckDBManager()
    smard = SmardClient()
    openmeteo = OpenMeteoClient()

    results = {
        "start_date": start_date,
        "end_date": end_date,
        "prices_count": 0,
        "generation_count": 0,
        "forecasts_count": 0,
        "weather_count": 0,
        "parquet_exported": {}
    }

    # 1. Day-Ahead Prices
    logger.info(f"Step 1: Pulling Day-Ahead Wholesale Prices ({start_date} to {end_date})...")
    if use_entsoe:
        entsoe = EntsoeClient()
        if entsoe.is_configured:
            prices_df = entsoe.fetch_day_ahead_prices(start_date, end_date)
        else:
            logger.warning("ENTSOE_API_TOKEN not found, falling back to SMARD (Bundesnetzagentur)")
            prices_df = smard.fetch_day_ahead_prices(start_date, end_date)
    else:
        prices_df = smard.fetch_day_ahead_prices(start_date, end_date)

    if not prices_df.empty:
        results["prices_count"] = db.upsert_prices(prices_df)
        logger.info(f"✓ Upserted {results['prices_count']} price records into DuckDB")

    # 2. Generation & Load
    logger.info(f"Step 2: Pulling Realized Generation & Load (Solar, Wind Onshore/Offshore, Total Load)...")
    gen_df = smard.fetch_generation_and_load(start_date, end_date)
    if not gen_df.empty:
        results["generation_count"] = db.upsert_generation(gen_df)
        logger.info(f"✓ Upserted {results['generation_count']} generation records into DuckDB")

    # 3. Forecasts
    logger.info(f"Step 3: Pulling Day-Ahead Renewable Generation Forecasts...")
    fc_df = smard.fetch_generation_forecasts(start_date, end_date)
    if not fc_df.empty:
        results["forecasts_count"] = db.upsert_forecasts(fc_df)
        logger.info(f"✓ Upserted {results['forecasts_count']} forecast records into DuckDB")

    # 4. Weather Data
    logger.info(f"Step 4: Pulling ERA5 Weather Data from Open-Meteo for German benchmark sites...")
    target_sites = sites or GERMAN_BENCHMARK_SITES
    weather_dfs = []
    for site in target_sites:
        try:
            w_df = openmeteo.fetch_site_weather(site, start_date, end_date)
            weather_dfs.append(w_df)
        except Exception as e:
            logger.error(f"Failed to fetch weather for {site.site_id if hasattr(site, 'site_id') else site}: {e}")

    if weather_dfs:
        combined_weather = pd.concat(weather_dfs, ignore_index=True)
        results["weather_count"] = db.upsert_weather(combined_weather)
        logger.info(f"✓ Upserted {results['weather_count']} weather records across {len(target_sites)} sites into DuckDB")

    # 5. Export to Parquet
    if export_parquet:
        logger.info("Step 5: Exporting clean datasets from DuckDB to compressed Parquet files...")
        storage = ParquetStorage()
        results["parquet_exported"] = storage.export_all_tables()
        logger.info("✓ Parquet export complete")

    # 6. Analytics & Summary Reporting
    logger.info("\n" + "=" * 60)
    logger.info("PPA PRICING & RISK ANALYTICS SUMMARY")
    logger.info("=" * 60)
    analytics = PpaRiskAnalytics(db=db)
    summary = analytics.get_summary_metrics()

    if summary:
        summary_rows = [
            ["Metric", "Value", "Unit / Notes"],
            ["Total Analyzed Hours", summary.get("total_hours"), "hours"],
            ["Baseload Market Price", f"{summary.get('baseload_price_eur_mwh'):.2f}", "EUR/MWh"],
            ["Price Range [Min, Max]", f"[{summary.get('min_price_eur_mwh'):.2f}, {summary.get('max_price_eur_mwh'):.2f}]", "EUR/MWh"],
            ["Price Volatility (StdDev)", f"{summary.get('price_volatility_eur_mwh'):.2f}", "EUR/MWh"],
            ["Negative Price Hours", f"{summary.get('negative_price_hours')} ({summary.get('pct_negative_hours'):.2f}%)", "hours (% of total)"],
            ["Solar Capture Price", f"{summary.get('solar_capture_price_eur_mwh'):.2f}" if summary.get('solar_capture_price_eur_mwh') else "N/A", "EUR/MWh (generation-weighted)"],
            ["Solar Capture Factor (MWF)", f"{summary.get('solar_capture_factor'):.4f}" if summary.get('solar_capture_factor') else "N/A", "Capture / Baseload ratio"],
            ["Wind Onshore Capture Price", f"{summary.get('wind_onshore_capture_price_eur_mwh'):.2f}" if summary.get('wind_onshore_capture_price_eur_mwh') else "N/A", "EUR/MWh (generation-weighted)"],
            ["Wind Onshore Capture Factor", f"{summary.get('wind_onshore_capture_factor'):.4f}" if summary.get('wind_onshore_capture_factor') else "N/A", "Capture / Baseload ratio"],
            ["Combined Wind Capture Price", f"{summary.get('total_wind_capture_price_eur_mwh'):.2f}" if summary.get('total_wind_capture_price_eur_mwh') else "N/A", "EUR/MWh (onshore + offshore)"],
            ["Combined Wind Capture Factor", f"{summary.get('total_wind_capture_factor'):.4f}" if summary.get('total_wind_capture_factor') else "N/A", "Capture / Baseload ratio"],
        ]
        print("\n" + tabulate(summary_rows[1:], headers=summary_rows[0], tablefmt="fancy_grid"))

        # Monthly breakdown
        monthly_df = analytics.get_monthly_capture_table()
        if not monthly_df.empty:
            print("\nMonthly Capture Prices & Marktwertfaktor:")
            print(tabulate(monthly_df, headers="keys", tablefmt="github", showindex=False))

        # Weather correlation
        corr_df = analytics.get_weather_price_correlation()
        if not corr_df.empty:
            print("\nLocal Weather vs Wholesale Price Correlations (Cannibalization Risk):")
            print(tabulate(corr_df, headers="keys", tablefmt="github", showindex=False))

    db.close()
    return results
