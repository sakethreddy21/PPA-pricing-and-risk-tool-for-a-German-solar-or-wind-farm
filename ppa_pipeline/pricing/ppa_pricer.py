import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

from ppa_pipeline.models.generation import AssetSpecification, simulate_asset_generation
from ppa_pipeline.models.price_simulation import PriceSimulationEngine, SimulationConfig
from ppa_pipeline.pricing.risk_metrics import ContractRiskMetrics, calculate_risk_metrics

logger = logging.getLogger(__name__)


@dataclass
class PpaContractStructure:
    """Terms and settlement conditions for a Power Purchase Agreement."""
    contract_name: str = "Standard Pay-as-Produced PPA"
    tenor_years: int = 5  # Contract duration
    settlement_type: str = "pay_as_produced"  # "pay_as_produced", "annual_baseload", "monthly_capture"
    balancing_cost_eur_mwh: float = 2.50  # Balancing and scheduling fee (forecast error)
    risk_premium_eur_mwh: float = 1.50  # Off-taker downside risk buffer
    floor_price_eur_mwh: Optional[float] = None  # Optional downside floor (e.g. 0.0 EUR/MWh)
    eeg_curtailment_clause: bool = True  # If True, curtail production during negative prices


@dataclass
class PpaValuationResult:
    """Final PPA pricing waterfall, cash flow metrics, and risk assessment."""
    asset_name: str
    technology: str
    capacity_mw: float
    tenor_years: int

    # Fair Fixed PPA Pricing Waterfall (EUR/MWh)
    expected_baseload_price: float
    cannibalization_discount: float  # Profile haircut
    expected_capture_price: float  # Generation-weighted
    balancing_cost: float
    risk_premium: float
    floor_option_value: float  # Value of floor if present
    fair_ppa_fixed_price: float  # Final fair strike price offered to developer

    # Capture ratios
    capture_factor_expected: float

    # Contract Value & Expected Annual Revenues
    expected_annual_generation_mwh: float
    expected_annual_revenue_ppa_eur: float
    expected_annual_revenue_merchant_eur: float
    ppa_revenue_uplift_vs_merchant_eur: float

    # Detailed risk metrics
    risk_metrics: ContractRiskMetrics

    def waterfall_breakdown(self) -> Dict[str, float]:
        """Returns the sequential waterfall items for charting."""
        return {
            "Expected Baseload Market Price": self.expected_baseload_price,
            "Cannibalization (Profile Haircut)": -self.cannibalization_discount,
            "Generation-Weighted Capture Price": self.expected_capture_price,
            "Balancing & Scheduling Costs": -self.balancing_cost,
            "Risk Buffer / Capital Margin": -self.risk_premium,
            "Floor Guarantee Premium": self.floor_option_value,
            "Fair Fixed PPA Price": self.fair_ppa_fixed_price,
        }

    def summary_table(self) -> Dict[str, Any]:
        """Summary dictionary for display and reporting."""
        return {
            "Asset": f"{self.asset_name} ({self.technology.upper()} - {self.capacity_mw} MW)",
            "Tenor": f"{self.tenor_years} Years",
            "Fair Fixed PPA Price": f"{self.fair_ppa_fixed_price:.2f} €/MWh",
            "Expected Baseload Price": f"{self.expected_baseload_price:.2f} €/MWh",
            "Expected Capture Price": f"{self.expected_capture_price:.2f} €/MWh",
            "Cannibalization Haircut": f"-{self.cannibalization_discount:.2f} €/MWh",
            "Marktwertfaktor (Capture Factor)": f"{self.capture_factor_expected * 100:.1f}%",
            "Expected Annual Generation": f"{self.expected_annual_generation_mwh:,.0f} MWh",
            "P50 Annual PPA Revenue": f"€{self.expected_annual_revenue_ppa_eur:,.0f}",
            "P90 Downside Revenue": f"€{self.risk_metrics.revenue_p90_eur:,.0f}",
            "Value at Risk (95% VaR)": f"€{self.risk_metrics.var_95_eur:,.0f}",
            "Expected Negative Hours/yr": f"{self.risk_metrics.expected_negative_hours_annual:.0f} hrs ({self.risk_metrics.pct_negative_hours:.1f}%)",
        }


class PayAsProducedPricer:
    """Quantitative valuation engine for German Pay-as-Produced (PaP) PPAs."""

    def __init__(
        self,
        historical_market_df: pd.DataFrame,
        weather_df: pd.DataFrame,
        sim_config: Optional[SimulationConfig] = None,
    ):
        self.market_df = historical_market_df
        self.weather_df = weather_df
        self.sim_engine = PriceSimulationEngine(historical_market_df, config=sim_config)

    def price_asset(
        self,
        asset_spec: AssetSpecification,
        contract: Optional[PpaContractStructure] = None,
        expected_baseload_override: Optional[float] = None,
    ) -> PpaValuationResult:
        """Calculates fair fixed Pay-as-Produced PPA strike price and risk profile."""
        contract = contract or PpaContractStructure()

        # 1. Simulate base hourly generation profile for the specific asset
        base_gen_df = simulate_asset_generation(asset_spec, self.weather_df, year_index=0)

        # 2. Run coupled Monte Carlo paths of hourly prices & generation
        sim_output = self.sim_engine.simulate_paths(
            base_generation_df=base_gen_df,
            tenor_years=contract.tenor_years,
            expected_baseload=expected_baseload_override,
        )
        price_matrix = sim_output["price_matrix"]
        gen_matrix = sim_output["gen_matrix"]

        # 3. Calculate full risk metrics distribution
        risk_metrics = calculate_risk_metrics(
            price_matrix=price_matrix,
            gen_matrix=gen_matrix,
            tenor_years=contract.tenor_years,
        )

        # 4. Fair PPA Pricing Waterfall
        baseload = risk_metrics.baseload_price_mean_eur_mwh
        exp_capture = risk_metrics.capture_price_mean_eur_mwh
        cannibalization = max(baseload - exp_capture, 0.0)

        # Floor option evaluation (if contract specifies a floor price, e.g. 0 EUR/MWh)
        floor_option_val = 0.0
        if contract.floor_price_eur_mwh is not None:
            # Payoff is max(Floor - Price, 0) weighted by generation
            floor_diff = np.maximum(contract.floor_price_eur_mwh - price_matrix, 0.0)
            floor_payoff_scenario = np.sum(floor_diff * gen_matrix, axis=0) / np.maximum(np.sum(gen_matrix, axis=0), 1e-6)
            floor_option_val = float(np.mean(floor_payoff_scenario))

        # Fair Pay-as-Produced fixed strike price:
        # K* = Expected Capture Price - Balancing Cost - Risk Premium + Floor Value
        fair_ppa_price = max(
            exp_capture - contract.balancing_cost_eur_mwh - contract.risk_premium_eur_mwh + floor_option_val,
            0.0,
        )

        # Annual revenue figures
        annual_gen = risk_metrics.volume_mean_mwh
        annual_ppa_revenue = annual_gen * fair_ppa_price
        annual_merchant_revenue = risk_metrics.revenue_mean_eur
        uplift = annual_ppa_revenue - annual_merchant_revenue

        return PpaValuationResult(
            asset_name=asset_spec.name,
            technology=asset_spec.technology.value,
            capacity_mw=asset_spec.capacity_mw,
            tenor_years=contract.tenor_years,
            expected_baseload_price=round(baseload, 2),
            cannibalization_discount=round(cannibalization, 2),
            expected_capture_price=round(exp_capture, 2),
            balancing_cost=round(contract.balancing_cost_eur_mwh, 2),
            risk_premium=round(contract.risk_premium_eur_mwh, 2),
            floor_option_value=round(floor_option_val, 2),
            fair_ppa_fixed_price=round(fair_ppa_price, 2),
            capture_factor_expected=round(risk_metrics.capture_factor_p50, 4),
            expected_annual_generation_mwh=round(annual_gen, 1),
            expected_annual_revenue_ppa_eur=round(annual_ppa_revenue, 0),
            expected_annual_revenue_merchant_eur=round(annual_merchant_revenue, 0),
            ppa_revenue_uplift_vs_merchant_eur=round(uplift, 0),
            risk_metrics=risk_metrics,
        )
