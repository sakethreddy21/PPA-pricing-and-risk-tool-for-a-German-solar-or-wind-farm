import logging
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any
import numpy as np
import pandas as pd
from scipy.stats import norm

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """Parameters controlling the Monte Carlo price and profile simulation."""
    num_scenarios: int = 500  # Number of Monte Carlo paths
    random_seed: Optional[int] = 42
    mean_reversion_speed: float = 0.15  # Theta: speed of reversion per hour
    base_volatility: float = 12.0  # Hourly volatility in EUR/MWh
    jump_intensity: float = 0.02  # Probability of price jump per hour
    jump_mean: float = -25.0  # Negative bias due to renewable flood
    jump_std: float = 35.0  # Spread of jump magnitudes
    cannibalization_sensitivity: float = 18.0  # EUR/MWh price suppression at 100% capacity factor
    expected_mean_price: float = 65.0  # Long-term expected baseline power price (EUR/MWh)


class PriceSimulationEngine:
    """Simulates realistic forward hourly German power prices coupled with renewable generation."""

    def __init__(self, historical_df: pd.DataFrame, config: Optional[SimulationConfig] = None):
        """
        Args:
            historical_df: DataFrame containing at least ['price_eur_mwh', 'timestamp_utc'],
                           and optionally ['solar_mwh', 'total_wind_mwh', 'total_load_mwh'].
            config: Simulation parameters
        """
        self.config = config or SimulationConfig()
        self.historical_df = historical_df.copy()
        self._calibrate_from_history()

    def _calibrate_from_history(self) -> None:
        """Extract diurnal and seasonal shapes and empirical volatility from historical data."""
        df = self.historical_df
        if "timestamp_utc" in df.columns:
            ts = pd.to_datetime(df["timestamp_utc"])
            df["hour"] = ts.dt.hour
            df["month"] = ts.dt.month
        else:
            df["hour"] = np.tile(np.arange(24), int(np.ceil(len(df) / 24)))[:len(df)]
            df["month"] = 5

        # Hourly diurnal baseline price shape
        self.hourly_profile = df.groupby("hour")["price_eur_mwh"].mean().to_dict()
        overall_mean = df["price_eur_mwh"].mean()
        self.diurnal_offsets = {h: self.hourly_profile[h] - overall_mean for h in range(24)}

        # Historical price volatility
        emp_vol = df["price_eur_mwh"].std()
        if not np.isnan(emp_vol) and emp_vol > 0:
            self.volatility = float(np.clip(emp_vol * 0.45, 8.0, 30.0))  # Hourly residual vol
        else:
            self.volatility = self.config.base_volatility

        self.hist_mean_price = float(overall_mean) if not np.isnan(overall_mean) else self.config.expected_mean_price
        logger.info(f"Calibrated price simulator: hist_mean={self.hist_mean_price:.2f} €/MWh, residual_vol={self.volatility:.2f}")

    def simulate_paths(
        self,
        base_generation_df: pd.DataFrame,
        num_scenarios: Optional[int] = None,
        tenor_years: int = 1,
        expected_baseload: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Runs Monte Carlo simulations of coupled hourly prices and plant generation.
        
        Args:
            base_generation_df: DataFrame containing hourly 'generation_mwh' and 'capacity_factor'
            num_scenarios: Number of Monte Carlo iterations (default from config)
            tenor_years: Contract duration in years
            expected_baseload: Expected market average baseload price override (EUR/MWh)
            
        Returns:
            Dictionary containing:
            - 'price_paths': 2D array of shape (num_hours, num_scenarios)
            - 'generation_paths': 2D array of shape (num_hours, num_scenarios)
            - 'timestamps': Index of simulated hours
        """
        n_paths = num_scenarios or self.config.num_scenarios
        rng = np.random.default_rng(self.config.random_seed)

        # Baseline single-year generation profile
        base_gen = base_generation_df["generation_mwh"].values
        base_cf = base_generation_df["capacity_factor"].values
        n_base_hours = len(base_gen)

        # Replicate or tile for contract tenor
        total_hours = n_base_hours * tenor_years
        hours_of_day = np.tile(np.arange(n_base_hours) % 24, tenor_years)

        target_mean = expected_baseload if expected_baseload is not None else self.config.expected_mean_price

        # 1. Deterministic Diurnal Baseline Price Curve: S(t)
        diurnal_shape = np.array([self.diurnal_offsets.get(h, 0.0) for h in hours_of_day])
        base_price_curve = target_mean + diurnal_shape

        # 2. Correlated Monte Carlo Simulation
        theta = self.config.mean_reversion_speed
        sigma = self.volatility
        p_jump = self.config.jump_intensity
        mu_j = self.config.jump_mean
        sigma_j = self.config.jump_std
        sens = self.config.cannibalization_sensitivity

        price_matrix = np.zeros((total_hours, n_paths))
        gen_matrix = np.zeros((total_hours, n_paths))

        # Vectorized generation across scenarios with annual volume weather variability (P50/P90 weather year)
        for s in range(n_paths):
            # Inter-annual weather resource variation (lognormal around 1.0, std ~ 6%)
            annual_resource_factor = rng.lognormal(mean=0.0, sigma=0.065)
            # Hourly micro-fluctuation in generation
            hourly_gen_noise = rng.normal(1.0, 0.05, size=total_hours)
            sim_cf = np.clip(np.tile(base_cf, tenor_years) * annual_resource_factor * hourly_gen_noise, 0.0, 1.0)
            
            # Plant capacity in MW
            cap_mw = float(base_generation_df["capacity_mw"].iloc[0]) if "capacity_mw" in base_generation_df.columns else 50.0
            sim_gen = sim_cf * cap_mw
            gen_matrix[:, s] = sim_gen

            # Simulate Mean-Reverting Ornstein-Uhlenbeck with Jumps
            # dX_t = -theta * X_t * dt + sigma * dW_t + J * dN_t
            x = 0.0
            norm_shocks = rng.normal(0.0, 1.0, size=total_hours)
            jump_occurrences = rng.random(size=total_hours) < p_jump
            jump_sizes = rng.normal(mu_j, sigma_j, size=total_hours)

            path_prices = np.zeros(total_hours)
            for t in range(total_hours):
                # Jump component
                jump = jump_sizes[t] if jump_occurrences[t] else 0.0
                # OU shock
                x += -theta * x + sigma * norm_shocks[t] + jump
                # Couple price negatively with simulated capacity factor (Cannibalization / Merit-Order)
                cannibalization_discount = sens * sim_cf[t]
                
                sim_price = base_price_curve[t] + x - cannibalization_discount
                path_prices[t] = sim_price

            price_matrix[:, s] = path_prices

        logger.info(f"Completed Monte Carlo simulation: {n_paths} paths over {total_hours} hours")
        return {
            "price_matrix": price_matrix,
            "gen_matrix": gen_matrix,
            "total_hours": total_hours,
            "num_scenarios": n_paths,
            "base_timestamps": base_generation_df.get("timestamp_utc", pd.date_range("2024-01-01", periods=n_base_hours, freq="h")),
        }
