"""The provisional projection: fills, actions, reservations, point in time (docs/tasks/M4-09.md; D29, D30, D34)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.corporate_actions import ActionType
from investment_engine.money import Money
from investment_engine.oms.intents import Side
from investment_engine.oms.order_states import OrderState as S
from investment_engine.oms.orders import Fill, Order, order_ids
from investment_engine.policy.accounts import AccountKind
from investment_engine.portfolio.provisional import project
from investment_engine.portfolio.reference import Unavailable
from investment_engine.portfolio.snapshot import SnapshotSource, StartingState, build_snapshot

CAL = load_us_equities_calendar()
NVDA = "EQ_US_NVDA"
START = datetime(2024, 1, 2, tzinfo=UTC)
D1, D2, D3 = date(2024, 6, 6), date(2024, 6, 7), date(2024, 6, 10)  # the split's ex-date is D3 (a Monday)


def t_open(d):
    return CAL.session(d).open


def t_close(d):
    return CAL.session(d).close


def starting(cash="100000", positions=()):
    return StartingState("R1", START, START, Decimal(cash), "USD", tuple((NVDA, Decimal(q)) for q in positions),
                         "owner", "D14")


class Orders:
    """In-memory stand-in for OrderStore.as_of and .fills: each order with its (recorded_at, state, filled) history."""

    def __init__(self):
        self.orders, self.history, self.fill_rows = [], {}, {}

    def add(self, n, side=Side.BUY, qty="10", limit="100", created=None, history=((None, S.NEW, "0"),)):
        order = Order(*order_ids(f"int-{n}", 1), f"int-{n}", 1, "c", "f", "R1", AccountKind.RESEARCH, NVDA, side,
                      Decimal(qty), "LIMIT", Decimal(limit), "DAY", D2, created or t_close(D1))
        self.orders.append(order)
        self.history[order.order_id] = [(when or order.created_at, state, Decimal(f)) for when, state, f in history]
        self.fill_rows[order.order_id] = []
        return order

    def fill(self, order, qty, price, executed, recorded=None, fill_id=None):
        self.fill_rows[order.order_id].append(Fill(order.order_id, Decimal(qty), Decimal(price), Decimal(0), "USD",
                                                   executed, recorded or executed, recorded or executed,
                                                   fill_id or f"f-{len(self.fill_rows[order.order_id])}-{order.order_id}",
                                                   "{}"))

    def as_of(self, account_id, at):
        out = []
        for order in self.orders:
            seen = [h for h in self.history[order.order_id] if h[0] <= at]
            if seen:
                out.append((order, seen[-1][1], seen[-1][2]))
        return out

    def fills(self, order_id):
        return list(self.fill_rows[order_id])


def action(kind, ex, *, ratio=None, amount=None, known=None, revision=1):
    return SimpleNamespace(source="yfinance", instrument_id=NVDA, action_type=kind, ex_date=ex,
                           ratio=None if ratio is None else Decimal(ratio),
                           amount=None if amount is None else Money(Decimal(amount), "USD"), revision=revision,
                           known=known or START)


class Knowledge:
    def __init__(self, actions=(), closes=None):
        self.actions, self.closes = list(actions), closes or {}

    def actions_between(self, source, instrument_id, first, last, *, at):
        return [a for a in self.actions if first <= a.ex_date <= last and a.known <= at]

    def latest_closed(self, source, instrument_id, session, *, at, calendar=None):
        price = self.closes.get(session)
        if price is None or t_close(session) > at:
            return None
        return SimpleNamespace(source="yfinance", instrument_id=NVDA, timeframe="D1", start_time=t_open(session),
                               revision=1, import_id="i", available_from=t_close(session), availability_basis="OBSERVED",
                               close=Decimal(price))


def covers(*_):
    return True


def proj(orders, at, *, knowledge=None, start=None, coverage_ok=True):
    return project("R1", at=at, starting=start or starting(), orders=orders, knowledge=knowledge or Knowledge(),
                   calendar=CAL, coverage=None, source="yfinance", covers=covers if coverage_ok else (lambda *_: False))


# ---------------------------------------------------------------- fills and point in time


@pytest.mark.unit
def test_a_buy_then_a_sell_hand_computed():
    orders = Orders()
    buy = orders.add(1, history=((None, S.NEW, "0"), (t_open(D2), S.FILLED, "10")))
    orders.fill(buy, "10", "100.00", t_open(D2))
    sell = orders.add(2, side=Side.SELL, qty="4", created=t_close(D2),
                      history=((None, S.NEW, "0"), (t_open(D3), S.FILLED, "4")))
    orders.fill(sell, "4", "110.00", t_open(D3))
    p = proj(orders, t_close(D3))
    assert (p.cash, p.positions, p.reservations) == (Decimal("99440.00"), ((NVDA, Decimal(6)),), ())


@pytest.mark.unit
def test_a_fill_recorded_after_t_is_unknown_and_a_later_cancel_still_reserves_at_t():
    orders = Orders()
    buy = orders.add(1, history=((None, S.SUBMITTED, "0"), (t_close(D2) + timedelta(hours=2), S.CANCELLED, "0")))
    late = orders.add(2, history=((None, S.SUBMITTED, "0"), (t_close(D2) + timedelta(hours=3), S.FILLED, "10")))
    orders.fill(late, "10", "100", t_open(D2), recorded=t_close(D2) + timedelta(hours=3))
    p = proj(orders, t_close(D2) + timedelta(hours=1))
    assert p.positions == () and p.cash == Decimal(100000)
    assert {r.order_id for r in p.reservations} == {buy.order_id, late.order_id}


# ---------------------------------------------------------------- reservations and exposure (D30)


@pytest.mark.unit
def test_open_orders_reserve_and_unknown_keeps_its_full_reservation():
    orders = Orders()
    orders.add(1, qty="10", limit="100", history=((None, S.UNKNOWN, "0"),))
    orders.add(2, side=Side.SELL, qty="5", history=((None, S.SUBMITTED, "0"),))
    p = proj(orders, t_close(D1) + timedelta(hours=1), start=starting(positions=("8",)))
    buy, sell = sorted(p.reservations, key=lambda r: r.side.value)
    assert (buy.remaining, buy.cash, sell.remaining, sell.cash) == (Decimal(10), Decimal(1000), Decimal(5), Decimal(0))


@pytest.mark.unit
def test_two_pending_buys_cannot_both_use_the_ten_percent_cap():
    """D30 / B6: $100,000 equity, a 10% cap: a pending $10,000 BUY leaves no room for a second."""
    from investment_engine.portfolio.fingerprint import Reservation
    from tests.engine.test_risk_checks import decide, failed
    from tests.engine.test_sizer import NVDA as SIZER_NVDA, sized, snap

    base = snap(cash="100000")
    second = sized(s=base).intent  # sized as if nothing were pending
    pending = replace(base, reservations=(Reservation("ord-first", SIZER_NVDA, Side.BUY, Decimal(82), Decimal("10000")),))
    decision, _ = decide(second, s=pending)
    assert failed(decision) == ["position"] or "position" in failed(decision)
    position = next(c for c in decision.checks if c.name == "position")
    assert f"reduce {second.quantity} -> 0" in position.reason
    assert decide(second, s=base)[0].outcome.value == "APPROVE"  # without the pending BUY it would pass


@pytest.mark.unit
def test_a_pending_sell_never_frees_cap_room_and_its_shares_cannot_be_sold_twice():
    orders = Orders()
    orders.add(1, side=Side.SELL, qty="6", history=((None, S.SUBMITTED, "0"),))
    p = proj(orders, t_close(D1) + timedelta(hours=1), start=starting(positions=("10",)))
    snap = build_snapshot("R1", at=t_close(D1) + timedelta(hours=1), starting=starting(positions=("10",)),
                          knowledge=Knowledge(closes={D1: "100"}), calendar=CAL, coverage=None, last_clear=None,
                          history=[], source="yfinance", projection=p)
    assert snap.held(NVDA) == 10 and snap.available_shares(NVDA) == 4 and snap.pending_buy_value() == 0


# ---------------------------------------------------------------- corporate actions (D34, R3, V3)


SPLIT = action(ActionType.SPLIT, D3, ratio="10")


@pytest.mark.unit
def test_pre_split_holdings_plus_a_post_split_fill_is_110():
    orders = Orders()
    buy = orders.add(1, created=t_close(D3), history=((None, S.NEW, "0"), (t_open(date(2024, 6, 11)), S.FILLED, "10")))
    orders.fill(buy, "10", "120", t_open(date(2024, 6, 11)))
    p = proj(orders, t_close(date(2024, 6, 11)), knowledge=Knowledge([SPLIT]), start=starting(positions=("10",)))
    assert p.positions == ((NVDA, Decimal(110)),)
    assert [a.kind for a in p.adjustments] == ["SPLIT"]


@pytest.mark.unit
def test_a_split_ratio_stored_with_decimal_places_still_leaves_whole_shares():
    """The local store keeps ratios as 4.000000000000 (the M4-13 full run): the held count must stay 204, not
    204.000000000000, since it becomes a SELL's quantity, its terms and its order id."""
    split = action(ActionType.SPLIT, D3, ratio="4.000000000000")
    p = proj(Orders(), t_close(D3), knowledge=Knowledge([split]), start=starting(positions=("51",)))
    ((_, quantity),) = p.positions
    assert str(quantity) == "204"
    dividend = action(ActionType.DIVIDEND, date(2024, 6, 11), amount="0.04")
    p = proj(Orders(), t_close(date(2024, 6, 11)), knowledge=Knowledge([split, dividend]),
             start=starting(positions=("51",)))
    assert str(p.receivables) == "8.16"


@pytest.mark.unit
@pytest.mark.parametrize("side, executed, entitled", [
    (Side.BUY, "before", True), (Side.BUY, "on", False), (Side.SELL, "on", True), (Side.SELL, "before", False)])
def test_dividend_entitlement_is_fixed_at_the_previous_close(side, executed, entitled):
    dividend = action(ActionType.DIVIDEND, D3, amount="0.10")
    orders = Orders()
    when = t_close(D2) if executed == "before" else t_open(D3)
    o = orders.add(1, side=side, created=when - timedelta(hours=8), history=((None, S.NEW, "0"), (when, S.FILLED, "10")))
    orders.fill(o, "10", "100", when)
    start = starting(positions=("10",) if side is Side.SELL else ())
    p = proj(orders, t_close(D3), knowledge=Knowledge([dividend]), start=start)
    assert p.receivables == (Decimal("1.00") if entitled else Decimal(0))


@pytest.mark.unit
def test_a_correction_learned_after_t_and_a_delayed_fill_follow_the_cutoff():
    late_split = action(ActionType.SPLIT, D3, ratio="10", known=t_close(D3) + timedelta(days=1))
    start = starting(positions=("10",))
    before = proj(Orders(), t_close(D3), knowledge=Knowledge([late_split]), start=start)
    assert before.positions == ((NVDA, Decimal(10)),)  # not yet known at t
    orders = Orders()
    o = orders.add(1, created=t_close(D1), history=((None, S.NEW, "0"), (t_close(D3), S.FILLED, "5")))
    orders.fill(o, "5", "100", t_open(D2), recorded=t_close(D3))  # executed before the split, known later
    early = proj(orders, t_close(D2), knowledge=Knowledge([SPLIT]), start=start)
    later = proj(orders, t_close(D3), knowledge=Knowledge([SPLIT]), start=start)
    assert early.positions == ((NVDA, Decimal(10)),)  # not recorded yet
    assert later.positions == ((NVDA, Decimal(150)),)  # (10 + 5) x 10: placed before the split


@pytest.mark.unit
@pytest.mark.parametrize("created", ["before", "at-open"], ids=["created-before", "split-at-its-open"])
def test_an_unresolved_order_across_a_split_is_unavailable_and_keeps_its_terms(created):
    orders = Orders()
    when = t_close(D2) if created == "before" else t_open(D3) - timedelta(minutes=30)
    o = orders.add(1, qty="10", limit="100", created=when, history=((None, S.UNKNOWN, "0"),))
    p = proj(orders, t_close(D3), knowledge=Knowledge([SPLIT]), start=starting(positions=("10",)))
    assert isinstance(p, Unavailable) and o.order_id in p.reason and "unresolved" in p.reason
    assert (o.quantity, o.limit_price) == (Decimal(10), Decimal(100))  # never changed


@pytest.mark.unit
@pytest.mark.parametrize("case, message", [
    ("fraction", "cash in lieu"), ("unsupported", "isn't supported"), ("coverage", "no established")])
def test_unsupported_cases_are_unavailable(case, message):
    start = starting(positions=("3",))
    if case == "fraction":
        p = proj(Orders(), t_close(D3), knowledge=Knowledge([action(ActionType.SPLIT, D3, ratio="1.5")]), start=start)
    elif case == "unsupported":
        p = proj(Orders(), t_close(D3), knowledge=Knowledge([action(ActionType.DELISTING, D3)]), start=start)
    else:
        p = proj(Orders(), t_close(D3), start=start, coverage_ok=False)
    assert isinstance(p, Unavailable) and message in p.reason


@pytest.mark.unit
def test_valuation_waits_for_a_close_in_the_new_units_and_stores_no_tenfold_equity():
    start = starting(cash="90000", positions=("10",))
    closes = {D2: "1000", D3: "100"}
    knowledge = Knowledge([SPLIT], closes)

    def snapshot(at):
        p = proj(Orders(), at, knowledge=knowledge, start=start)
        return build_snapshot("R1", at=at, starting=start, knowledge=knowledge, calendar=CAL, coverage=None,
                              last_clear=None, history=[], source="yfinance", projection=p)

    before = snapshot(t_open(D3) - timedelta(minutes=1))
    assert before.equity == Decimal("100000") and before.source is SnapshotSource.PROVISIONAL
    during = snapshot(t_open(D3) + timedelta(hours=1))  # 100 shares, last close still 1,000 pre-split
    assert isinstance(during, Unavailable) and "awaits a close" in during.reason
    after = snapshot(t_close(D3) + timedelta(minutes=5))
    assert after.equity == Decimal("100000") and after.held(NVDA) == 100


@pytest.mark.unit
def test_a_dividend_receivable_counts_in_equity_but_is_not_spendable():
    start = starting(cash="90000", positions=("100",))
    knowledge = Knowledge([action(ActionType.DIVIDEND, D3, amount="0.50")], {D3: "100"})
    at = t_close(D3) + timedelta(minutes=5)
    p = proj(Orders(), at, knowledge=knowledge, start=start)
    snap = build_snapshot("R1", at=at, starting=start, knowledge=knowledge, calendar=CAL, coverage=None,
                          last_clear=None, history=[], source="yfinance", projection=p)
    assert snap.receivables == Decimal("50.00") and snap.equity == Decimal("100050.00")
    assert snap.available_cash() == Decimal("90000")


@pytest.mark.unit
def test_the_gates_fingerprint_changes_with_a_fill_or_a_new_order_and_not_with_time():
    from investment_engine.portfolio.provisional import ProvisionalFingerprints

    orders = Orders()
    gated = orders.add(1, history=((None, S.NEW, "0"),))
    snapshots = SimpleNamespace(starting_state=lambda account_id: starting())
    provider = ProvisionalFingerprints(snapshots, orders, knowledge=Knowledge(), calendar=CAL, coverage=None)
    provider_covers = provider.at("R1", t_close(D1) + timedelta(hours=1), excluding_order=gated.order_id)
    later = provider.at("R1", t_close(D1) + timedelta(hours=5), excluding_order=gated.order_id)
    assert provider_covers == later  # an unchanged portfolio, later: the same fingerprint
    other = orders.add(2, history=((None, S.NEW, "0"),), created=t_close(D1) + timedelta(hours=2))
    assert provider.at("R1", t_close(D1) + timedelta(hours=5), excluding_order=gated.order_id) != later  # new order
    orders.history[other.order_id].append((t_close(D1) + timedelta(hours=6), S.FILLED, Decimal(10)))
    orders.fill(other, "10", "100", t_close(D1) + timedelta(hours=6))
    assert provider.at("R1", t_close(D1) + timedelta(hours=7), excluding_order=gated.order_id) != later  # a fill
