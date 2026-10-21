"""M5-13: hard-kill disposable Core/worker children and restart original IDs."""
import pytest

from investment_engine.audit.events import AuditStore
from investment_engine.events.outbox import Outbox
from investment_engine.ledger.sources import opening_bundle
from investment_engine.ledger.store import LedgerStore
from investment_engine.oms.order_states import ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
from tests.engine import process_harness
from tests.engine.test_order_store import OWNER, Env

pytestmark=pytest.mark.postgres


@pytest.mark.parametrize("fault",["m5_before_journal_commit","m5_before_processed_mark","m5_after_ledger_commit"])
def test_real_core_crash_replays_one_fill_one_posting_and_one_mark(pg_database,tmp_path,fault):
    from investment_engine.config import market_store_dir
    from tests.engine.test_ledger_time import accepted
    e=Env(pg_database)
    try:
        audit=AuditStore(e.db)
        states=PortfolioSnapshotStore(e.db,audit,e.accounts,e.clock)
        start=states.declare_start("R1",by=OWNER,reason="declared initial cash",effective_at=e.clock.now())
        ledger=LedgerStore(e.db,audit=audit,outbox=Outbox(e.db,writer=ProcessRole.CORE,clock=e.clock),clock=e.clock,command_clock=e.clock)
        original=ledger.activate("R1",opening_lots=(),source_bundle=opening_bundle(start,at=e.clock.now()),by=OWNER,reason="explicit activation")
        for role,name in ((ProcessRole.CORE,"core"),(ProcessRole.EXECUTION,"worker")):
            previous=getattr(e,name)
            db=previous._db
            setattr(e,name,OrderStore(db,role=role,audit=AuditStore(db),outbox=Outbox(db,writer=role,clock=e.clock),clock=e.clock))
        order,fill=accepted(e,"BUY","1","10",executed=e.clock.now(),recorded=e.clock.now(),fee="0")
        for orders in (e.core,e.worker):
            orders._outbox.publish_pending(limit=1000)
        spec={"role":"m5_ledger","at":e.clock.now().isoformat(),"command_at":e.clock.now().isoformat(),
              "market":str(market_store_dir()),"account":"R1","fault":fault}
        assert process_harness.run(spec,dsn=pg_database,tmp=tmp_path) is None
        after=ledger.read_head("R1",known_at=e.clock.now())
        assert (after.book_id==original.book_id)==(fault!="m5_after_ledger_commit")
        spec["fault"]=None
        process_harness.run(spec,dsn=pg_database,tmp=tmp_path)
        head=ledger.read_head("R1",known_at=e.clock.now())
        assert head.version==original.version+1
        assert e.db.fetchone("SELECT count(*) FROM ledger_transactions")[0]==2
        assert e.db.fetchone("SELECT count(*) FROM processed_events WHERE consumer='accounting-ledger' AND outcome='applied'")[0]==1
        assert len(e.core.fills(order.order_id))==1
        before=head.book_id
        assert e.worker.record_fill(fill,expected_aggregate_version=e.worker.get(order.order_id)[1].aggregate_version).value=="DUPLICATE"
        process_harness.run(spec,dsn=pg_database,tmp=tmp_path)
        assert ledger.read_head("R1",known_at=e.clock.now()).book_id==before
    finally:
        e.close()


def test_real_worker_killed_inside_public_snapshot_transaction_restarts_cleanly(pg_database,tmp_path):
    from investment_engine.config import market_store_dir
    from investment_engine.reconciliation.snapshots import BrokerSetupStore
    from tests.engine.test_reconciliation_incidents import Env as CashEnv
    e=CashEnv(pg_database)
    try:
        states=PortfolioSnapshotStore(e.db,e.audit,e.accounts,e.live)
        BrokerSetupStore(e.db,audit=e.audit,accounts=e.accounts,states=states,command_clock=e.live).request(
            "R1",source="yfinance",coverage_evidence=(),by=OWNER,reason="explicit independent simulation setup")
        spec={"role":"m5_snapshot","at":e.clock.now().isoformat(),"command_at":e.live.now().isoformat(),
              "market":str(market_store_dir()),"account":"R1","fault":"m5_snapshot_before_commit"}
        assert process_harness.run(spec,dsn=pg_database,tmp=tmp_path) is None
        assert e.db.fetchone("SELECT count(*) FROM broker_snapshots")[0]==0
        spec["fault"]=None
        process_harness.run(spec,dsn=pg_database,tmp=tmp_path)
        assert e.db.fetchone("SELECT count(*) FROM broker_snapshots")[0]==1
        assert e.db.fetchone("SELECT count(*) FROM broker_ingestion_observations")[0]==1
        entries=e.db.fetchone("SELECT count(*) FROM ledger_entries")[0]
        process_harness.run(spec,dsn=pg_database,tmp=tmp_path)
        assert e.db.fetchone("SELECT count(*) FROM broker_snapshots")[0]==1
        assert e.db.fetchone("SELECT count(*) FROM ledger_entries")[0]==entries
    finally:
        e.conn.close()
