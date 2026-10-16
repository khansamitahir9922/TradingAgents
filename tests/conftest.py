"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
import socket

import pytest


def _blank_settings_overlay():
    """Blank every TRADINGAGENTS_* setting before the package is imported.

    The package loads .env on import and folds these variables into
    DEFAULT_CONFIG, so a contributor's own settings would become the defaults
    the suite asserts on. A blank value is still present, so load_dotenv leaves
    it alone, and the overlay reads it as unset. Tests of the overlay set their own.
    """
    from dotenv import dotenv_values, find_dotenv

    names = set(os.environ)
    for filename in (".env", ".env.enterprise"):
        names |= set(dotenv_values(find_dotenv(filename, usecwd=True)))
    for name in names:
        if name.startswith("TRADINGAGENTS_"):
            os.environ[name] = ""


_blank_settings_overlay()


def _own_file_locations():
    """Keep the suite's results, cache and memory log in a directory of its own.

    Set before the package is imported, whose defaults put them in the user's
    home: a test reading the user's cache would see what their runs fetched.
    """
    import tempfile

    home = tempfile.mkdtemp(prefix="tradingagents-tests-")
    os.environ["TRADINGAGENTS_RESULTS_DIR"] = os.path.join(home, "logs")
    os.environ["TRADINGAGENTS_CACHE_DIR"] = os.path.join(home, "cache")
    os.environ["TRADINGAGENTS_MEMORY_LOG_PATH"] = os.path.join(home, "memory", "trading_memory.md")


_own_file_locations()


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")
    # yfinance caches each symbol's time zone on disk, in the home directory
    # by default; the suite keeps it in a directory of its own.
    import tempfile

    import yfinance

    yfinance.set_tz_cache_location(tempfile.mkdtemp(prefix="tradingagents-tests-yf-"))


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Tests do not reach the network; one that must is marked integration."""
    if request.node.get_closest_marker("integration"):
        return

    def refuse(*args, **kwargs):
        raise OSError(f"test tried to reach the network: {args[1:] or kwargs}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: refuse(None, *a))
    # yfinance's HTTP client is libcurl, which never touches Python's sockets.
    from curl_cffi import requests as curl_requests

    monkeypatch.setattr(curl_requests.Session, "request", refuse)
    monkeypatch.setattr(curl_requests.AsyncSession, "request", refuse)
    _guard_postgres(request, monkeypatch)


# ---------------------------------------------------------------- PostgreSQL (docs/tasks/M3-00.md rule 4)
# libpq connects without Python's sockets, and its settings can also come from PG* environment variables and
# service files. So every psycopg entry point is wrapped: unmarked tests can't connect at all, and `postgres`
# tests reach only a pinned numeric loopback address, judged on the effective parameters. Refusals name the
# offending keyword, never a value (the DSN may hold a password).
PG_ALLOWED_KEYWORDS = frozenset({"host", "port", "dbname", "user", "password", "connect_timeout",
                                 "application_name", "sslmode"})
PG_LOOPBACK = {"localhost": "127.0.0.1", "127.0.0.1": "127.0.0.1", "::1": "::1"}
PG_CONNECTION_OPTIONS = ("autocommit", "prepare_threshold", "context", "row_factory", "cursor_factory")
# The real connect functions, looked up at call time so the harness tests can put a recorder here.
PG_REAL: dict[str, object] = {}


class PostgresGuardError(OSError):
    """A test tried to open a PostgreSQL connection it isn't allowed to open."""


def pg_effective_params(conninfo: str = "", **kwargs) -> dict[str, str]:
    """The checked connection parameters, with hostaddr pinned to loopback; raises PostgresGuardError."""
    from psycopg.conninfo import conninfo_to_dict

    try:
        params = {k: str(v) for k, v in conninfo_to_dict(conninfo, **kwargs).items() if v is not None}
    except Exception:
        raise PostgresGuardError("PostgreSQL connection string could not be parsed") from None
    unsupported = sorted(set(params) - PG_ALLOWED_KEYWORDS)
    if unsupported:
        raise PostgresGuardError(f"PostgreSQL connection keyword(s) not allowed in tests: {', '.join(unsupported)}")
    if params.get("host", "") not in PG_LOOPBACK:
        raise PostgresGuardError("PostgreSQL tests may connect only to one loopback host (localhost, 127.0.0.1, ::1)")
    if not params.get("port", "5432").isdigit():
        raise PostgresGuardError("PostgreSQL port must be a single number")
    params["hostaddr"] = PG_LOOPBACK[params["host"]]
    return params


def _guard_postgres(request, monkeypatch):
    try:
        import psycopg
        from psycopg.conninfo import make_conninfo
    except ImportError:  # the base install has no PostgreSQL driver: nothing to guard
        return
    allowed = request.node.get_closest_marker("postgres") is not None

    def neutralize():
        # Every ambient libpq setting is removed for the test's duration; only the explicit DSN counts.
        for name in [n for n in os.environ if n.upper().startswith("PG")]:
            monkeypatch.delenv(name)

    if allowed:
        neutralize()
    PG_REAL.setdefault("sync", psycopg.Connection.connect)
    PG_REAL.setdefault("async", psycopg.AsyncConnection.connect)

    def checked(conninfo, kwargs):
        if not allowed:
            raise PostgresGuardError("test tried to connect to PostgreSQL; mark it postgres")
        neutralize()  # again at connect time, in case the test itself set one
        options = {k: kwargs.pop(k) for k in PG_CONNECTION_OPTIONS if k in kwargs}
        return make_conninfo("", **pg_effective_params(conninfo, **kwargs)), options

    def connect(conninfo="", **kwargs):
        pinned, options = checked(conninfo, kwargs)
        return PG_REAL["sync"](pinned, **options)

    async def connect_async(conninfo="", **kwargs):
        pinned, options = checked(conninfo, kwargs)
        return await PG_REAL["async"](pinned, **options)

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(psycopg.Connection, "connect", staticmethod(connect))
    monkeypatch.setattr(psycopg.AsyncConnection, "connect", staticmethod(connect_async))


@pytest.fixture(autouse=True)
def _at_a_terminal(monkeypatch):
    """Tests of the interactive steps run as if at a terminal; pytest's stdin is
    not one. A test of an unattended run sets isatty to False itself."""
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)


@pytest.fixture(autouse=True)
def _own_cli_prefs(tmp_path, monkeypatch):
    """The CLI keeps the last run's selections in the user's home; tests keep theirs apart."""
    monkeypatch.setattr("cli.prefs._PREFS_PATH", tmp_path / "cli_prefs.json")


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY",
    "ZHIPU_CN_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        # `or` not a .get default: an env var present but empty (e.g. a key left
        # blank in a .env copied from .env.example) must still get the placeholder.
        monkeypatch.setenv(env_var, os.environ.get(env_var) or "placeholder")


@pytest.fixture(autouse=True)
def _isolate_config():
    """Reset the global dataflows config before and after each test.

    ``set_config`` merges (it never clears keys absent from the override), so a
    test that sets e.g. ``tool_vendors`` would otherwise leak into later tests
    and make routing behavior order-dependent. Replace the global outright so
    every test starts from a clean DEFAULT_CONFIG.
    """
    import copy

    import tradingagents.dataflows.config as config_module
    import tradingagents.default_config as default_config

    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
