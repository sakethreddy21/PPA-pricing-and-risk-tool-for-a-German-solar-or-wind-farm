import logging
from pathlib import Path
from typing import Optional, Union
import duckdb
import pandas as pd
from ppa_pipeline.config import PARQUET_DIR, DUCKDB_PATH

logger = logging.getLogger(__name__)


class ParquetStorage:
    """Handles exporting DuckDB tables/views to Parquet and querying Parquet directly."""

    def __init__(self, output_dir: Optional[Union[str, Path]] = None, db_path: Optional[Union[str, Path]] = None):
        self.output_dir = Path(output_dir or PARQUET_DIR)
        self.db_path = str(db_path or DUCKDB_PATH)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_all_tables(self) -> dict:
        """Export all primary tables and views from DuckDB to compressed Parquet files."""
        tables_to_export = [
            ("market_prices", "market_prices.parquet"),
            ("market_generation", "market_generation.parquet"),
            ("market_forecasts", "market_forecasts.parquet"),
            ("weather_timeseries", "weather_timeseries.parquet"),
            ("v_ppa_market", "ppa_market_combined.parquet"),
            ("v_monthly_capture_metrics", "monthly_capture_metrics.parquet"),
        ]

        conn = duckdb.connect(self.db_path)
        exported = {}
        for source_name, file_name in tables_to_export:
            out_file = self.output_dir / file_name
            try:
                # Check if table has data
                cnt = conn.execute(f"SELECT COUNT(*) FROM {source_name}").fetchone()[0]
                if cnt > 0:
                    conn.execute(f"""
                        COPY {source_name} TO '{out_file}' (FORMAT PARQUET, COMPRESSION ZSTD);
                    """)
                    exported[source_name] = {"rows": cnt, "path": str(out_file)}
                    logger.info(f"Exported {source_name} ({cnt} rows) to {out_file}")
                else:
                    exported[source_name] = {"rows": 0, "path": None}
            except Exception as e:
                logger.warning(f"Skipped export for {source_name}: {e}")
        conn.close()
        return exported

    @staticmethod
    def read_parquet_query(parquet_path: str, sql_filter: str = "") -> pd.DataFrame:
        """Query a Parquet file directly using DuckDB without intermediate memory copy."""
        query = f"SELECT * FROM read_parquet('{parquet_path}') {sql_filter}"
        return duckdb.query(query).df()
