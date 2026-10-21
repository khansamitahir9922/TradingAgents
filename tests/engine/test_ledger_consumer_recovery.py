"""M5-10: per-event consumer lock, atomic effect/mark and independent retries."""
import threading

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.events.consumer import Consumer
from tests.engine.test_consumers import effects, env as env, publish
from tests.engine.test_outbox import NOW, envelope

pytestmark = pytest.mark.postgres


def make_consumer(db):
    def effect(event):
        db.execute("INSERT INTO test_effects VALUES (:id,:a,:v)",
                   {"id": event.event_id, "a": event.aggregate_id, "v": event.aggregate_version})
    return Consumer(db, name="accounting-ledger", handles={"test.happened": effect},
                    clock=ReplayClock(NOW), serialize=True)


def test_two_accounting_consumers_have_one_effect_and_no_false_failure(env):
    publish(env, envelope("a", 1), envelope("a", 2))
    barrier = threading.Barrier(2)
    reports = []
    instances = [make_consumer(env.connect()) for _ in range(2)]

    def run(c):
        barrier.wait(timeout=20)
        reports.append(c.run_once())

    threads = [threading.Thread(target=run, args=(c,)) for c in instances]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()
    assert len(reports) == 2 and sum(r.failed for r in reports) == 0
    assert effects(env) == [("a", 1), ("a", 2)]
    assert env.db.fetchone("SELECT count(*) FROM consumer_failures")[0] == 0


@pytest.mark.parametrize("crash", ["before-effect", "before-mark"])
def test_accounting_effect_and_mark_roll_back_together(env, monkeypatch, crash):
    publish(env, envelope("a", 1))
    consumer = make_consumer(env.connect())
    original = consumer._db.execute

    def execute(sql, params=None):
        marker = "INSERT INTO test_effects" if crash == "before-effect" else "INSERT INTO processed_events"
        if sql.startswith(marker):
            raise KeyboardInterrupt("simulated consumer process death")
        return original(sql, params)

    monkeypatch.setattr(consumer._db, "execute", execute)
    with pytest.raises(KeyboardInterrupt):
        consumer.run_once()
    assert effects(env) == []
    monkeypatch.undo()
    assert consumer.run_once().applied == 1
    assert consumer.run_once().applied == 0
    assert effects(env) == [("a", 1)]


def test_accounting_dispatcher_refuses_an_outer_account_transaction(env):
    consumer = make_consumer(env.connect())
    with consumer._db.transaction(), pytest.raises(RuntimeError, match="outer transaction"):
        consumer.run_once()


@pytest.mark.parametrize("crash", ["before-journal", "before-mark", "after-commit"])
def test_actual_journal_restarts_with_one_posting_and_one_processed_fill(pg_database, monkeypatch, crash):
    from investment_engine.audit.events import AuditStore
    from investment_engine.events.outbox import Outbox
    from investment_engine.ledger.service import AccountingService, SourceSelector
    from investment_engine.ledger.sources import opening_bundle
    from investment_engine.ledger.store import LedgerStore
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
    from tests.engine.test_ledger_actions import CAL, coverage
    from tests.engine.test_ledger_time import accepted
    from tests.engine.test_order_store import OWNER, Env as LedgerEnv

    e = LedgerEnv(pg_database)
    try:
        audit = AuditStore(e.db)
        e.snapshots = PortfolioSnapshotStore(e.db, audit, e.accounts, e.clock)
        e.ledger = LedgerStore(e.db, audit=audit, outbox=Outbox(e.db, writer=ProcessRole.CORE, clock=e.clock),
                                clock=e.clock, command_clock=e.clock)
        state = e.snapshots.declare_start("R1", by=OWNER, reason="declared cash", effective_at=e.clock.now())
        initial = e.ledger.activate("R1", opening_lots=(), source_bundle=opening_bundle(state, at=e.clock.now()),
                                     by=OWNER, reason="explicit activation")
        order, fill = accepted(e, "BUY", "1", "10", executed=e.clock.now(), recorded=e.clock.now(), fee="0")
        selector = SourceSelector(e.db, clock=e.clock, command_clock=e.clock, calendar=CAL, provider="yfinance",
            coverage=lambda a, t: (coverage(t),), delivered_actions=lambda a, t: ())
        service = AccountingService(e.db, clock=e.clock, command_clock=e.clock, sources=selector)
        # RecordingOutbox is used by the old OMS fixture; copy its immutable
        # envelopes into the real transactional publisher for the process test.
        outbox = Outbox(e.db, writer=ProcessRole.EXECUTION, clock=e.clock)
        with e.db.transaction():
            for event in (*e.core_outbox.events, *e.worker_outbox.events):
                outbox.add(event)
        outbox.publish_pending(limit=1000)
        original = e.db.execute

        def execute(sql, params=None):
            if crash == "before-journal" and sql.startswith("INSERT INTO ledger_entries"):
                raise KeyboardInterrupt("before journal commit")
            if (crash == "before-mark" and sql.startswith("INSERT INTO processed_events") and
                    e.db.fetchone("SELECT count(*) FROM ledger_transactions")[0] > 1):
                raise KeyboardInterrupt("after journal effect, before processed mark")
            return original(sql, params)

        monkeypatch.setattr(e.db, "execute", execute)
        if crash == "after-commit":
            assert service.consumer.run_once().failed == 0
        else:
            with pytest.raises(KeyboardInterrupt):
                service.consumer.run_once()
            assert e.ledger.read_head("R1", known_at=e.clock.now()).book_id == initial.book_id
        monkeypatch.undo()
        assert service.consumer.run_once().failed == 0
        assert service.consumer.run_once().applied == 0
        head = e.ledger.read_head("R1", known_at=e.clock.now())
        assert len([tx for b in e.ledger.ancestry(head.book_id) for tx in b.transactions
                    if any(r.stored_record_id == fill.fill_id for r in tx.sources)]) == 1
        assert e.db.fetchone("SELECT count(*) FROM processed_events WHERE consumer='accounting-ledger' AND outcome='applied'")[0] == 1
        assert len(e.core.fills(order.order_id)) == 1
    finally:
        e.close()
