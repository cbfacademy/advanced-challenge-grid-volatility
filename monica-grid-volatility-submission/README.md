# Grid Volatility: sell overpriced power, except when the grid is tight

*Submission v2. Changes from v1: separate cumulative charts for the training and validation periods, showing every strategy including do nothing, each line labelled with its final total, and each day the V2 guard stood aside marked; the pipeline also writes an interactive chart page, referenced from the decision memo.*

Our recommendation is in **[DECISION_MEMO.md](DECISION_MEMO.md)**. This repo contains the pipeline that produces every number in it.

**In one sentence:** we short GB day-ahead power when the hourly auction clears more than 10% above the cost of running a gas plant (UK CCGT SRMC). That is strategy **V1**. **V2** adds a guard that stands aside when forecast demand minus forecast wind says the grid will be tight. V2 is the recommendation.

## Quick start

Requires **Python 3.12** (pinned by `.python-version`) and the dataset in `data/` as supplied in the template repo.

```bash
# macOS / Linux
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python run.py          # runs the full pipeline (well under a minute)
pytest -q              # 10 unit tests on synthetic data (no dataset needed)
```

On Windows (PowerShell), replace the first two lines with `py -3.12 -m venv venv` and `.\venv\Scripts\Activate.ps1`.

**Viewing the interactive charts.** On your own machine, double-click `outputs/interactive_charts.html`. In GitHub Codespaces, run `python -m http.server 8000 --directory outputs`, open the forwarded port 8000 in your browser, and click `interactive_charts.html`.

**What you should see.** `run.py` prints each step with timings, then ends with:

```
Validation period (2023 onwards):
  Always short (-25MW)           total £    145,009   Sharpe  0.15   max drawdown £  -369,163
  V1: short above +10%           total £    185,559   Sharpe  0.25   max drawdown £  -332,432
  V2: V1 + tight-system guard    total £    278,083   Sharpe  1.18   max drawdown £   -78,486
```

Options: `--data-dir PATH` if the dataset lives elsewhere (it is found by file name anywhere under that folder), `--out-dir PATH`, and `--engine sqlite` to run the SQL on SQLite instead of DuckDB.

## What the pipeline produces (`outputs/`)

| File | What it is |
|---|---|
| `interactive_charts.html` | Interactive version of the cumulative charts: switch between training and validation, toggle strategies, show or hide V2 guard days, hover for daily values, drag to zoom. Open it in a browser from your clone (GitHub shows HTML as source); it loads Chart.js from a CDN, so it needs an internet connection |
| `results.md` | All headline tables: benchmarks, V1 and V2 for validation, training and full periods; robustness checks; kill-condition monitor |
| `data_quality_report.md` | Every validation check, what was found and what was done about it |
| `figures/cumulative_pnl_train.png` | Cumulative profit for 2016–2022 for every strategy (do nothing, always long, always short, V1, V2), each labelled with its final total. Dashed grey verticals mark each day the V2 guard stood aside; the two days where that mattered most are highlighted in orange with their value |
| `figures/cumulative_pnl_validation.png` | The same chart for the validation period, 2023 onwards |
| `v2_guard_days.csv` | Every day the guard stood aside: half-hours blocked and V2 minus V1 profit that day |
| `figures/move_by_srmc_gap.png` | Evidence for the hypothesis: how far prices move to cashout, by SRMC gap |
| `metrics_summary.csv`, `monthly_pnl.csv`, `robustness_validation.csv` | Machine-readable versions of the tables |
| `kill_condition_monitor_v2_{train,validation}.csv` | Day-by-day P&L, drawdown and kill-condition flags |
| `data_quality_log.csv` | The data quality checks as a table |

## How it works

```
data/*.parquet, fuel_prices.xlsx
   │  1. load         src/gridvol/io.py        (files found by name; header row of the xlsx located automatically)
   │  2. validate     src/gridvol/validate.py  (UTC, duplicates, gaps, outliers, structural nulls, lookahead)
   │  3. model table  sql/01_model_table.sql   (SQL join of prices, daily SRMC and forecasts: DuckDB or SQLite)
   │  4. strategies   src/gridvol/strategy.py  (benchmarks, V1, V2; guard fitted on 2016–2022 only)
   │  5. metrics      src/gridvol/metrics.py   (P&L, Sharpe, drawdown, worst day/week, hit rate, kill conditions)
   ▼  6. report       src/gridvol/report.py    (charts, interactive HTML page, Markdown, CSV)
outputs/
```

All settings (dates, thresholds, position size, kill limits) live in `src/gridvol/config.py`.

## Data handling

The full log is regenerated on every run in `outputs/data_quality_report.md`. The decisions:

- **Time zones.** Every timestamp is normalised to UTC. A missing time zone is assumed UTC, as the data dictionary states; any other time zone is converted. We aggregate by UTC day because UK local days have 46 or 50 half-hours on clock-change days (21 such days in the data), which would break daily joins. The daily `UK Power Day` SRMC is joined to the UTC calendar date of each half-hour. That is an assumption: if the fuel day follows a gas-day convention (06:00–06:00), a few hours a day pick up the neighbouring day's SRMC.
- **Gaps.** Prices are never imputed.
  - A half-hour with no hourly price or no cashout is neither traded nor scored.
  - The trailing periods without cashout are not yet settled, so they are excluded from P&L.
  - Missing daily SRMC is forward-filled for up to 3 days, because fuel prices move slowly.
  - Missing forecasts mean the guard can't be evaluated. Those half-hours trade as V1 by default; set `guard_fail_safe=True` to stand aside instead.
- **Outliers.** Price spikes are kept, because they are real market events and the risk the strategy is managing. The largest cashout is £4,038/MWh. Only values outside hard bounds are treated as data errors and nulled: prices outside −£1,000 to £10,000/MWh, negative wind, implausible demand.
- **Duplicates.** Duplicated timestamps are removed (keeping the last row) and reported, including whether the duplicate rows disagree. The SQL gap check also counts missing half-hour slots.
- **Structural nulls.** Some columns start part-way through the history because the feed didn't exist yet. For example, the German interconnector forecast is entirely empty and the Irish one starts at the end of 2020. These are reported with their first and last dates, never back-filled.
- **Lookahead.** Outturn (actual) columns in the forecast files are never used as inputs.
- **GFS file.** Two problems, so we don't use it for trading:
  - Its `wind_forecast` and `solar_forecast` columns are swapped (the pipeline detects this by correlation).
  - Even corrected, its wind series has a 297MW error against actual wind, compared with 1,012MW for the generation forecast. A day-ahead forecast shouldn't be that accurate, so the series was likely reconstructed after the event.
- **Interconnector forecasts.** Incomplete, clustered at link capacity, and adding them did not improve the guard, so they are reported but not used.

## Method

- **The decision.** For every delivery hour, decide at the 09:00 hourly auction whether to be short 25MW or flat, holding the position to cashout. The P&L per half-hour is the brief's formula with the 15:00 position equal to the 09:00 one: `0.5 × X × (cashout − hourly price)`.
- **V1.** Short when the hourly price is more than 10% above that day's SRMC.
- **V2.** V1, but flat when forecast `demand_forecast_ndf − wind_forecast` exceeds 34,039MW. That threshold is the 80th percentile over V1-signal half-hours in 2016–2022. It was chosen from the 70th, 80th and 90th percentiles by the best 2016–2022 Sharpe ratio.
- **Train and validation.** Parameters are fitted on 2016–2022. Everything from 2023 onwards is validation. Benchmarks (do nothing, always long, always short) are scored on the same periods.
- **Robustness** (in `results.md`):
  - results without the single worst validation day (8 Jan 2025);
  - results if the trade is placed at 15:00 instead of 09:00;
  - performance net of always short, because cashout has settled below the hourly auction on average in most years, which flatters any short position.

## Assumptions and limitations

- **Price-contingent order at 09:00.** The signal uses the hourly clearing price, so the 09:00 trade must be a price-contingent sell order at 1.1 × SRMC. If only fixed volumes can be submitted, the 15:00 execution variant applies, and it is weaker: see `results.md`.
- **Selection bias.** The +10% entry level was chosen after seeing 2023+ results. The V2 guard threshold was fitted on 2016–2022 only.
- **Forecast timing.** The third-party forecasts are assumed to have been available before 09:00 on the day before delivery, as the brief states. The files carry only a download date, not a publication time.
- **No costs.** P&L is frictionless: no fees, slippage, collateral or liquidity limits.
- **Thin validation.** The validation period is about 3.75 years and contains one dominant event (8 Jan 2025), so read V2's advantage as tail protection, not higher average returns.

## Repository layout

```
run.py                     entry point
src/gridvol/               pipeline modules (config, io, validate, strategy, metrics, report)
sql/                       SQL run on DuckDB (or SQLite): model table and monthly P&L
tests/test_pipeline.py     unit tests on synthetic data
outputs/                   generated by run.py
DECISION_MEMO.md           one-page recommendation
```

## Troubleshooting

- **`FileNotFoundError: Could not find [...]`.** Run from the repo root, or pass `--data-dir` pointing at the folder that contains the dataset.
- **DuckDB fails to install.** Run with `--engine sqlite`. The SQL is portable, and SQLite ships with Python.

AI tools (Claude, GitHub Copilot) helped with analysis and scaffolding. Every figure is produced by `run.py` from the raw data.
