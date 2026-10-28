import logging
from dataclasses import dataclass
from typing import Dict, Any, List
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ContractRiskMetrics:
    """Comprehensive volumetric, profile, and financial risk metrics for a PPA contract."""
    # Volume Risk (MWh)
    volume_p10_mwh: float
    volume_p50_mwh: float
    volume_p90_mwh: float
    volume_mean_mwh: float
    volume_std_mwh: float

    # Capture Price Risk (EUR/MWh)
    capture_price_p10_eur_mwh: float
    capture_price_p50_eur_mwh: float
    capture_price_p90_eur_mwh: float
    capture_price_mean_eur_mwh: float
    capture_price_std_eur_mwh: float

    # Baseload Price (EUR/MWh)
    baseload_price_mean_eur_mwh: float

    # Capture Factor (Marktwertfaktor)
    capture_factor_p50: float
    capture_factor_p90: float

    # Financial Revenue Distribution (EUR per year or total contract)
    revenue_p10_eur: float
    revenue_p50_eur: float
    revenue_p90_eur: float
    revenue_mean_eur: float
    revenue_std_eur: float

    # Downside Tail Risk (95% Confidence)
    var_95_eur: float  # Value at Risk: P50 - 5th percentile
    cvar_95_eur: float  # Expected Shortfall: average of worst 5%

    # Profile & Shape Risk
    profile_cost_eur_mwh: float  # Baseload Price - Capture Price
    shape_risk_volatility_eur_mwh: float

    # Negative Price Exposure
    expected_negative_hours_annual: float
    pct_negative_hours: float
    unhedged_negative_cash_drain_eur: float

    def to_dict(self) -> Dict[str, Any]:
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in self.__dict__.items()}


def calculate_risk_metrics(
    price_matrix: np.ndarray,
    gen_matrix: np.ndarray,
    tenor_years: int = 1,
) -> ContractRiskMetrics:
    """Calculates quantitative risk metrics across simulated Monte Carlo paths.
    
    Args:
        price_matrix: Shape (num_hours, num_scenarios)
        gen_matrix: Shape (num_hours, num_scenarios)
        tenor_years: Contract duration
        
    Returns:
        ContractRiskMetrics dataclass
    """
    num_hours, n_scenarios = price_matrix.shape

    # 1. Volume metrics per scenario (annualized MWh)
    total_mwh_per_scenario = np.sum(gen_matrix, axis=0)
    annual_mwh_per_scenario = total_mwh_per_scenario / tenor_years

    # In energy finance: P90 is conservative low production (10th percentile of CDF),
    # P10 is optimistic high production (90th percentile).
    vol_p90 = float(np.percentile(annual_mwh_per_scenario, 10))  # Downside 90% exceedance
    vol_p50 = float(np.percentile(annual_mwh_per_scenario, 50))
    vol_p10 = float(np.percentile(annual_mwh_per_scenario, 90))
    vol_mean = float(np.mean(annual_mwh_per_scenario))
    vol_std = float(np.std(annual_mwh_per_scenario))

    # 2. Baseload prices per scenario
    baseload_per_scenario = np.mean(price_matrix, axis=0)
    mean_baseload = float(np.mean(baseload_per_scenario))

    # 3. Generation-weighted Capture Price per scenario
    # P_cap = Sum(P_t * Q_t) / Sum(Q_t)
    total_revenues_per_scenario = np.sum(price_matrix * gen_matrix, axis=0)
    capture_price_per_scenario = total_revenues_per_scenario / np.maximum(total_mwh_per_scenario, 1e-6)

    # For prices: P90 conservative downside is 10th percentile
    cap_p90 = float(np.percentile(capture_price_per_scenario, 10))
    cap_p50 = float(np.percentile(capture_price_per_scenario, 50))
    cap_p10 = float(np.percentile(capture_price_per_scenario, 90))
    cap_mean = float(np.mean(capture_price_per_scenario))
    cap_std = float(np.std(capture_price_per_scenario))

    # 4. Capture factor
    cf_per_scenario = capture_price_per_scenario / np.maximum(baseload_per_scenario, 1e-6)
    cf_p50 = float(np.percentile(cf_per_scenario, 50))
    cf_p90 = float(np.percentile(cf_per_scenario, 10))

    # 5. Financial revenues (annualized EUR)
    annual_rev_per_scenario = total_revenues_per_scenario / tenor_years
    rev_p90 = float(np.percentile(annual_rev_per_scenario, 10))
    rev_p50 = float(np.percentile(annual_rev_per_scenario, 50))
    rev_p10 = float(np.percentile(annual_rev_per_scenario, 90))
    rev_mean = float(np.mean(annual_rev_per_scenario))
    rev_std = float(np.std(annual_rev_per_scenario))

    # 6. Value at Risk (VaR 95%) and CVaR 95%
    var_95_cutoff = float(np.percentile(annual_rev_per_scenario, 5))
    var_95 = float(rev_p50 - var_95_cutoff)
    worst_5pct_mask = annual_rev_per_scenario <= var_95_cutoff
    cvar_95_level = float(np.mean(annual_rev_per_scenario[worst_5pct_mask]))
    cvar_95 = float(rev_p50 - cvar_95_level)

    # 7. Profile / Shape risk
    profile_cost = float(mean_baseload - cap_mean)
    shape_vol = float(np.std(baseload_per_scenario - capture_price_per_scenario))

    # 8. Negative price exposure
    negative_mask = price_matrix < 0
    negative_hours_per_scenario = np.sum(negative_mask, axis=0) / tenor_years
    avg_neg_hours = float(np.mean(negative_hours_per_scenario))
    pct_neg_hours = float((avg_neg_hours / (num_hours / tenor_years)) * 100.0)

    # Negative cash drain (revenue lost during negative hours where generator pays)
    neg_rev_per_scenario = np.sum(np.where(negative_mask, price_matrix * gen_matrix, 0.0), axis=0) / tenor_years
    avg_neg_drain = float(np.abs(np.mean(neg_rev_per_scenario)))

    return ContractRiskMetrics(
        volume_p10_mwh=vol_p10,
        volume_p50_mwh=vol_p50,
        volume_p90_mwh=vol_p90,
        volume_mean_mwh=vol_mean,
        volume_std_mwh=vol_std,
        capture_price_p10_eur_mwh=cap_p10,
        capture_price_p50_eur_mwh=cap_p50,
        capture_price_p90_eur_mwh=cap_p90,
        capture_price_mean_eur_mwh=cap_mean,
        capture_price_std_eur_mwh=cap_std,
        baseload_price_mean_eur_mwh=mean_baseload,
        capture_factor_p50=cf_p50,
        capture_factor_p90=cf_p90,
        revenue_p10_eur=rev_p10,
        revenue_p50_eur=rev_p50,
        revenue_p90_eur=rev_p90,
        revenue_mean_eur=rev_mean,
        revenue_std_eur=rev_std,
        var_95_eur=var_95,
        cvar_95_eur=cvar_95,
        profile_cost_eur_mwh=profile_cost,
        shape_risk_volatility_eur_mwh=shape_vol,
        expected_negative_hours_annual=avg_neg_hours,
        pct_negative_hours=pct_neg_hours,
        unhedged_negative_cash_drain_eur=avg_neg_drain,
    )
