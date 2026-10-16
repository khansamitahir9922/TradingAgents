"""The local PostgreSQL test harness and its connection guard (docs/tasks/M3-00.md)."""

import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

import tests.conftest as root_conftest
from tests.engine.conftest import (
    ENV_TEST_PG_DSN,
    PG_SKIP_REASON,
    maintenance_dsn,
    temporary_database,
)

SECRET = "S3cretProbeValue"  # a recognisable fake password: it must never appear in any message
LOCAL = f"host=localhost port=5432 dbname=postgres user=probe password={SECRET}"


@pytest.fixture
def recorder(monkeypatch):
    """Replaces the real connect functions, so probes never make a request."""
    calls = []

    def sync(conninfo, **options):
        calls.append((conninfo_to_dict(conninfo), {n: v for n, v in os.environ.items() if n.upper().startswith("PG")}))
        return "connection"

    async def asynchronous(conninfo, **options):
        return sync(conninfo, **options)

    monkeypatch.setitem(root_conftest.PG_REAL, "sync", sync)
    monkeypatch.setitem(root_conftest.PG_REAL, "async", asynchronous)
    return calls


def run_without_loop(coroutine):
    """Drive a coroutine that never suspends. An event loop would open a socket pair, which the socket guard
    (rightly) refuses; the recorder and the guard both finish without awaiting I/O."""
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    raise AssertionError("the probe suspended")


ENTRY_POINTS = {
    "psycopg.connect": lambda *a, **k: psycopg.connect(*a, **k),
    "Connection.connect": lambda *a, **k: psycopg.Connection.connect(*a, **k),
    "AsyncConnection.connect": lambda *a, **k: run_without_loop(psycopg.AsyncConnection.connect(*a, **k)),
}

REFUSED = [
    ("non-loopback host", "host=db.example port=5432 dbname=postgres user=probe password=" + SECRET, {}),
    ("hostaddr override", LOCAL + " hostaddr=203.0.113.10", {}),
    ("service", "service=x user=probe password=" + SECRET, {}),
    ("multi-host", "host=localhost,db.example port=5432 user=probe password=" + SECRET, {}),
    ("URI with hostaddr", f"postgresql://probe:{SECRET}@localhost:5432/postgres?hostaddr=203.0.113.10", {}),
    ("URI remote host", f"postgresql://probe:{SECRET}@db.example:5432/postgres", {}),
    ("keyword host override", LOCAL, {"host": "db.example"}),
    ("keyword hostaddr override", LOCAL, {"hostaddr": "203.0.113.10"}),
    ("options keyword", LOCAL + " options=-csearch_path=x", {}),
]


@pytest.mark.unit
@pytest.mark.postgres
@pytest.mark.parametrize("entry", list(ENTRY_POINTS))
@pytest.mark.parametrize("case, conninfo, kwargs", REFUSED, ids=[c[0] for c in REFUSED])
def test_unsupported_connection_parameters_are_refused_before_connecting(recorder, entry, case, conninfo, kwargs):
    with pytest.raises(root_conftest.PostgresGuardError) as error:
        ENTRY_POINTS[entry](conninfo, **kwargs)
    assert recorder == []
    assert SECRET not in str(error.value) and "203.0.113.10" not in str(error.value)


@pytest.mark.unit
@pytest.mark.postgres
@pytest.mark.parametrize("entry", list(ENTRY_POINTS))
@pytest.mark.parametrize("variable, value", [("PGHOST", "db.example"), ("PGHOSTADDR", "203.0.113.10"),
                                             ("PGSERVICE", "remote"), ("PGSERVICEFILE", "C:/elsewhere/pg_service.conf"),
                                             ("PGPORT", "6543")])
def test_ambient_libpq_settings_are_neutralized_and_loopback_is_pinned(recorder, monkeypatch, entry, variable, value):
    monkeypatch.setenv(variable, value)
    ENTRY_POINTS[entry](LOCAL)
    (params, environment), = recorder
    assert environment == {}  # no PG* variable reached the real connect
    assert params["host"] == "localhost" and params["hostaddr"] == "127.0.0.1" and params["port"] == "5432"
    assert value not in params.values()


@pytest.mark.unit
@pytest.mark.postgres
def test_supported_local_forms_reach_the_recorder_pinned(recorder):
    psycopg.connect(f"postgresql://probe:{SECRET}@127.0.0.1:5432/postgres")
    psycopg.connect("host=::1 port=5432 dbname=postgres user=probe", password=SECRET, autocommit=True)
    assert [p["hostaddr"] for p, _ in recorder] == ["127.0.0.1", "::1"]


@pytest.mark.unit
@pytest.mark.parametrize("entry", list(ENTRY_POINTS))
def test_a_test_without_the_marker_cannot_connect(recorder, entry):
    with pytest.raises(root_conftest.PostgresGuardError, match="mark it postgres"):
        ENTRY_POINTS[entry](LOCAL)
    assert recorder == []


@pytest.mark.unit
def test_without_the_dsn_postgres_tests_skip_with_the_documented_reason(request, monkeypatch):
    monkeypatch.delenv(ENV_TEST_PG_DSN, raising=False)
    assert maintenance_dsn() is None
    request.node.add_marker(pytest.mark.postgres)
    with pytest.raises(pytest.skip.Exception, match="PostgreSQL test DSN not set") as skipped:
        request.getfixturevalue("pg_database")
    assert str(skipped.value.msg) == PG_SKIP_REASON


# ---------------------------------------------------------------- against the real local server


def _database_exists(name: str) -> bool:
    with psycopg.connect(maintenance_dsn(), autocommit=True) as admin:
        return admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is not None


@pytest.mark.postgres
def test_pg_database_is_fresh_empty_and_loopback(pg_database):
    with psycopg.connect(pg_database) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        tables = conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'").fetchone()[0]
        address = conn.execute("SELECT host(inet_server_addr())").fetchone()[0]
    assert name.startswith("ie_test_") and tables == 0 and address in ("127.0.0.1", "::1")
    assert _database_exists(name)


@pytest.mark.postgres
def test_a_temporary_database_is_dropped_afterwards_even_after_a_failure():
    dsn = maintenance_dsn()
    if dsn is None:
        pytest.skip(PG_SKIP_REASON)
    with temporary_database(dsn) as database:
        name = conninfo_to_dict(database)["dbname"]
        assert _database_exists(name)
    assert not _database_exists(name)
    with pytest.raises(RuntimeError, match="the test failed"), temporary_database(dsn) as database:
        failed = conninfo_to_dict(database)["dbname"]
        with psycopg.connect(database) as conn:  # an open connection doesn't stop the drop (FORCE)
            conn.execute("CREATE TABLE t (x int)")
            raise RuntimeError("the test failed")
    assert not _database_exists(failed)
