"""Fixtures for investment_engine tests.

Every engine test gets its own data directory, so nothing reads or writes the
user's real one (~/.investment_engine), in the spirit of tests/conftest.py,
which does the same for TradingAgents' results and caches.

PostgreSQL tests (marked `postgres`, docs/tasks/M3-00.md) each get a fresh,
empty database created from template0 through the maintenance DSN in
INVESTMENT_ENGINE_TEST_PG_DSN, and dropped afterwards even when the test
fails. Without the variable they skip with a visible reason. The DSN is never
printed: it may hold a password. It is handed out as a SecretDsn, a str whose
repr is redacted, and assertion explanations involving one are withheld (Codex
M3 review B8). Code beyond the fixture (the root connection guard, the driver)
rebuilds plain connection text, so every report is also scrubbed at the report
boundary: each DSN and password the fixtures read is replaced in tracebacks,
locals and captured output, wherever it came from (Codex M3 re-review R1),
and a value pytest would shorten is redacted before it is shortened.
"""

import os
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from investment_engine.config import ENV_DATA_DIR

ENV_TEST_PG_DSN = "INVESTMENT_ENGINE_TEST_PG_DSN"
PG_SKIP_REASON = "PostgreSQL test DSN not set (see docs/dev/postgresql.md)"


@pytest.fixture(autouse=True)
def _own_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "engine-data"
    monkeypatch.setenv(ENV_DATA_DIR, str(data))
    return data


class SecretDsn(str):
    """A DSN that libpq can use as a str, but whose repr (used by pytest's failure reports, `--showlocals` and
    `!r` formatting) never shows its text."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<test PostgreSQL DSN, redacted>"


def pytest_assertrepr_compare(config, op, left, right):
    """pytest explains a failed comparison by quoting both sides. When a DSN is one side, the other may contain
    it (`dsn in output`), so neither side is quoted, only its type."""
    if isinstance(left, SecretDsn) or isinstance(right, SecretDsn):
        def shown(side):
            return repr(side) if isinstance(side, SecretDsn) else f"<{type(side).__name__}, not shown>"
        return [f"{shown(left)} {op} {shown(right)}",
                "(the comparison involves a test database DSN; neither side is shown)"]
    return None


_SECRETS: set[str] = set()  # every DSN and password the fixtures have read, as they may appear in a report
_SPELLING_DEPTH = 3  # escapings composed: the guard's libpq text, then pytest's repr of it, inside a dict's repr


def _spellings(secret: str) -> set[str]:
    """`secret` as a report can show it: as written, libpq-quoted, repr'd and URL-encoded, and every composition of
    those up to `_SPELLING_DEPTH` deep (a libpq-quoted password shown by repr is both; Codex M3 re-review R1)."""
    from urllib.parse import quote

    escapes = (lambda v: v.replace("\\", "\\\\").replace("'", "\\'"),  # libpq conninfo quoting
               lambda v: repr(v)[1:-1],  # Python repr, as pytest shows arguments and locals
               lambda v: quote(v, safe=""))  # a URI DSN's percent-encoding
    found = frontier = {secret}
    for _ in range(_SPELLING_DEPTH):
        frontier = {escape(v) for v in frontier for escape in escapes} - found
        found = found | frontier
    return found


def _remember(dsn: str) -> None:
    from psycopg.conninfo import conninfo_to_dict

    found = _spellings(str(dsn))
    try:
        password = conninfo_to_dict(str(dsn)).get("password")
    except Exception:  # an unparsable DSN is refused later; its whole text is still remembered
        password = None
    if password:  # of any length: a short password is still a password
        found |= _spellings(password)
    _SECRETS.update(v for v in found if v)


def _scrub(text: str) -> str:
    """One pass, longest spelling first, so a short password can't match inside an earlier replacement. A short
    password redacts its every occurrence, wanted or not: an unreadable report is preferred to a leaked one."""
    import re

    if not _SECRETS:
        return text
    pattern = "|".join(re.escape(secret) for secret in sorted(_SECRETS, key=len, reverse=True))
    return re.sub(pattern, "<redacted>", text)


def _redact_before_truncation() -> None:
    """pytest shortens a long repr (arguments, locals, assertion operands) by cutting out its middle, before any
    report exists, so a password split by the cut leaves a fragment no full spelling matches (Codex M3 third
    re-review). SafeRepr.repr is where every truncating saferepr goes through, so a value that shows a remembered
    secret in full is redacted first and shortened only afterwards. This is pytest's private API (9.1.1): if it
    changes, this raises at import and every engine test fails, rather than leaking quietly."""
    from _pytest._io import saferepr as module

    cls, ellipsize = module.SafeRepr, module._ellipsize
    original = cls.repr
    if getattr(original, "redacts_secrets", False):
        return

    def repr(self, x):
        shown = original(self, x)
        if not _SECRETS or self.maxsize is None:  # untruncated: the report boundary finds every full spelling
            return shown
        full = original(cls(None, self.use_ascii), x)
        scrubbed = _scrub(full)
        return shown if scrubbed == full else ellipsize(scrubbed, self.maxsize)

    repr.redacts_secrets = True
    cls.repr = repr


_redact_before_truncation()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """The report boundary: whatever a setup, call or teardown failure shows (arguments, locals, normalized
    connection text, captured output, logs), no remembered DSN or password survives into it."""
    outcome = yield
    report = outcome.get_result()
    if not _SECRETS:
        return
    if report.longrepr is not None:
        text = str(report.longrepr)
        if _scrub(text) != text:
            report.longrepr = _scrub(text)
    report.sections = [(title, _scrub(content)) for title, content in report.sections]


def maintenance_dsn() -> str | None:
    value = os.environ.get(ENV_TEST_PG_DSN)
    if not value:
        return None
    _remember(value)
    return SecretDsn(value)


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
        database = SecretDsn(make_conninfo(dsn, dbname=name))
        _remember(database)
        yield database
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


@dataclass
class Backend:
    """One test database at schema 4 on one backend; `make()` opens another connection to it."""

    kind: str
    make: Callable[[], object]
    first: object


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgres)])
def backend(request, tmp_path) -> Iterator[Backend]:
    """The M1-M2 stores run on both backends (docs/tasks/M3-02.md); new M3 stores use PostgreSQL only."""
    from investment_engine.storage.database import PostgresDatabase, SqliteDatabase
    from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
    from investment_engine.storage.sqlite import apply_schema, open_operational_db

    opened = []
    if request.param == "sqlite":
        path = tmp_path / "operational.sqlite3"

        def make():
            opened.append(open_operational_db(path))
            return SqliteDatabase(opened[-1])

        first = make()
        apply_schema(first.connection)
    else:
        dsn = request.getfixturevalue("pg_database")

        def make():
            opened.append(open_operational_pg(dsn))
            return PostgresDatabase(opened[-1])

        first = make()
        apply_pg_schema(first.connection)
    yield Backend(request.param, make, first)
    for conn in opened:
        conn.close()


@pytest.fixture
def database(backend):
    return backend.first


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
