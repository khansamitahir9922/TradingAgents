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


# ---------------------------------------------------------------- the DSN never reaches failure output (Codex B8)

CANARY = "IE_FAKE_PASSWORD_CANARY"
NESTED_CONFTEST = '''
from contextlib import contextmanager

import pytest

from tests.engine import conftest as actual

pytest_plugins = ("tests.engine.conftest",)


@pytest.fixture(autouse=True)
def fake_database(monkeypatch, request):
    """The real pg_database fixture, with a fake DSN and no server: nothing connects."""
    monkeypatch.setenv(actual.ENV_TEST_PG_DSN, "host=localhost user=fake password=IE_FAKE_PASSWORD_CANARY")

    @contextmanager
    def fake(dsn):
        if request.node.get_closest_marker("setup_fails"):
            raise RuntimeError("database setup failed")
        yield actual.SecretDsn(str(dsn) + " dbname=ie_test_fake")
        if request.node.get_closest_marker("teardown_fails"):
            raise RuntimeError("database teardown failed")

    monkeypatch.setattr(actual, "temporary_database", fake)
'''
NESTED_TESTS = '''
import pytest

pytestmark = pytest.mark.postgres


def test_body_fails(pg_database):
    print("captured output names no credentials")
    assert False, "forced failure without printing credentials"


def test_equality_fails(pg_database):
    assert pg_database == "host=elsewhere"


def test_containment_fails(pg_database):
    assert pg_database not in "prefix " + pg_database


def test_repr_and_format(pg_database):
    assert repr(pg_database) == f"{pg_database!r}" and "password" not in repr(pg_database)
    raise RuntimeError(f"value was {pg_database!r}")


@pytest.mark.setup_fails
def test_setup_fails(pg_database):
    pass


@pytest.mark.teardown_fails
def test_teardown_fails(pg_database):
    pass
'''


@pytest.mark.unit
@pytest.mark.parametrize("options", [[], ["-l", "--tb=long", "-rA"], ["--tb=native"]], ids=["default", "locals",
                                                                                              "native"])
def test_failing_postgres_tests_never_print_the_dsn(tmp_path, options):
    """A nested pytest run with the real fixture and a fake password: every failure route stays redacted."""
    import subprocess
    import sys
    from pathlib import Path

    (tmp_path / "conftest.py").write_text(NESTED_CONFTEST, encoding="utf-8")
    (tmp_path / "test_nested.py").write_text(NESTED_TESTS, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    postgres\n    setup_fails\n    teardown_fails\n",
                                         encoding="utf-8")
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(tmp_path),
                          "--confcutdir", str(tmp_path), *options, str(tmp_path / "test_nested.py")],
                         capture_output=True, text=True, timeout=120, cwd=root,
                         env={**os.environ, "PYTHONPATH": str(root)})
    text = out.stdout + out.stderr
    assert "4 failed, 1 passed, 2 errors" in text, text[-2000:]  # every route was really exercised
    assert CANARY not in text and "password=" not in text
    assert "<test PostgreSQL DSN, redacted>" in text


NESTED_DRIVER_CONFTEST = '''
import pytest

import tests.conftest as root
from tests.engine import conftest as actual

pytest_plugins = ("tests.conftest", "tests.engine.conftest")


@pytest.fixture(autouse=True)
def fake_driver(monkeypatch):
    """The real root guard and the real pg_database fixture; only the final driver call is replaced. It parses the
    plain connection text the guard normalized, as the driver does, so the parameters are its locals, then fails."""
    monkeypatch.setenv(actual.ENV_TEST_PG_DSN, DSN)

    def failure(conninfo, **kwargs):
        from psycopg.conninfo import conninfo_to_dict

        parameters = conninfo_to_dict(conninfo)
        assert parameters
        raise RuntimeError("synthetic driver connection failure")

    monkeypatch.setitem(root.PG_REAL, "sync", failure)
'''
# Synthetic credentials only. Codex M3 second re-review R1: a three-character password, and one whose libpq quoting
# is then escaped again by repr. Third re-review: a DSN long enough (389 characters normalized) that pytest
# shortens the driver's conninfo argument, with the cut inside the password.
DRIVER_CASES = {
    "canary": ("IE_DRIVER_PASSWORD_CANARY", {}),
    "short": ("q7X", {}),
    "quoted": ("IE_quote'back\\slash", {}),
    "long": ("IE_LONG_PASSWORD_CANARY_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd",
             {"user": "u" * 63, "application_name": "v" * 180}),
}


def leaked_spellings(password: str, text: str) -> list[str]:
    """The ways `password` can be shown, written out here independently of the fixture's own list; and, for a
    password long enough to have them, any 12-character fragment a shortened repr could leave."""
    libpq = password.replace("\\", "\\\\").replace("'", "\\'")
    shown = {password, libpq, repr(password)[1:-1], repr(libpq)[1:-1], repr(repr(libpq)[1:-1])[1:-1]}
    shown |= {password[i:i + 12] for i in range(len(password) - 11)}
    return sorted(spelling for spelling in shown if spelling in text)


NESTED_DRIVER_TESTS = '''
import pytest


@pytest.mark.postgres
def test_connection_setup(pg_database):
    pass


@pytest.mark.postgres
def test_logged_and_printed(pg_database):
    pass
'''


@pytest.mark.unit
@pytest.mark.parametrize("case", DRIVER_CASES.values(), ids=DRIVER_CASES.keys())
@pytest.mark.parametrize("options", [[], ["-l", "--tb=long", "-rA"], ["--tb=native", "-rA"]],
                         ids=["default", "locals", "native"])
def test_a_failing_connection_setup_never_prints_the_password(tmp_path, options, case):
    """Codex re-review R1: the guard rebuilds the DSN as plain text for the driver; a driver failure's traceback
    (its arguments and, with -l, its locals) must still not show the password or any part of it, however short,
    however escaped and however pytest shortens it. Diagnostics stay."""
    import subprocess
    import sys
    from pathlib import Path

    from psycopg.conninfo import make_conninfo

    password, extra = case
    dsn = make_conninfo(**{"host": "localhost", "user": "fake", "password": password, "dbname": "postgres", **extra})
    (tmp_path / "conftest.py").write_text(f"DSN = {dsn!r}\n" + NESTED_DRIVER_CONFTEST, encoding="utf-8")
    (tmp_path / "test_nested.py").write_text(NESTED_DRIVER_TESTS, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    postgres\n", encoding="utf-8")
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(tmp_path),
                          "--confcutdir", str(tmp_path), *options, str(tmp_path / "test_nested.py")],
                         capture_output=True, text=True, timeout=120, cwd=root,
                         env={**os.environ, "PYTHONPATH": str(root)})
    text = out.stdout + out.stderr
    assert "2 error" in text and text.count("synthetic driver connection failure") >= 2, text[-3000:]
    assert not leaked_spellings(password, text)
    if "--tb=native" not in options:  # native tracebacks show no arguments; the others show the connection text
        assert "<redacted>" in text  # still shown, minus the password


@pytest.mark.unit
def test_the_scrubber_covers_composed_spellings_and_never_rescans_its_marker(monkeypatch):
    """Codex re-review R1, directly on the scrubber: a password of any length is remembered, each composed escaping
    is redacted, and a password that also occurs in the marker itself ("red" in "<redacted>") is replaced once."""
    from psycopg.conninfo import make_conninfo

    from tests.engine import conftest as actual

    quote, backslash = "'", chr(92)
    password = f"a{quote}b{backslash}c"
    monkeypatch.setattr(actual, "_SECRETS", set())
    dsn = make_conninfo(host="localhost", user="fake", password=password, dbname="postgres")
    actual._remember(dsn)
    actual._remember(make_conninfo(host="localhost", user="fake", password="red", dbname="postgres"))
    libpq = password.replace(backslash, 2 * backslash).replace(quote, backslash + quote)
    assert libpq in dsn  # the guard's plain text, which pytest then shows by repr
    shown = [password, libpq, repr(libpq), repr(repr(libpq)), repr({"password": password}), repr({"dsn": dsn})]
    scrubbed = actual._scrub(" | ".join(["conninfo = " + s for s in shown]) + " | password=red | red")
    assert all(f"b{backslash}" not in part and f"a{quote}" not in part for part in scrubbed.split(" | ")), scrubbed
    assert "red" not in scrubbed.replace("<redacted>", ""), scrubbed
    assert "<redacted>" in scrubbed and "<<" not in scrubbed and scrubbed.count("conninfo = ") == len(shown)


@pytest.mark.unit
def test_a_shortened_repr_never_keeps_part_of_a_password(monkeypatch):
    """Codex M3 third re-review, directly on pytest's own saferepr: a value too long to show whole is redacted
    before it is shortened, so no part of a remembered password survives the cut; other values are unchanged."""
    from _pytest._io.saferepr import DEFAULT_REPR_MAX_SIZE, saferepr
    from psycopg.conninfo import make_conninfo

    from tests.engine import conftest as actual

    password, extra = DRIVER_CASES["long"]
    monkeypatch.setattr(actual, "_SECRETS", set())
    dsn = make_conninfo(host="localhost", password=password, dbname="postgres", **extra)
    plain = "x" * 300
    assert len(dsn) > DEFAULT_REPR_MAX_SIZE
    plain_before, before = saferepr(plain), saferepr(dsn)  # nothing remembered yet
    assert leaked_spellings(password, before)  # the cut alone leaves a fragment: what this guards against
    actual._remember(dsn)
    for value in (dsn, {"conninfo": dsn}, [dsn, dsn], ("prefix", {"password": password, "pad": "w" * 300})):
        shown = saferepr(value)
        assert len(shown) <= DEFAULT_REPR_MAX_SIZE and not leaked_spellings(password, shown), shown
    assert saferepr(plain) == plain_before and len(plain_before) == DEFAULT_REPR_MAX_SIZE  # shortened as ever
    assert saferepr(dsn, maxsize=None) == repr(dsn)  # untruncated: left to the report boundary
