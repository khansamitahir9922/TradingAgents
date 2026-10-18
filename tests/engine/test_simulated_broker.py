"""The simulated broker's causal daily model (docs/tasks/M4-06.md rules 2–9)."""

import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from investment_engine.execution.simulated_broker import FeeSchedule, SimulatedBroker
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.oms.intents import Side
from investment_engine.oms.orders import Order, order_ids
from investment_engine.policy.accounts import AccountKind
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg

pytestmark = pytest.mark.postgres
CAL = load_us_equities_calendar()
DAY = date(2024, 3, 5)
SESSION = CAL.session(DAY)
OPEN, CLOSE = SESSION.open, SESSION.close
CUTOFF = CAL.next_session(DAY).open
BEFORE = OPEN - timedelta(hours=2)
FEES = FeeSchedule("fees-1", Decimal("0"), Decimal("5"))


def bar(o, h, low, revision=1):
    return SimpleNamespace(open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(o), source="yfinance",
                           instrument_id="EQ_US_NVDA", timeframe="D1", start_time=OPEN, revision=revision,
                           import_id=f"imp-{revision}")


class Knowledge:
    """Scripted first-known revisions: [(known_at, bar)], the earliest known one at or before `not_after` wins."""

    def __init__(self, *revisions):
        self.revisions = sorted(revisions, key=lambda r: r[0])

    def first_known_closed(self, source, instrument_id, session, *, not_after, calendar=None):
        known = [r for r in self.revisions if r[0] <= not_after]
        return known[0] if known else None


@pytest.fixture
def db(pg_database):
    conn = open_operational_pg(pg_database)
    apply_pg_schema(conn)
    yield PostgresDatabase(conn)
    conn.close()


def broker(db, *revisions):
    return SimulatedBroker(db, knowledge=Knowledge(*revisions), calendar=CAL, source="yfinance", fees=FEES)


def order(n=1, side=Side.BUY, limit="100.00", qty="10"):
    return Order(*order_ids(f"int-{n}", 1), f"int-{n}", 1, "c", "f", "R1", AccountKind.RESEARCH, "EQ_US_NVDA",
                 side, Decimal(qty), "LIMIT", Decimal(limit), "DAY", DAY, BEFORE - timedelta(hours=1))


def kinds(b, at):
    return [(m.kind, m.delivered_at) for m in b.messages(after=None, at=at)]


def fill_of(b, at):
    (m,) = [m for m in b.messages(after=None, at=at) if m.kind == "FILL"]
    return m.fill, json.loads(m.fill.provenance)


# ---------------------------------------------------------------- the fill table (rule 3)


@pytest.mark.unit
@pytest.mark.parametrize("side, limit, o, h, low, price, executed, timing", [
    (Side.BUY, "100.00", "99.00", "101", "98", "99.05", "open", "AT_OPEN"),   # 99 x 1.0005 = 99.0495 -> 99.05
    (Side.BUY, "100.00", "99.98", "101", "98", "100.00", "open", "AT_OPEN"),  # 100.02999 capped at the limit
    (Side.BUY, "100.00", "103.00", "104", "99.5", "100.00", "close", "INTRADAY_UNKNOWN"),
    (Side.SELL, "100.00", "101.00", "102", "99", "100.95", "open", "AT_OPEN"),  # 101 x 0.9995 = 100.9495 -> 100.95
    (Side.SELL, "100.00", "97.00", "100.5", "96", "100.00", "close", "INTRADAY_UNKNOWN"),
])
def test_the_daily_fill_table(db, side, limit, o, h, low, price, executed, timing):
    b = broker(db, (CLOSE + timedelta(minutes=10), bar(o, h, low)))
    assert b.submit(order(side=side, limit=limit), at=BEFORE).accepted
    fill, provenance = fill_of(b, CUTOFF)
    assert fill.price == Decimal(price) and fill.quantity == Decimal(10) and fill.fee == Decimal(0)
    assert fill.executed_at == (OPEN if executed == "open" else CLOSE)
    assert provenance["timing"] == timing and provenance["bar"]["revision"] == 1 and provenance["fees"] == "fees-1"


@pytest.mark.unit
def test_a_limit_never_reached_expires_and_an_intraday_touch_is_never_stamped_at_the_open(db):
    b = broker(db, (CLOSE + timedelta(minutes=10), bar("105", "106", "101")))
    b.submit(order(), at=BEFORE)
    assert kinds(b, CUTOFF) == [("ACK", BEFORE), ("EXPIRED", CLOSE + timedelta(minutes=10))]


@pytest.mark.unit
def test_a_submit_at_or_after_the_open_is_rejected(db):
    b = broker(db)
    result = b.submit(order(), at=OPEN)
    assert not result.accepted and "rest from the open" in result.reason


# ---------------------------------------------------------------- the decision moment (V1)


@pytest.mark.unit
def test_nothing_is_delivered_before_the_bar_is_known_and_later_corrections_are_ignored(db):
    known = CLOSE + timedelta(minutes=10)  # e.g. available 20:00, delivered 20:10 with replay latency
    b = broker(db, (known, bar("99", "101", "98", revision=1)), (known + timedelta(hours=1), bar("50", "51", "49", 2)))
    b.submit(order(), at=BEFORE)
    assert kinds(b, known - timedelta(microseconds=1)) == [("ACK", BEFORE)]
    early, _ = fill_of(b, known)
    late_broker = broker(db, (known, bar("99", "101", "98", revision=1)), (known + timedelta(hours=1), bar("50", "51", "49", 2)))
    late, provenance = fill_of(late_broker, CUTOFF)  # polled late, after the correction arrived
    assert early == late and provenance["bar"]["revision"] == 1 and provenance["decided_at"] == known.isoformat()


@pytest.mark.unit
def test_a_bar_known_only_after_the_cutoff_counts_as_missing(db):
    b = broker(db, (CUTOFF + timedelta(minutes=1), bar("99", "101", "98")))
    b.submit(order(), at=BEFORE)
    messages = b.messages(after=None, at=CUTOFF + timedelta(hours=2))
    assert [(m.kind, m.delivered_at) for m in messages] == [("ACK", BEFORE), ("EXPIRED", CUTOFF)]
    assert "no market data" in messages[-1].reason


# ---------------------------------------------------------------- cancels (R1, V2)


@pytest.mark.unit
def test_a_cancel_before_the_open_is_conclusive_without_any_price(db):
    b = broker(db)  # no bar at all: nothing to read
    b.submit(order(), at=BEFORE)
    result = b.cancel(order().client_order_id, at=BEFORE + timedelta(minutes=5))
    assert result.outcome == "CANCELLED" and kinds(b, BEFORE + timedelta(minutes=5))[-1][0] == "CANCELLED"


@pytest.mark.unit
def test_the_same_pending_answer_before_the_bar_then_distinct_outcomes(db, pg_database):
    """R1: BUY limit 100, cancel at 10:00. Bar (a) opens at 90; bar (b) opens 110 and touches 95."""
    ten = OPEN + timedelta(minutes=30)
    known = CLOSE + timedelta(minutes=10)
    outcomes = []
    for n, the_bar in ((1, bar("90", "95", "89")), (2, bar("110", "111", "95"))):
        b = broker(db, (known, the_bar))
        o = order(n)
        b.submit(o, at=BEFORE)
        pending = b.cancel(o.client_order_id, at=ten)
        assert (pending.outcome, pending.received_at) == ("PENDING", ten)
        assert b.lookup(o.client_order_id, at=ten).status == "CANCEL_RECEIVED"
        assert [m.kind for m in b.messages(after=None, at=known - timedelta(seconds=1))
                if m.client_order_id == o.client_order_id] == ["ACK"]
        outcomes.append([m.kind for m in b.messages(after=None, at=known) if m.client_order_id == o.client_order_id])
    assert outcomes == [["ACK", "FILL"], ["ACK", "CANCELLED"]]


@pytest.mark.unit
def test_a_retry_or_a_restart_keeps_the_first_receipt_time(db):
    ten = OPEN + timedelta(minutes=30)
    b = broker(db, (CLOSE + timedelta(minutes=10), bar("110", "111", "95")))
    b.submit(order(), at=BEFORE)
    b.cancel(order().client_order_id, at=ten)
    again = b.cancel(order().client_order_id, at=ten + timedelta(minutes=20))
    restarted = broker(db, (CLOSE + timedelta(minutes=10), bar("110", "111", "95")))
    assert again.received_at == ten and restarted.cancel(order().client_order_id, at=ten + timedelta(hours=1)).received_at == ten


@pytest.mark.unit
@pytest.mark.parametrize("offset, outcome", [(-1, "PENDING"), (0, "TOO_LATE"), (30 * 60, "TOO_LATE")],
                         ids=["just-before", "exactly-at", "after"])
@pytest.mark.parametrize("polling", ["frequent", "first-poll-late"])
def test_late_cancels_never_rewrite_a_decided_outcome(db, offset, outcome, polling):
    """V2: BUY limit 100, open 110, low 95, bar known at 16:00 exchange time (D)."""
    decided = CLOSE  # 16:00 exchange time
    b = broker(db, (decided, bar("110", "111", "95")))
    b.submit(order(), at=BEFORE)
    c = decided + timedelta(seconds=offset)
    if polling == "frequent":  # every poll before the cancel's own time: the clock only moves forward
        poll = OPEN + timedelta(minutes=30)
        while poll < c:
            b.messages(after=None, at=poll)
            poll += timedelta(minutes=45)
    result = b.cancel(order().client_order_id, at=c)
    assert result.outcome == outcome
    final = [(m.kind, m.delivered_at) for m in b.messages(after=None, at=decided + timedelta(hours=2))]
    expected = [("ACK", BEFORE), ("CANCELLED" if outcome == "PENDING" else "FILL", decided)]
    assert final == expected


@pytest.mark.unit
def test_a_cancel_after_the_missing_data_cutoff_meets_the_expiry(db):
    b = broker(db)
    b.submit(order(), at=BEFORE)
    assert b.cancel(order().client_order_id, at=CUTOFF + timedelta(minutes=1)).outcome == "TOO_LATE"
    assert [m.kind for m in b.messages(after=None, at=CUTOFF + timedelta(hours=1))] == ["ACK", "EXPIRED"]


@pytest.mark.unit
def test_a_pending_cancel_with_no_market_data_ends_cancelled_without_a_fill(db):
    b = broker(db)
    b.submit(order(), at=BEFORE)
    b.cancel(order().client_order_id, at=OPEN + timedelta(minutes=5))
    messages = b.messages(after=None, at=CUTOFF + timedelta(hours=1))
    assert [m.kind for m in messages] == ["ACK", "CANCELLED"] and "no market data" in messages[-1].reason


# ---------------------------------------------------------------- the rest of the port


@pytest.mark.unit
def test_half_days_expire_at_their_own_close(db):
    half = date(2024, 11, 29)  # the day after Thanksgiving closes at 13:00 ET
    session = CAL.session(half)
    b = SimulatedBroker(db, knowledge=Knowledge((session.close + timedelta(minutes=5), bar("120", "121", "110"))),
                        calendar=CAL, source="yfinance", fees=FEES)
    o = Order(*order_ids("int-h", 1), "int-h", 1, "c", "f", "R1", AccountKind.RESEARCH, "EQ_US_NVDA", Side.BUY,
              Decimal(1), "LIMIT", Decimal("100.00"), "DAY", half, session.open - timedelta(hours=3))
    b.submit(o, at=session.open - timedelta(hours=1))
    assert [m.kind for m in b.messages(after=None, at=session.close + timedelta(hours=1))] == ["ACK", "EXPIRED"]
    assert session.close - session.open == timedelta(hours=3, minutes=30)


@pytest.mark.unit
def test_two_runs_give_identical_messages_and_ids(db, pg_database):
    def run(conn_db):
        b = broker(conn_db, (CLOSE + timedelta(minutes=10), bar("99", "101", "98")))
        b.submit(order(7), at=BEFORE)
        return b.messages(after=None, at=CUTOFF)

    first = run(db)
    conn = open_operational_pg(pg_database)
    try:
        assert run(PostgresDatabase(conn)) == first  # the same state, read back by a fresh broker
    finally:
        conn.close()


@pytest.mark.unit
@pytest.mark.parametrize("case", ["submit_then_lookup", "submit_is_idempotent", "unknown_order_has_no_record",
                                  "cancel_before_the_open_is_conclusive", "messages_are_stable_and_filtered_by_delivery"])
def test_the_contract_suite(db, case):
    from investment_engine.execution import broker_contract

    getattr(broker_contract, case)(lambda: broker(db), order, BEFORE)
