import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TechnologyType(str, Enum):
    SOLAR_PV = "solar_pv"
    WIND_ONSHORE = "wind_onshore"
    WIND_OFFSHORE = "wind_offshore"


@dataclass
class AssetSpecification:
    """Technical and volumetric specification of a renewable energy asset."""
    name: str = "German Renewable Asset"
    technology: TechnologyType = TechnologyType.SOLAR_PV
    capacity_mw: float = 50.0  # Nameplate capacity (MW)
    location_id: str = "bavaria_solar"
    # Solar specific parameters
    dc_ac_ratio: float = 1.20  # Inverter sizing ratio
    temp_coeff_pmax: float = -0.0038  # -0.38%/deg C cell temp coefficient
    noct_celsius: float = 45.0  # Nominal Operating Cell Temperature
    solar_system_losses: float = 0.06  # 6% soiling, wiring, mismatch
    # Wind specific parameters
    hub_height_m: float = 120.0  # Turbine hub height
    reference_height_m: float = 100.0  # ERA5 reference height
    wind_shear_exponent: float = 0.143  # Power law alpha (0.143 onshore, 0.10 offshore)
    cut_in_speed_ms: float = 3.0
    rated_speed_ms: float = 11.5
    cut_out_speed_ms: float = 25.0
    wind_system_losses: float = 0.08  # 8% wake losses, electrical, availability
    # Contract parameters
    annual_degradation_rate: float = 0.005  # 0.5% per annum degradation


class SolarPvModel:
    """Converts hourly meteorological irradiance and temperature to AC power output."""

    @staticmethod
    def calculate_hourly_generation(
        spec: AssetSpecification,
        gti_wm2: pd.Series,
        temp_c: pd.Series,
        year_index: int = 0,
    ) -> pd.Series:
        """Calculate hourly Solar AC Generation in MWh.
        
        Formula:
        1. Cell Temperature: T_cell = T_amb + GTI * (NOCT - 20) / 800
        2. DC Output: P_dc = Capacity_DC * (GTI / 1000) * [1 + gamma * (T_cell - 25)]
        3. AC Output: min(P_dc, Capacity_AC) * (1 - losses) * (1 - degradation)^year
        """
        # Capacity DC based on DC/AC ratio
        dc_capacity = spec.capacity_mw * spec.dc_ac_ratio
        ac_capacity = spec.capacity_mw

        # Clean non-negative irradiance
        gti_clean = np.maximum(gti_wm2.fillna(0.0).values, 0.0)
        temp_clean = temp_c.fillna(15.0).values

        # 1. Cell temperature estimate
        cell_temp = temp_clean + gti_clean * ((spec.noct_celsius - 20.0) / 800.0)

        # 2. Temperature derating factor
        temp_derate = 1.0 + spec.temp_coeff_pmax * (cell_temp - 25.0)
        temp_derate = np.clip(temp_derate, 0.5, 1.2)

        # 3. DC generation (MW)
        p_dc = dc_capacity * (gti_clean / 1000.0) * temp_derate

        # 4. Inverter clipping (AC capacity limit)
        p_ac = np.minimum(p_dc, ac_capacity)

        # 5. System losses and aging degradation
        degradation_factor = (1.0 - spec.annual_degradation_rate) ** year_index
        p_net = p_ac * (1.0 - spec.solar_system_losses) * degradation_factor

        # 1 hour timestep -> MW * 1h = MWh
        return pd.Series(np.maximum(p_net, 0.0), index=gti_wm2.index)


class WindTurbineModel:
    """Converts hourly wind speed to electrical power output using standard turbine power curves."""

    @staticmethod
    def calculate_hourly_generation(
        spec: AssetSpecification,
        wind_speed_ref_ms: pd.Series,
        year_index: int = 0,
    ) -> pd.Series:
        """Calculate hourly Wind Generation in MWh.
        
        Formula:
        1. Hub Height Extrapolation: v_hub = v_ref * (hub_height / ref_height)^alpha
        2. Power Curve:
           - v < cut_in: P = 0
           - cut_in <= v < rated: P = Rated * (v^3 - cut_in^3) / (rated^3 - cut_in^3)
           - rated <= v < cut_out: P = Rated
           - v >= cut_out: P = 0 (Storm cut-off)
        3. Net Output: P * (1 - wake_losses) * (1 - degradation)^year
        """
        speeds = np.maximum(wind_speed_ref_ms.fillna(0.0).values, 0.0)

        # 1. Wind speed at turbine hub height (Hellmann power law)
        shear = 0.10 if spec.technology == TechnologyType.WIND_OFFSHORE else spec.wind_shear_exponent
        v_hub = speeds * ((spec.hub_height_m / spec.reference_height_m) ** shear)

        # 2. Power curve transformation
        v_in = spec.cut_in_speed_ms
        v_rated = spec.rated_speed_ms
        v_out = spec.cut_out_speed_ms
        rated_cap = spec.capacity_mw

        p_raw = np.zeros_like(v_hub)

        # Partial load regime (Cubic aerodynamic power curve)
        partial_mask = (v_hub >= v_in) & (v_hub < v_rated)
        denom = (v_rated ** 3 - v_in ** 3)
        if denom > 0:
            p_raw[partial_mask] = rated_cap * ((v_hub[partial_mask] ** 3 - v_in ** 3) / denom)

        # Full load rated regime
        rated_mask = (v_hub >= v_rated) & (v_hub < v_out)
        p_raw[rated_mask] = rated_cap

        # Beyond cut-out is 0 (already 0)

        # 3. System & wake losses and degradation
        degradation_factor = (1.0 - spec.annual_degradation_rate) ** year_index
        p_net = p_raw * (1.0 - spec.wind_system_losses) * degradation_factor

        return pd.Series(np.maximum(p_net, 0.0), index=wind_speed_ref_ms.index)


def simulate_asset_generation(
    spec: AssetSpecification,
    weather_df: pd.DataFrame,
    year_index: int = 0,
) -> pd.DataFrame:
    """Transforms a weather timeseries into plant-level generation output (MWh) and capacity factor.
    
    Args:
        spec: Asset technical parameters
        weather_df: DataFrame with weather variables (timestamp_utc, direct_normal_irradiance_wm2 /
                    global_tilted_irradiance_wm2, wind_speed_100m_ms, temperature_2m_c)
        year_index: 0-indexed year of operation for degradation adjustment
        
    Returns:
        DataFrame with timestamp_utc, generation_mwh, capacity_factor, and technology
    """
    df = weather_df.copy()

    if spec.technology == TechnologyType.SOLAR_PV:
        # Determine solar irradiance series (use GTI or estimate from DNI)
        if "global_tilted_irradiance_wm2" in df.columns:
            gti = df["global_tilted_irradiance_wm2"]
        elif "direct_normal_irradiance_wm2" in df.columns:
            gti = df["direct_normal_irradiance_wm2"] * 1.15  # Approx tilted enhancement
        else:
            raise ValueError("No solar irradiance columns found in weather dataframe")

        temp = df["temperature_2m_c"] if "temperature_2m_c" in df.columns else pd.Series(15.0, index=df.index)
        generation_mwh = SolarPvModel.calculate_hourly_generation(spec, gti, temp, year_index=year_index)

    elif spec.technology in (TechnologyType.WIND_ONSHORE, TechnologyType.WIND_OFFSHORE):
        if "wind_speed_100m_ms" in df.columns:
            speed = df["wind_speed_100m_ms"]
        elif "wind_speed_10m_ms" in df.columns:
            speed = df["wind_speed_10m_ms"]
        else:
            raise ValueError("No wind speed columns found in weather dataframe")

        generation_mwh = WindTurbineModel.calculate_hourly_generation(spec, speed, year_index=year_index)
    else:
        raise ValueError(f"Unsupported technology: {spec.technology}")

    result_df = pd.DataFrame({
        "timestamp_utc": df["timestamp_utc"] if "timestamp_utc" in df.columns else df.index,
        "generation_mwh": generation_mwh.values,
        "capacity_factor": (generation_mwh.values / spec.capacity_mw),
        "technology": spec.technology.value,
        "capacity_mw": spec.capacity_mw,
    })

    return result_df
