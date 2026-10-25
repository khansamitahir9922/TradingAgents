"""M6-08: operator entry points for research, with roles, reasons and read-only views."""
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest
from typer.testing import CliRunner

from investment_engine import research_cli as cli
from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.cli import app
from investment_engine.clock import ReplayClock
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.symbols import SymbolMapping
from investment_engine.oms.order_states import ProcessRole
from investment_engine.policy.accounts import AccountRegistry, NotAuthorized, Role
from investment_engine.research.contracts import JobState
from investment_engine.storage.sqlite import SqliteInstrumentRepository, SqliteSymbolResolver
from tests.engine.test_research_store import Env

T = datetime(2026, 1, 9, 15, tzinfo=UTC)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "test")
NVDA = Instrument("EQ_US_NVDA", AssetClass.EQUITY, "USD", "XNAS", "America/New_York", InstrumentStatus.ACTIVE,
                  date(2019, 1, 1), None)
SETTINGS = {"provider": "google", "quick_model": "gemini-quick-001", "deep_model": "gemini-deep-001"}
runner = CliRunner()


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    e.accounts = AccountRegistry(e.db, AuditStore(e.db), e.clock)
    e.accounts.bootstrap_admin("owner", os_user="test")
    for role in (Role.TRADER, Role.VIEWER):
        e.accounts.add_operator(role.value.lower(), role, by=OWNER, reason="test operator")
    SqliteInstrumentRepository(e.db).add(NVDA)
    SqliteSymbolResolver(e.db).add(SymbolMapping("EQ_US_NVDA", "yfinance", "NVDA", date(2019, 1, 1), None))
    yield e
    e.conn.close()


def request(env, operator, **kw):
    return cli.request_research(env.db, instrument_id="EQ_US_NVDA", operator=operator, reason="check the thesis",
                                live_clock=ReplayClock(T), **SETTINGS, **kw)


@pytest.mark.postgres
@pytest.mark.parametrize("operator", ["trader", "owner"])
def test_a_trader_or_admin_requests_research_for_today(env, operator):
    version = request(env, operator)
    assert version.state is JobState.REQUESTED
    job = env.store(ProcessRole.CORE).job(version.job_id)
    assert (job.ticker, job.research_date, job.requested_by) == ("NVDA", date(2026, 1, 9), operator)
    assert job.settings.quick_model == "gemini-quick-001" and job.settings.max_debate_rounds == 1


@pytest.mark.postgres
def test_a_viewer_cannot_request(env):
    with pytest.raises(NotAuthorized):
        request(env, "viewer")
    assert env.db.fetchone("SELECT count(*) FROM research_jobs")[0] == 0


@pytest.mark.postgres
def test_a_historical_date_is_refused(env):
    with pytest.raises(ValueError, match="current exchange date"):
        request(env, "trader", research_date=date(2026, 1, 8))
    assert request(env, "trader", research_date=date(2026, 1, 9)).state is JobState.REQUESTED


@pytest.mark.postgres
@pytest.mark.parametrize("operator,allowed", [("owner", True), ("trader", False), ("viewer", False)])
def test_only_an_admin_sets_the_budget(env, operator, allowed):
    def call():
        return cli.set_budget(env.db, operator=operator, reason="provisional D46", daily_requests=3,
                              daily_tokens=300_000, reserve_requests=1, reserve_tokens=100_000, live_clock=ReplayClock(T))

    if allowed:
        assert call().version == 1
    else:
        with pytest.raises(NotAuthorized):
            call()


@pytest.mark.postgres
def test_read_views_change_nothing(env):
    version = request(env, "trader")
    before = env.counts()
    assert "REQUESTED" in cli.status_text(env.db, version.job_id)
    assert "No budget policy" in cli.budget_text(env.db, day=date(2026, 1, 9))
    assert env.counts() == before


def test_read_commands_open_read_only_connections(monkeypatch):
    observed = []

    class Connection:
        def close(self):
            observed.append("closed")

    monkeypatch.setattr("investment_engine.cli._open_db", lambda *, read_only: (observed.append(read_only), (
        Connection(), object()))[1])
    monkeypatch.setattr(cli, "status_text", lambda db, job_id: "STATUS")
    monkeypatch.setattr(cli, "budget_text", lambda db, *, day: "BUDGET")
    for args in (["research", "status", "rjb-x"], ["research", "budget", "show"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
    assert observed == [True, "closed", True, "closed"]


def test_the_research_group_is_registered_and_never_loads_tradingagents():
    assert runner.invoke(app, ["research", "--help"]).exit_code == 0
    code = ("import sys, investment_engine.cli, investment_engine.research_cli; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('tradingagents', 'langchain_core', 'langgraph')"
            " or m.startswith('investment_engine.research.adapter')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
