"""M5-05: pinned effective/knowledge queries and explicit raw-mark P&L."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.ledger.balances import balances, value_balances
from investment_engine.ledger.contracts import AccountingUnavailable
from investment_engine.ledger.postings import post_fill
from investment_engine.ledger.sources import opening_bundle
from investment_engine.lineage.records import canonical_json
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.oms.order_states import OrderState as S
from investment_engine.oms.orders import Fill, FillOutcome
from tests.engine.test_candles import bar
from tests.engine.test_fill_postings import Cost400
from tests.engine.test_ledger_activation import activate, env as env
from tests.engine.test_order_store import OWNER

pytestmark = pytest.mark.postgres
CAL = load_us_equities_calendar()
NVDA = "EQ_US_NVDA"


def accepted(e, side, quantity, price, *, executed, recorded, fee="1", broker_id="f"):
    e.clock.advance_to(recorded)
    order = e.created(side=side, quantity=quantity)
    status = e.walk(order, S.SUBMITTING, S.SUBMITTED)
    fill = Fill(order.order_id, Decimal(quantity), Decimal(price), Decimal(fee), "USD", executed, recorded, recorded,
                broker_id, "{}")
    assert e.worker.record_fill(fill, expected_aggregate_version=status.aggregate_version) is FillOutcome.RECORDED
    return order, fill


def example(e):
    opening = activate(e)
    initial = e.clock.now()
    close = CAL.session(initial.date()).close
    buy, first = accepted(e, "BUY", "10", "100", executed=initial + timedelta(hours=4), recorded=close, broker_id="buy")
    purchase = post_fill(buy, first, ledger=e.ledger, orders=e.core)
    sell, second = accepted(e, "SELL", "4", "120", executed=initial + timedelta(hours=5),
                            recorded=close + timedelta(microseconds=1), broker_id="sell")
    sale = post_fill(sell, second, ledger=e.ledger, orders=e.core, cost_basis=Cost400())
    return initial, close, opening, purchase, sale


def test_effective_time_and_knowledge_cutoff_are_independent_and_never_fallback(env):
    initial, close, opening, purchase, sale = example(env)
    later = env.clock.now()
    before_execution = balances("R1", effective_at=initial, known_at=later, book_id=sale.book_id, ledger=env.ledger)
    assert before_execution.cash == 100000 and before_execution.positions == ()
    at_first_capture = balances("R1", effective_at=close, known_at=close, book_id=purchase.book_id, ledger=env.ledger)
    assert at_first_capture.cash == 98999 and at_first_capture.positions == ((NVDA, Decimal(10)),)
    unavailable = balances("R1", effective_at=close, known_at=close, book_id=sale.book_id, ledger=env.ledger)
    assert isinstance(unavailable, AccountingUnavailable)
    assert isinstance(balances("R2", effective_at=close, known_at=later, book_id=sale.book_id, ledger=env.ledger), AccountingUnavailable)
    assert balances("R1", effective_at=close, known_at=later, book_id=opening.book_id, ledger=env.ledger).cash == 100000


def test_adr_pnl_identity_and_missing_marks_are_not_zero(env):
    _, close, _, _, sale = example(env)
    value = balances("R1", effective_at=close, known_at=env.clock.now(), book_id=sale.book_id, ledger=env.ledger)
    assert (value.cash, value.gross_realized, value.fees) == (Decimal(99478), Decimal(80), Decimal(2))
    assert value.costs == ((NVDA, Decimal(600)),)
    session = CAL.session(close.date())
    mark = bar(start_time=session.open, end_time=session.close, event_time=session.close, available_from=session.close,
               received_at=close, processed_at=close, open=Decimal(125), high=Decimal(125), low=Decimal(125), close=Decimal(125))
    report = value_balances(value, marks={NVDA: (mark, close)}, calendar=CAL, source="yfinance", ledger=env.ledger)
    assert report.complete
    assert (report.market_value, report.unrealized, report.equity, report.net_pnl) == (Decimal(750), Decimal(150), Decimal(100228), Decimal(228))
    assert report.equity - report.opening_capital == report.net_pnl
    missing = value_balances(value, marks={}, calendar=CAL, source="yfinance", ledger=env.ledger)
    assert not missing.complete and missing.unrealized is missing.equity is missing.net_pnl is None
    assert missing.balances.cash == 99478
    late = value_balances(value, marks={NVDA: (mark, close + timedelta(days=1))}, calendar=CAL, source="yfinance", ledger=env.ledger)
    assert not late.complete and late.net_pnl is None
    wrong = value_balances(value, marks={NVDA: (replace(mark, source="other"), close)}, calendar=CAL, source="yfinance", ledger=env.ledger)
    assert not wrong.complete


def test_same_timestamp_later_arrival_cannot_change_an_old_pinned_book(env):
    activate(env)
    at = CAL.session(env.clock.now().date()).close
    order, fill = accepted(env, "BUY", "1", "10", executed=at, recorded=at, fee="0", broker_id="same1")
    first = post_fill(order, fill, ledger=env.ledger, orders=env.core)
    original = balances("R1", effective_at=at, known_at=at, book_id=first.book_id, ledger=env.ledger)
    encoded = canonical_json(original)
    order, fill = accepted(env, "BUY", "2", "20", executed=at, recorded=at, fee="0", broker_id="same2")
    second = post_fill(order, fill, ledger=env.ledger, orders=env.core)
    assert canonical_json(balances("R1", effective_at=at, known_at=at, book_id=first.book_id, ledger=env.ledger)) == encoded
    assert balances("R1", effective_at=at, known_at=at, book_id=second.book_id, ledger=env.ledger).positions == ((NVDA, Decimal(3)),)


def test_cash_only_initial_condition_needs_no_mark_or_previous_calendar_year(env):
    start = env.snapshots.declare_start("R1",by=OWNER,reason="initial cash only",
                                        effective_at=datetime(2019,1,2,tzinfo=UTC))
    head = env.ledger.activate("R1",opening_lots=(),source_bundle=opening_bundle(start,at=env.clock.now()),
                              by=OWNER,reason="explicit activation")
    value = balances("R1",effective_at=start.effective_at,known_at=env.clock.now(),book_id=head.book_id,ledger=env.ledger)
    result = value_balances(value,marks={},calendar=CAL,source="yfinance",ledger=env.ledger)
    assert result.complete and result.equity == 100000 and result.net_pnl == 0
