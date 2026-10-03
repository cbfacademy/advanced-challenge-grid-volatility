"""Validate and clean every input. Every check appends a row to an issues log, which
becomes outputs/data_quality_report.md, so each cleaning decision is visible and
reproducible rather than done by hand.

Principles:
- Normalise every timestamp to UTC. UTC days always have 48 half-hours; UK local days
  have 46 or 50 on clock-change days, which would silently break daily joins.
- Never impute prices. A missing price means that half-hour is not traded or scored.
- Keep genuine price spikes (they are the risk we are managing). Only values outside
  hard physical bounds are treated as errors and set to null.
- Treat structural nulls (a link or data feed that did not exist yet) as "not available",
  not as missing data to be filled.
- Outturn (actual) columns are never used as trading inputs: they are only known after delivery.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Config
from .io import SqlEngine

HALF_HOUR_S = 1800


@dataclass
class IssueLog:
    rows: list = field(default_factory=list)

    def add(self, dataset: str, check: str, finding: str, action: str, count: int | float | None = None):
        self.rows.append({"dataset": dataset, "check": check, "finding": finding,
                          "action": action, "count": count})

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["dataset", "check", "finding", "action", "count"])


# ---------------------------------------------------------------- helpers
def to_utc(s: pd.Series, name: str, dataset: str, log: IssueLog) -> pd.Series:
    s = pd.to_datetime(s)
    if s.dt.tz is None:
        log.add(dataset, "time zone", f"`{name}` has no time zone", "assumed UTC (per data dictionary)")
        return s.dt.tz_localize("UTC")
    tz = str(s.dt.tz)
    if tz not in ("UTC", "utc", "+00:00"):
        log.add(dataset, "time zone", f"`{name}` is in {tz}", "converted to UTC")
    return s.dt.tz_convert("UTC")


def add_keys(df: pd.DataFrame, ts_col: str) -> pd.DataFrame:
    df = df.copy()
    df["ts_key"] = ((df[ts_col] - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).astype("int64")
    df["date_utc"] = df[ts_col].dt.strftime("%Y-%m-%d")
    return df


def dedupe(df: pd.DataFrame, key: str, value_cols: list[str], dataset: str, log: IssueLog) -> pd.DataFrame:
    dup_mask = df.duplicated(key, keep=False)
    n_dup = int(df.duplicated(key).sum())
    if n_dup:
        conflicting = int(df[dup_mask].groupby(key)[value_cols].nunique(dropna=False).gt(1).any(axis=1).sum())
        log.add(dataset, "duplicates", f"{n_dup} duplicate rows on `{key}` ({conflicting} keys with conflicting values)",
                "kept the last row per key", n_dup)
        df = df.drop_duplicates(key, keep="last")
    else:
        log.add(dataset, "duplicates", f"no duplicate rows on `{key}`", "none", 0)
    return df.sort_values(key).reset_index(drop=True)


def null_bounds(df: pd.DataFrame, col: str, lo: float, hi: float, dataset: str, log: IssueLog, unit: str):
    bad = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
    n = int(bad.sum())
    log.add(dataset, "outliers (hard bounds)",
            f"{n} values of `{col}` outside [{lo:,.0f}, {hi:,.0f}] {unit}",
            "set to null (treated as data errors)" if n else "none", n)
    df.loc[bad, col] = np.nan
    return df


def grid_gaps(engine: SqlEngine, table: str) -> int:
    """Count missing half-hour slots using a SQL window function."""
    q = f"""
        SELECT COALESCE(SUM((step / {HALF_HOUR_S}) - 1), 0) AS missing_slots
        FROM (SELECT ts_key - LAG(ts_key) OVER (ORDER BY ts_key) AS step FROM {table}) s
        WHERE step > {HALF_HOUR_S}
    """
    return int(engine.query(q)["missing_slots"].iloc[0])


def null_profile(df: pd.DataFrame, dataset: str, cols: list[str], ts_col: str) -> pd.DataFrame:
    rows = []
    for c in cols:
        nn = df[c].notna()
        rows.append({
            "dataset": dataset, "column": c, "null_pct": round(100 * (1 - nn.mean()), 1),
            "first_value_utc": df.loc[nn, ts_col].min() if nn.any() else None,
            "last_value_utc": df.loc[nn, ts_col].max() if nn.any() else None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- per-dataset cleaning
def clean_market(raw: pd.DataFrame, cfg: Config, engine: SqlEngine, log: IssueLog) -> pd.DataFrame:
    ds = "market_prices"
    df = raw.rename(columns={"da_hr_epex_price": "hr_price", "da_hh_epex_price": "hh_price"}).copy()
    df["delivery_start_utc"] = to_utc(df["delivery_start_utc"], "delivery_start_utc", ds, log)
    df = add_keys(df, "delivery_start_utc")
    df = dedupe(df, "ts_key", ["hr_price", "hh_price", "cashout_price"], ds, log)

    engine.register("v_market_keys", df[["ts_key"]])
    gaps = grid_gaps(engine, "v_market_keys")
    off_grid = int((df["ts_key"] % HALF_HOUR_S != 0).sum())
    log.add(ds, "gaps", f"{gaps} missing half-hour slots; {off_grid} timestamps off the :00/:30 grid",
            "missing slots are not traded or scored (no imputation)", gaps)

    for c in ["hr_price", "hh_price", "cashout_price"]:
        df = null_bounds(df, c, cfg.price_hard_min, cfg.price_hard_max, ds, log, "£/MWh")
        spikes = df[c].abs() > 1000
        if spikes.any():
            i = df.loc[spikes, c].idxmax()
            log.add(ds, "outliers (spikes)",
                    f"{int(spikes.sum())} values of `{c}` beyond ±£1,000/MWh; max £{df.at[i, c]:,.0f} "
                    f"on {df.at[i, 'date_utc']}", "kept: genuine market events, and the risk being managed",
                    int(spikes.sum()))

    # The hourly auction trades whole hours, so both half-hours of an hour must share one price.
    hour_key = df["ts_key"] // 3600
    mismatched = int(df.groupby(hour_key)["hr_price"].nunique().gt(1).sum())
    log.add(ds, "consistency", f"{mismatched} clock hours where the two half-hours carry different hourly prices",
            "none needed" if mismatched == 0 else "flagged; those hours use each half-hour's own value", mismatched)

    # Unsettled periods: cashout is published after delivery, so the tail is legitimately empty.
    settled = df["cashout_price"].notna()
    last_settled = df.loc[settled, "delivery_start_utc"].max()
    tail = int((~settled & (df["delivery_start_utc"] > last_settled)).sum())
    inner = int((~settled & (df["delivery_start_utc"] <= last_settled)).sum())
    log.add(ds, "gaps", f"{tail} trailing half-hours without cashout (after {last_settled:%Y-%m-%d %H:%M} UTC, not yet settled)",
            "usable for signals, excluded from P&L", tail)
    log.add(ds, "gaps", f"{inner} historical half-hours missing cashout; "
            f"{int(df['hr_price'].isna().sum())} missing hourly price; {int(df['hh_price'].isna().sum())} missing half-hourly price",
            "those half-hours are not traded or scored", inner)

    # Why UTC: show the clock-change days that a local-time grouping would create.
    local_counts = df["delivery_start_utc"].dt.tz_convert("Europe/London").dt.date.value_counts()
    n_odd = int(local_counts.isin([46, 50]).sum())
    log.add(ds, "time zone", f"{n_odd} UK local days have 46 or 50 half-hours (clock changes)",
            "all joins and daily aggregation done on UTC days (always 48 half-hours)", n_odd)
    return df


def clean_fuel(raw: pd.DataFrame, cfg: Config, log: IssueLog) -> pd.DataFrame:
    ds = "fuel_prices"
    log.add(ds, "layout", "title row above the header row", "header located by name ('UK Power Day')")
    df = raw[["UK Power Day", "UK CCGT SRMC (£/MWh)"]].rename(
        columns={"UK Power Day": "power_day", "UK CCGT SRMC (£/MWh)": "srmc"}).copy()
    df["power_day"] = pd.to_datetime(df["power_day"], errors="coerce")
    bad_dates = int(df["power_day"].isna().sum())
    df = df.dropna(subset=["power_day"])
    df["srmc"] = pd.to_numeric(df["srmc"], errors="coerce")
    log.add(ds, "parsing", f"{bad_dates} rows with an unparseable date", "dropped", bad_dates)
    df["power_day"] = df["power_day"].dt.strftime("%Y-%m-%d")
    n_dup = int(df.duplicated("power_day").sum())
    df = df.drop_duplicates("power_day", keep="last")
    log.add(ds, "duplicates", f"{n_dup} duplicate days", "kept the last row" if n_dup else "none", n_dup)

    nonpos = int((df["srmc"] <= 0).sum())
    df.loc[df["srmc"] <= 0, "srmc"] = np.nan
    log.add(ds, "outliers (hard bounds)", f"{nonpos} non-positive SRMC values", "set to null" if nonpos else "none", nonpos)

    full = pd.DataFrame({"power_day": pd.date_range(df["power_day"].min(), df["power_day"].max(), freq="D").strftime("%Y-%m-%d")})
    df = full.merge(df, on="power_day", how="left").sort_values("power_day")
    missing = int(df["srmc"].isna().sum())
    df["srmc"] = df["srmc"].ffill(limit=cfg.srmc_ffill_days)
    still = int(df["srmc"].isna().sum())
    log.add(ds, "gaps", f"{missing} days without SRMC", f"forward-filled up to {cfg.srmc_ffill_days} days "
            f"(fuel prices move slowly); {still} remain null and those days are not traded", missing)
    log.add(ds, "time zone", "`UK Power Day` is a daily label with no time",
            "joined to the UTC calendar date of each half-hour (assumption, see README)")
    return df.reset_index(drop=True)


def clean_forecast(raw: pd.DataFrame, cols: dict[str, str], bounds: dict[str, tuple], dataset: str,
                   log: IssueLog) -> pd.DataFrame:
    df = raw[["delivery_start_utc", *cols]].rename(columns=cols).copy()
    df["delivery_start_utc"] = to_utc(df["delivery_start_utc"], "delivery_start_utc", dataset, log)
    df = add_keys(df, "delivery_start_utc")
    df = dedupe(df, "ts_key", list(cols.values()), dataset, log)
    for c, (lo, hi) in bounds.items():
        df = null_bounds(df, c, lo, hi, dataset, log, "MW")
        log.add(dataset, "gaps", f"{int(df[c].isna().sum())} half-hours with no `{c}`",
                "guard cannot be evaluated there: see `guard_fail_safe` in config", int(df[c].isna().sum()))
    outturn = [c for c in raw.columns if c in ("wind", "demand", "solar", "ccgt", "nuclear") or c.endswith("_outturn")
               or c.startswith("demand_indo") or c.startswith("demand_itsdo")]
    if outturn:
        log.add(dataset, "lookahead", f"outturn (actual) columns present: {', '.join(sorted(outturn))}",
                "never used as trading inputs (only known after delivery)")
    return df[["ts_key", *cols.values()]]


def check_gfs(raw: pd.DataFrame, gen_raw: pd.DataFrame, log: IssueLog) -> None:
    """GFS is not used for trading. These checks document why."""
    ds = "gfs_renewables_forecast"
    if "wind_outturn" not in raw.columns:
        return
    corr_wind_col = raw["wind_forecast"].corr(raw["wind_outturn"])
    corr_solar_col = raw["solar_forecast"].corr(raw["wind_outturn"])
    swapped = corr_solar_col > corr_wind_col
    log.add(ds, "column labels",
            f"correlation with wind outturn: `wind_forecast` {corr_wind_col:.2f}, `solar_forecast` {corr_solar_col:.2f}",
            "columns are swapped: `solar_forecast` holds wind and vice versa" if swapped else "labels look correct")
    gfs_wind = raw["solar_forecast"] if swapped else raw["wind_forecast"]
    m = pd.DataFrame({"t": raw["delivery_start_utc"], "gfs": gfs_wind}).merge(
        gen_raw[["delivery_start_utc", "wind_forecast", "wind"]], left_on="t", right_on="delivery_start_utc").dropna()
    if len(m):
        mae_gfs = (m["gfs"] - m["wind"]).abs().mean()
        mae_gen = (m["wind_forecast"] - m["wind"]).abs().mean()
        log.add(ds, "lookahead",
                f"GFS wind error vs actual {mae_gfs:,.0f} MW, against {mae_gen:,.0f} MW for the generation_forecasts wind forecast",
                "excluded from the strategy: far more accurate than a day-ahead forecast should be, "
                "so it is likely reconstructed after the event" if mae_gfs < 0.5 * mae_gen else "no concern")


def check_interconnectors(raw: pd.DataFrame, log: IssueLog) -> None:
    ds = "interconnector_forecasts"
    cols = [c for c in raw.columns if c.endswith("_forecast")]
    empty = [c for c in cols if raw[c].isna().all()]
    cover = {c: round(100 * raw[c].notna().mean()) for c in cols if c not in empty}
    log.add(ds, "gaps", f"entirely empty: {', '.join(empty) or 'none'}; coverage %: {cover}",
            "not used: incomplete links, values cluster at link capacity, and adding them did not improve the guard")
