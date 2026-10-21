"""M5-07: broker account evidence is independent of internal accounting/OMS fills."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.execution.simulated_broker import FeeSchedule, SimulatedBroker
from investment_engine.market.corporate_actions import ActionType
from investment_engine.money import Money
from investment_engine.oms.intents import Side
from investment_engine.policy.accounts import AccountRegistry
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
from investment_engine.reconciliation.snapshots import BrokerSetupStore
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.test_ledger_actions import corporate, coverage
from tests.engine.test_simulated_broker import BEFORE, CAL, CLOSE, DAY, OPEN, Knowledge, bar, order

pytestmark=pytest.mark.postgres
OWNER=Actor(ActorKind.OPERATOR,"owner","ADMIN","test")


class Market(Knowledge):
    def __init__(self,*revisions,actions=()):
        super().__init__(*revisions)
        self.actions=actions

    def first_known_closed(self,source,instrument_id,session,*,not_after,calendar=None):
        start=CAL.session(session).open
        matching=[r for r in self.revisions if r[0]<=not_after and r[1].start_time==start]
        return matching[0] if matching else None

    def actions_between(self,source,instrument_id,first,last,*,at):
        return [a for a in self.actions if a.source==source and a.instrument_id==instrument_id and first<=a.ex_date<=last and a.available_from<=at]


@pytest.fixture
def env(pg_database):
    conn=open_operational_pg(pg_database)
    apply_pg_schema(conn)
    db=PostgresDatabase(conn)
    clock=ReplayClock(BEFORE)
    audit=AuditStore(db)
    accounts=AccountRegistry(db,audit,clock)
    accounts.bootstrap_admin("owner",os_user="test")
    from investment_engine.policy.accounts import AccountKind
    states=PortfolioSnapshotStore(db,audit,accounts,clock)
    for name in ("R1","R2"):
        accounts.create_account(name,AccountKind.RESEARCH,"USD",by=OWNER,reason="synthetic research",effective_at=BEFORE)
        states.declare_start(name,by=OWNER,reason="declared initial cash",effective_at=BEFORE)
    setups=BrokerSetupStore(db,audit=audit,accounts=accounts,states=states,command_clock=clock)
    evidence=coverage(BEFORE).evidence_refs
    for name in ("R1","R2"):
        setups.request(name,source="yfinance",coverage_evidence=evidence,by=OWNER,reason="explicit independent simulator seed")
    yield db,clock
    conn.close()


def broker(db,market,account="R1"):
    return SimulatedBroker(db,knowledge=market,calendar=CAL,source="yfinance",fees=FeeSchedule("fee-test",Decimal(1),Decimal(0)),account_id=account)


def test_independent_cash_and_shares_after_real_broker_fill_fee_cancel_and_two_accounts(env):
    db,_=env
    b=broker(db,Market((CLOSE,bar("100","120","90"))))
    initial=b.snapshot("R1",at=BEFORE)
    assert initial.complete and initial.cash==100000 and initial.positions==()
    o=order(qty="10")
    assert b.submit(o,at=BEFORE).accepted
    resting=b.snapshot("R1",at=OPEN)
    assert resting.complete and len(resting.open_orders)==1 and resting.cash==100000
    filled=b.snapshot("R1",at=CLOSE)
    assert filled.cash==98999 and filled.positions[0].quantity==10
    assert len(filled.execution_refs)==1 and filled.open_orders==()
    assert b.snapshot("R1",at=CLOSE)==filled
    untouched=broker(db,Market(),account="R2").snapshot("R2",at=CLOSE)
    assert untouched.cash==100000 and untouched.positions==()
    assert db.fetchone("SELECT count(*) FROM fills")[0]==0  # worker has not ingested anything
    assert db.fetchone("SELECT count(*) FROM ledger_entries")[0]==0
    # Public internal declarations remain unrelated to broker's now-filled account.
    db.execute("CREATE TEMP TABLE unrelated_internal_state (cash NUMERIC)")
    db.execute("INSERT INTO unrelated_internal_state VALUES (1)")
    assert b.snapshot("R1",at=CLOSE).cash==98999
    cancelled=replace(order(n=2),target_session=CAL.next_session(DAY).date)
    assert b.submit(cancelled,at=CLOSE).accepted
    b.cancel(cancelled.client_order_id,at=CLOSE)
    assert b.snapshot("R1",at=CLOSE).cash==98999


def test_unscoped_wrong_account_missing_seed_and_retrograde_request_are_not_complete(env):
    db,_=env
    market=Market()
    unscoped=broker(db,market,account=None)
    assert not unscoped.snapshot("R1",at=BEFORE).complete
    b=broker(db,market)
    assert not b.snapshot("R2",at=BEFORE).complete
    assert b.snapshot("R1",at=CLOSE).complete
    assert not b.snapshot("R1",at=BEFORE).complete


def test_split_and_unpaid_dividend_use_broker_private_sources_only(env):
    db,_=env
    next_day=CAL.next_session(DAY)
    split=corporate(ex_date=next_day.date,known=next_day.open-timedelta(hours=1),ratio=Decimal(10))
    dividend=corporate(ActionType.DIVIDEND,ex_date=CAL.next_session(next_day.date).date,
                        known=CAL.next_session(next_day.date).open-timedelta(hours=1),amount=Money(Decimal(".1"),"USD"))
    market=Market((CLOSE,bar("100","120","90")),actions=(split,dividend))
    b=broker(db,market)
    b.submit(order(),at=BEFORE)
    assert b.snapshot("R1",at=CLOSE).positions[0].quantity==10
    split_snapshot=b.snapshot("R1",at=next_day.open)
    assert split_snapshot.positions[0].quantity==100 and split_snapshot.cash==98999
    after=b.snapshot("R1",at=CAL.next_session(next_day.date).open)
    assert after.cash==98999 and after.positions[0].quantity==100
    assert after.raw_hash!=split_snapshot.raw_hash
    assert db.fetchone("SELECT count(*) FROM sim_broker.account_actions")[0]==2


def test_private_execution_changes_are_visible_without_oms_or_ledger_repairs(env):
    db,_=env
    b=broker(db,Market((CLOSE,bar("100","120","90"))))
    b.submit(order(),at=BEFORE)
    b.snapshot("R1",at=CLOSE)
    # Append an additional vendor execution fact, not an internal journal adjustment.
    db.execute("INSERT INTO sim_broker.account_executions SELECT broker_fill_id || '-extra',account_id,instrument_id,side,"
               "quantity,price,fee,currency,executed_at,known_at,"
               "(content::jsonb || jsonb_build_object('broker_fill_id',broker_fill_id || '-extra'))::text "
               "FROM sim_broker.account_executions")
    changed=b.snapshot("R1",at=CLOSE)
    assert changed.cash==97998 and changed.positions[0].quantity==20
    assert len(changed.execution_refs)==2


def test_buy_and_sell_with_fees_reproduce_cash_99478_and_six_shares(env):
    db,_=env
    next_session=CAL.next_session(DAY)

    class DailyMarket(Market):
        def first_known_closed(self,source,instrument_id,session,*,not_after,calendar=None):
            target=CAL.session(session)
            if target.close>not_after:
                return None
            price="100" if session==DAY else "120"
            return target.close,replace_bar(price,target)

    def replace_bar(price,session):
        value=bar(price,str(Decimal(price)+1),str(Decimal(price)-1))
        value.start_time=session.open
        return value

    b=broker(db,DailyMarket())
    b.submit(order(),at=BEFORE)
    assert b.snapshot("R1",at=CLOSE).cash==98999
    sale=replace(order(n=2,side=Side.SELL,limit="120",qty="4"),target_session=next_session.date)
    assert b.submit(sale,at=CLOSE).accepted
    result=b.snapshot("R1",at=next_session.close)
    assert result.complete and result.cash==99478 and result.positions[0].quantity==6


def test_wrong_accepted_internal_fill_does_not_rewrite_independent_broker_facts(pg_database):
    from investment_engine.oms.order_states import OrderState as S
    from tests.engine.test_order_store import OWNER as actual_owner, Env

    e=Env(pg_database)
    try:
        audit=AuditStore(e.db)
        states=PortfolioSnapshotStore(e.db,audit,e.accounts,e.clock)
        states.declare_start("R1",by=actual_owner,reason="synthetic declared start",effective_at=BEFORE)
        setups=BrokerSetupStore(e.db,audit=audit,accounts=e.accounts,states=states,command_clock=e.clock)
        setups.request("R1",source="yfinance",coverage_evidence=coverage(BEFORE).evidence_refs,
                        by=actual_owner,reason="explicit independent seed")
        b=broker(e.db,Market((CLOSE,bar("100","120","90"))))
        b.submit(order(),at=BEFORE)
        original=b.snapshot("R1",at=CLOSE)
        internal=e.created()
        e.walk(internal,S.SUBMITTING,S.SUBMITTED)
        e.fill(internal,price="1",fill_id="bad-internal-ingestion")
        assert e.core.fills(internal.order_id)[0].price==1
        from investment_engine.events.outbox import Outbox
        from investment_engine.ledger.balances import balances
        from investment_engine.ledger.postings import post_fill
        from investment_engine.ledger.sources import opening_bundle
        from investment_engine.ledger.store import LedgerStore
        from investment_engine.oms.order_states import ProcessRole

        ledger=LedgerStore(e.db,audit=audit,outbox=Outbox(e.db,writer=ProcessRole.CORE,clock=e.clock),clock=e.clock,command_clock=e.clock)
        ledger.activate("R1",opening_lots=(),source_bundle=opening_bundle(states.starting_state("R1"),at=e.clock.now()),
                         by=actual_owner,reason="explicit ledger activation for fault probe")
        posted=post_fill(internal,e.core.fills(internal.order_id)[0],ledger=ledger,orders=e.core)
        internal_balance=balances("R1",effective_at=e.clock.now(),known_at=e.clock.now(),book_id=posted.book_id,ledger=ledger)
        assert internal_balance.cash==99990
        result=b.snapshot("R1",at=e.clock.now())
        assert result.complete and result.cash==original.cash==98999 and result.positions[0].quantity==10
        assert balances("R1",effective_at=e.clock.now(),known_at=e.clock.now(),book_id=posted.book_id,ledger=ledger).cash==99990
    finally:
        e.close()


@pytest.mark.parametrize("column,value",[("quantity",Decimal("NaN")),("price",Decimal("Infinity")),
                                         ("fee",Decimal("NaN")),("known_at",OPEN-timedelta(seconds=1))])
def test_private_execution_sql_rejects_nonfinite_or_premature_facts(env,column,value):
    from psycopg import Error as PgError

    db,_=env
    b=broker(db,Market((CLOSE,bar("100","120","90"))))
    b.submit(order(),at=BEFORE)
    b.snapshot("R1",at=CLOSE)
    columns=["broker_fill_id","account_id","instrument_id","side","quantity","price","fee","currency","executed_at","known_at","content"]
    selected=["broker_fill_id || '-invalid'" if c=="broker_fill_id" else "%s" if c==column else c for c in columns]
    with pytest.raises(PgError),db.connection.transaction():
        db.connection.execute("INSERT INTO sim_broker.account_executions SELECT "+",".join(selected)+" FROM sim_broker.account_executions",(value,))


def test_identical_research_setup_on_different_command_days_keeps_snapshot_identity(pg_database):
    from investment_engine.policy.accounts import AccountKind
    from tests.engine.conftest import maintenance_dsn, temporary_database
    def capture(dsn,delay):
        conn=open_operational_pg(dsn)
        try:
            apply_pg_schema(conn)
            db=PostgresDatabase(conn)
            command=ReplayClock(BEFORE+timedelta(days=delay))
            audit=AuditStore(db)
            accounts=AccountRegistry(db,audit,command)
            accounts.bootstrap_admin("owner",os_user="test")
            accounts.create_account("R1",AccountKind.RESEARCH,"USD",by=OWNER,reason="same research account",effective_at=BEFORE)
            states=PortfolioSnapshotStore(db,audit,accounts,command)
            states.declare_start("R1",by=OWNER,reason="same declared cash",effective_at=BEFORE)
            setup=BrokerSetupStore(db,audit=audit,accounts=accounts,states=states,command_clock=command).request(
                "R1",source="yfinance",coverage_evidence=(),by=OWNER,reason="same approved setup")
            value=broker(db,Market()).snapshot("R1",at=BEFORE)
            return setup,value
        finally:
            conn.close()
    first_setup,first=capture(pg_database,5)
    with temporary_database(maintenance_dsn()) as second_dsn:
        second_setup,second=capture(second_dsn,6)
    assert first_setup.command_at!=second_setup.command_at
    assert first_setup.setup_id==second_setup.setup_id
    assert first.snapshot_id==second.snapshot_id
    assert first==second
