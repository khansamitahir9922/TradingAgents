"""M6-10: research is advisory and isolated. Its presence, absence or crash changes no execution or accounting."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from investment_engine.audit.events import AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.events.outbox import Outbox
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.oms.order_states import ProcessRole
from investment_engine.reporting.research_view import latest_evidence
from investment_engine.research.contracts import (
    BudgetPolicy,
    ContextSource,
    JobState,
    Rating,
    ResearchContext,
    UntrustedLevels,
)
from investment_engine.research.store import ResearchStore
from investment_engine.research.worker import ResearchWorker
from investment_engine.storage.database import PostgresDatabase
from tests.engine import process_harness
from tests.engine.test_research_contracts import job, record
from tests.engine.test_research_store import TRADER, Env
from tests.engine.test_research_worker import FakePort

pytestmark = pytest.mark.postgres
RESEARCH_AT = datetime(2024, 5, 28, 14, tzinfo=UTC)  # inside the synthetic M5 run's window


def _store(db, role, clock):
    return ResearchStore(db, role=role, audit=AuditStore(db), outbox=Outbox(db, writer=role, clock=clock),
                         clock=clock)


def seed_research(db):
    """A succeeded bullish-looking context, an unclaimed request and a crashed claim: every research state."""
    clock = ReplayClock(RESEARCH_AT)
    core, worker = _store(db, ProcessRole.CORE, clock), _store(db, ProcessRole.RESEARCH, clock)
    with db.transaction():
        db.execute("SELECT set_config('investment_engine.process_role','core-engine',true)")
        core.set_policy(BudgetPolicy(1, 3, 300_000, None, 1, 100_000, "owner", RESEARCH_AT, "isolation test"))
    done = job(requested_at=RESEARCH_AT)
    core.request(done, by=TRADER)
    claim = worker.claim(done.job_id, expected_version=1, worker_id="rw-1", lease=timedelta(minutes=30))
    ctx = ResearchContext(claim.run_id, "EQ_US_NVDA", Rating.BUY, None, UntrustedLevels(None, None), 5, RESEARCH_AT,
                          RESEARCH_AT + timedelta(days=30), (), ContextSource.TYPED)
    worker.finish(done.job_id, expected_version=2, worker_id="rw-1",
                  record=replace(record(), job_id=done.job_id, started_at=RESEARCH_AT, finished_at=RESEARCH_AT),
                  context=ctx, usage=None)
    core.request(job(requested_at=RESEARCH_AT + timedelta(seconds=1)), by=TRADER)
    crashed = job(requested_at=RESEARCH_AT + timedelta(seconds=2))
    core.request(crashed, by=TRADER)
    clock.advance_by(timedelta(seconds=2))
    worker.claim(crashed.job_id, expected_version=1, worker_id="rw-dead", lease=timedelta(minutes=30))
    return ctx


def test_execution_and_accounting_are_identical_with_or_without_research_and_never_read_it(tmp_path, monkeypatch):
    from tests.engine.conftest import maintenance_dsn, temporary_database
    from tests.engine.test_m5_accounting_demo import Demo

    outputs, statements = [], []
    for n, with_research in enumerate((False, True)):
        with temporary_database(maintenance_dsn()) as dsn:
            demo = Demo(dsn, tmp_path / str(n))
            try:
                if with_research:
                    seed_research(demo.env.stores.db)
                    real = PostgresDatabase._run

                    def capture(self, sql, params, _real=real):
                        statements.append(sql)
                        return _real(self, sql, params)

                    monkeypatch.setattr(PostgresDatabase, "_run", capture)
                result, payload = demo.run()
                monkeypatch.undo()
                outputs.append((result.accounting_json, result.proposals, result.orders, result.stops))
            finally:
                demo.close()
    assert outputs[0] == outputs[1]  # byte-identical economic record and identical order outcomes
    assert statements and not [s for s in statements if "research" in s.lower()]


def test_the_research_role_cannot_write_any_order_table(pg_database):
    env = Env(pg_database)
    try:
        for sql in ("INSERT INTO orders (order_id) VALUES ('x')", "INSERT INTO fills (fill_id) VALUES ('x')",
                    "INSERT INTO gate_decisions (order_id) VALUES ('x')",
                    "INSERT INTO cancel_requests (order_id) VALUES ('x')"):
            with pytest.raises(Exception, match="no valid process role|written only by|violates not-null"), \
                    env.conn.transaction():
                env.conn.execute("SELECT set_config('investment_engine.process_role','research-worker',true)")
                env.conn.execute(sql)
    finally:
        env.conn.close()


def test_a_hard_killed_research_process_is_reclaimed_once_without_a_duplicate(pg_database, tmp_path):
    env = Env(pg_database)
    try:
        at = datetime(2026, 1, 9, 15, tzinfo=UTC)
        core = env.store(ProcessRole.CORE)
        with env.db.transaction():
            env.db.execute("SELECT set_config('investment_engine.process_role','core-engine',true)")
            core.set_policy(BudgetPolicy(1, 3, 300_000, None, 1, 100_000, "owner", at, "kill test"))
        core.request(job(), by=TRADER)
        killed = process_harness.run({"role": "research", "at": at.isoformat(), "fault": "research_mid_run"},
                                     dsn=pg_database, tmp=tmp_path)
        assert killed is None  # really killed at its fault point
        versions = env.store(ProcessRole.RESEARCH).versions(job().job_id)
        assert [v.state for v in versions] == [JobState.REQUESTED, JobState.CLAIMED]  # the crash left its claim
        assert env.db.fetchone("SELECT count(*) FROM research_records")[0] == 0
        env.clock.advance_by(timedelta(minutes=16))  # past the child's lease (10 min deadline + 5 min margin)
        report = ResearchWorker(env.db, worker_id="rw-restart", clock=env.clock, port=FakePort(),
                                calendar=load_us_equities_calendar(), deadline=timedelta(minutes=10)).step()
        assert report.succeeded == 1
        final = env.store(ProcessRole.RESEARCH).versions(job().job_id)
        assert [v.state for v in final] == [JobState.REQUESTED, JobState.CLAIMED, JobState.CLAIMED,
                                            JobState.SUCCEEDED]
        assert final[1].actor == "research-child" and final[1].run_id != final[3].run_id  # the crash stays visible
        assert env.db.fetchone("SELECT count(*) FROM research_contexts")[0] == 1
    finally:
        env.conn.close()


def test_every_displayed_item_resolves_to_its_record_settings_and_code_version(pg_database):
    env = Env(pg_database)
    try:
        ctx = seed_research(env.db)
        evidence = latest_evidence(env.db, "EQ_US_NVDA", at=RESEARCH_AT + timedelta(days=1))
        assert evidence.context == ctx and evidence.record.run_id == ctx.run_id
        assert evidence.record.settings.quick_model and evidence.record.code_version
        job_id = evidence.record.job_id
        assert env.store(ProcessRole.CORE).job(job_id).settings == evidence.record.settings
    finally:
        env.conn.close()
