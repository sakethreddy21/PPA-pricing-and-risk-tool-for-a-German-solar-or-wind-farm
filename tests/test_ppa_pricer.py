import pytest
import pandas as pd
import numpy as np

from ppa_pipeline.models.generation import AssetSpecification, TechnologyType
from ppa_pipeline.pricing.ppa_pricer import PayAsProducedPricer, PpaContractStructure
from ppa_pipeline.pricing.risk_metrics import calculate_risk_metrics


def test_calculate_risk_metrics():
    # 100 hours, 50 scenarios
    price_matrix = np.random.normal(60.0, 15.0, (100, 50))
    gen_matrix = np.random.uniform(5.0, 20.0, (100, 50))

    rm = calculate_risk_metrics(price_matrix, gen_matrix, tenor_years=1)

    assert rm.baseload_price_mean_eur_mwh > 0
    assert rm.capture_price_mean_eur_mwh > 0
    assert rm.volume_p90_mwh <= rm.volume_p50_mwh <= rm.volume_p10_mwh
    assert rm.var_95_eur >= 0.0


def test_ppa_pricer_waterfall_consistency():
    hours = 168
    market_df = pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-05-01", periods=hours, freq="h"),
        "price_eur_mwh": [65.0] * hours,
    })
    weather_df = pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-05-01", periods=hours, freq="h"),
        "global_tilted_irradiance_wm2": [500.0] * hours,
        "temperature_2m_c": [20.0] * hours,
    })

    asset = AssetSpecification(technology=TechnologyType.SOLAR_PV, capacity_mw=10.0)
    contract = PpaContractStructure(
        tenor_years=1,
        balancing_cost_eur_mwh=2.0,
        risk_premium_eur_mwh=1.0,
        floor_price_eur_mwh=None,
    )

    pricer = PayAsProducedPricer(market_df, weather_df)
    res = pricer.price_asset(asset, contract)

    # Check waterfall arithmetic
    expected_ppa = res.expected_capture_price - res.balancing_cost - res.risk_premium
    assert np.isclose(res.fair_ppa_fixed_price, max(expected_ppa, 0.0), atol=0.05)


def test_floor_option_increases_ppa_value():
    hours = 168
    # Market with negative prices
    market_df = pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-05-01", periods=hours, freq="h"),
        "price_eur_mwh": [-20.0 if i % 4 == 0 else 50.0 for i in range(hours)],
    })
    weather_df = pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-05-01", periods=hours, freq="h"),
        "global_tilted_irradiance_wm2": [600.0] * hours,
        "temperature_2m_c": [20.0] * hours,
    })

    asset = AssetSpecification(technology=TechnologyType.SOLAR_PV, capacity_mw=10.0)
    contract_no_floor = PpaContractStructure(floor_price_eur_mwh=None)
    contract_with_floor = PpaContractStructure(floor_price_eur_mwh=0.0)

    pricer = PayAsProducedPricer(market_df, weather_df)
    res_no_floor = pricer.price_asset(asset, contract_no_floor)
    res_with_floor = pricer.price_asset(asset, contract_with_floor)

    assert res_with_floor.floor_option_value > 0.0
    assert res_with_floor.fair_ppa_fixed_price >= res_no_floor.fair_ppa_fixed_price
