"""Positions and P&L.

Profit per half-hour, from the challenge brief, with X = 09:00 position and Y = position after 15:00:
    profit = 0.5 * [ X * (hh_price - hr_price) + Y * (cashout_price - hh_price) ]
All strategies here hold the 09:00 position to cashout (Y = X), which simplifies to
    profit = 0.5 * X * (cashout_price - hr_price)

Strategies:
    always_long   +25MW every half-hour (benchmark)
    always_short  -25MW every half-hour (benchmark)
    v1            -25MW when the hourly price is more than `entry_gap_pct` above daily SRMC, else flat
    v2            v1, but flat when forecast (demand - wind) is above a threshold fitted on TRAIN only
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config


def halfhour_pnl(x: np.ndarray, y: np.ndarray, hr: pd.Series, hh: pd.Series, co: pd.Series) -> np.ndarray:
    """General two-auction formula from the brief. If Y == X the half-hourly price cancels out,
    so a missing half-hourly price does not matter for hold-to-cashout positions."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    hh_filled = hh.where(hh.notna() | (x != y), hr).to_numpy(dtype=float)
    return 0.5 * (x * (hh_filled - hr.to_numpy(dtype=float)) + y * (co.to_numpy(dtype=float) - hh_filled))


def period_labels(dates: pd.Series, cfg: Config) -> pd.Series:
    d = pd.to_datetime(dates).dt.date
    return pd.Series(np.where(d <= cfg.train_end, "train",
                              np.where(d >= cfg.validation_start, "validation", "gap")), index=dates.index)


def v1_signal(model: pd.DataFrame, cfg: Config) -> pd.Series:
    return model["gap_pct"] > cfg.entry_gap_pct


def fit_guard_threshold(model: pd.DataFrame, cfg: Config) -> float:
    """Percentile of forecast residual demand over V1-signal half-hours in the TRAIN period only."""
    train = (model["period"] == "train") & v1_signal(model, cfg)
    values = model.loc[train, "resid_demand_fc"].dropna()
    if values.empty:
        raise ValueError("No training rows with forecasts: cannot fit the V2 guard")
    return float(values.quantile(cfg.guard_percentile))


def guard_active(model: pd.DataFrame, threshold: float, cfg: Config) -> pd.Series:
    tight = model["resid_demand_fc"] > threshold
    missing = model["resid_demand_fc"].isna()
    return tight | missing if cfg.guard_fail_safe else tight.fillna(False)


def positions(model: pd.DataFrame, threshold: float, cfg: Config) -> dict[str, np.ndarray]:
    size = cfg.position_mw
    sig = v1_signal(model, cfg).to_numpy()
    guard = guard_active(model, threshold, cfg).to_numpy()
    n = len(model)
    return {
        "always_long": np.full(n, size),
        "always_short": np.full(n, -size),
        "v1": np.where(sig, -size, 0.0),
        "v2": np.where(sig & ~guard, -size, 0.0),
    }


def compute_pnl(model: pd.DataFrame, pos: dict[str, np.ndarray]) -> pd.DataFrame:
    out = model[["ts_key", "date_utc", "period"]].copy()
    for name, x in pos.items():
        assert np.all(np.abs(x) <= 25.0 + 1e-9), "position limit breached"
        out[f"pos_{name}"] = x
        out[f"pnl_{name}"] = halfhour_pnl(x, x, model["hr_price"], model["hh_price"], model["cashout_price"])
    return out


def pnl_3pm_execution(model: pd.DataFrame, x: np.ndarray) -> pd.Series:
    """Robustness variant that needs no price-contingent order: sit out 09:00, then take the
    same position in the 15:00 half-hourly auction once the hourly price is known (X=0, Y=x)."""
    zero = np.zeros(len(model))
    p = halfhour_pnl(zero, x, model["hr_price"], model["hh_price"], model["cashout_price"])
    return pd.Series(p, index=model.index).where(model["hh_price"].notna() | (x == 0), np.nan)
