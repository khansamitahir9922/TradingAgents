"""Where the platform keeps its data.

Everything on disk lives under one data directory, outside the repository:
$INVESTMENT_ENGINE_DATA_DIR if set (and non-empty), else ~/.investment_engine.
The Operational Database is PostgreSQL from M3 (ADR-008), reached through the
DSN in $INVESTMENT_ENGINE_PG_DSN. Variables are read on every call, never at
import, and nothing here creates folders. The DSN may hold a password: it is
never printed, logged or put in an error message.
"""

import os
from pathlib import Path

ENV_DATA_DIR = "INVESTMENT_ENGINE_DATA_DIR"
ENV_PG_DSN = "INVESTMENT_ENGINE_PG_DSN"


class OperationalDatabaseNotConfigured(RuntimeError):
    """The Operational Database's DSN isn't set; the message names the variable, never a value."""


def data_dir() -> Path:
    configured = os.environ.get(ENV_DATA_DIR)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".investment_engine"


def operational_db_path() -> Path:
    """The M1–M2 SQLite Operational Database file; from M3 only a source for `db copy-from-sqlite`."""
    return data_dir() / "operational.sqlite3"


def operational_db_dsn() -> str:
    """The PostgreSQL Operational Database's DSN (docs/tasks/M3-03.md)."""
    dsn = os.environ.get(ENV_PG_DSN)
    if not dsn:
        raise OperationalDatabaseNotConfigured(
            f"{ENV_PG_DSN} is not set. PostgreSQL is the Operational Database from M3; "
            "see docs/dev/postgresql.md")
    return dsn


def market_store_dir() -> Path:
    """The Market-Data Store (Parquet; architecture Part E)."""
    return data_dir() / "market"
