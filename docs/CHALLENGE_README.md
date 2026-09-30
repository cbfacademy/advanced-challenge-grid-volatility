# Grid Volatility Challenge 
# Full Requirements

## Commercial Context

Imagine trying to keep the power grid balanced when a sudden heatwave spikes air conditioning demand or unexpected cloud cover drops solar power generation in minutes. Modern energy trading desks face this precise high-stakes challenge every day.

As renewable energy grows and extreme weather becomes more frequent, power grids experience rapid, unpredictable shifts in supply and demand. Missing these changes can lead to costly trading losses, severe power shortfalls, or massive price surges.

In this challenge, you will step into the role of lead data architects and quantitative analysts.

**Your task:** Build the pipeline and decision framework that a trading desk would use to anticipate volatility, hedge risk, and keep energy moving where it is needed most.

## Technical Expectations

- **Core stack:** Python and SQL
- **Recommended SQL engine:** SQLite (built into Python) or DuckDB (`pip install duckdb`)
- **AI tools:** Use is encouraged but not required, to accelerate data wrangling and model scaffolding
- **Code quality:** Clean, reproducible, and runs successfully from a clean clone

Teams will receive a pre-packaged **Grid Volatility Data Pack** to minimise setup time. The focus is on robust data validation, cleaning, and dynamic data synthesis.

**Note:** A simple, clearly reasoned approach is preferred to a complex one you can't explain. You are not expected to produce a production-grade forecast.

## Required Deliverables

### 1. `DECISION_MEMO.md`

A single-page executive brief detailing:

- **Hypothesis:** Your one-line hypothesis and why you chose it
- **Recommendation:** The action or decision you would advise a trading desk to take
- **Trade-offs:** Key compromises, risks, limitations, and rejected alternatives
- **Metrics and kill conditions:** How you'd measure success, and what would cause you to revisit

### 2. GitHub Repo

A reviewer should be able to run the program and reproduce your key outputs without manual steps. Update the [`README.md`](/README.md) detailing how to run it and what to expect.

## Pitching Session Rules

- Strict **no-slide** rule
- 5-minute live technical demo/walkthrough
- 3-minute executive Q&A

## Criterion

### Shortlisting

| Factor | Weight | What strong looks like |
| :--- | :--- | :--- |
| Problem framing | 25% | Clearly articulates the business decision, develops a focused and testable hypothesis, identifies key assumptions and risks |
| Technical execution | 25% | Method is sound and appropriate to the time. Assumptions and limitations are acknowledged. Outputs are reproducible. |
| Data handling | 25% | Identifies and documents seeded data issues. Handles gaps, outliers, etc. sensibly. |
| Clarity of output | 25% | `DECISION_MEMO` and repo communicate the recommendation clearly. A reviewer can follow it without the team present. |

### Pitch Day

| Factor | Weight | What strong looks like |
| :--- | :--- | :--- |
| Decision clarity | 30% | States the decision and why. Demo tells one coherent story. |
| Technical substance | 25% | Code runs cleanly. Can speak to methods and limitations clearly. |
| Communication | 25% | Clear, confident, well-paced. Uses the allocated time fully. |
| Q&A | 25% | Answers directly. Shows depth when probed. |
