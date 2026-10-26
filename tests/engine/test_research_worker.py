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
from investment_engine.research.contracts import JobState, RunOutcome
from investment_engine.research.store import StaleJob
from investment_engine.research.worker import ResearchWorker
from investment_engine.research_cli import set_budget
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
    set_budget(e.db, operator="owner", reason="test policy", daily_requests=10, daily_tokens=10_000,
               reserve_requests=1, reserve_tokens=100, live_clock=e.clock)
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
    set_budget(env.db, operator="owner", reason="low", daily_requests=1, daily_tokens=50, reserve_requests=1,
               reserve_tokens=100, live_clock=env.clock)
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


WRITER_DOMAINS = ("investment_engine.execution", "investment_engine.killswitch", "investment_engine.ledger.store",
                  "investment_engine.ledger.service", "investment_engine.ledger.postings", "investment_engine.reconciliation",
                  "investment_engine.risk", "investment_engine.portfolio", "investment_engine.policy",
                  "investment_engine.oms.order_store", "investment_engine.oms.pipeline", "investment_engine.oms.conversion",
                  "investment_engine.oms.approvals", "investment_engine.oms.intent_store")


@pytest.mark.postgres
def test_a_constructed_worker_has_loaded_no_other_domains_writer_code(pg_database):
    import subprocess
    import sys

    code = (
        "import sys\n"
        "from datetime import UTC, datetime, timedelta\n"
        "from investment_engine.clock import ReplayClock\n"
        "from investment_engine.market.calendar.us_equities import load_us_equities_calendar\n"
        "from investment_engine.research.worker import ResearchWorker\n"
        "from investment_engine.storage.database import PostgresDatabase\n"
        "from investment_engine.storage.postgres import open_operational_pg\n"
        "from investment_engine.storage.postgres import apply_pg_schema\n"
        "conn = open_operational_pg(sys.stdin.readline().strip())\n"
        "apply_pg_schema(conn)\n"
        "w = ResearchWorker(PostgresDatabase(conn), worker_id='probe', clock=ReplayClock(datetime(2026, 1, 9, tzinfo=UTC)),\n"
        "                   port=object(), calendar=load_us_equities_calendar(), deadline=timedelta(minutes=1))\n"
        "w.store.claimable(at=datetime(2026, 1, 9, tzinfo=UTC))\n"
        "print('\\n'.join(sorted(sys.modules)))\n")
    done = subprocess.run([sys.executable, "-c", code], input=pg_database + "\n", capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-2000:]
    loaded = done.stdout.split()
    assert [m for m in loaded if any(m == d or m.startswith(d + ".") for d in WRITER_DOMAINS)] == []


class PartialPort(FakePort):
    """Makes one recorded call, then stalls: what was captured must survive abandonment."""

    def __init__(self, block):
        super().__init__(block=block)
        self.captured = ((), (), (), ())

    def run(self, job, *, attempt, clock):
        from investment_engine.research.contracts import CallRecord

        self.captured = ((CallRecord("c1", "Market Analyst", "gemini-quick-001", clock.now(), clock.now(), 5, 2,
                                     None),), (), (), ())
        return super().run(job, attempt=attempt, clock=clock)

    def partial(self):
        return self.captured


def test_an_abandoned_run_keeps_its_partial_capture(env):
    release = threading.Event()
    w = worker(env, PartialPort(release), deadline=timedelta(milliseconds=200))
    try:
        assert w.step().failed == 1
        final = env.store(ProcessRole.RESEARCH).current(job().job_id)
        rec = env.store(ProcessRole.RESEARCH).record(final.run_id)
        assert rec.usage.requests == 1 and len(rec.calls) == 1 and "partial capture" in " ".join(rec.warnings)
    finally:
        release.set()
        w.wait_for_stalled(timeout=5)


def test_an_uncaptured_run_is_shown_as_not_measured_never_zero(env):
    from investment_engine.research_cli import show_text

    release = threading.Event()
    w = worker(env, FakePort(block=release), deadline=timedelta(milliseconds=200))
    try:
        w.step()
        final = env.store(ProcessRole.RESEARCH).current(job().job_id)
        text = show_text(env.db, final.run_id)
        assert "NOT MEASURED" in text and "0 requests" not in text
    finally:
        release.set()
        w.wait_for_stalled(timeout=5)


def test_the_code_version_comes_from_the_packages_own_checkout(tmp_path, monkeypatch):
    import subprocess
    from pathlib import Path

    import investment_engine

    package = Path(investment_engine.__file__).parent
    head = subprocess.run(["git", "-C", str(package), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    monkeypatch.chdir(tmp_path)  # launched from an unrelated directory
    assert entry._code_version() == head
    assert entry._code_version(tmp_path) == "unversioned"  # not this package's checkout
