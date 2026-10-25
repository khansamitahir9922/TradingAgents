"""M6-02: append-only research evidence with process-role writers and CAS job versions."""
import threading
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.events.outbox import Outbox
from investment_engine.oms.order_states import ProcessRole
from investment_engine.research.contracts import (
    BudgetUsage,
    ContextSource,
    JobState,
    Rating,
    ResearchContext,
    RunOutcome,
    UntrustedLevels,
)
from investment_engine.research.store import ResearchStore, StaleJob
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.test_research_contracts import job, record

T = datetime(2026, 1, 9, 15, tzinfo=UTC)
LEASE = timedelta(minutes=30)
TRADER = Actor(ActorKind.OPERATOR, "op-trader", "TRADER", None)
pytestmark = pytest.mark.postgres


class Env:
    def __init__(self, dsn):
        self.conn = open_operational_pg(dsn)
        apply_pg_schema(self.conn)
        self.db = PostgresDatabase(self.conn)
        self.clock = ReplayClock(T)

    def store(self, role):
        audit = AuditStore(self.db)
        return ResearchStore(self.db, role=role, audit=audit,
                             outbox=Outbox(self.db, writer=role, clock=self.clock), clock=self.clock)

    def counts(self):
        return tuple(self.db.fetchone(f"SELECT count(*) FROM {t}")[0] for t in (
            "research_jobs", "research_job_versions", "research_records", "research_contexts",
            "research_budget_usage", "outbox"))


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    yield e
    e.conn.close()


def context_for(run_id):
    return ResearchContext(run_id, "EQ_US_NVDA", Rating.HOLD, None, UntrustedLevels(None, None), 5, T,
                           T + timedelta(days=7), (), ContextSource.TYPED)


def requested(env):
    core = env.store(ProcessRole.CORE)
    version = core.request(job(), by=TRADER)
    return core, env.store(ProcessRole.RESEARCH), version


def test_request_claim_and_succeed_atomically_with_one_event(env):
    core, worker, v1 = requested(env)
    assert (v1.version, v1.state) == (1, JobState.REQUESTED)
    assert worker.claimable(at=T) == (job().job_id,)
    claim = worker.claim(job().job_id, expected_version=1, worker_id="rw-1", lease=LEASE)
    assert (claim.version.state, claim.attempt) == (JobState.CLAIMED, 1)
    rec = record(attempt=1)
    assert claim.run_id == rec.run_id
    usage = BudgetUsage(date(2026, 1, 9), rec.run_id, "ACTUAL", 1, 13, None, T)
    done = worker.finish(job().job_id, expected_version=2, worker_id="rw-1", record=rec,
                         context=context_for(rec.run_id), usage=usage)
    assert done.state is JobState.SUCCEEDED
    assert worker.record(rec.run_id) == rec and worker.context(rec.run_id) == context_for(rec.run_id)
    assert worker.latest_context("EQ_US_NVDA", at=T) == context_for(rec.run_id)
    assert env.db.fetchone("SELECT count(*) FROM outbox WHERE writer='research-worker' "
                           "AND event_type='research.completed'")[0] == 1
    assert worker.claimable(at=T + timedelta(days=1)) == ()


def test_failure_at_each_finish_write_leaves_nothing(env, monkeypatch):
    core, worker, _ = requested(env)
    claim = worker.claim(job().job_id, expected_version=1, worker_id="rw-1", lease=LEASE)
    before = env.counts()
    original = env.db.execute
    for table in ("research_records", "research_contexts", "research_budget_usage", "research_job_versions", "outbox"):
        def fail(sql, params=None, _t=table):
            original(sql, params)
            if sql.startswith(f"INSERT INTO {_t} "):
                raise RuntimeError("injected")
        monkeypatch.setattr(env.db, "execute", fail)
        with pytest.raises(RuntimeError, match="injected"):
            worker.finish(job().job_id, expected_version=2, worker_id="rw-1", record=record(),
                          context=context_for(claim.run_id),
                          usage=BudgetUsage(date(2026, 1, 9), claim.run_id, "ACTUAL", 1, 1, None, T))
        monkeypatch.setattr(env.db, "execute", original)
        assert env.counts() == before


def test_two_workers_one_claim_and_stale_finisher_refused_after_reclaim(env, pg_database):
    core, worker, _ = requested(env)
    results = []

    def claim(name):
        e = Env.__new__(Env)
        e.conn = open_operational_pg(pg_database)
        try:
            e.db, e.clock = PostgresDatabase(e.conn), env.clock
            results.append(e.store(ProcessRole.RESEARCH).claim(job().job_id, expected_version=1, worker_id=name,
                                                               lease=LEASE))
        except StaleJob:
            results.append(None)
        finally:
            e.conn.close()

    threads = [threading.Thread(target=claim, args=(f"rw-{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r is None for r in results) == [False, True]
    first = next(r for r in results if r)
    with pytest.raises(StaleJob):  # the lease has not expired
        worker.claim(job().job_id, expected_version=2, worker_id="rw-9", lease=LEASE)
    env.clock.advance_by(LEASE)
    assert worker.claimable(at=env.clock.now()) == (job().job_id,)
    second = worker.claim(job().job_id, expected_version=2, worker_id="rw-9", lease=LEASE)
    assert second.attempt == 2 and second.run_id != first.run_id
    with pytest.raises(StaleJob):  # the crashed first attempt cannot finish now
        worker.finish(job().job_id, expected_version=2, worker_id=first.version.actor,
                      record=record(attempt=1, outcome=RunOutcome.FAILED, failure="late"), context=None, usage=None)
    env.clock.advance_by(LEASE)
    assert worker.claimable(at=env.clock.now()) == ()  # at most one re-claim


@pytest.mark.parametrize("sql", [
    "UPDATE research_jobs SET content=content", "DELETE FROM research_job_versions", "TRUNCATE research_records CASCADE",
    "INSERT INTO research_jobs SELECT * FROM research_jobs ON CONFLICT (job_id) DO UPDATE SET content='x'",
])
def test_sql_cannot_rewrite_research_history(env, sql):
    requested(env)
    with pytest.raises(Exception, match="append-only"), env.conn.transaction():
        env.conn.execute("SELECT set_config('investment_engine.process_role','core-engine',true)")
        env.conn.execute(sql)


def test_wrong_role_writes_are_refused_by_api_and_sql(env):
    core, worker, _ = requested(env)
    with pytest.raises(PermissionError):
        core.claim(job().job_id, expected_version=1, worker_id="core", lease=LEASE)
    with pytest.raises(PermissionError):
        worker.request(job(requested_at=T + timedelta(seconds=1)), by=TRADER)
    with pytest.raises(Exception, match="only the research-worker"), env.conn.transaction():
        env.conn.execute("SELECT set_config('investment_engine.process_role','core-engine',true)")
        env.conn.execute("INSERT INTO research_job_versions VALUES (%s,2,'CLAIMED',%s,'x',%s,'r','{}')",
                         (job().job_id, T, T + LEASE))
    with pytest.raises(Exception, match="edge/sequence"), env.conn.transaction():
        env.conn.execute("SELECT set_config('investment_engine.process_role','research-worker',true)")
        env.conn.execute("INSERT INTO research_job_versions VALUES (%s,2,'SUCCEEDED',%s,'x',NULL,'r','{}')",
                         (job().job_id, T))


def test_succeeded_needs_its_context_and_failed_has_none(env):
    core, worker, _ = requested(env)
    claim = worker.claim(job().job_id, expected_version=1, worker_id="rw-1", lease=LEASE)
    with pytest.raises(ValueError):
        worker.finish(job().job_id, expected_version=2, worker_id="rw-1", record=record(), context=None, usage=None)
    failed = record(outcome=RunOutcome.FAILED, failure="provider 429")
    with pytest.raises(ValueError):
        worker.finish(job().job_id, expected_version=2, worker_id="rw-1", record=failed,
                      context=context_for(claim.run_id), usage=None)
    assert worker.finish(job().job_id, expected_version=2, worker_id="rw-1", record=failed, context=None,
                         usage=None).state is JobState.FAILED
    assert worker.latest_context("EQ_US_NVDA", at=T + timedelta(days=1)) is None


def test_request_is_idempotent_and_a_record_for_another_job_is_refused(env):
    core, worker, v1 = requested(env)
    assert core.request(job(), by=TRADER) == v1
    worker.claim(job().job_id, expected_version=1, worker_id="rw-1", lease=LEASE)
    with pytest.raises(ValueError):
        worker.finish(job().job_id, expected_version=2, worker_id="rw-1",
                      record=replace(record(), job_id="rjb-other"), context=None, usage=None)


def test_upgrade_from_populated_0020_keeps_rows(pg_database, monkeypatch):
    from investment_engine.storage import postgres as pg

    scripts = pg._pg_schema_scripts()
    monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: [(n, s) for n, s in scripts if n <= 20])
    conn = open_operational_pg(pg_database)
    try:
        assert pg.apply_pg_schema(conn) == 20
        db = PostgresDatabase(conn)
        with db.transaction():
            db.execute("INSERT INTO accounts VALUES ('R1','RESEARCH','USD',:t,:t)", {"t": T})
        before = db.fetchall("SELECT * FROM accounts ORDER BY 1")
        monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: scripts)
        assert pg.apply_pg_schema(conn) == 21
        assert db.fetchall("SELECT * FROM accounts ORDER BY 1") == before
    finally:
        conn.close()
