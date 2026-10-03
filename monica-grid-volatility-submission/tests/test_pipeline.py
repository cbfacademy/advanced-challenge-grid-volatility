"""Unit tests on small synthetic data: no dataset needed. Run with `pytest -q`."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gridvol import metrics, strategy, validate  # noqa: E402
from gridvol.config import Config  # noqa: E402
from gridvol.io import SqlEngine  # noqa: E402

CFG = Config()


def test_short_profits_when_price_falls():
    hr, hh, co = pd.Series([100.0]), pd.Series([95.0]), pd.Series([80.0])
    x = np.array([-25.0])
    # 0.5 * -25 * (80 - 100) = +250
    assert strategy.halfhour_pnl(x, x, hr, hh, co)[0] == pytest.approx(250.0)


def test_two_auction_formula_matches_brief():
    hr, hh, co = pd.Series([100.0]), pd.Series([110.0]), pd.Series([90.0])
    x, y = np.array([10.0]), np.array([-5.0])
    expected = 0.5 * (10 * (110 - 100) + -5 * (90 - 110))
    assert strategy.halfhour_pnl(x, y, hr, hh, co)[0] == pytest.approx(expected)


def test_missing_half_hourly_price_ignored_when_held_to_cashout():
    hr, hh, co = pd.Series([100.0]), pd.Series([np.nan]), pd.Series([80.0])
    x = np.array([-25.0])
    assert strategy.halfhour_pnl(x, x, hr, hh, co)[0] == pytest.approx(250.0)


def _model(n_train=200, n_val=100, seed=0):
    rng = np.random.default_rng(seed)
    dates = ([date(2020, 1, 1)] * n_train) + ([date(2024, 1, 1)] * n_val)
    m = pd.DataFrame({
        "ts_key": np.arange(n_train + n_val) * 1800,
        "date_utc": [d.isoformat() for d in dates],
        "hr_price": rng.uniform(50, 150, n_train + n_val),
        "hh_price": rng.uniform(50, 150, n_train + n_val),
        "cashout_price": rng.uniform(50, 150, n_train + n_val),
        "srmc": 80.0,
        "resid_demand_fc": rng.uniform(15000, 45000, n_train + n_val),
    })
    m["gap_pct"] = 100 * (m["hr_price"] - m["srmc"]) / m["srmc"]
    m["period"] = strategy.period_labels(m["date_utc"], CFG)
    return m


def test_guard_threshold_uses_training_data_only():
    m = _model()
    t1 = strategy.fit_guard_threshold(m, CFG)
    m.loc[m["period"] == "validation", "resid_demand_fc"] = 999_999.0   # changing validation must not move it
    assert strategy.fit_guard_threshold(m, CFG) == pytest.approx(t1)


def test_positions_respect_limit_and_v2_is_subset_of_v1():
    m = _model()
    pos = strategy.positions(m, strategy.fit_guard_threshold(m, CFG), CFG)
    for x in pos.values():
        assert np.all(np.abs(x) <= 25)
    assert np.all((pos["v2"] == 0) | (pos["v2"] == pos["v1"]))
    assert (pos["v2"] != 0).sum() < (pos["v1"] != 0).sum()


def test_always_long_and_short_are_mirror_images():
    m = _model()
    pnl = strategy.compute_pnl(m, strategy.positions(m, 30000.0, CFG))
    assert pnl["pnl_always_long"].sum() == pytest.approx(-pnl["pnl_always_short"].sum())


def test_max_drawdown():
    pnl = pd.DataFrame({"date_utc": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
                        "pnl_x": [100.0, -300.0, 50.0, 400.0], "pos_x": [1, 1, 1, 1]})
    assert metrics.summarise(pnl, "x")["max_drawdown_gbp"] == pytest.approx(-300.0)


def test_cleaning_converts_time_zone_and_removes_duplicates():
    log = validate.IssueLog()
    ts = pd.to_datetime(["2024-07-01 10:00", "2024-07-01 10:30", "2024-07-01 10:30"]).tz_localize("Europe/London")
    raw = pd.DataFrame({"delivery_start_utc": ts, "da_hr_epex_price": [50.0, 50.0, 50.0],
                        "da_hh_epex_price": [49.0, 51.0, 52.0], "cashout_price": [40.0, 45.0, 46.0]})
    out = validate.clean_market(raw, CFG, SqlEngine("sqlite"), log)
    assert len(out) == 2
    assert str(out["delivery_start_utc"].dt.tz) == "UTC"
    assert out["delivery_start_utc"].iloc[0] == pd.Timestamp("2024-07-01 09:00", tz="UTC")  # BST is UTC+1
    assert "duplicates" in set(log.frame()["check"])


def test_sql_gap_detection_and_hard_bounds():
    log = validate.IssueLog()
    ts = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:30", "2024-01-01 02:00"], utc=True)
    raw = pd.DataFrame({"delivery_start_utc": ts, "da_hr_epex_price": [50.0, 50.0, 99999.0],
                        "da_hh_epex_price": [50.0, 50.0, 50.0], "cashout_price": [50.0, 50.0, 50.0]})
    out = validate.clean_market(raw, CFG, SqlEngine("sqlite"), log)
    gaps = log.frame().query("check == 'gaps'")["count"].iloc[0]
    assert gaps == 2                       # 01:00 and 01:30 missing
    assert np.isnan(out["hr_price"].iloc[2])  # 99,999 is outside hard bounds -> null


def test_gfs_column_swap_detected():
    log = validate.IssueLog()
    rng = np.random.default_rng(1)
    wind = rng.uniform(0, 10000, 500)
    t = pd.date_range("2024-01-01", periods=500, freq="30min", tz="UTC")
    gfs = pd.DataFrame({"delivery_start_utc": t, "wind_forecast": rng.uniform(0, 500, 500),
                        "solar_forecast": wind + rng.normal(0, 100, 500), "wind_outturn": wind})
    gen = pd.DataFrame({"delivery_start_utc": t, "wind_forecast": wind + rng.normal(0, 1000, 500), "wind": wind})
    validate.check_gfs(gfs, gen, log)
    assert "swapped" in log.frame().iloc[0]["action"]
