import argparse
import sys
from tabulate import tabulate
from ppa_pipeline.pipeline import run_pipeline
from ppa_pipeline.storage.duckdb_manager import DuckDBManager
from ppa_pipeline.analytics.ppa_metrics import PpaRiskAnalytics

PRESETS = {
    "2024-q1": ("2024-01-01", "2024-03-31"),
    "2024-summer": ("2024-06-01", "2024-08-31"),
    "2024-sample": ("2024-05-01", "2024-05-31"),
    "2023-sample": ("2023-06-01", "2023-06-30"),
}


def main():
    parser = argparse.ArgumentParser(
        description="German Solar & Wind PPA Data Pipeline: SMARD/ENTSO-E & Open-Meteo ERA5 -> DuckDB/Parquet"
    )
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--preset",
        type=str,
        choices=list(PRESETS.keys()),
        default="2024-sample",
        help="Date preset (default: 2024-sample: May 2024, high solar & wind dynamics)",
    )
    parser.add_argument(
        "--use-entsoe",
        action="store_true",
        help="Use ENTSO-E API instead of SMARD for day-ahead prices (requires ENTSOE_API_TOKEN)",
    )
    parser.add_argument(
        "--no-parquet",
        action="store_true",
        help="Disable automatic Parquet export",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display current DuckDB database table counts and exit",
    )
    parser.add_argument(
        "--analytics-only",
        action="store_true",
        help="Run PPA capture analytics on existing DuckDB data without fetching new data",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Execute custom SQL query against DuckDB and print result table",
    )
    parser.add_argument(
        "--price",
        action="store_true",
        help="Run Pay-as-Produced PPA pricer and risk simulation for a renewable asset",
    )
    parser.add_argument(
        "--tech",
        type=str,
        choices=["solar_pv", "wind_onshore", "wind_offshore"],
        default="solar_pv",
        help="Asset technology for PPA valuation (default: solar_pv)",
    )
    parser.add_argument(
        "--capacity",
        type=float,
        default=50.0,
        help="Asset nameplate capacity in MW (default: 50.0)",
    )
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        help="Location ID (e.g. bavaria_solar, lower_saxony_wind, schleswig_wind)",
    )
    parser.add_argument(
        "--tenor",
        type=int,
        default=5,
        help="PPA contract duration in years (default: 5)",
    )

    args = parser.parse_args()

    if args.status:
        db = DuckDBManager()
        counts = db.get_table_counts()
        print("\nDuckDB Table Counts:")
        print(tabulate([[k, v] for k, v in counts.items()], headers=["Table", "Row Count"], tablefmt="fancy_grid"))
        db.close()
        return

    if args.query:
        db = DuckDBManager()
        df = db.query(args.query)
        print(f"\nQuery Results ({len(df)} rows):")
        print(tabulate(df, headers="keys", tablefmt="fancy_grid", showindex=False))
        db.close()
        return

    if args.analytics_only:
        db = DuckDBManager()
        analytics = PpaRiskAnalytics(db=db)
        summary = analytics.get_summary_metrics()
        if not summary:
            print("No data in DuckDB yet. Run the pipeline first: python main.py")
            return
        monthly_df = analytics.get_monthly_capture_table()
        print("\nMonthly Capture Prices & Marktwertfaktor:")
        print(tabulate(monthly_df, headers="keys", tablefmt="github", showindex=False))

        corr_df = analytics.get_weather_price_correlation()
        if not corr_df.empty:
            print("\nWeather vs Price Correlations:")
            print(tabulate(corr_df, headers="keys", tablefmt="github", showindex=False))
        db.close()
        return

    if args.price:
        from ppa_pipeline.models.generation import AssetSpecification, TechnologyType
        from ppa_pipeline.pricing.ppa_pricer import PayAsProducedPricer, PpaContractStructure

        db = DuckDBManager()
        market_df = db.query("SELECT * FROM market_prices ORDER BY timestamp_utc;")
        if market_df.empty:
            print("No market price data in DuckDB. Ingest data first with: python main.py")
            db.close()
            return

        tech_enum = TechnologyType(args.tech)
        default_loc = "bavaria_solar" if tech_enum == TechnologyType.SOLAR_PV else "lower_saxony_wind"
        location_id = args.location or default_loc

        weather_df = db.query(f"SELECT * FROM weather_timeseries WHERE location_id = '{location_id}' ORDER BY timestamp_utc;")
        if weather_df.empty:
            # Fallback to any location in weather_timeseries
            weather_df = db.query("SELECT * FROM weather_timeseries ORDER BY timestamp_utc LIMIT 744;")

        db.close()

        asset = AssetSpecification(
            name=f"German {args.tech.replace('_', ' ').title()}",
            technology=tech_enum,
            capacity_mw=args.capacity,
            location_id=location_id,
        )
        contract = PpaContractStructure(tenor_years=args.tenor)

        pricer = PayAsProducedPricer(historical_market_df=market_df, weather_df=weather_df)
        val = pricer.price_asset(asset_spec=asset, contract=contract)

        print("\n" + "=" * 65)
        print("PAY-AS-PRODUCED PPA VALUATION & PRICING WATERFALL")
        print("=" * 65)
        waterfall_rows = [[k, f"{v:+.2f} €/MWh" if k != "Fair Fixed PPA Price" and k != "Generation-Weighted Capture Price" else f"{v:.2f} €/MWh"] for k, v in val.waterfall_breakdown().items()]
        print(tabulate(waterfall_rows, headers=["Waterfall Component", "EUR / MWh"], tablefmt="fancy_grid"))

        print("\nKey Contract Metrics & Tail Risk Profile:")
        summary_rows = [[k, v] for k, v in val.summary_table().items()]
        print(tabulate(summary_rows, headers=["Metric", "Valuation Result"], tablefmt="fancy_grid"))
        return


    # Determine date range
    if args.start and args.end:
        start_date = args.start
        end_date = args.end
    elif args.preset:
        start_date, end_date = PRESETS[args.preset]
    else:
        start_date, end_date = ("2024-05-01", "2024-05-31")

    run_pipeline(
        start_date=start_date,
        end_date=end_date,
        use_entsoe=args.use_entsoe,
        export_parquet=not args.no_parquet,
    )


if __name__ == "__main__":
    main()
