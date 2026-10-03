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

## Reproduce from a fresh clone

The prepared market and forecast files are committed under `data/`, so a clone
of this repository contains the full input dataset; no separate download or
API access is required. The analysis was run with **Python 3.12.15**. The
version is recorded in [`.python-version`](.python-version), and
[`requirements.txt`](requirements.txt) pins the analysis dependencies and
their runtime dependencies.

Clone the repository and change into its root:

```bash
git clone https://github.com/recentlyhatched/advanced-challenge-grid-volatility.git
cd advanced-challenge-grid-volatility
```

Create an isolated Python 3.12 environment and install the locked dependencies.
Use Python 3.12.15 to match the tested interpreter exactly.

macOS / Linux (with Python 3.12.15 installed):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell (with Python 3.12 installed):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Confirm the interpreter with `python --version` (expected: `Python 3.12.15`).

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

The script reads the checked-in files in `data/` and overwrites all four
generated outputs above. It does not write to an absolute path, require a
local configuration file, access a network service, or use random sampling.
The console confirms the HTML and CSV output locations.

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
