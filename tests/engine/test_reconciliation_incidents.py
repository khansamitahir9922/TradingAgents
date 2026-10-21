"""M5-09: immutable incidents, current Admin authorization and fresh resolution."""
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from psycopg import Error as PgError

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.events.outbox import Outbox
from investment_engine.ledger.balances import balances
from investment_engine.ledger.sources import opening_bundle
from investment_engine.ledger.store import LedgerStore
from investment_engine.oms.order_states import ProcessRole
from investment_engine.policy.accounts import AccountRegistry, Role
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
from investment_engine.reconciliation.compare import InternalOrders, compare
from investment_engine.reconciliation.incidents import IncidentStore, StaleEvidence, StaleIncident
from investment_engine.reconciliation.snapshots import SIM_CASH_BASIS, BrokerSnapshotStore
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import open_operational_pg
from tests.engine.test_ledger_store import T, open_store
from tests.engine.test_reconciliation_contracts import snapshot

pytestmark=pytest.mark.postgres
OWNER=Actor(ActorKind.OPERATOR,"owner","ADMIN","test")


class Env:
    def __init__(self,dsn):
        self.dsn=dsn
        self.conn,self.db,_=open_store(dsn)
        self.clock=ReplayClock(T)
        self.live=ReplayClock(T+timedelta(days=1))
        self.audit=AuditStore(self.db)
        self.accounts=AccountRegistry(self.db,self.audit,self.live)
        self.accounts.bootstrap_admin("owner",os_user="test")
        states=PortfolioSnapshotStore(self.db,self.audit,self.accounts,self.live)
        start=states.declare_start("R1",by=OWNER,reason="declared cash",cash=Decimal(100),effective_at=T)
        self.outbox=Outbox(self.db,writer=ProcessRole.CORE,clock=self.clock)
        self.ledger=LedgerStore(self.db,audit=self.audit,outbox=self.outbox,clock=self.clock,command_clock=self.live)
        self.ledger.activate("R1",opening_lots=(),source_bundle=opening_bundle(start,at=T),by=OWNER,reason="explicit")
        self.snapshots=BrokerSnapshotStore(self.db,role=ProcessRole.EXECUTION,audit=self.audit,
            outbox=Outbox(self.db,writer=ProcessRole.EXECUTION,clock=self.clock),clock=self.clock)
        self.store=self.connect_store(self.db)

    def connect_store(self,db,current=None):
        audit=AuditStore(db)
        return IncidentStore(db,audit=audit,outbox=Outbox(db,writer=ProcessRole.CORE,clock=self.clock),
                              accounts=AccountRegistry(db,audit,self.live),clock=self.clock,command_clock=self.live,
                              current_evidence=current or self.current)

    def capture(self,cash):
        at=self.clock.now()
        value=snapshot(broker="simulated",broker_account_id="sim/R1",cash=Decimal(cash),positions=(),
                        effective_at=at,taken_at=at,received_at=at,cash_basis=SIM_CASH_BASIS)
        self.snapshots.record(value)
        self.snapshots.record_ingestion(value.snapshot_id,complete=True,prefix_ref="complete-empty-broker-stream")
        return self.current("R1",at)

    def current(self,account_id,at):
        head=self.ledger.read_head(account_id,known_at=at)
        reported=self.snapshots.latest(account_id,known_at=at)
        prefix=self.snapshots.ingestion(reported.snapshot_id,known_at=at)
        internal=InternalOrders(account_id,at,at,"sim/R1",reported.snapshot_id,prefix.observation_id,prefix.complete,at,())
        value=balances(account_id,effective_at=at,known_at=at,book_id=head.book_id,ledger=self.ledger)
        return compare(account_id,snapshot=reported,ledger_balances=value,internal_orders=internal,known_at=at)

    def opened(self):
        result=self.capture("99")
        return self.store.observe(result),result


@pytest.fixture
def env(pg_database):
    e=Env(pg_database)
    yield e
    e.conn.close()


def test_discrepancy_open_duplicate_and_acknowledgement_never_resolves_or_repairs(env):
    incident,result=env.opened()
    assert env.store.observe(result).incident_id==incident.incident_id
    assert env.store.state(incident.incident_id).state=="OPEN"
    before=env.db.fetchone("SELECT count(*) FROM ledger_entries")[0]
    changed=env.store.acknowledge(incident.incident_id,expected_sequence=1,by=OWNER,reason="investigating")
    assert changed.state=="ACKNOWLEDGED" and changed.command_at==env.live.now() and changed.business_at==T
    assert not env.store.readiness("R1",at=T).ready
    assert env.db.fetchone("SELECT count(*) FROM reconciliation_incidents")[0]==1
    assert env.db.fetchone("SELECT count(*) FROM ledger_entries")[0]==before


def test_later_current_match_resolves_only_by_admin_and_new_discrepancy_opens_new_incident(env):
    incident,_=env.opened()
    env.clock.advance_by(timedelta(seconds=1))
    matched=env.capture("100")
    assert matched.status=="MATCH"
    env.store.observe(matched)
    assert not env.store.readiness("R1",at=env.clock.now()).ready
    changed=env.store.resolve(incident.incident_id,expected_sequence=1,match_id=matched.result_id,by=OWNER,reason="checked current matching evidence")
    assert changed.state=="RESOLVED"
    assert env.store.readiness("R1",at=env.clock.now()).ready
    env.clock.advance_by(timedelta(seconds=1))
    new=env.store.observe(env.capture("98"))
    assert new.incident_id!=incident.incident_id


@pytest.mark.parametrize("role",[Role.TRADER,Role.VIEWER])
def test_trader_or_viewer_cannot_acknowledge(env,role):
    incident,_=env.opened()
    env.accounts.add_operator("reader",role,by=OWNER,reason="test role")
    actor=Actor(ActorKind.OPERATOR,"reader",role.value,"test")
    with pytest.raises(PermissionError):
        env.store.acknowledge(incident.incident_id,expected_sequence=1,by=actor,reason="not allowed",business_at=T)
    assert len(env.store.history(incident.incident_id))==1


def test_deactivated_admin_is_not_revived_by_historical_business_time(env):
    incident,_=env.opened()
    env.live.advance_by(timedelta(days=1))
    env.accounts.deactivate_operator("owner",by=OWNER,reason="deactivated now")
    with pytest.raises(PermissionError):
        env.store.acknowledge(incident.incident_id,expected_sequence=1,by=OWNER,reason="past replay is not authority",business_at=T)


def test_stale_match_or_new_uncompared_snapshot_cannot_resolve(env):
    incident,_=env.opened()
    env.clock.advance_by(timedelta(seconds=1))
    matched=env.capture("100")
    env.store.observe(matched)
    env.clock.advance_by(timedelta(seconds=1))
    env.capture("98")  # not observed by Core yet, but public evidence is already newer
    with pytest.raises(StaleEvidence):
        env.store.resolve(incident.incident_id,expected_sequence=1,match_id=matched.result_id,by=OWNER,reason="stale match")
    assert env.store.state(incident.incident_id).state=="OPEN"


def test_two_transition_writers_have_one_cas_successor(env):
    incident,_=env.opened()
    barrier=threading.Barrier(2)
    outcomes=[]

    def write():
        c=open_operational_pg(env.dsn)
        try:
            store=env.connect_store(PostgresDatabase(c))
            barrier.wait(timeout=20)
            try:
                store.acknowledge(incident.incident_id,expected_sequence=1,by=OWNER,reason="racing acknowledgement")
                outcomes.append("ok")
            except StaleIncident:
                outcomes.append("stale")
        finally:
            c.close()

    threads=[threading.Thread(target=write) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    assert sorted(outcomes)==["ok","stale"]
    assert len(env.store.history(incident.incident_id))==2


def test_observation_failure_rolls_back_result_incident_audit_and_event(env,monkeypatch):
    result=env.capture("99")
    names=("reconciliation_results","reconciliation_incidents","reconciliation_transitions","audit_events","outbox")
    before=tuple(env.db.fetchone(f"SELECT count(*) FROM {n}")[0] for n in names)
    def fail(_event): raise RuntimeError("outbox fault")
    monkeypatch.setattr(env.outbox,"add",fail)
    # Store uses the injected outbox that shares this transaction.
    monkeypatch.setattr(env.store,"outbox",env.outbox)
    with pytest.raises(RuntimeError,match="outbox fault"):
        env.store.observe(result)
    assert tuple(env.db.fetchone(f"SELECT count(*) FROM {n}")[0] for n in names)==before


@pytest.mark.parametrize("change", ["deactivate", "newer-mismatch"])
def test_prior_lock_holder_prevents_stale_admin_transition(env, change):
    incident, _ = env.opened()
    env.clock.advance_by(timedelta(seconds=1))
    matched = env.capture("100")
    env.store.observe(matched)
    attempted = threading.Event()
    outcomes = []

    def command():
        conn = open_operational_pg(env.dsn)
        try:
            db = PostgresDatabase(conn)
            original = db.lock

            def lock(*names):
                awaited = "operator|owner" if change == "deactivate" else "account-control|R1"
                if awaited in names:
                    attempted.set()
                original(*names)

            db.lock = lock
            store = env.connect_store(db)
            try:
                if change == "deactivate":
                    store.acknowledge(incident.incident_id, expected_sequence=1, by=OWNER,
                                      reason="wait for operator lock", business_at=T)
                else:
                    store.resolve(incident.incident_id, expected_sequence=1, match_id=matched.result_id,
                                  by=OWNER, reason="wait for account lock")
                outcomes.append("unexpected success")
            except (PermissionError, StaleEvidence) as exc:
                outcomes.append("unauthorized" if isinstance(exc, PermissionError) else "stale")
        finally:
            conn.close()

    with env.db.transaction():
        env.db.lock("operator|owner" if change == "deactivate" else "account-control|R1")
        thread = threading.Thread(target=command)
        thread.start()
        assert attempted.wait(timeout=20)
        if change == "deactivate":
            env.live.advance_by(timedelta(seconds=1))
            env.accounts.deactivate_operator("owner", by=OWNER, reason="first lock holder")
        else:
            # Same replay instant: sequencing and current pins, not a clock tick,
            # must reject the previously valid MATCH.
            env.store.observe(env.capture("98"))
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert outcomes == ["unauthorized" if change == "deactivate" else "stale"]
    assert env.store.state(incident.incident_id).state == "OPEN"
    assert len(env.store.history(incident.incident_id)) == 1


@pytest.mark.parametrize("table",["reconciliation_results","reconciliation_incidents","reconciliation_transitions","reconciliation_evidence"])
@pytest.mark.parametrize("operation",["UPDATE {table} SET {column}={column}","DELETE FROM {table}","TRUNCATE {table} CASCADE"])
def test_all_incident_history_is_immutable(env,table,operation):
    env.opened()
    column="result_id" if table in ("reconciliation_results","reconciliation_evidence") else "incident_id"
    with pytest.raises(PgError,match="append-only"),env.conn.transaction():
        env.conn.execute(operation.format(table=table,column=column))
