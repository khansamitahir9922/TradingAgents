"""Fixtures for investment_engine tests.

Every engine test gets its own data directory, so nothing reads or writes the
user's real one (~/.investment_engine), in the spirit of tests/conftest.py,
which does the same for TradingAgents' results and caches.

PostgreSQL tests (marked `postgres`, docs/tasks/M3-00.md) each get a fresh,
empty database created from template0 through the maintenance DSN in
INVESTMENT_ENGINE_TEST_PG_DSN, and dropped afterwards even when the test
fails. Without the variable they skip with a visible reason. The DSN is never
printed: it may hold a password.
"""

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from investment_engine.config import ENV_DATA_DIR

ENV_TEST_PG_DSN = "INVESTMENT_ENGINE_TEST_PG_DSN"
PG_SKIP_REASON = "PostgreSQL test DSN not set (see docs/dev/postgresql.md)"


@pytest.fixture(autouse=True)
def _own_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "engine-data"
    monkeypatch.setenv(ENV_DATA_DIR, str(data))
    return data


def maintenance_dsn() -> str | None:
    return os.environ.get(ENV_TEST_PG_DSN) or None


@contextmanager
def temporary_database(dsn: str) -> Iterator[str]:
    """Create `ie_test_<hex>` from template0; yield its DSN; drop it on the way out, whatever happened."""
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    name = "ie_test_" + secrets.token_hex(8)
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(name)))
    try:
        yield make_conninfo(dsn, dbname=name)
    finally:
        _drop(dsn, name)


def _drop(dsn: str, name: str, attempts: int = 20) -> None:
    """Drop the test database. A plain drop is retried while something else still has it open, typically
    an autovacuum worker, which runs as the superuser, so the non-superuser test role can't terminate it
    (WITH (FORCE) then fails with InsufficientPrivilege). FORCE is the last resort, for the test's own
    leftover connections."""
    import time

    import psycopg
    from psycopg import errors, sql

    statement = sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name))
    with psycopg.connect(dsn, autocommit=True) as admin:
        for _ in range(attempts):
            try:
                admin.execute(statement)
                return
            except errors.ObjectInUse:
                time.sleep(0.25)
        admin.execute(statement + sql.SQL(" WITH (FORCE)"))


@pytest.fixture
def pg_database(request) -> Iterator[str]:
    """A fresh, empty database for one `postgres` test; yields its DSN; dropped afterwards."""
    if request.node.get_closest_marker("postgres") is None:
        raise RuntimeError("pg_database is only for tests marked postgres")
    dsn = maintenance_dsn()
    if dsn is None:
        pytest.skip(PG_SKIP_REASON)
    with temporary_database(dsn) as database:
        yield database
