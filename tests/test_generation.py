import pytest
import pandas as pd
import numpy as np

from ppa_pipeline.models.generation import (
    AssetSpecification,
    TechnologyType,
    SolarPvModel,
    WindTurbineModel,
    simulate_asset_generation,
)


def test_solar_generation_physics():
    spec = AssetSpecification(
        technology=TechnologyType.SOLAR_PV,
        capacity_mw=10.0,
        dc_ac_ratio=1.2,
        solar_system_losses=0.05,
    )

    # 1. Zero irradiance -> zero output
    zero_gti = pd.Series([0.0, 0.0])
    ambient_temp = pd.Series([20.0, 25.0])
    gen_zero = SolarPvModel.calculate_hourly_generation(spec, zero_gti, ambient_temp)
    assert np.all(gen_zero == 0.0)

    # 2. Peak irradiance (1000 W/m2) at 25C cell temp (approx 15C ambient)
    gti_peak = pd.Series([1000.0])
    temp_amb = pd.Series([15.0])
    gen_peak = SolarPvModel.calculate_hourly_generation(spec, gti_peak, temp_amb)
    
    # Inverter clips at AC capacity (10 MW), minus 5% losses = ~9.5 MWh
    assert 9.0 <= gen_peak.iloc[0] <= 10.0

    # 3. Inverter clipping: massive irradiance should not exceed AC capacity * (1 - losses)
    gti_extreme = pd.Series([1500.0])
    gen_extreme = SolarPvModel.calculate_hourly_generation(spec, gti_extreme, temp_amb)
    assert gen_extreme.iloc[0] <= 10.0 * 0.95 + 1e-3


def test_wind_power_curve_physics():
    spec = AssetSpecification(
        technology=TechnologyType.WIND_ONSHORE,
        capacity_mw=20.0,
        cut_in_speed_ms=3.0,
        rated_speed_ms=11.5,
        cut_out_speed_ms=25.0,
        wind_system_losses=0.08,
        hub_height_m=100.0,
        reference_height_m=100.0,
    )

    # 1. Below cut-in (e.g. 2.0 m/s) -> 0 MW
    sub_cut_in = pd.Series([1.5, 2.5])
    gen_sub = WindTurbineModel.calculate_hourly_generation(spec, sub_cut_in)
    assert np.all(gen_sub == 0.0)

    # 2. At rated speed (12.0 m/s) -> rated capacity minus losses
    rated_speed = pd.Series([12.0])
    gen_rated = WindTurbineModel.calculate_hourly_generation(spec, rated_speed)
    expected_net = 20.0 * (1 - 0.08)
    assert np.isclose(gen_rated.iloc[0], expected_net, atol=0.1)

    # 3. Beyond cut-out speed (e.g. 28.0 m/s) -> 0 MW (storm protection)
    storm_speed = pd.Series([28.0, 32.0])
    gen_storm = WindTurbineModel.calculate_hourly_generation(spec, storm_speed)
    assert np.all(gen_storm == 0.0)


def test_simulate_asset_generation_dataframe():
    weather_df = pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-05-01", periods=24, freq="h"),
        "global_tilted_irradiance_wm2": [0] * 6 + [300, 600, 800, 900, 850, 700, 400, 100] + [0] * 10,
        "temperature_2m_c": [15.0] * 24,
        "wind_speed_100m_ms": [6.5] * 24,
    })

    spec = AssetSpecification(technology=TechnologyType.SOLAR_PV, capacity_mw=50.0)
    out_df = simulate_asset_generation(spec, weather_df)

    assert len(out_df) == 24
    assert "generation_mwh" in out_df.columns
    assert "capacity_factor" in out_df.columns
    assert np.all(out_df["capacity_factor"] >= 0.0)
    assert np.all(out_df["capacity_factor"] <= 1.0)
