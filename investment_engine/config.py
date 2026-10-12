"""Where the platform keeps its data.

Everything lives under one data directory, outside the repository:
$INVESTMENT_ENGINE_DATA_DIR if set (and non-empty), else ~/.investment_engine.
The variable is read on every call, never at import, and nothing here
creates folders.
"""

import os
from pathlib import Path

ENV_DATA_DIR = "INVESTMENT_ENGINE_DATA_DIR"


def data_dir() -> Path:
    configured = os.environ.get(ENV_DATA_DIR)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".investment_engine"


def operational_db_path() -> Path:
    """The Operational Database: SQLite in M1–M2 (ADR-008)."""
    return data_dir() / "operational.sqlite3"


def market_store_dir() -> Path:
    """The Market-Data Store (Parquet; architecture Part E)."""
    return data_dir() / "market"
