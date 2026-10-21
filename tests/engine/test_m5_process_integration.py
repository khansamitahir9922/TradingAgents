"""M5-10: Core/worker accounting uses independent connections and public evidence."""
from decimal import Decimal

import pytest

from investment_engine.core.engine import CoreEngine
from investment_engine.execution.simulated_broker import FeeSchedule, SimulatedBroker
from investment_engine.execution.worker import ExecutionWorker
from investment_engine.ledger.service import AccountingService, SourceSelector
from investment_engine.oms.pipeline import ControlStores
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import open_operational_pg
from investment_engine.storage.sqlite import SqliteInstrumentRepository
from tests.engine.test_reconciliation_incidents import OWNER, Env, T
from tests.engine.test_simulated_broker import CAL, Knowledge

pytestmark = pytest.mark.postgres


@pytest.fixture
def setup(pg_database):
    env = Env(pg_database)
    from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
    from investment_engine.reconciliation.snapshots import BrokerSetupStore
    BrokerSetupStore(env.db, audit=env.audit, accounts=env.accounts,
                     states=PortfolioSnapshotStore(env.db, env.audit, env.accounts, env.live),
                     command_clock=env.live).request("R1", source="yfinance", coverage_evidence=(), by=OWNER,
                                                   reason="approved simulated setup")
    connections = []
    def db():
        conn = open_operational_pg(pg_database)
        connections.append(conn)
        return PostgresDatabase(conn)
    worker_db, broker_db = db(), db()
    broker = SimulatedBroker(broker_db, knowledge=Knowledge(), calendar=CAL, source="yfinance",
                             fees=FeeSchedule("test", Decimal(0), Decimal(5)), account_id="R1")
    worker = ExecutionWorker(worker_db, clock=env.clock, broker=broker, accounts=frozenset({"R1"}))
    selector = SourceSelector(env.db, clock=env.clock, command_clock=env.live, calendar=CAL,
                              provider="yfinance", coverage=(), delivered_actions=lambda a, t: ())
    service = AccountingService(env.db, clock=env.clock, command_clock=env.live, sources=selector)
    stores = ControlStores.open(env.db, env.live, instruments=SqliteInstrumentRepository(env.db))
    engine = CoreEngine(stores, clock=env.clock, accounting=service)
    yield env, worker, service, engine, db
    for conn in connections:
        conn.close()
    env.conn.close()


def test_zero_orders_converge_at_one_replay_instant_and_repeat_has_no_new_accounting_rows(setup):
    env, worker, service, engine, _ = setup
    assert not service.ready("R1", T).ready
    worker.step()
    engine.publish_and_consume()
    engine.sync_accounting("R1", at=T)
    assert service.ready("R1", T).ready
    before = tuple(env.db.fetchone("SELECT count(*) FROM " + table)[0] for table in
                   ("broker_snapshots", "ledger_batches", "reconciliation_results", "reconciliation_incidents"))
    worker.step()
    engine.publish_and_consume()
    engine.sync_accounting("R1", at=T)
    assert tuple(env.db.fetchone("SELECT count(*) FROM " + table)[0] for table in
                 ("broker_snapshots", "ledger_batches", "reconciliation_results", "reconciliation_incidents")) == before
    assert service.projection("R1", T).cash == Decimal(100)


def test_activated_account_with_missing_source_service_has_no_provisional_fallback(setup):
    _, _, service, _, _ = setup
    from investment_engine.portfolio.reference import Unavailable
    assert isinstance(service.projection("R1", T), Unavailable)


def test_expected_accounting_gap_does_not_poison_a_gate_transaction(setup, monkeypatch):
    env, worker, service, engine, _ = setup
    from investment_engine.ledger.contracts import AccountingUnavailable
    from investment_engine.portfolio.reference import Unavailable
    worker.step()
    engine.sync_accounting("R1", at=T)
    assert service.ready("R1", T).ready
    def missing(*args, **kwargs):
        raise AccountingUnavailable("R1", T, ("required source unavailable",))
    monkeypatch.setattr(service, "current", missing)
    with env.db.transaction():
        env.db.lock("account-control|R1")
        assert isinstance(service.projection("R1", T), Unavailable)
        assert env.db.fetchone("SELECT 1")[0] == 1


def test_new_unmapped_message_invalidates_an_earlier_complete_prefix_at_same_time(setup, monkeypatch):
    from investment_engine.execution.broker_port import BrokerMessage
    _, worker, service, engine, _ = setup
    worker.step()
    engine.sync_accounting("R1", at=T)
    assert service.ready("R1", T).ready
    message = BrokerMessage("unmapped-message", "unmapped-client", "ACK", T, None, "source cannot be mapped")
    monkeypatch.setattr(worker.broker, "messages", lambda **kwargs: [message])
    worker.step()
    engine.sync_accounting("R1", at=T)
    assert not service.ready("R1", T).ready
    assert service.incidents.latest("R1").status == "INCOMPLETE"


@pytest.mark.parametrize("error", ["ordinary", "lost"])
def test_worker_snapshot_failure_is_bounded_and_connection_loss_keeps_type(setup, monkeypatch, error):
    import psycopg
    env, worker, _, _, _ = setup
    def fail(*args, **kwargs):
        if error == "lost":
            raise psycopg.OperationalError("test connection lost")
        raise RuntimeError("vendor failure")
    monkeypatch.setattr(worker.broker, "snapshot", fail)
    if error == "lost":
        with pytest.raises(psycopg.OperationalError):
            worker.step()
    else:
        worker.step()
    assert env.db.fetchone("SELECT count(*) FROM broker_snapshots")[0] == 0


def test_direct_order_writes_take_account_lock_before_reading_reservations(pg_database, monkeypatch):
    from tests.engine.test_order_store import Env as OrderEnv
    env = OrderEnv(pg_database)
    order = env.order()
    locked = []
    original = env.core._db.lock
    def lock(*names):
        locked.extend(names)
        original(*names)
    monkeypatch.setattr(env.core._db, "lock", lock)
    try:
        env.core.create(order, by=OWNER, correlation_id="lock-probe")
        assert "account-control|R1" in locked
    finally:
        env.close()


def test_offline_harness_posts_real_fill_and_reconciles_without_advancing_time_for_readiness(pg_database, tmp_path, monkeypatch):
    from investment_engine.clock import ReplayClock
    from investment_engine.events.outbox import Outbox
    from investment_engine.ledger.sources import opening_bundle
    from investment_engine.ledger.store import LedgerStore
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.portfolio.reference import StoreKnowledge
    from investment_engine.reconciliation.snapshots import BrokerSetupStore
    from investment_engine.simulation.run import simulate
    from tests.engine.test_ledger_actions import coverage
    from tests.engine.test_simulated_run import Run

    outcomes = []
    original_submit = ExecutionWorker.submit
    def submit(worker, order_id):
        outcome = original_submit(worker, order_id)
        outcomes.append(outcome)
        return outcome
    monkeypatch.setattr(ExecutionWorker, "submit", submit)
    run = Run(pg_database, tmp_path)
    try:
        stores = run.env.stores
        at = run.views[0].generated_at
        clock = ReplayClock(at)
        ledger = LedgerStore(stores.db, audit=stores.audit,
            outbox=Outbox(stores.db, writer=ProcessRole.CORE, clock=clock), clock=clock,
            command_clock=run.env.clock)
        ledger.activate("R2", opening_lots=(), source_bundle=opening_bundle(stores.snapshots.starting_state("R2"), at=at),
                          by=OWNER, reason="explicit M5 research activation")
        cov = coverage(at)
        BrokerSetupStore(stores.db, audit=stores.audit, accounts=stores.accounts, states=stores.snapshots,
                         command_clock=run.env.clock).request("R2", source="yfinance", coverage_evidence=cov.evidence_refs,
                                                               by=OWNER, reason="independent simulated seed")

        def factory(db, replay_clock):
            selector = SourceSelector(db, clock=replay_clock, command_clock=run.env.clock, calendar=CAL,
                provider="yfinance", coverage=lambda a, t: (coverage(t),), delivered_actions=lambda a, t: (), market_root=run.env.root)
            return AccountingService(db, clock=replay_clock, command_clock=run.env.clock, sources=selector)

        report = simulate("R2", views=run.views[:1], open_db=run.open_db, knowledge=StoreKnowledge(run.env.reader, CAL),
            calendar=CAL, coverage=cov, flag_path=run.flag, source="yfinance", calendar_version="cal-1", code_version="test",
            accounting_factory=factory)
        last_result = stores.db.fetchone("SELECT content FROM reconciliation_results WHERE account_id='R2' ORDER BY sequence DESC LIMIT 1")
        import json

        from investment_engine.lineage.records import decode
        result = None if last_result is None else decode(json.loads(last_result[0]))
        assert not report.stops and report.orders == 1, (report, result)
        [(order, status)] = run.orders().for_account("R2")
        assert status.state.value == "FILLED"
        assert "ACCOUNTING_WAIT" in outcomes and outcomes.count("SUBMITTED") == 1
        assert len(run.orders().gate_decisions(order.order_id)) == 1
        assert stores.db.fetchone("SELECT count(*) FROM reconciliation_incidents")[0] == 0
        assert stores.db.fetchone("SELECT status FROM reconciliation_results WHERE account_id='R2' ORDER BY sequence DESC LIMIT 1")[0] == "MATCH"
        assert stores.db.fetchone("SELECT count(*) FROM ledger_transactions")[0] == 2  # opening + actual accepted fill
        assert stores.db.fetchone("SELECT count(*) FROM processed_events WHERE consumer='accounting-ledger' AND outcome='applied'")[0] == 1
        # Portfolio source is checked by decoding the stored snapshot, not a UI label.
        snap = stores.snapshots.get(stores.db.fetchone("SELECT snapshot_id FROM portfolio_snapshots LIMIT 1")[0])
        assert snap.source.value == "LEDGER" and snap.ledger_book_id
    finally:
        run.close()


def test_stalled_snapshot_blocks_further_broker_calls_until_it_returns(setup, monkeypatch):
    import threading
    env, worker, _, _, _ = setup
    release = threading.Event()
    calls = []
    original = worker.broker.snapshot
    def stalled(*args, **kwargs):
        calls.append("snapshot")
        release.wait(timeout=10)
        return original(*args, **kwargs)
    monkeypatch.setattr(worker.broker, "snapshot", stalled)
    worker.deadline_seconds = 0.01
    try:
        worker.step()
        assert worker.broker_stalled()
        worker.step()
        assert calls == ["snapshot"]
        assert env.db.fetchone("SELECT count(*) FROM broker_snapshots")[0] == 0
    finally:
        release.set()
        if worker._stalled:
            worker._stalled.join(timeout=10)
            assert not worker._stalled.is_alive()


def test_snapshot_persistence_connection_failure_is_not_swallowed_as_a_broker_error(setup, monkeypatch):
    import psycopg

    from investment_engine.reconciliation.snapshots import BrokerSnapshotStore
    _, worker, _, _, _ = setup
    def lost(*args, **kwargs):
        raise psycopg.OperationalError("worker persistence connection lost")
    monkeypatch.setattr(BrokerSnapshotStore, "record", lost)
    with pytest.raises(psycopg.OperationalError):
        worker.step()


def test_new_order_cancel_can_close_while_accounting_is_unavailable(pg_database, tmp_path):
    from investment_engine.events.outbox import Outbox
    from investment_engine.ledger.sources import opening_bundle
    from investment_engine.ledger.store import LedgerStore
    from investment_engine.oms.order_states import ProcessRole
    from tests.engine.test_intent_pipeline import SESSIONS
    from tests.engine.worker_env import WorkerEnv, pre_open

    env = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "flags")
    try:
        order, view = env.convert(SESSIONS[60])
        worker = env.worker(pre_open(order, view))
        ledger = LedgerStore(env.stores.db, audit=env.stores.audit,
            outbox=Outbox(env.stores.db, writer=ProcessRole.CORE, clock=worker.clock),
            clock=worker.clock, command_clock=env.clock)
        ledger.activate("R2", opening_lots=(), source_bundle=opening_bundle(env.stores.snapshots.starting_state("R2"), at=worker.clock.now()),
                          by=OWNER, reason="activate accounting")
        assert worker.submit(order.order_id) == "ACCOUNTING_WAIT"
        assert env.state(order).state.value == "NEW"
        env.cancel(order)
        worker.step()
        worker.step()
        assert env.state(order).state.value == "GATE_REJECTED"
        assert not worker.orders.open_cancels()
        assert not env.broker.submits
    finally:
        env.close()
