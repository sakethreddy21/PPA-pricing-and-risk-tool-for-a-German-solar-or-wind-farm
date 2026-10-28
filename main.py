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
