# PPA Pricing and Risk Tool for German Solar & Wind Farms

An automated data pipeline and risk modeling engine tailored for German renewable energy Power Purchase Agreements (PPAs). It ingests wholesale electricity market data and ERA5 weather data, standardizes time series across German market boundaries, and stores datasets in **DuckDB** and partitioned **Parquet** files for PPA valuation, capture rate analysis, and merchant risk assessment.

---

## ⚡ Core Features

- **Electricity Market Ingestion**:
  - **SMARD (Bundesnetzagentur)**: Direct, open access without requiring an API key.
    - Day-Ahead wholesale prices (DE-LU bidding zone, hourly resolution)
    - Realized generation by technology (Solar PV, Wind Onshore, Wind Offshore, Total Grid Load)
    - Day-Ahead renewable generation forecasts
  - **ENTSO-E Transparency Platform**: Full support for European Day-Ahead prices (`A44`) using `ENTSOE_API_TOKEN`.
- **Weather & Resource Ingestion (ERA5 / Open-Meteo)**:
  - Hourly reanalysis and forecast weather data for representative German benchmark renewable clusters:
    - **Brandenburg**: High-capacity solar hub in Eastern Germany
    - **Bavaria**: Largest installed PV base in Southern Germany
    - **Schleswig-Holstein**: High-yield onshore wind corridor
    - **Lower Saxony**: Major onshore wind generation belt
    - **North Sea**: German Bight offshore wind cluster
  - Critical variables: GHI, Direct Normal Irradiance (DNI), 100m Hub-Height Wind Speed, 10m Wind Speed, Temperature, Surface Pressure.
- **High-Performance Storage**:
  - **DuckDB** (`data/ppa_market.duckdb`): Embedded columnar database optimized for fast time-series analytical queries and views.
  - **Apache Parquet** (`data/parquet/*.parquet`): ZSTD-compressed columnar storage for zero-copy queries and integration with downstream quantitative models.
- **PPA Risk Analytics**:
  - **Baseload Price**: Flat time-weighted average price ($\bar{P}$).
  - **Solar & Wind Capture Price**: Generation-weighted revenue price ($P_{\text{capture}} = \frac{\sum P_t \times Q_t}{\sum Q_t}$).
  - **Capture Factor / Market Value Factor (*Marktwertfaktor*)**: Ratio of capture price to baseload price ($MWF = \frac{P_{\text{capture}}}{\bar{P}}$).
  - **Solar Cannibalization & Merit-Order Effect**: Hourly price suppression analysis during solar peak hours.
  - **Negative Price Exposure**: Count and percentage of negative pricing hours (critical for EEG § 51 and merchant PPA risk).
  - **Weather-Price Correlation**: Empirical relationship between local solar irradiance / wind speeds and wholesale power prices.

---

## 🚀 Quickstart

### 1. Environment Setup

```bash
# Enable Python 3.12 (via pyenv or system Python)
pyenv local 3.12.7

# Activate the pre-configured virtual environment
source .venv/bin/activate

# Install / update dependencies (duckdb, pandas, pyarrow, openmeteo-requests, etc.)
pip install -r requirements.txt
```

### 2. Ingest Data & Run PPA Capture Analytics

To fetch data, store it in DuckDB, export Parquet files, and calculate PPA metrics:

```bash
# Run for a custom date range
python main.py --start 2024-05-01 --end 2024-05-31

# Or run using presets (e.g. 2024-sample, 2024-q1, 2024-summer)
python main.py --preset 2024-sample
```

### 3. Check Database Status & Query Tables

```bash
# Check current table row counts in DuckDB
python main.py --status

# View monthly capture prices and Marktwertfaktor without re-fetching
python main.py --analytics-only

# Execute custom SQL queries directly against DuckDB
python main.py --query "SELECT month, baseload_price_eur_mwh, solar_capture_price_eur_mwh, solar_capture_factor, negative_price_hours FROM v_monthly_capture_metrics"
```

---

## 📊 Database Schema & Views

### DuckDB Tables (`data/ppa_market.duckdb`)

| Table Name | Description | Key Columns |
| :--- | :--- | :--- |
| `market_prices` | Day-ahead electricity prices | `timestamp_utc`, `price_eur_mwh`, `bidding_zone` |
| `market_generation` | Actual grid generation & load | `timestamp_utc`, `solar_mwh`, `wind_onshore_mwh`, `wind_offshore_mwh`, `total_load_mwh` |
| `market_forecasts` | Day-ahead generation forecasts | `timestamp_utc`, `solar_forecast_mwh`, `wind_onshore_forecast_mwh`, `wind_offshore_forecast_mwh` |
| `weather_timeseries` | ERA5 hourly weather | `timestamp_utc`, `location_id`, `temperature_2m_c`, `direct_normal_irradiance_wm2`, `wind_speed_100m_ms` |

### Analytical Views

- **`v_ppa_market`**: Joins hourly day-ahead prices with actual solar and wind generation, calculating hourly revenues (`price * generation`) and negative pricing flags.
- **`v_monthly_capture_metrics`**: Computes monthly Baseload Price, Solar Capture Price, Wind Capture Price, Marktwertfaktor (capture factor), and negative price hours.

---

## 📁 Querying Parquet Files Directly with Python / DuckDB

DuckDB allows querying exported Parquet files directly without spinning up a database server:

```python
import duckdb

# Query combined PPA market Parquet directly
df = duckdb.query("""
    SELECT 
        timestamp_utc,
        price_eur_mwh,
        solar_mwh,
        total_wind_mwh,
        is_negative_price
    FROM read_parquet('data/parquet/ppa_market_combined.parquet')
    WHERE price_eur_mwh < 0
    ORDER BY price_eur_mwh ASC
    LIMIT 10
""").df()

print(df)
```

---

## 🔑 Optional: ENTSO-E API Configuration

If you prefer using the ENTSO-E Transparency Platform over SMARD for wholesale prices:
1. Register for a free account at [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/).
2. Request an API key under your account settings.
3. Set the environment variable:
   ```bash
   export ENTSOE_API_TOKEN="your-entsoe-token-here"
   ```
4. Run the pipeline with `--use-entsoe`:
   ```bash
   python main.py --preset 2024-sample --use-entsoe
   ```
