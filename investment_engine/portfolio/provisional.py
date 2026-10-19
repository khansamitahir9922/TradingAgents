"""The provisional projection: positions and cash from the declared start plus recorded fills, adjusted for splits
and dividends, with open-order reservations, all as known at `at` (D29, D30, D34; docs/tasks/M4-09.md).

This is a labelled projection, not a ledger: M5's ledger becomes authoritative.

Rules (M4-09 rules 1–3):
- **Point in time.** Only fills with recorded_at <= at, actions whose revision was known at `at`, and each order's
  state as of `at` (OrderStore.as_of). A correction or fill learned later never changes the projection at `at`.
- **Chronological.** The declared start, each fill at its executed_at, and each action at its effective time (the
  open of its ex-date session) are replayed in time order. At equal times, actions come before fills. Fills are
  ordered by (executed_at, fill_id), actions by (effective time, action identity). A SPLIT multiplies the held
  quantity by its ratio. A DIVIDEND's entitlement is the shares held when it takes effect, i.e. at the previous
  close, because nothing executes between that close and the ex-date's open. It becomes a **receivable**, in
  equity but not spendable cash.
- **Unsupported or uncertain is Unavailable**, with the reason: no established action coverage for an
  instrument held during the period; a split leaving a fraction of a share; another action type, or a dividend
  in another currency, for a held instrument; and an order not final at `at` that was created before an action
  on its instrument that took effect at or before `at` (created_at < e <= at). The order's terms and reservation
  never change.
- **Reservations** (D30): every order open at `at` reserves its unfilled remainder. A BUY reserves remainder x
  limit of cash; a SELL reserves its shares; UNKNOWN reserves in full. The commission is 0 in M4's fee schedule,
  so no fee is reserved.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal
from zoneinfo import ZoneInfo

from investment_engine.lineage.records import canonical_json, register
from investment_engine.market.availability import check_utc
from investment_engine.market.corporate_actions import ActionType
from investment_engine.oms.intents import Side
from investment_engine.oms.order_states import OPEN
from investment_engine.portfolio.fingerprint import Reservation, economic_fingerprint
from investment_engine.portfolio.reference import Unavailable
from investment_engine.risk.decisions import exact

_CTX = Context(prec=34)


@dataclass(frozen=True)
class Adjustment:
    kind: str  # SPLIT | DIVIDEND
    instrument_id: str
    effective_at: datetime
    value: Decimal  # the split ratio, or the dividend receivable credited
    action_ref: str  # source|instrument|ex_date|type|revision


@dataclass(frozen=True)
class Projection:
    account_id: str
    at: datetime
    cash: Decimal  # after fills; reservations are commitments, not spending
    receivables: Decimal  # dividends earned, not yet spendable (D34)
    positions: tuple[tuple[str, Decimal], ...]  # sorted (instrument_id, whole shares), non-zero
    reservations: tuple[Reservation, ...]
    adjustments: tuple[Adjustment, ...]
    history_hash: str  # the fills and order states it used

    def held(self, instrument_id: str) -> Decimal:
        return dict(self.positions).get(instrument_id, Decimal(0))

    def fingerprint(self, *, excluding_order: str | None = None) -> str:
        return economic_fingerprint(cash=self.cash, positions=self.positions,
                                    reservations=[r for r in self.reservations if r.order_id != excluding_order])


for _cls in (Adjustment, Projection):
    register(_cls)


def _action_ref(a) -> str:
    return f"{a.source}|{a.instrument_id}|{a.ex_date.isoformat()}|{a.action_type.value}|r{a.revision}"


@exact  # one fully specified Decimal context, whatever the caller's (Codex M4 review B2)
def project(account_id: str, *, at: datetime, starting, orders, knowledge, calendar, coverage, source: str,
            covers=None) -> Projection | Unavailable:
    """The projection at `at`, or Unavailable with the reason. `covers(coverage, source, instrument, first, last)`
    is M3's established-coverage test (portfolio.snapshot._covers)."""
    at = check_utc(at, "at")
    if at < starting.effective_at:
        return Unavailable(f"{account_id}'s declared start is after {at.isoformat()}")
    zone = ZoneInfo(calendar.timezone)
    first, last = starting.effective_at.astimezone(zone).date(), at.astimezone(zone).date()

    as_of = orders.as_of(account_id, at)  # (order, state, filled) known at `at`
    fills = []
    for order, _state, _filled in as_of:
        for f in orders.fills(order.order_id):
            if f.recorded_at <= at and f.executed_at <= at:
                fills.append((f.executed_at, 1, f.fill_id, ("fill", order, f)))
    instruments = {i for i, _ in starting.positions} | {o.instrument_id for o, _, _ in as_of}
    if instruments and hasattr(knowledge, "action_history"):
        # Replay knowledge holds only what was fed to it. Its action history must be established: every action
        # revision delivered from before the declared start, including those announced before the feed began
        # (Codex M4 review B7; re-review R3). A feed's start time is no such proof. The store's own knowledge is
        # the whole store. Nothing held and no orders: nothing to carry, so no history is needed.
        history = knowledge.action_history
        if history is None:
            return Unavailable("the replay's action history isn't established (its feed wasn't composed with the "
                               f"actions outstanding before it began); actions since {account_id}'s declared start "
                               "can't be established")
        if history.complete_from > starting.effective_at:
            return Unavailable(f"the replay's action history begins at {history.complete_from.isoformat()}, after "
                               f"{account_id}'s declared start {starting.effective_at.isoformat()}")

    actions = []
    for instrument_id in sorted(instruments):
        for a in knowledge.actions_between(source, instrument_id, first, last, at=at):
            session = a.ex_date if calendar.is_session(a.ex_date) else calendar.next_session(a.ex_date).date
            effective = calendar.session(session).open
            if effective <= starting.effective_at:
                # In force when the start was declared, so already reflected in it. The comparison is of instants,
                # not dates (B7): a start declared before an ex-date's open still receives that day's action, and
                # one declared at the very instant it takes effect is taken to reflect it.
                continue
            if effective <= at:
                actions.append((effective, 0, _action_ref(a), ("action", a, None)))

    held = {i: Decimal(q) for i, q in starting.positions}
    ever_held = set(held)
    cash, receivables, adjustments = Decimal(starting.cash), Decimal(0), []
    for when, _rank, _key, (kind, x, f) in sorted(fills + actions, key=lambda e: (e[0], e[1], e[2])):
        if kind == "fill":
            order = x
            amount = _CTX.multiply(f.quantity, f.price)
            if order.side is Side.BUY:
                held[order.instrument_id] = held.get(order.instrument_id, Decimal(0)) + f.quantity
                cash = _CTX.subtract(_CTX.subtract(cash, amount), f.fee)
                ever_held.add(order.instrument_id)
            else:
                held[order.instrument_id] = held.get(order.instrument_id, Decimal(0)) - f.quantity
                cash = _CTX.subtract(_CTX.add(cash, amount), f.fee)
            continue
        a = x
        shares = held.get(a.instrument_id, Decimal(0))
        if shares == 0:
            continue  # nothing held: the action changes nothing for this account
        if a.action_type is ActionType.SPLIT:
            after = _CTX.multiply(shares, a.ratio)
            if after != after.to_integral_value():
                return Unavailable(f"the {a.ex_date} split of {a.instrument_id} leaves {after} shares; cash in lieu "
                                   "isn't known (D34)")
            held[a.instrument_id] = after.quantize(Decimal(1))  # whole shares: no exponent from the ratio's scale
            adjustments.append(Adjustment("SPLIT", a.instrument_id, when, a.ratio, _action_ref(a)))
        elif a.action_type is ActionType.DIVIDEND:
            if a.amount.currency != starting.currency:
                return Unavailable(f"a {a.amount.currency} dividend on {a.instrument_id} isn't supported (D34)")
            credit = _CTX.multiply(shares, a.amount.amount)
            receivables = _CTX.add(receivables, credit)
            adjustments.append(Adjustment("DIVIDEND", a.instrument_id, when, credit, _action_ref(a)))
        else:
            return Unavailable(f"a {a.action_type} on {a.ex_date} for {a.instrument_id} isn't supported (D34)")

    for instrument_id in sorted(ever_held):
        if covers is not None and not covers(coverage, source, instrument_id, first, last):
            return Unavailable(f"no established {source} action coverage for {instrument_id} from {first} to "
                               f"{last}; quantities can't be carried without it")

    reservations = []
    for order, state, filled in as_of:
        if state not in OPEN:
            continue
        crossed = [e for e, _, _, (_, a, _) in actions if a.instrument_id == order.instrument_id
                   and order.created_at < e <= at]
        if crossed:
            return Unavailable(f"order {order.order_id} is unresolved across a corporate action on "
                               f"{order.instrument_id} (effective {crossed[0].isoformat()}); its basis can't be "
                               "established (D34)")
        remaining = order.quantity - filled
        cash_reserved = _CTX.multiply(remaining, order.limit_price) if order.side is Side.BUY else Decimal(0)
        reservations.append(Reservation(order.order_id, order.instrument_id, order.side, remaining, cash_reserved))

    positions = tuple(sorted((i, q) for i, q in held.items() if q != 0))
    if any(q < 0 for _, q in positions):
        return Unavailable("recorded fills would leave a short position; long only (D2)")
    history = canonical_json([(f[2], f[3][2].recorded_at.isoformat()) for f in fills] +
                             [(o.order_id, s.value, str(q)) for o, s, q in as_of])
    return Projection(account_id, at, cash, receivables, positions, tuple(sorted(reservations, key=lambda r: r.order_id)),
                      tuple(adjustments), "hist-" + hashlib.sha256(history.encode()).hexdigest())


class ProvisionalFingerprints:
    """The gate's FingerprintProvider from M4-09: the projection at `at`, excluding the order being gated."""

    def __init__(self, snapshots, orders, *, knowledge, calendar, coverage, source: str = "yfinance") -> None:
        self.snapshots, self.orders = snapshots, orders
        self.knowledge, self.calendar, self.coverage, self.source = knowledge, calendar, coverage, source

    def at(self, account_id: str, at: datetime, *, excluding_order: str | None):
        from investment_engine.portfolio.snapshot import _covers

        projection = project(account_id, at=at, starting=self.snapshots.starting_state(account_id),
                             orders=self.orders, knowledge=self.knowledge, calendar=self.calendar,
                             coverage=self.coverage, source=self.source, covers=_covers)
        if isinstance(projection, Unavailable):
            return projection
        return projection.fingerprint(excluding_order=excluding_order)


__all__ = ["Adjustment", "Projection", "ProvisionalFingerprints", "project"]
