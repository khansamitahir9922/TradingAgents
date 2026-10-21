"""M5-07: public setup commands and worker-only immutable account evidence."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from psycopg import Error as PgError

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.events.outbox import Outbox
from investment_engine.oms.order_states import ProcessRole
from investment_engine.policy.accounts import AccountKind, AccountRegistry
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
from investment_engine.reconciliation.snapshots import BrokerSetupStore, BrokerSnapshotStore
from tests.engine.test_ledger_store import T, open_store
from tests.engine.test_reconciliation_contracts import snapshot

pytestmark = pytest.mark.postgres
OWNER = Actor(ActorKind.OPERATOR,"owner","ADMIN","test")


@pytest.fixture
def env(pg_database):
    conn,db,_ = open_store(pg_database)
    clock=ReplayClock(T)
    audit=AuditStore(db)
    accounts=AccountRegistry(db,audit,clock)
    accounts.bootstrap_admin("owner",os_user="test")
    states=PortfolioSnapshotStore(db,audit,accounts,clock)
    states.declare_start("R1",by=OWNER,reason="declared initial condition",effective_at=T)
    setup=BrokerSetupStore(db,audit=audit,accounts=accounts,states=states,command_clock=clock)
    outbox=Outbox(db,writer=ProcessRole.EXECUTION,clock=clock)
    writer=BrokerSnapshotStore(db,role=ProcessRole.EXECUTION,audit=audit,outbox=outbox,clock=clock)
    yield db,clock,accounts,states,setup,writer
    conn.close()


def test_setup_is_immutable_idempotent_research_only_and_current_admin(env):
    db,clock,accounts,states,store,_=env
    first=store.request("R1",source="yfinance",coverage_evidence=(),by=OWNER,reason="explicit simulated seed")
    assert first.cash == 100000 and first.starting_state_id == states.starting_state("R1").state_id
    clock.advance_by(timedelta(seconds=1))
    assert store.request("R1",source="yfinance",coverage_evidence=(),by=OWNER,reason="retry") == first
    accounts.create_account("P",AccountKind.PAPER,"USD",by=OWNER,reason="paper")
    states.declare_start("P",by=OWNER,reason="paper start")
    with pytest.raises(ValueError,match="RESEARCH"):
        store.request("P",source="yfinance",coverage_evidence=(),by=OWNER,reason="not allowed")
    fake=Actor(ActorKind.OPERATOR,"forged","ADMIN","test")
    with pytest.raises(PermissionError):
        store.request("R1",source="yfinance",coverage_evidence=(),by=fake,reason="forged role")
    assert db.fetchone("SELECT count(*) FROM broker_setup_requests")[0] == 1
    assert db.fetchone("SELECT count(*) FROM sim_broker.account_seeds")[0] == 0  # only worker may consume


def test_worker_snapshot_values_are_unchanged_and_repeat_capture_has_no_new_event(env):
    db,clock,_,_,_,store=env
    value=snapshot()
    assert store.record(value) == value
    assert store.record(value) == value
    assert store.latest("R1",known_at=clock.now()) == value
    assert db.fetchone("SELECT count(*) FROM outbox")[0] == 1
    assert db.fetchone("SELECT count(*) FROM broker_snapshots")[0] == 1
    later=T+timedelta(seconds=1)
    clock.advance_to(later)
    changed=replace(value,effective_at=later,taken_at=later,received_at=later,cash=Decimal(99))
    store.record(changed)
    assert store.latest("R1",known_at=T) == value
    assert store.latest("R1",known_at=later).cash == 99


@pytest.mark.parametrize("sql",["UPDATE broker_snapshots SET content=content","DELETE FROM broker_snapshots",
                                "TRUNCATE broker_snapshots CASCADE","UPDATE broker_setup_requests SET content=content"])
def test_public_account_evidence_is_append_only(env,sql):
    db,_,_,_,setup,store=env
    setup.request("R1",source="yfinance",coverage_evidence=(),by=OWNER,reason="seed")
    store.record(snapshot())
    with pytest.raises(PgError,match="append-only"),db.connection.transaction():
        db.connection.execute(sql)


def test_wrong_role_and_future_snapshot_are_refused_by_api_and_sql(env):
    db,clock,_,_,_,store=env
    store.record(snapshot())
    core=BrokerSnapshotStore(db,role=ProcessRole.CORE,audit=AuditStore(db),
        outbox=Outbox(db,writer=ProcessRole.CORE,clock=clock),clock=clock)
    with pytest.raises(PermissionError):
        core.record(snapshot())
    with pytest.raises(PgError,match="Execution Worker"),db.connection.transaction():
        db.connection.execute("SELECT set_config('investment_engine.process_role','core-engine',true)")
        db.connection.execute("INSERT INTO broker_snapshots SELECT snapshot_id || 'x',account_id,version+10,effective_at,taken_at,received_at,recorded_at,content FROM broker_snapshots")
    with pytest.raises(ValueError,match="receipt"):
        store.record(replace(snapshot(),received_at=T+timedelta(days=1)))


def test_late_persistence_preserves_receipt_but_not_earlier_database_knowledge(env):
    _,clock,_,_,_,store=env
    received=snapshot()
    clock.advance_by(timedelta(seconds=1))
    assert store.record(received)==received
    assert store.latest("R1",known_at=T) is None
    assert store.latest("R1",known_at=clock.now())==received
    clock.advance_by(timedelta(seconds=1))
    assert store.record(received)==received


def test_ingestion_progress_is_separate_from_unchanged_vendor_values_and_append_only(env):
    db,clock,_,_,_,store=env
    value=snapshot()
    store.record(value)
    partial=store.record_ingestion(value.snapshot_id,complete=False,prefix_ref="budget-limited-message-prefix")
    assert not partial.complete
    assert store.record_ingestion(value.snapshot_id,complete=False,prefix_ref="budget-limited-message-prefix")==partial
    done=store.record_ingestion(value.snapshot_id,complete=True,prefix_ref="all-available-messages")
    assert done.observation_id!=partial.observation_id
    assert store.ingestion(value.snapshot_id,known_at=clock.now())==done
    assert store.get(value.snapshot_id)==value
    assert db.fetchone("SELECT count(*) FROM broker_snapshots")[0]==1
    assert db.fetchone("SELECT count(*) FROM broker_ingestion_observations")[0]==2
    with pytest.raises(PgError,match="append-only"),db.connection.transaction():
        db.connection.execute("UPDATE broker_ingestion_observations SET complete=true")
