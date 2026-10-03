"""Locate and load the raw files, and provide a small SQL engine wrapper.

SQL runs on DuckDB when it is installed (the default via requirements.txt) and falls
back to SQLite from the Python standard library otherwise. The SQL in /sql is written
to run unchanged on both: timestamps are passed as integer epoch seconds and dates as
'YYYY-MM-DD' strings, so no engine-specific date functions are needed.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import OPTIONAL_FILES, REQUIRED_FILES


# ---------------------------------------------------------------- file discovery
def find_files(data_dir: Path) -> dict[str, Path]:
    """Search data_dir recursively for each expected file name."""
    found: dict[str, Path] = {}
    for key, name in {**REQUIRED_FILES, **OPTIONAL_FILES}.items():
        matches = sorted(data_dir.rglob(name))
        if matches:
            found[key] = matches[0]
    missing = [REQUIRED_FILES[k] for k in REQUIRED_FILES if k not in found]
    if missing:
        raise FileNotFoundError(
            f"Could not find {missing} anywhere under {data_dir.resolve()}. "
            "Run from the repo root, or pass --data-dir pointing at the folder holding the dataset."
        )
    return found


# ---------------------------------------------------------------- loaders
def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def read_fuel_prices(path: Path) -> pd.DataFrame:
    """The workbook has a title row above the real header, so locate the header by name."""
    raw = pd.read_excel(path, header=None, engine="openpyxl")
    header_rows = raw.index[raw.apply(lambda r: r.astype(str).str.strip().eq("UK Power Day").any(), axis=1)]
    if len(header_rows) == 0:
        raise ValueError(f"No 'UK Power Day' header found in {path.name}")
    h = header_rows[0]
    df = raw.iloc[h + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[h]]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- SQL engine
class SqlEngine:
    """Register pandas DataFrames as tables and run SQL against them."""

    def __init__(self, prefer: str = "duckdb"):
        self.kind = "sqlite"
        if prefer == "duckdb":
            try:
                import duckdb  # noqa: F401
                self.kind = "duckdb"
            except ImportError:
                pass
        if self.kind == "duckdb":
            import duckdb
            self._con = duckdb.connect(database=":memory:")
        else:
            self._con = sqlite3.connect(":memory:")

    def register(self, name: str, df: pd.DataFrame) -> None:
        if self.kind == "duckdb":
            self._con.register(f"_{name}_view", df)
            self._con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _{name}_view")
            self._con.unregister(f"_{name}_view")
        else:
            df.to_sql(name, self._con, index=False, if_exists="replace")

    def query(self, sql: str) -> pd.DataFrame:
        if self.kind == "duckdb":
            return self._con.execute(sql).df()
        return pd.read_sql_query(sql, self._con)

    def run_file(self, path: Path) -> pd.DataFrame:
        return self.query(path.read_text(encoding="utf-8"))
