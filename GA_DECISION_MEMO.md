# Decision memo: GB generation-signal strategy

**Decision date:** 3 October 2026  
**Sample:** 3,925 complete delivery days, 2016–2 October 2026  
**Scope:** Historical, gross P/L; positions capped at ±25 MW.

## Recommendation

**Do not deploy a generation-triggered strategy yet.** Prioritize the
wind-short, nuclear-short, and solar-long directions for a pre-registered,
out-of-sample paper test with execution costs; park their opposite directions
unless new evidence supports them. Unconditional short power outperformed
each signal-conditioned rule in gross P/L, so this sample does not establish
a persistent or deployable edge.

## Evidence

The rules below take the indicated position only when the generation-share
threshold is active; otherwise they are flat. Long and short results are
opposite for the same active observations.

| Strategy | Gross P/L |
|---|---:|
| Wind ≥30% — short when active | £583,238 |
| Wind ≥30% — long when active | −£583,238 |
| Solar ≥0.5% — short when active | −£79,679 |
| Solar ≥0.5% — long when active | £79,679 |
| Nuclear ≥20% — short when active | £575,566 |
| Nuclear ≥20% — long when active | −£575,566 |
| Gas-referenced power — always short 25 MW | £3,059,606 |
| Gas-referenced power — always long 25 MW | −£3,059,606 |
| No action — flat | £0 |

The gas-referenced benchmarks are unconditional power positions evaluated
with the challenge's power P/L formula; they are not gas-commodity trades.
Monthly cumulative P/L charts and annual results are in
[`GA_analysis/wind_hypothesis_backtest.html`](GA_analysis/wind_hypothesis_backtest.html)
and [`GA_analysis/wind_hypothesis_annual_pnl.csv`](GA_analysis/wind_hypothesis_annual_pnl.csv).

## Trade-offs, metrics, and kill conditions

High wind and nuclear short rules were profitable in-sample, while the solar
short rule lost money. The always-short benchmark made substantially more,
but carries unconditional exposure and large drawdowns. No transaction costs,
slippage, or market impact are included; a flat position avoids those costs
but forgoes any market return.

Proceed only to paper testing. Before that test, specify costs and risk limits.
Continue only if **out-of-sample, after-cost P/L is positive**, exceeds the
no-action baseline, and is competitive with matched always-long/short
benchmarks without breaching the pre-set drawdown limit. Stop or revise the
strategy if net P/L is non-positive, performance fails to beat no action, or
the drawdown limit is breached. Reproduce the report with
`python GA_analysis/wind_hypothesis_backtest.py`; setup is in [`README.md`](README.md).
