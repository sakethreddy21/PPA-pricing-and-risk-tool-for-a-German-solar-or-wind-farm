import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from ppa_pipeline.storage.duckdb_manager import DuckDBManager
from ppa_pipeline.models.generation import AssetSpecification, TechnologyType
from ppa_pipeline.models.price_simulation import SimulationConfig
from ppa_pipeline.pricing.ppa_pricer import PayAsProducedPricer, PpaContractStructure
from ppa_pipeline.analytics.ppa_metrics import PpaRiskAnalytics

app = FastAPI(
    title="German Renewable PPA Pricing API",
    version="1.0.0",
    description="Quantitative REST API for Pay-as-Produced PPA valuation and risk simulation.",
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PricingRequest(BaseModel):
    technology: str = Field("solar_pv", description="Asset type: solar_pv, wind_onshore, wind_offshore")
    capacity_mw: float = Field(50.0, ge=1.0, le=500.0, description="Plant nameplate capacity in MW")
    location_id: Optional[str] = Field("bavaria_solar", description="German benchmark cluster ID")
    tenor_years: int = Field(5, ge=1, le=15, description="Contract duration in years")
    expected_baseload_eur_mwh: Optional[float] = Field(65.0, description="Forward baseload power price")
    balancing_cost_eur_mwh: float = Field(2.50, description="Balancing/imbalance fee in EUR/MWh")
    risk_premium_eur_mwh: float = Field(1.50, description="Off-taker capital/risk buffer in EUR/MWh")
    floor_price_eur_mwh: Optional[float] = Field(None, description="Optional downside floor strike")
    num_scenarios: int = Field(500, ge=50, le=1000, description="Monte Carlo simulation iterations")


class PricingResponse(BaseModel):
    asset_name: str
    technology: str
    capacity_mw: float
    tenor_years: int
    fair_ppa_fixed_price: float
    expected_baseload_price: float
    cannibalization_discount: float
    expected_capture_price: float
    balancing_cost: float
    risk_premium: float
    floor_option_value: float
    capture_factor_expected: float
    expected_annual_generation_mwh: float
    expected_annual_revenue_ppa_eur: float
    expected_annual_revenue_merchant_eur: float
    waterfall: Dict[str, float]
    summary_table: Dict[str, Any]
    risk_metrics: Dict[str, Any]


@app.get("/api/health")
def health_check():
    try:
        db = DuckDBManager(read_only=True)
        counts = db.get_table_counts()
        db.close()
        return {"status": "healthy", "database": "connected", "table_counts": counts}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/api/metadata")
def get_metadata():
    return {
        "technologies": [
            {"id": "solar_pv", "label": "Solar PV", "default_location": "bavaria_solar"},
            {"id": "wind_onshore", "label": "Onshore Wind", "default_location": "lower_saxony_wind"},
            {"id": "wind_offshore", "label": "Offshore Wind", "default_location": "north_sea_offshore"},
        ],
        "locations": [
            {"id": "bavaria_solar", "label": "Bavaria (High Solar Irradiance Hub)", "tech": "solar_pv"},
            {"id": "brandenburg_solar", "label": "Brandenburg (Eastern Solar Belt)", "tech": "solar_pv"},
            {"id": "lower_saxony_wind", "label": "Lower Saxony (High-Yield Onshore Wind)", "tech": "wind_onshore"},
            {"id": "schleswig_wind", "label": "Schleswig-Holstein (Coastal Wind Corridor)", "tech": "wind_onshore"},
            {"id": "north_sea_offshore", "label": "North Sea (German Bight Offshore Cluster)", "tech": "wind_offshore"},
        ],
    }


@app.post("/api/price", response_model=PricingResponse)
def calculate_ppa_price(req: PricingRequest):
    try:
        db = DuckDBManager(read_only=True)
        market_df = db.query("SELECT * FROM market_prices ORDER BY timestamp_utc;")
        if market_df.empty:
            db.close()
            raise HTTPException(status_code=400, detail="No historical market data in database. Run ingestion first.")

        location_id = req.location_id
        if not location_id:
            location_id = "bavaria_solar" if req.technology == "solar_pv" else "lower_saxony_wind"

        weather_df = db.query(f"SELECT * FROM weather_timeseries WHERE location_id = '{location_id}' ORDER BY timestamp_utc;")
        if weather_df.empty:
            weather_df = db.query("SELECT * FROM weather_timeseries ORDER BY timestamp_utc LIMIT 744;")
        db.close()

        tech_enum = TechnologyType(req.technology)
        asset_spec = AssetSpecification(
            name=f"German {req.technology.replace('_', ' ').title()}",
            technology=tech_enum,
            capacity_mw=req.capacity_mw,
            location_id=location_id,
        )

        contract = PpaContractStructure(
            contract_name=f"{req.tenor_years}Y Pay-as-Produced PPA",
            tenor_years=req.tenor_years,
            balancing_cost_eur_mwh=req.balancing_cost_eur_mwh,
            risk_premium_eur_mwh=req.risk_premium_eur_mwh,
            floor_price_eur_mwh=req.floor_price_eur_mwh,
        )

        sim_config = SimulationConfig(
            num_scenarios=req.num_scenarios,
            expected_mean_price=req.expected_baseload_eur_mwh or 65.0,
        )

        pricer = PayAsProducedPricer(
            historical_market_df=market_df,
            weather_df=weather_df,
            sim_config=sim_config,
        )

        val = pricer.price_asset(
            asset_spec=asset_spec,
            contract=contract,
            expected_baseload_override=req.expected_baseload_eur_mwh,
        )

        return PricingResponse(
            asset_name=val.asset_name,
            technology=val.technology,
            capacity_mw=val.capacity_mw,
            tenor_years=val.tenor_years,
            fair_ppa_fixed_price=val.fair_ppa_fixed_price,
            expected_baseload_price=val.expected_baseload_price,
            cannibalization_discount=val.cannibalization_discount,
            expected_capture_price=val.expected_capture_price,
            balancing_cost=val.balancing_cost,
            risk_premium=val.risk_premium,
            floor_option_value=val.floor_option_value,
            capture_factor_expected=val.capture_factor_expected,
            expected_annual_generation_mwh=val.expected_annual_generation_mwh,
            expected_annual_revenue_ppa_eur=val.expected_annual_revenue_ppa_eur,
            expected_annual_revenue_merchant_eur=val.expected_annual_revenue_merchant_eur,
            waterfall=val.waterfall_breakdown(),
            summary_table=val.summary_table(),
            risk_metrics=val.risk_metrics.to_dict(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/duck-curve")
def get_duck_curve():
    db = DuckDBManager(read_only=True)
    analytics = PpaRiskAnalytics(db=db)
    df = analytics.get_solar_cannibalization_profile()
    db.close()
    if df.empty:
        return []
    return df.to_dict(orient="records")


@app.get("/api/capture-history")
def get_capture_history():
    db = DuckDBManager(read_only=True)
    analytics = PpaRiskAnalytics(db=db)
    df = analytics.get_monthly_capture_table()
    db.close()
    if df.empty:
        return []
    return df.to_dict(orient="records")


@app.get("/api/weather-correlations")
def get_weather_correlations():
    db = DuckDBManager(read_only=True)
    analytics = PpaRiskAnalytics(db=db)
    df = analytics.get_weather_price_correlation()
    db.close()
    if df.empty:
        return []
    return df.to_dict(orient="records")

