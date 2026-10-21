"""M5-13: independent rational expectations, 200 flows and repeated real DB races."""
import random
import threading
from datetime import timedelta
from decimal import Decimal, Inexact, Rounded, localcontext
from fractions import Fraction

import pytest

from investment_engine.ledger.actions import plan_action
from investment_engine.ledger.contracts import Unit, journal
from investment_engine.ledger.lots import FifoBook
from investment_engine.ledger.postings import plan_fifo_fill, post_fill
from investment_engine.ledger.sources import action_reference, fill_reference, opening_bundle
from investment_engine.oms.intents import Side
from investment_engine.oms.orders import Fill, Order, order_ids
from investment_engine.policy.accounts import AccountKind
from tests.engine.test_ledger_actions import CAL, NVDA, OPEN, PRIOR, corporate
from tests.engine.test_ledger_contracts import source

SEEDS = tuple(range(200))
RACE_REPETITIONS = 50


def cents(n):
    return Decimal(f"{n//100}.{n%100:02}")


def fact(seed,n,side,quantity,price,fee,when,known):
    iid=f"flow-{seed}-{n}"
    order=Order(*order_ids(iid,1),iid,1,"content","fingerprint","R1",AccountKind.RESEARCH,NVDA,Side(side),
                 Decimal(quantity),"LIMIT",price,"DAY",when.date(),when-timedelta(seconds=1))
    fill=Fill(order.order_id,Decimal(quantity),price,fee,"USD",when,known,known,f"execution-{seed}-{n}","{}")
    return order,fill


@pytest.mark.parametrize("seed",SEEDS)
def test_fixed_seed_flow_conserves_currency_quantity_cost_and_pnl(seed):
    rng=random.Random(seed)
    known=CAL.session(OPEN.date()+timedelta(days=2)).close
    fifo=FifoBook("R1",at=known)
    transactions=[journal("R1",PRIOR-timedelta(days=1),known,(source(),),
        (("CASH",Unit("CURRENCY","USD"),Decimal(100000)),("CAPITAL",Unit("CURRENCY","USD"),Decimal(-100000))))]
    lots=[]
    cash=Fraction(100000)
    fees=Fraction()
    for n in range(5):
        quantity=rng.randint(1,20)
        price,fee=cents(rng.randint(100,10000)),cents(rng.randint(1,100))
        order,fill=fact(seed,n,"BUY",quantity,price,fee,PRIOR-timedelta(seconds=10-n),known)
        plan=plan_fifo_fill(order,fill,ref=fill_reference(order,fill),posted_at=known,fifo=fifo)
        transactions.append(plan.transaction)
        lots.append([quantity,Fraction(price)*quantity])
        cash-=Fraction(price)*quantity+Fraction(fee)
        fees+=Fraction(fee)
    original_cost=sum((cost for _,cost in lots),Fraction())
    ratio=rng.choice((2,10))
    split=corporate(ratio=Decimal(ratio))
    transactions.append(plan_action(split,ref=action_reference(split,delivered_at=split.available_from,calendar=CAL),
                                    posted_at=known,fifo=fifo,calendar=CAL))
    for lot in lots:
        lot[0]*=ratio
    total=sum(q for q,_ in lots)
    assert sum(int(lot.remaining_quantity) for lot in fifo.lots())==total
    assert sum((Fraction(lot.remaining_cost) for lot in fifo.lots()),Fraction())==original_cost
    from investment_engine.market.corporate_actions import ActionType
    from investment_engine.money import Money
    dividend=cents(rng.randint(1,100))
    action=corporate(ActionType.DIVIDEND,ex_date=OPEN.date()+timedelta(days=1),amount=Money(dividend,"USD"))
    transactions.append(plan_action(action,ref=action_reference(action,delivered_at=action.available_from,calendar=CAL),
        posted_at=known,fifo=fifo,calendar=CAL,prior_close_quantity=Decimal(total)))
    sold=rng.randint(1,total)
    remaining=sold
    expected_cost=Fraction()
    for lot in lots:
        take=min(remaining,lot[0])
        allocation=lot[1]*take/lot[0] if lot[0] else Fraction()
        expected_cost+=allocation
        lot[0]-=take
        lot[1]-=allocation
        remaining-=take
    price,fee=cents(rng.randint(100,20000)),cents(rng.randint(1,100))
    order,fill=fact(seed,5,"SELL",sold,price,fee,known-timedelta(seconds=1),known)
    # Vary caller precision/traps without using them for independent expectations.
    with localcontext() as context:
        context.prec=1 if seed%2 else 6
        context.traps[Inexact]=context.traps[Rounded]=True
        plan=plan_fifo_fill(order,fill,ref=fill_reference(order,fill),posted_at=known,fifo=fifo)
    transactions.append(plan.transaction)
    cash+=Fraction(price)*sold-Fraction(fee)
    fees+=Fraction(fee)
    actual_cost=sum((Fraction(m.cost) for m in plan.lot_matches),Fraction())
    assert actual_cost==expected_cost
    assert sum((Fraction(lot.remaining_cost) for lot in fifo.lots()),Fraction())+actual_cost==original_cost
    assert sum(int(lot.remaining_quantity) for lot in fifo.lots())==total-sold
    totals={}
    for transaction in transactions:
        represented={}
        for entry in transaction.entries:
            amount=Fraction(entry.debit)-Fraction(entry.credit)
            represented[entry.unit.key]=represented.get(entry.unit.key,Fraction())+amount
            key=entry.account,entry.unit.key
            totals[key]=totals.get(key,Fraction())+amount
        assert represented and all(v==0 for v in represented.values())
    assert totals[("CASH","CURRENCY:USD")]==cash
    assert totals[("CUSTODY_SHARES","SECURITY:"+NVDA)]==total-sold
    assert totals[("FEES","CURRENCY:USD")]==fees
    assert totals[("DIVIDEND_RECEIVABLE:"+NVDA,"CURRENCY:USD")]==Fraction(dividend)*total
    assert -totals.get(("REALIZED_PNL:"+NVDA,"CURRENCY:USD"),Fraction())==Fraction(price)*sold-expected_cost
    before=fifo.lots()
    assert plan_fifo_fill(order,fill,ref=fill_reference(order,fill),posted_at=known,fifo=fifo)==plan
    assert fifo.lots()==before  # duplicate planning does not consume twice


@pytest.mark.postgres
def test_fifty_competing_posting_races_have_one_effect_each(pg_database):
    from investment_engine.audit.events import AuditStore
    from investment_engine.events.outbox import Outbox
    from investment_engine.ledger.store import LedgerStore
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.oms.order_store import OrderStore
    from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from tests.engine.test_ledger_time import accepted
    from tests.engine.test_order_store import OWNER, Env
    e=Env(pg_database)
    try:
        audit=AuditStore(e.db)
        states=PortfolioSnapshotStore(e.db,audit,e.accounts,e.clock)
        start=states.declare_start("R1",by=OWNER,reason="known cash",effective_at=e.clock.now())
        ledger=LedgerStore(e.db,audit=audit,outbox=Outbox(e.db,writer=ProcessRole.CORE,clock=e.clock),clock=e.clock,command_clock=e.clock)
        initial=ledger.activate("R1",opening_lots=(),source_bundle=opening_bundle(start,at=e.clock.now()),by=OWNER,reason="explicit")
        for n in range(RACE_REPETITIONS):
            order,fill=accepted(e,"BUY","1","1",executed=e.clock.now(),recorded=e.clock.now(),fee="0",broker_id=f"race-{n}")
            barrier=threading.Barrier(2)
            results=[]
            failures=[]
            def write(barrier=barrier,results=results,failures=failures,order=order,fill=fill):
                conn=open_operational_pg(pg_database)
                try:
                    db=PostgresDatabase(conn)
                    audit=AuditStore(db)
                    outbox=Outbox(db,writer=ProcessRole.CORE,clock=e.clock)
                    books=LedgerStore(db,audit=audit,outbox=outbox,clock=e.clock,command_clock=e.clock)
                    orders=OrderStore(db,role=ProcessRole.CORE,audit=audit,outbox=outbox,clock=e.clock)
                    barrier.wait(timeout=20)
                    results.append(post_fill(order,fill,ledger=books,orders=orders).book_id)
                except Exception as exc:
                    failures.append(type(exc).__name__)
                finally:
                    conn.close()
            threads=[threading.Thread(target=write) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
                assert not t.is_alive()
            assert not failures and len(results)==2 and len(set(results))==1
        head=ledger.read_head("R1",known_at=e.clock.now())
        assert head.version==initial.version+RACE_REPETITIONS
        assert len([ref for ref in head.sources if ref.kind=="fill"])==RACE_REPETITIONS
        assert e.db.fetchone("SELECT count(*) FROM ledger_transactions WHERE account_id='R1'")[0]==RACE_REPETITIONS+1
    finally:
        e.close()


@pytest.mark.postgres
def test_fifty_incident_cas_races_preserve_evidence_and_other_account(pg_database):
    from investment_engine.reconciliation.incidents import StaleIncident
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from tests.engine.test_reconciliation_incidents import OWNER, Env
    e=Env(pg_database)
    try:
        entries=e.db.fetchone("SELECT count(*) FROM ledger_entries")[0]
        for _ in range(RACE_REPETITIONS):
            incident,_=e.opened()
            barrier=threading.Barrier(2)
            outcomes=[]
            def acknowledge(barrier=barrier,outcomes=outcomes,incident=incident):
                conn=open_operational_pg(pg_database)
                try:
                    store=e.connect_store(PostgresDatabase(conn))
                    barrier.wait(timeout=20)
                    try:
                        store.acknowledge(incident.incident_id,expected_sequence=1,by=OWNER,reason="CAS race")
                        outcomes.append("ok")
                    except StaleIncident:
                        outcomes.append("stale")
                finally:
                    conn.close()
            threads=[threading.Thread(target=acknowledge) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
                assert not t.is_alive()
            assert sorted(outcomes)==["ok","stale"]
            assert not e.store.readiness("R1",at=e.clock.now()).ready
            e.clock.advance_by(timedelta(seconds=1))
            matched=e.capture("100")
            e.store.observe(matched)
            e.store.resolve(incident.incident_id,expected_sequence=2,match_id=matched.result_id,by=OWNER,reason="later current match")
            e.clock.advance_by(timedelta(seconds=1))
        assert e.db.fetchone("SELECT count(*) FROM reconciliation_incidents")[0]==RACE_REPETITIONS
        assert e.db.fetchone("SELECT count(*) FROM reconciliation_transitions")[0]==3*RACE_REPETITIONS
        assert e.db.fetchone("SELECT count(*) FROM ledger_entries")[0]==entries
        assert e.db.fetchone("SELECT count(*) FROM broker_snapshots WHERE account_id='R2'")[0]==0
        assert e.db.fetchone("SELECT count(*) FROM ledger_batches WHERE account_id='R2'")[0]==0
    finally:
        e.conn.close()


@pytest.mark.postgres
def test_fifty_fill_proposal_races_never_size_from_cash_after_an_unposted_fill(pg_database,tmp_path):
    from investment_engine.clock import ReplayClock
    from investment_engine.core.engine import CoreEngine
    from investment_engine.events.outbox import Outbox
    from investment_engine.execution.factory import build_gate_reads
    from investment_engine.execution.worker import ExecutionWorker
    from investment_engine.killswitch.flag import KillSwitchReader
    from investment_engine.ledger.contracts import identity
    from investment_engine.ledger.service import AccountingService, SourceSelector
    from investment_engine.ledger.store import LedgerStore
    from investment_engine.oms.order_states import ProcessRole
    from investment_engine.oms.orders import FillOutcome
    from investment_engine.oms.pipeline import propose
    from investment_engine.portfolio.fingerprint import DeclaredFingerprints
    from investment_engine.reconciliation.contracts import (
        BrokerOpenOrder,
        BrokerPosition,
        BrokerSnapshot,
    )
    from investment_engine.reconciliation.snapshots import SIM_CASH_BASIS
    from tests.engine.broker_doubles import ScriptedBroker
    from tests.engine.test_intent_pipeline import SESSIONS, view_for
    from tests.engine.test_ledger_actions import coverage
    from tests.engine.test_order_store import OWNER
    from tests.engine.worker_env import WorkerEnv

    class SnapshotBroker(ScriptedBroker):
        """Independent test broker, valuing its own message book, never the OMS."""
        def snapshot(self, account_id, *, at):
            messages=[m for m in self.queue if m.delivered_at<=at]
            fills=[m.fill for m in messages if m.fill]
            spent=sum((f.quantity*f.price+f.fee for f in fills),Decimal(0))
            quantity=sum((f.quantity for f in fills),Decimal(0))
            resting=tuple(BrokerOpenOrder(o.order_id,o.client_order_id,o.instrument_id,o.side.value,"OPEN",o.quantity-filled)
                          for o,state,filled in self.orders.values() if state=="OPEN")
            return BrokerSnapshot(account_id,"simulated","sim/"+account_id,"simulated",at,at,at,"USD",Decimal(100000)-spent,
                (BrokerPosition(NVDA,quantity,"SHARES"),) if quantity else (),resting,SIM_CASH_BASIS,"independent-test-seed",
                identity(tuple((m.message_id,m.fill.broker_fill_id) for m in messages if m.fill)),tuple(f.broker_fill_id for f in fills),True,())

    e=WorkerEnv(pg_database,tmp_path/"market",tmp_path/"control")
    try:
        e.account("UNRELATED",level=0)
        view=e.approved_view(SESSIONS[60])
        at=view.generated_at+timedelta(minutes=1)
        clock=ReplayClock(at)
        (order,)=CoreEngine(e.stores,clock=clock).convert("R2",at=at).converted
        ledger=LedgerStore(e.stores.db,audit=e.stores.audit,outbox=Outbox(e.stores.db,writer=ProcessRole.CORE,clock=clock),
                            clock=clock,command_clock=e.clock)
        ledger.activate("R2",opening_lots=(),source_bundle=opening_bundle(e.stores.snapshots.starting_state("R2"),at=at),by=OWNER,reason="M5 race fixture")
        def service(db,clock):
            selector=SourceSelector(db,clock=clock,command_clock=e.clock,calendar=CAL,provider="yfinance",
                coverage=lambda a,t:(coverage(t),),delivered_actions=lambda a,t:(),market_root=e.root)
            return AccountingService(db,clock=clock,command_clock=e.clock,sources=selector)
        core=service(e.stores.db,clock)
        worker_stores=e.connect(ReplayClock(at))
        worker_service=service(worker_stores.db,worker_stores.clock)
        broker=SnapshotBroker()
        worker=ExecutionWorker(worker_stores.db,clock=worker_stores.clock,broker=broker,kill_switch=KillSwitchReader(e.flag),
                                 accounting=worker_service,accounts=frozenset({"R2"}))
        worker.reads=build_gate_reads(worker_stores,worker.orders,knowledge=e.knowledge,calendar=CAL,
            fingerprints=DeclaredFingerprints(worker_stores.snapshots),accounting=worker_service)
        worker.step()
        core.synchronize("R2",at=at)
        worker.step()
        core.synchronize("R2",at=at)
        assert worker.orders.get(order.order_id)[1].state.value=="SUBMITTED"
        for n in range(RACE_REPETITIONS):
            decision=view_for(e.stores,e.reader,SESSIONS[60],tag=f"race-{n}",generated_at=at)
            message=broker.send("FILL",order.client_order_id,at,quantity="1",price="120.00",fill_id=f"race-fill-{n}")
            accepted=Fill(order.order_id,Decimal(1),Decimal(120),Decimal(0),"USD",at,at,at,message.fill.broker_fill_id,message.fill.provenance)
            before={r[0] for r in e.stores.db.fetchall("SELECT snapshot_id FROM portfolio_snapshots")}
            version=worker.orders.get(order.order_id)[1].aggregate_version
            barrier=threading.Barrier(2)
            results=[]
            failures=[]
            def fill(barrier=barrier,accepted=accepted,version=version,failures=failures):
                try:
                    barrier.wait(timeout=20)
                    assert worker.orders.record_fill(accepted,expected_aggregate_version=version) is FillOutcome.RECORDED
                except Exception as exc:
                    failures.append(type(exc).__name__)
            def proposal(barrier=barrier,decision=decision,results=results,failures=failures):
                try:
                    barrier.wait(timeout=20)
                    results.append(propose("R2",decision,at=at,stores=e.stores,knowledge=e.knowledge,calendar=CAL,
                        coverage=coverage(at),calendar_version="cal-1",code_version="race",correlation_id="race",
                        orders=core.orders,accounting=core))
                except Exception as exc:
                    failures.append(type(exc).__name__)
            threads=[threading.Thread(target=fill),threading.Thread(target=proposal)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
                assert not t.is_alive()
            assert not failures and len(results)==1
            after={r[0] for r in e.stores.db.fetchall("SELECT snapshot_id FROM portfolio_snapshots")}
            new=after-before
            if results[0].outcome.value=="PREREQUISITE_MISSING":
                assert "snapshot" in results[0].missing and not new
            else:
                assert len(new)==1
                saved=e.stores.snapshots.get(next(iter(new)))
                assert saved.cash==100000-120*n  # serialized before the concurrent fill, never after it
            worker.step()  # duplicate delivery is harmless; publish the independent updated capture
            core.outbox.publish_pending()
            worker.outbox.publish_pending()
            assert core.consumer.run_once(limit=1000).failed==0
            core.synchronize("R2",at=at)
            assert core.ready("R2",at).ready
        value=core.current_balances("R2",at)
        assert value.cash==94000 and value.positions==((NVDA,Decimal(50)),)
        assert not core.incidents.unresolved("R2")
        assert e.stores.db.fetchone("SELECT count(*) FROM ledger_batches WHERE account_id='UNRELATED'")[0]==0
    finally:
        e.close()
