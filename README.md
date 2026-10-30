# PPA Pricing and Risk Tool for German Solar & Wind Farms

An institutional-grade quantitative data pipeline, risk modeling engine, and interactive dashboard tailored for German renewable energy **Power Purchase Agreements (PPAs)**. 

### 🌟 Flagship Project: Pay-as-Produced (PaP) PPA Pricer
Given any German wind or solar asset, the tool estimates the **fair fixed PPA strike price** ($K^*$) and models the complete downside risk profile (volume risk, profile cannibalization, balancing fees, and negative price hours under EEG § 51).

---

## ⚡ Key Capabilities

1. **Automated Market & Weather Ingestion Pipeline**:
   * **SMARD (Bundesnetzagentur)**: Direct open-access hourly Day-Ahead power prices (`DE-LU` bidding zone), actual generation by technology, and grid forecasts.
   * **ENTSO-E Transparency Platform**: Full European Day-Ahead API integration.
   * **ERA5 Atmospheric Reanalysis (Open-Meteo)**: Hourly solar irradiance (GTI, DNI) and 100m hub-height wind speeds across 5 benchmark German clusters:
     * *Bavaria* & *Brandenburg* (High-capacity solar PV hubs)
     * *Lower Saxony* & *Schleswig-Holstein* (High-yield onshore wind corridors)
     * *North Sea* (German Bight offshore wind cluster)
2. **Physical Generation Asset Models**:
   * **Solar PV**: Thermal cell temperature derating ($NOCT$), inverter AC clipping ratio ($DC/AC$), and annual degradation.
   * **Wind Turbines**: Hellmann power law wind shear extrapolation to hub height, standard IEC Class II/III cubic aerodynamic power curve, cut-in / rated / storm cut-out shutoff, and wake derating.
3. **Correlated Price Simulation & Monte Carlo Engine**:
   * Calibrated diurnal and monthly price shapes.
   * Mean-Reverting Ornstein-Uhlenbeck with Jump Diffusion (MRJD).
   * Coupled endogenous cannibalization modeling: Wholesale spot prices dynamically depress during hours of high simulated renewable output.
4. **Pay-as-Produced Valuation Waterfall**:
   * Evaluates Expected Baseload Price $\rightarrow$ Cannibalization / Profile Haircut $\rightarrow$ Expected Capture Price $\rightarrow$ Balancing & Forecast Costs $\rightarrow$ Risk Buffer $\rightarrow$ Downside Floor Guarantee $\rightarrow$ **Fair Fixed PPA Price**.
5. **Quantitative Risk Metrics**:
   * Volumetric and revenue distributions ($P10 / P50 / P90$).
   * 95% Value at Risk ($VaR_{95}$) and 95% Conditional Value at Risk ($CVaR_{95}$ / Expected Shortfall).
   * Negative pricing hour exposure and cash drain (EEG § 51 regulatory risk).
6. **Interactive Financial Terminal Dashboard**:
   * Streamlit & Plotly app with asset parameter sliders, interactive pricing waterfall, Monte Carlo fan charts, and diurnal duck-curve diagnostics.

---

## 🚀 Quickstart

### 1. Installation
Install the project in editable mode with development dependencies:

```bash
# Clone the repository and enter directory
cd "PPA pricing and risk tool for a German solar or wind farm"

# Activate the virtual environment
source .venv/bin/activate

# Install package and dependencies
pip install -e .
```

### 2. Launch the Next.js + FastAPI Modern Web Stack
Run the full-stack financial terminal:

```bash
# Terminal 1: Start FastAPI REST Backend (Port 8000)
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Start Next.js App Router Frontend (Port 3000)
cd frontend && npm run dev
```
* **Frontend UI**: [http://localhost:3000](http://localhost:3000)
* **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)

*(Optional: The classic Streamlit dashboard is also available via `streamlit run dashboard/app.py`)*


### 3. Price Assets via CLI
Run the Pay-as-Produced PPA pricer directly from the terminal:

```bash
# Price a 50 MW Solar PV asset in Bavaria over a 5-year tenor
python main.py --price --tech solar_pv --capacity 50.0 --tenor 5

# Price a 75 MW Onshore Wind farm in Lower Saxony over a 10-year tenor
python main.py --price --tech wind_onshore --capacity 75.0 --tenor 10
```

### 4. Ingest Historical Market & Weather Data
Pull German wholesale power prices and ERA5 weather into DuckDB and Parquet:

```bash
# Run for a preset (e.g. May 2024 with high renewable dynamics)
python main.py --preset 2024-sample

# Run for a custom date range
python main.py --start 2024-01-01 --end 2024-03-31
```

### 5. Run Analytics & Database Queries
```bash
# Check current table row counts in DuckDB
python main.py --status

# View historical monthly capture prices and Marktwertfaktor
python main.py --analytics-only

# Execute custom SQL queries directly against DuckDB
python main.py --query "SELECT month, baseload_price_eur_mwh, solar_capture_price_eur_mwh, solar_capture_factor, negative_price_hours FROM v_monthly_capture_metrics"
```

---

## 🧪 Testing & CI

Run the unit test suite using `pytest`:

```bash
pytest
```
* Automated testing includes solar cell physics, wind power curves, Monte Carlo path dimensions, cannibalization sensitivity, pricing waterfall arithmetic, and floor options.
* GitHub Actions CI configuration is located at `.github/workflows/ci.yml`.

---

## 📖 Methodology & Limitations

For the complete mathematical formulations, equations, and modeling assumptions, consult:
📄 **[METHODOLOGY.md](METHODOLOGY.md)**

* **Contract Payoffs**: Formulaic definition of Pay-as-Produced vs. Baseload swaps.
* **Physics Formulations**: Solar thermal derating, inverter clipping, and wind shear models.
* **Price Dynamics**: Mean-reverting Ornstein-Uhlenbeck jump processes and cannibalization coupling.
* **Risk Definitions**: $P10 / P50 / P90$, Value at Risk ($VaR$), and German EEG § 51 negative price thresholds.
* **Limitations**: German single-bidding-zone basis risk and transmission redispatch considerations.
