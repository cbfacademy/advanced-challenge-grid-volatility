"""All tunable settings in one place. Change values here, not in the code."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Config:
    # Periods. Parameters are fitted on TRAIN only; VALIDATION is untouched until scoring.
    train_start: date = date(2016, 1, 1)
    train_end: date = date(2022, 12, 31)
    validation_start: date = date(2023, 1, 1)

    # Trading rules
    position_mw: float = 25.0            # hard limit from the brief: -25MW to +25MW
    entry_gap_pct: float = 10.0          # V1: short when hourly price > SRMC by more than this %
    guard_percentile: float = 0.80       # V2: stand aside when forecast (demand - wind) is above this
                                         #     percentile of V1-signal hours in the TRAIN period
    guard_fail_safe: bool = False        # if a forecast is missing: False = trade as V1, True = stand aside

    # Data validation
    price_hard_min: float = -1000.0      # outside these bounds a price is treated as a data error (set to null)
    price_hard_max: float = 10000.0      # inside them, spikes are kept: they are real market events
    srmc_ffill_days: int = 3             # forward-fill a missing daily SRMC for at most this many days
    demand_bounds_mw: tuple = (5000.0, 70000.0)
    wind_bounds_mw: tuple = (0.0, 40000.0)

    # Kill conditions (review triggers for V2)
    kill_daily_loss_gbp: float = -100_000.0
    kill_drawdown_gbp: float = -150_000.0
    kill_rolling_days: int = 365          # K3: rolling 12-month P&L below zero => review the hypothesis
    kill_guard_miss_gbp: float = -40_000.0  # K4: a day losing more than this => the guard missed; recalibrate


CONFIG = Config()

REQUIRED_FILES = {
    "market": "market_prices.parquet",
    "fuel": "fuel_prices.xlsx",
    "generation": "generation_forecasts.parquet",
    "demand": "demand_forecasts.parquet",
}
OPTIONAL_FILES = {
    "gfs": "gfs_renewables_forecast.parquet",
    "interconnector": "interconnector_forecasts.parquet",
}
