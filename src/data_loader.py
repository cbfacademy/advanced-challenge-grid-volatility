"""Data loading and validation utilities."""

import sqlite3
from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
CSV_PATH = DATA_DIR / "grid_volatility_expanded_dataset.csv"
DB_PATH = DATA_DIR / "grid_volatility.db"


def load_with_pandas() -> pd.DataFrame:
    """Load the data pack as a Pandas DataFrame."""
    return pd.read_csv(CSV_PATH, parse_dates=["timestamp"])


def connect_sqlite() -> sqlite3.Connection:
    """Connect to the SQLite database.

    If the database doesn't exist, it will be created from the CSV.
    """
    if not DB_PATH.exists():
        dataframe = load_with_pandas()
        connect = sqlite3.connect(DB_PATH)
        dataframe.to_sql("grid_volatility", connect, index=False, if_exists="replace")
        connect.close()

    return sqlite3.connect(DB_PATH)


def query_sqlite(query: str) -> pd.DataFrame:
    """Run a SQL query against the SQLite database and return a DataFrame."""
    connect = connect_sqlite()
    
    try:
        return pd.read_sql_query(query, connect)
    finally:
        connect.close()

def connect_duckdb():
    """Connect to DuckDB and register the CSV as a view."""
    con = duckdb.connect()
    con.execute(f"CREATE OR REPLACE VIEW grid_volatility AS SELECT * FROM read_csv_auto('{CSV_PATH}')")
    return con


def query_duckdb(query: str) -> pd.DataFrame:
    """Run a SQL query against DuckDB and return a DataFrame."""
    con = connect_duckdb()
    try:
        return con.execute(query).df()
    finally:
        con.close()