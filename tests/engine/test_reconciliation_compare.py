"""M5-08: comparable prefixes, exact differences and normalized resting orders."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from investment_engine.ledger.sources import fill_reference
from investment_engine.oms.order_states import OrderState as S
from investment_engine.oms.orders import Fill
from investment_engine.reconciliation.compare import InternalOrders, compare, oms_fingerprint
from investment_engine.reconciliation.contracts import BrokerOpenOrder, BrokerPosition
from investment_engine.reconciliation.snapshots import SIM_CASH_BASIS
from tests.engine.test_ledger_portfolio import NVDA, T, value
from tests.engine.test_reconciliation_contracts import snapshot as fixture_snapshot
from tests.engine.test_simulated_broker import order


def snapshot(**changes):
    initial=fixture_snapshot(broker="simulated",broker_account_id="sim/R1",effective_at=T,taken_at=T,received_at=T,
                              cash=Decimal(99478),positions=(BrokerPosition(NVDA,Decimal(6),"SHARES"),),cash_basis=SIM_CASH_BASIS)
    return replace(initial,**changes)


def internal(snap=None,rows=(),**changes):
    snap=snap or snapshot()
    return replace(InternalOrders("R1",T,T,"sim/R1",snap.snapshot_id,"stored-worker-prefix",True,T,tuple(rows),()),**changes)


def result(snap=None,ledger=None,evidence=None):
    snap=snap or snapshot()
    return compare("R1",snapshot=snap,ledger_balances=ledger or value(),internal_orders=evidence or internal(snap),known_at=T)


def test_exact_complete_match_is_pure_and_pins_both_records():
    ledger,s=value(),snapshot()
    answer=result(s,ledger)
    assert answer.status=="MATCH" and answer.differences==() and answer.reasons==()
    assert answer.book_id==ledger.query.book_id and answer.snapshot_id==s.snapshot_id
    assert answer.oms_hash==oms_fingerprint(internal(s))
    assert ledger==value() and s==snapshot()


@pytest.mark.parametrize("changes,field",[
    ({"cash":Decimal("99478.0001")},"cash"),
    ({"positions":(BrokerPosition(NVDA,Decimal(7),"SHARES"),)},f"position:{NVDA}"),
    ({"execution_refs":("broker-extra-buy","broker-extra-sell")},"executions"),
])
def test_exact_seeded_discrepancies_have_no_tolerance(changes,field):
    s=snapshot(**changes)
    answer=result(s)
    assert answer.status=="MISMATCH"
    assert field in [d.field for d in answer.differences]
    assert all(answer.book_id in d.reason and answer.snapshot_id in d.reason for d in answer.differences)


@pytest.mark.parametrize("changes",[
    {"account_id":"R2"},{"broker_account_id":"sim/other"},{"cash_basis":"BUYING_POWER"},
    {"taken_at":T+timedelta(seconds=1),"received_at":T+timedelta(seconds=1)},
    {"effective_at":T-timedelta(seconds=1)},
    {"complete":False,"cash":None,"positions":None,"open_orders":None,"reasons":("coverage missing",)},
])
def test_incomparable_or_missing_source_never_passes(changes):
    s=snapshot(**changes)
    assert result(s).status=="INCOMPLETE"


def test_known_delivery_gap_is_incomplete_but_claimed_complete_missing_fill_is_mismatch():
    s=snapshot(execution_refs=("unconsumed-broker-fill",))
    incomplete=internal(s,prefix_complete=False,delivery_gaps=("worker budget stopped before unconsumed-broker-fill",))
    answer=result(s,evidence=incomplete)
    assert answer.status=="INCOMPLETE" and "unconsumed-broker-fill" in " ".join(answer.reasons)
    assert result(s,evidence=internal(s)).status=="MISMATCH"


def test_unknown_and_submitting_orders_cannot_claim_match_even_if_values_agree():
    o=order()
    for state in (S.UNKNOWN,S.SUBMITTING):
        assert result(evidence=internal(rows=((o,state,Decimal(0),()),))).status=="INCOMPLETE"


@pytest.mark.parametrize("state,broker_status",[(S.SUBMITTED,"OPEN"),(S.CANCEL_PENDING,"OPEN"),(S.CANCEL_PENDING,"CANCEL_RECEIVED")])
def test_resting_order_statuses_are_normalized_not_compared_as_raw_strings(state,broker_status):
    o=order()
    reported=BrokerOpenOrder(o.order_id,o.client_order_id,o.instrument_id,o.side.value,broker_status,o.quantity)
    s=snapshot(open_orders=(reported,))
    assert result(s,evidence=internal(s,rows=((o,state,Decimal(0),()),))).status=="MATCH"
    mismatch=replace(reported,remaining=Decimal(9))
    altered=snapshot(open_orders=(mismatch,))
    assert result(altered,evidence=internal(altered,rows=((o,state,Decimal(0),()),))).status=="MISMATCH"


def test_new_order_does_not_change_reconcilable_oms_hash_but_foreign_broker_order_does():
    o=order()
    empty=internal()
    added=internal(rows=((o,S.NEW,Decimal(0),()),))
    assert oms_fingerprint(empty)==oms_fingerprint(added)
    assert result(evidence=added).status=="MATCH"
    s=snapshot(open_orders=(BrokerOpenOrder(o.order_id,o.client_order_id,o.instrument_id,"BUY","OPEN",o.quantity),))
    assert result(s,evidence=internal(s)).status=="MISMATCH"


def test_future_fill_is_excluded_from_earlier_cutoff_and_unknown_accounting_is_not_zero():
    o=order()
    future=Fill(o.order_id,Decimal(1),Decimal(1),Decimal(0),"USD",T,T+timedelta(days=1),T+timedelta(days=1),"future","{}")
    assert result(evidence=internal(rows=((o,S.CANCELLED,Decimal(0),(future,)),))).status=="MATCH"
    missing=value(complete=False,reasons=("new accepted fill has no established cost",))
    answer=result(ledger=missing)
    assert answer.status=="INCOMPLETE" and "cost" in " ".join(answer.reasons)


def test_known_accepted_fill_must_be_posted_and_prefix_must_name_this_capture():
    o=order()
    f=Fill(o.order_id,Decimal(10),Decimal(1),Decimal(0),"USD",T,T,T,"accepted","{}")
    s=snapshot(execution_refs=("accepted",))
    rows=((o,S.FILLED,Decimal(10),(f,)),)
    assert result(s,evidence=internal(s,rows=rows)).status=="INCOMPLETE"
    posted=value(sources=(fill_reference(o,f),))
    assert result(s,ledger=posted,evidence=internal(s,rows=rows)).status=="MATCH"
    assert result(s,ledger=posted,evidence=internal(s,rows=rows,snapshot_id="older-capture")).status=="INCOMPLETE"


def test_hostile_decimal_context_cannot_round_remaining_quantity_or_oms_hash():
    o=order(qty="1000")
    f=Fill(o.order_id,Decimal(1),Decimal(1),Decimal(0),"USD",T,T,T,"partial","{}")
    reported=BrokerOpenOrder(o.order_id,o.client_order_id,o.instrument_id,"BUY","OPEN",Decimal(999))
    s=snapshot(execution_refs=("partial",),open_orders=(reported,))
    evidence=internal(s,rows=((o,S.PARTIALLY_FILLED,Decimal(1),(f,)),))
    ledger=value(sources=(fill_reference(o,f),))
    expected=result(s,ledger,evidence)
    with localcontext() as ctx:
        ctx.prec=1
        ctx.traps[Inexact]=ctx.traps[Rounded]=True
        actual=result(s,ledger,evidence)
    assert actual==expected and actual.status=="MATCH"
