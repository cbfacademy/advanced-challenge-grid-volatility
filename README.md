# Grid Volatility Challenge

Welcome to the Grid Volatility Challenge! This repo contains everything you need to get started. 

## The Challenge

You are stepping into the role of a lead analyst at an energy trading desk. Your mission is to build a pipeline and decision framework that helps the desk anticipate weather-driven demand volatility and keep energy moving where it is needed most. 

**Python Version**: This project is pinned to **Python 3.12** via `.python-version`. This is to avoid build failures with scientific libraries (pandas, NumPy, DubkDB). 

If you use `pyenv` or `pyenv-win`, it will be selected automatically. Please do not modify this file unless intentionally updating the project's Python version. 

**Full challenge requirements:** see [`CHALLENGE_README.md`](/docs/CHALLENGE_README.md).

## Prerequisites 
- Python 3.12
- `pip` - comes with Python 
- Git for cloning the repo

### Installing Python

**macOS (Homebrew):**

```bash
brew install python@3.12
```
**Windows:**

Download the Python 3.12 executable directly from [`python.org/downloads`](python.org/downloads) and run the installer. Ensure you check the box that says "Add python.exe to PATH" during setup. 

## Getting Started

### 1. Fork the repo
Click "Fork" in the top-right of the GitHub repo page, then clone your fork:
```bash
git clone https://github.com/<your-username>/advanced-challenge-grid-volatility.git
cd advanced-challenge-grid-volatility
```

### 2. Create a Virtual Environment

macOS / Linux:
```bash
python3.12 -m venv venv
source venv/bin/activate
```

Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Windows (Command Prompt):
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

You should see `venv` at the start of your terminal prompt, indicating the environment is active.

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Note: SQLite is built into Python. No installation required.

### 4. Verify the Setup

Run this quick check to confirm everything is installed correctly:
```bash
python -c "import pandas, numpy, duckdb, sqlite3; print('All imports OK')"
```

You should see `All imports OK`.

## What This Repo Does Right Now

At present, the repo provides:
- A pre-packaged data set at `data/grid_volatility_expanded_dataset.csv`
- A data loader at `src/data_loader.py` that:
    - Loads the CSV into a Pandas DataFrame
    - Builds a SQLite database from the CSV (on first run)
    - Provides functions to query the data via SQLite or DuckDB
- A data dictionary at `data/DATA_DICTIONARY.md` - this will describe the columns, units, and known data issues

There is no analysis or forecast model yet. You'll be working on this!

## How to Use It

### Option 1: Interact with the Data Loader in Python

Create a scratch script or run Python interactively:
```bash
python

from src.data_loader import load_with_pandas, query_sqlite, query_duckdb

# Load the raw data
df = load_with_pandas()
print(df.head())

# Query via SQLite
result = query_sqlite("SELECT COUNT(*) as rows FROM grid_volatility")
print(result)

# Query via DuckDB (if installed)
result = query_duckdb("SELECT * FROM grid_volatility LIMIT 5")
print(result)
```

### Option 2: Use SQL Directly

Once the SQLite database exists (data/grid_volatility.db), you can query it with any SQLite client:
```bash
sqlite3 data/grid_volatility.db "SELECT COUNT(*) FROM grid_volatility;"
```

Or with DuckDB's CLI:
```bash
duckdb -c "SELECT * FROM 'data/grid_volatility_expanded_dataset.csv' LIMIT 5;"
```

### Option 3: Build Your Own Analysis

Create a new script in `src/`. Import the data loader and build from there.

### Project Structure
```text
├── data/
│   ├── DATA_DICTIONARY.md       # Describes the data pack
│   └── grid_volatility_expanded_dataset.csv
├── docs/
│   ├── BUILD_DAY_TIMELINE.md    # Schedule for the day
│   └── CHALLENGE_README.md      # Full challenge requirements
└── src/
    ├── __init__.py
    └── data_loader.py           # Load and query the data
├── .gitignore
├── .python-version              # Pins Python 3.12
├── CONTRIBUTING.md              # How to contribute to this repo
├── DECISION_MEMO.md             # Your executive brief - TO COMPLETE
├── README.md                    # This file - TO COMPLETE
├── requirements.txt             # Lists dependencies
```

### Deliverables

By the end of the build day, your repo should contain:
- `DECISION_MEMO.md` — a one-page executive brief with your hypothesis, recommendation, trade-offs, and metrics.
- A reproducible repo including a clear `README` — your code should run from a clean clone with no manual steps.

Please raise a PR with your work by the feature freeze deadline.

See `docs/CHALLENGE_README.md` for the full brief and criterion.
