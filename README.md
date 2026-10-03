# Grid Volatility Challenge: generation strategy backtest

This repository evaluates GB power-market strategies conditioned on **wind,
solar, and nuclear generation forecasts**. It compares each signal with
unconditional gas-referenced power positions (always long and always short)
and a no-action baseline. The analysis uses the repository's historical data
and produces a monthly cumulative P/L chart, a detailed HTML report, and an
annual P/L CSV.

For the decision and the headline results, see
[`GA_DECISION_MEMO.md`](GA_DECISION_MEMO.md). For the full challenge specification,
see [`docs/CHALLENGE.md`](docs/CHALLENGE.md); the available data are described
in [`data/DATA_DICTIONARY.md`](data/DATA_DICTIONARY.md).

## Requirements

- Python 3.12 (also recorded in [`.python-version`](.python-version))
- `pip`
- The historical data files included under `data/`

The script needs no database, API credentials, or external data download.
Install the pinned Python dependencies from the repository root:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Create an isolated environment

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Reproduce the analysis

From the repository root, run:

```bash
python GA_analysis/wind_hypothesis_backtest.py
```

This uses the fixed default end date of **2 October 2026** and writes:

- `GA_analysis/wind_hypothesis_backtest.html` — charts, strategy performance,
  generation-mix analysis, and Elexon revision analysis.
- `GA_analysis/wind_hypothesis_annual_pnl.csv` — annual gross P/L by strategy and
  sample.
- `GA_analysis/GA_training_phase_gross_pnl.png` and
  `GA_analysis/GA_validation_phase_gross_pnl.png` — monthly cumulative gross P/L
  split at 1 January 2023; each phase starts from £0.

To run through another delivery date covered by the local data:

```bash
python GA_analysis/wind_hypothesis_backtest.py --end-date YYYY-MM-DD
```

The cumulative strategy charts aggregate half-hourly P/L into **monthly**
totals before accumulating it over time. The full-sample comparisons include
short-on-active-signal rules for wind (forecast share at least 30%), solar
(at least 0.5%), and nuclear (at least 20%), plus the inverse long versions.
They are compared with always-long and always-short 25 MW power positions and
no action. These gas-referenced benchmarks use the power-market P/L formula;
they are not trades in gas itself.

## P/L and interpretation

For each half-hour the backtest applies the challenge formula:

```text
P/L = 0.5 × [X × (DA-HH − DA-HR) + Y × (cashout − DA-HH)]
```

Here `X` is the 9am hourly-auction position and `Y` is the position held after
the 3pm half-hourly auction. The tested threshold rules hold their position
through cashout. All positions are capped at ±25 MW. The reported results are
**gross historical P/L**: transaction costs, slippage, market impact, and
out-of-sample selection are not included, so they should not be interpreted
as deployable returns.

## Repository data

The prepared datasets are included in `data/`. No separate data download is
required. Consult [`data/DATA_DICTIONARY.md`](data/DATA_DICTIONARY.md) for
datasets, date coverage, and folder layout.
