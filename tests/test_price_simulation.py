import pytest
import pandas as pd
import numpy as np

from ppa_pipeline.models.price_simulation import PriceSimulationEngine, SimulationConfig


@pytest.fixture
def sample_market_df():
    # 7 days of hourly data (168 hours)
    hours = 168
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-05-01", periods=hours, freq="h"),
        "price_eur_mwh": 65.0 + 15.0 * np.sin(np.linspace(0, 7 * 2 * np.pi, hours)) + np.random.normal(0, 5, hours),
    })


@pytest.fixture
def sample_generation_df():
    hours = 168
    cf = np.clip(0.3 + 0.3 * np.sin(np.linspace(0, 7 * 2 * np.pi, hours)), 0.0, 1.0)
    return pd.DataFrame({
        "generation_mwh": cf * 50.0,
        "capacity_factor": cf,
        "capacity_mw": 50.0,
    })


def test_simulation_engine_dimensions(sample_market_df, sample_generation_df):
    cfg = SimulationConfig(num_scenarios=20, random_seed=42)
    engine = PriceSimulationEngine(sample_market_df, config=cfg)
    
    output = engine.simulate_paths(sample_generation_df, tenor_years=2)
    
    price_matrix = output["price_matrix"]
    gen_matrix = output["gen_matrix"]

    expected_hours = 168 * 2
    assert price_matrix.shape == (expected_hours, 20)
    assert gen_matrix.shape == (expected_hours, 20)
    assert not np.isnan(price_matrix).any()
    assert not np.isnan(gen_matrix).any()


def test_cannibalization_sensitivity():
    hours = 24
    market_df = pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-05-01", periods=hours, freq="h"),
        "price_eur_mwh": [70.0] * hours,
    })
    
    # Compare zero capacity factor vs 100% capacity factor
    low_gen = pd.DataFrame({"generation_mwh": [0.0] * hours, "capacity_factor": [0.0] * hours, "capacity_mw": 50.0})
    high_gen = pd.DataFrame({"generation_mwh": [50.0] * hours, "capacity_factor": [1.0] * hours, "capacity_mw": 50.0})

    cfg = SimulationConfig(num_scenarios=50, random_seed=42, cannibalization_sensitivity=25.0)
    engine = PriceSimulationEngine(market_df, config=cfg)

    low_sim = engine.simulate_paths(low_gen, tenor_years=1)
    high_sim = engine.simulate_paths(high_gen, tenor_years=1)

    # Average simulated price during high generation should be significantly lower
    assert np.mean(high_sim["price_matrix"]) < np.mean(low_sim["price_matrix"])
