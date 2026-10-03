"""Run the full pipeline: validate and clean -> build model table (SQL) -> strategies -> metrics -> reports.

Usage (from the repo root):
    python run.py                      # looks for the dataset under ./data
    python run.py --data-dir path/to/data --out-dir outputs --engine sqlite
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gridvol import metrics, report, strategy, validate  # noqa: E402
from gridvol.config import CONFIG  # noqa: E402
from gridvol.io import SqlEngine, find_files, read_fuel_prices, read_parquet  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
    ap.add_argument("--engine", choices=["duckdb", "sqlite"], default="duckdb")
    args = ap.parse_args(argv)
    cfg = CONFIG
    t0 = time.time()
    out = args.out_dir
    (out / "figures").mkdir(parents=True, exist_ok=True)

    def step(msg):
        print(f"[{time.time() - t0:5.1f}s] {msg}", flush=True)

    # 1. Locate and load ------------------------------------------------------------
    files = find_files(args.data_dir)
    step("Found: " + ", ".join(f"{k}={v.relative_to(args.data_dir)}" for k, v in files.items()))
    engine = SqlEngine(prefer=args.engine)
    step(f"SQL engine: {engine.kind}")
    raw = {k: (read_fuel_prices(p) if k == "fuel" else read_parquet(p)) for k, p in files.items()}

    # 2. Validate and clean -----------------------------------------------------------
    log = validate.IssueLog()
    market = validate.clean_market(raw["market"], cfg, engine, log)
    fuel = validate.clean_fuel(raw["fuel"], cfg, log)
    wind = validate.clean_forecast(raw["generation"], {"wind_forecast": "wind_fc"},
                                   {"wind_fc": cfg.wind_bounds_mw}, "generation_forecasts", log)
    demand = validate.clean_forecast(raw["demand"], {"demand_forecast_ndf": "demand_fc"},
                                     {"demand_fc": cfg.demand_bounds_mw}, "demand_forecasts", log)
    if "gfs" in raw:
        validate.check_gfs(raw["gfs"], raw["generation"], log)
    if "interconnector" in raw:
        validate.check_interconnectors(raw["interconnector"], log)
    nulls = pd.concat([
        validate.null_profile(market, "market_prices", ["hr_price", "hh_price", "cashout_price"], "delivery_start_utc"),
        validate.null_profile(raw["generation"], "generation_forecasts", ["wind_forecast"], "delivery_start_utc"),
        validate.null_profile(raw["demand"], "demand_forecasts", ["demand_forecast_ndf"], "delivery_start_utc"),
    ] + ([validate.null_profile(raw["interconnector"], "interconnector_forecasts",
                                [c for c in raw["interconnector"].columns if c.endswith("_forecast")], "delivery_start_utc")]
         if "interconnector" in raw else []), ignore_index=True)
    report.write_dq_report(log.frame(), nulls, out / "data_quality_report.md", engine.kind)
    log.frame().to_csv(out / "data_quality_log.csv", index=False)
    step(f"Validation done: {len(log.rows)} checks -> outputs/data_quality_report.md")

    # 3. Build the model table in SQL --------------------------------------------------
    engine.register("market", market[["ts_key", "date_utc", "hr_price", "hh_price", "cashout_price"]])
    engine.register("fuel", fuel)
    engine.register("wind", wind)
    engine.register("demand", demand)
    model = engine.run_file(ROOT / "sql" / "01_model_table.sql")
    model["period"] = strategy.period_labels(model["date_utc"], cfg)
    step(f"Model table: {len(model):,} settled half-hours, {model['date_utc'].min()} to {model['date_utc'].max()}")

    # 4. Strategies (guard fitted on TRAIN only) -------------------------------------
    threshold = strategy.fit_guard_threshold(model, cfg)
    pos = strategy.positions(model, threshold, cfg)
    pnl = strategy.compute_pnl(model, pos)
    signal = strategy.v1_signal(model, cfg)
    guard = strategy.guard_active(model, threshold, cfg) & signal
    guard_share = {p: 100 * guard[model["period"] == p].sum() / max(signal[model["period"] == p].sum(), 1)
                   for p in ["train", "validation"]}
    step(f"V2 guard threshold (fitted on train): {threshold:,.0f} MW")

    # 5. Metrics -------------------------------------------------------------------------
    tables = {"validation": metrics.summary_table(pnl, "validation"),
              "train": metrics.summary_table(pnl, "train"),
              "full": metrics.summary_table(pnl, None)}
    pd.concat(tables.values()).to_csv(out / "metrics_summary.csv", index=False)

    val = pnl["period"] == "validation"
    v1_daily = metrics.daily(pnl[val], "pnl_v1")
    worst_day = v1_daily.idxmin().strftime("%Y-%m-%d")
    no_worst = pnl[val & (pnl["date_utc"] != worst_day)]
    pnl_3pm = pnl[val].copy()
    rob = []
    for s in ["always_short", "v1", "v2"]:
        pnl_3pm[f"pnl3_{s}"] = strategy.pnl_3pm_execution(model[val], pos[s][val.to_numpy()]).to_numpy()
        r3 = metrics.summarise(pnl_3pm.dropna(subset=[f"pnl3_{s}"]), s, pnl_col=f"pnl3_{s}", pos_col=f"pos_{s}")
        rx = metrics.summarise(no_worst, s)
        rob.append({"strategy": metrics.LABELS[s],
                    "as_tested_total_gbp": tables["validation"].set_index("strategy").at[metrics.LABELS[s], "total_pnl_gbp"],
                    f"excl_{worst_day}_total_gbp": rx["total_pnl_gbp"],
                    "executed_at_3pm_total_gbp": r3["total_pnl_gbp"],
                    "executed_at_3pm_sharpe": r3["sharpe_annualised"],
                    "executed_at_3pm_max_drawdown_gbp": r3["max_drawdown_gbp"]})
    robustness = pd.DataFrame(rob)
    robustness.to_csv(out / "robustness_validation.csv", index=False)

    kill_parts = []
    for per in ["train", "validation"]:
        mon = metrics.kill_monitor(pnl, cfg, period=per)
        mon.to_csv(out / f"kill_condition_monitor_v2_{per}.csv")
        kill_parts.append(metrics.kill_summary(mon, cfg, per))
    kill = pd.concat(kill_parts, ignore_index=True)

    engine.register("pnl", pnl[["date_utc"] + [f"pnl_{s}" for s in metrics.STRATEGIES]])
    monthly = engine.run_file(ROOT / "sql" / "02_monthly_pnl.sql")
    monthly.to_csv(out / "monthly_pnl.csv", index=False)
    step("Metrics, robustness checks and kill-condition monitor done")

    # 6. Charts and reports ------------------------------------------------------------------
    # Days when the V2 guard stood aside from at least one V1 trade, and what that was worth.
    gd = pd.DataFrame({"date_utc": pd.to_datetime(pnl["date_utc"]), "period": pnl["period"],
                       "blocked": guard.to_numpy(), "diff": (pnl["pnl_v2"] - pnl["pnl_v1"]).to_numpy()})
    guard_days = gd.groupby("date_utc").agg(period=("period", "first"), blocked_halfhours=("blocked", "sum"),
                                            v2_minus_v1_gbp=("diff", "sum"))
    guard_days[guard_days["blocked_halfhours"] > 0].to_csv(out / "v2_guard_days.csv")
    report.cumulative_chart(pnl, out / "figures" / "cumulative_pnl_train.png", "train",
                            "Cumulative profit by strategy, training period (2016–2022)", guard_days=guard_days)
    report.cumulative_chart(pnl, out / "figures" / "cumulative_pnl_validation.png", "validation",
                            "Cumulative profit by strategy, validation period (2023 onwards)", guard_days=guard_days)
    report.write_interactive(pnl, guard_days, tables, threshold, out / "interactive_charts.html")
    buckets = report.gap_bucket_chart(model, out / "figures" / "move_by_srmc_gap.png")
    report.write_results(out / "results.md", tables=tables, robustness=robustness, kill=kill,
                         threshold=threshold, guard_share=guard_share, buckets=buckets, cfg=cfg)
    step("Reports written to outputs/")

    v = tables["validation"].set_index("strategy")
    print("\nValidation period (2023 onwards):")
    for s in ["Always short (-25MW)", "V1: short above +10%", "V2: V1 + tight-system guard"]:
        print(f"  {s:30} total £{v.at[s, 'total_pnl_gbp']:>11,.0f}   Sharpe {v.at[s, 'sharpe_annualised']:5.2f}"
              f"   max drawdown £{v.at[s, 'max_drawdown_gbp']:>10,.0f}")
    print(f"\nDone in {time.time() - t0:.1f}s. Open outputs/results.md and outputs/data_quality_report.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
