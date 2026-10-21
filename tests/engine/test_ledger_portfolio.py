"""M5-06: authoritative accounting projections and OMS economic reservations."""
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    BalanceQuery,
    LedgerBalances,
    SourceRef,
)
from investment_engine.ledger.fingerprint import LedgerFingerprints, project
from investment_engine.lineage.records import canonical_json, decode
from investment_engine.oms.order_states import OrderState as S
from investment_engine.portfolio.reference import Unavailable
from investment_engine.portfolio.snapshot import SnapshotSource, StartingState, build_snapshot
from tests.engine.test_candles import bar
from tests.engine.test_ledger_actions import CAL, NVDA
from tests.engine.test_provisional_positions import Orders

T = datetime(2024,6,7,20,tzinfo=UTC)


def value(**changes):
    return replace(LedgerBalances(BalanceQuery("R1",T,T,"book-1"),Decimal(99478),"USD",((NVDA,Decimal(6)),),
                                  ((NVDA,Decimal(600)),),(),Decimal(80),Decimal(0),Decimal(2),(),True,()),**changes)


def orders():
    result = Orders()
    result.add(1,qty="10",limit="100",created=T,history=((T,S.NEW,"0"),))
    result.add(2,side="SELL",qty="2",limit="120",created=T,history=((T,S.UNKNOWN,"0"),))
    return result


class Knowledge:
    def latest_closed(self,source,instrument_id,session,*,at,calendar):
        s = calendar.session(session)
        return bar(source=source,start_time=s.open,end_time=s.close,event_time=s.close,available_from=s.close,
                   received_at=s.close,processed_at=s.close,open=Decimal(125),high=Decimal(125),low=Decimal(125),close=Decimal(125))


def starting():
    return StartingState("R1",datetime(2019,1,2,tzinfo=UTC),T,Decimal(100000),"USD",(),"owner","declared")


def snapshot(projection,**kwargs):
    return build_snapshot("R1",at=T,starting=starting(),knowledge=Knowledge(),calendar=CAL,coverage=None,
                          last_clear=None,history=[],source="yfinance",projection=projection,**kwargs)


def test_new_ledger_snapshot_uses_six_shares_and_99478_cash_with_oms_reservations():
    pending = orders()
    result = snapshot(value(),ledger_orders=pending)
    assert result.source is SnapshotSource.LEDGER
    assert result.cash == 99478 and result.held(NVDA) == 6 and result.equity == 100228
    assert result.available_cash() == 98478 and result.available_shares(NVDA) == 4
    assert result.pending_buy_value(NVDA) == 1000
    assert result.ledger_book_id == "book-1" and result.ledger_query_id == value().query.query_id
    import json
    assert decode(json.loads(canonical_json(result))) == result


def test_pending_buys_consume_cap_space_and_pending_unknown_sell_never_frees_holdings():
    pending = orders()
    pending.add(3,qty="20",limit="101",created=T,history=((T,S.UNKNOWN,"0"),))
    result = snapshot(value(),ledger_orders=pending)
    assert result.pending_buy_value(NVDA) == 3020
    assert result.held(NVDA) == 6 and result.available_shares(NVDA) == 4
    adapter = LedgerFingerprints(lambda account,at:value(), pending)
    with_self = adapter.at("R1",T,excluding_order=None)
    without_self = adapter.at("R1",T,excluding_order=pending.orders[0].order_id)
    projected = project(value(),orders=pending,account_id="R1",at=T)
    assert with_self == projected.fingerprint()
    assert without_self == projected.fingerprint(excluding_order=pending.orders[0].order_id)
    assert with_self != without_self


def test_missing_ledger_readiness_cost_or_reservation_input_never_falls_back():
    assert isinstance(snapshot(value()),Unavailable)
    missing = AccountingUnavailable("R1",T,("basis missing",))
    adapter = LedgerFingerprints(lambda account,at:missing,orders())
    assert isinstance(adapter.at("R1",T,excluding_order=None),Unavailable)
    incomplete = value(complete=False,reasons=("action coverage missing",))
    assert isinstance(snapshot(incomplete,ledger_orders=orders()),Unavailable)
    assert isinstance(snapshot(value(query=BalanceQuery("R1",T,T.replace(hour=21),"book-1")),ledger_orders=orders()),Unavailable)
    assert isinstance(snapshot(value(costs=()),ledger_orders=orders()),Unavailable)


def test_post_action_raw_mark_and_unresolved_order_basis_wait_fail_closed():
    at = CAL.session(date(2024,6,10)).open
    ref = SourceRef("action","yfinance/EQ_US_NVDA/SPLIT/2024-06-10",1,"split","a"*64,at,at,at,"yfinance")
    v = value(query=BalanceQuery("R1",at,at,"split-book"),positions=((NVDA,Decimal(60)),),sources=(ref,))
    pending = Orders()
    pending.add(1,created=T,history=((T,S.UNKNOWN,"0"),))
    assert isinstance(project(v,orders=pending,account_id="R1",at=at),Unavailable)
    result = build_snapshot("R1",at=at,starting=starting(),knowledge=Knowledge(),calendar=CAL,coverage=None,
                            last_clear=None,history=[],source="yfinance",projection=v,ledger_orders=Orders())
    assert isinstance(result,Unavailable)


def test_clear_epoch_and_floor_unchanged_for_ledger_source():
    from investment_engine.risk.limits import Halt

    clear = Halt("R1",False,T,"owner","clear","limits-v1",Decimal(110000))
    result = build_snapshot("R1",at=T,starting=starting(),knowledge=Knowledge(),calendar=CAL,coverage=None,
                            last_clear=clear,history=[],source="yfinance",projection=value(),ledger_orders=Orders())
    assert result.peak_equity == 110000 and result.baseline_at == T


def test_actual_risk_position_check_counts_ledger_pending_buys():
    from tests.engine.test_risk_checks import decide
    from tests.engine.test_sizer import sized

    pending = Orders()
    pending.add(1,qty="100",limit="100",created=T,history=((T,S.UNKNOWN,"0"),))
    result = snapshot(value(),ledger_orders=pending)
    decision,_ = decide(replace(sized().intent,quantity=Decimal(1)),s=result)
    position = next(c for c in decision.checks if c.name == "position")
    assert not position.passed
    assert result.held(NVDA) == 6 and result.pending_buy_value(NVDA) == 10000
