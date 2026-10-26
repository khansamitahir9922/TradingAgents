"""M6-07: the Research Worker claims, runs within budget and deadline, saves atomically, recovers."""
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.oms.order_states import ProcessRole
from investment_engine.policy.accounts import AccountRegistry
from investment_engine.research import __main__ as entry
from investment_engine.research.adapter import RunOutput
from investment_engine.research.budget import ResearchBudget
from investment_engine.research.contracts import JobState, RunOutcome
from investment_engine.research.store import StaleJob
from investment_engine.research.worker import ResearchWorker
from tests.engine.test_research_contracts import job, record
from tests.engine.test_research_store import TRADER, Env

T = datetime(2026, 1, 9, 15, tzinfo=UTC)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "test")
CAL = load_us_equities_calendar()
pytestmark = pytest.mark.postgres

STATE = {"final_rating": "Hold", "final_decision_structured": {"rating": "Hold", "executive_summary": "s",
                                                               "investment_thesis": "t"},
         "trader_proposal_structured": None}


class FakePort:
    """Stands in for the adapter: returns a successful run, or blocks until released."""

    def __init__(self, state=STATE, block: threading.Event | None = None):
        self.state, self.block, self.runs = state, block, []

    def run(self, job, *, attempt, clock):
        self.runs.append(attempt)
        if self.block is not None:
            self.block.wait(30)
        rec = replace(record(), job_id=job.job_id, attempt=attempt, started_at=clock.now(), finished_at=clock.now())
        return RunOutput(rec, dict(self.state))


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    e.accounts = AccountRegistry(e.db, AuditStore(e.db), e.clock)
    e.accounts.bootstrap_admin("owner", os_user="test")
    ResearchBudget(e.store(ProcessRole.CORE), accounts=e.accounts, clock=e.clock, command_clock=e.clock).set_policy(
        daily_requests=10, daily_tokens=10_000, daily_usd=None, reserve_requests=1, reserve_tokens=100,
        by=OWNER, reason="test policy")
    e.store(ProcessRole.CORE).request(job(), by=TRADER)
    yield e
    e.conn.close()


def worker(env, port, **kw):
    kw.setdefault("deadline", timedelta(seconds=5))
    return ResearchWorker(env.db, worker_id=kw.pop("worker_id", "rw-1"), clock=env.clock, port=port, calendar=CAL,
                          **kw)


def test_a_requested_job_is_run_saved_and_published(env):
    report = worker(env, FakePort()).step()
    assert (report.claimed, report.succeeded, report.failed) == (1, 1, 0)
    store = env.store(ProcessRole.RESEARCH)
    final = store.current(job().job_id)
    assert final.state is JobState.SUCCEEDED
    assert store.context(final.run_id).rating.value == "Hold"
    assert env.db.fetchone("SELECT count(*) FROM event_log WHERE event_type='research.completed'")[0] == 1
    assert {u.kind for u in store.usage_on(T.date())} == {"RESERVED", "ACTUAL"}
    assert worker(env, FakePort()).step().claimed == 0  # nothing left to do


def test_budget_refusal_is_recorded_without_running(env):
    ResearchBudget(env.store(ProcessRole.CORE), accounts=env.accounts, clock=env.clock,
                   command_clock=env.clock).set_policy(daily_requests=1, daily_tokens=50, daily_usd=None,
                                                       reserve_requests=1, reserve_tokens=100, by=OWNER, reason="low")
    port = FakePort()
    report = worker(env, port).step()
    assert report.refused == 1 and port.runs == []
    current = env.store(ProcessRole.RESEARCH).current(job().job_id)
    assert current.state is JobState.BUDGET_REFUSED and "tokens 0 + 100 > 50" in current.reason


def test_no_rating_is_a_failed_run_with_its_record_and_no_context(env):
    report = worker(env, FakePort(state={"final_rating": "REVIEW", "final_decision_structured": None})).step()
    assert report.failed == 1
    store = env.store(ProcessRole.RESEARCH)
    final = store.current(job().job_id)
    assert final.state is JobState.FAILED and "no rating" in final.reason
    assert store.record(final.run_id).outcome is RunOutcome.FAILED
    assert store.latest_context("EQ_US_NVDA", at=T + timedelta(days=1)) is None


def test_a_run_past_its_deadline_fails_and_the_stalled_worker_starts_nothing_new(env):
    release = threading.Event()
    port = FakePort(block=release)
    w = worker(env, port, deadline=timedelta(milliseconds=200))
    report = w.step()
    assert report.failed == 1 and w.stalled()
    final = env.store(ProcessRole.RESEARCH).current(job().job_id)
    assert final.state is JobState.FAILED and "deadline" in final.reason
    env.store(ProcessRole.CORE).request(job(requested_at=T + timedelta(minutes=1)), by=TRADER)
    assert w.step().claimed == 0  # stalled: the stuck call has not returned
    release.set()
    w.wait_for_stalled(timeout=5)
    env.clock.advance_by(timedelta(minutes=1))  # the worker's clock reaches the second request
    assert not w.stalled() and w.step().claimed == 1


def test_a_crashed_claim_expires_is_reclaimed_once_and_the_late_finisher_is_refused(env):
    store = env.store(ProcessRole.RESEARCH)
    crashed = store.claim(job().job_id, expected_version=1, worker_id="rw-dead", lease=timedelta(minutes=10))
    assert worker(env, FakePort()).step().claimed == 0  # leased to the crashed worker
    env.clock.advance_by(timedelta(minutes=10))
    report = worker(env, FakePort(), worker_id="rw-2").step()
    assert report.succeeded == 1
    final = store.current(job().job_id)
    assert final.run_id != crashed.run_id and store.record(final.run_id).attempt == 2
    with pytest.raises(StaleJob):
        store.finish(job().job_id, expected_version=2, worker_id="rw-dead",
                     record=replace(record(attempt=1, outcome=RunOutcome.FAILED, failure="late"), job_id=job().job_id),
                     context=None, usage=None)
    assert env.db.fetchone("SELECT count(*) FROM research_contexts")[0] == 1


def test_the_lease_covers_the_whole_bounded_run(env):
    w = worker(env, FakePort(), deadline=timedelta(minutes=20))
    w.step()
    claimed = next(v for v in env.store(ProcessRole.RESEARCH).versions(job().job_id) if v.state is JobState.CLAIMED)
    assert claimed.lease_until - claimed.at > timedelta(minutes=20)


# ------------------------------------------------------------------ entry-point startup checks (D48)

@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    for name in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ALPACA_API_KEY_ID"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "secrets").mkdir()
    return tmp_path


def test_startup_refuses_without_its_own_secrets_file(paths, capsys):
    assert entry.main(["run", "--once"]) == 2
    assert "research_worker.env" in capsys.readouterr().out


def test_startup_refuses_an_ambient_llm_key_without_printing_it(paths, monkeypatch, capsys):
    (paths / "secrets" / "research_worker.env").write_text("GOOGLE_API_KEY=file-value-123\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_API_KEY", "ambient-value-456")
    assert entry.main(["run", "--once"]) == 2
    out = capsys.readouterr().out
    assert "GOOGLE_API_KEY" in out and "ambient-value-456" not in out and "file-value-123" not in out


@pytest.mark.parametrize("hazard", ["broker-variable", "execution-secrets-file"])
def test_startup_refuses_visible_broker_credentials(paths, monkeypatch, capsys, hazard):
    (paths / "secrets" / "research_worker.env").write_text("GOOGLE_API_KEY=file-value-123\n", encoding="utf-8")
    if hazard == "broker-variable":
        monkeypatch.setenv("ALPACA_API_KEY_ID", "broker-value-789")
    else:
        (paths / "secrets" / "execution_worker.env").write_text("BROKER_KEY=x\n", encoding="utf-8")
    assert entry.main(["run", "--once"]) == 2
    out = capsys.readouterr().out
    assert "broker" in out.lower() and "broker-value-789" not in out


def test_a_lost_connection_reaches_the_reconnect_and_the_loop_resumes(env):
    import psycopg

    from investment_engine.research.worker import ResearchWorker as RW

    calls = {"steps": 0, "rebuilt": 0}
    first = worker(env, FakePort())

    def broken_step():
        calls["steps"] += 1
        raise psycopg.OperationalError("server closed the connection")

    first.step = broken_step
    rebuilt = worker(env, FakePort(), worker_id="rw-rebuilt")

    def reconnect():
        calls["rebuilt"] += 1
        return rebuilt

    real_step = rebuilt.step
    done = []
    rebuilt.step = lambda: done.append(real_step())
    result = RW.run(first, poll_seconds=Decimal("0"), stop=lambda: bool(done), reconnect=reconnect)
    assert calls == {"steps": 1, "rebuilt": 1} and result is rebuilt
    assert env.store(ProcessRole.RESEARCH).current(job().job_id).state is JobState.SUCCEEDED


def test_without_reconnect_a_lost_connection_is_raised_typed(env):
    import psycopg

    w = worker(env, FakePort())
    w.step = lambda: (_ for _ in ()).throw(psycopg.OperationalError("gone"))
    with pytest.raises(psycopg.OperationalError):
        w.run(poll_seconds=Decimal("0"), stop=lambda: False)


@pytest.mark.parametrize("name", ["TYPESAFE_API_KEY", "TRADINGAGENTS_DEEP_THINK_PROVIDER", "GOOGLE_GENAI_USE_VERTEXAI",
                                  "GOOGLE_CLOUD_PROJECT"])
def test_startup_refuses_ambient_switches_that_change_upstream_providers(paths, monkeypatch, capsys, name):
    (paths / "secrets" / "research_worker.env").write_text("GOOGLE_API_KEY=file-value-123\n", encoding="utf-8")
    monkeypatch.setenv(name, "ambient-switch-555")
    assert entry.main(["run", "--once"]) == 2
    out = capsys.readouterr().out
    assert name in out and "ambient-switch-555" not in out and "file-value-123" not in out


def _slow_reservation(monkeypatch, env, delay, during=None):
    """The budget-day lock wait takes `delay` on the worker's clock; `during` runs while it waits."""
    from investment_engine.research.budget import ResearchBudget as RB

    real = RB.reserve

    def slow(self, run_id):
        env.clock.advance_by(delay)
        if during is not None:
            during()
        return real(self, run_id)

    monkeypatch.setattr(RB, "reserve", slow)


def test_a_run_that_could_outlive_its_lease_is_never_started(env, monkeypatch):
    port = FakePort()
    _slow_reservation(monkeypatch, env, timedelta(minutes=6))  # lease = deadline + 5 min
    report = worker(env, port, deadline=timedelta(minutes=30)).step()
    assert port.runs == [] and report.failed == 1
    final = env.store(ProcessRole.RESEARCH).current(job().job_id)
    assert final.state is JobState.FAILED and "lease" in final.reason and "not started" in final.reason


def test_a_worker_whose_claim_was_taken_starts_nothing_and_writes_nothing(env, monkeypatch):
    port = FakePort()

    def taken():  # the lease expires while A waits; B re-claims
        env.clock.advance_by(timedelta(minutes=40))
        env.store(ProcessRole.RESEARCH).claim(job().job_id, expected_version=2, worker_id="rw-B",
                                              lease=timedelta(minutes=35))

    _slow_reservation(monkeypatch, env, timedelta(0), during=taken)
    report = worker(env, port, worker_id="rw-A", deadline=timedelta(minutes=30)).step()
    assert port.runs == [] and report.claimed == 1 and report.succeeded == report.failed == 0
    current = env.store(ProcessRole.RESEARCH).current(job().job_id)
    assert (current.state, current.actor) == (JobState.CLAIMED, "rw-B")
