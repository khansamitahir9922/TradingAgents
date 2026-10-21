"""Typed ledger projection with as-of OMS reservations; no provisional fallback."""
from dataclasses import dataclass
from fractions import Fraction

from investment_engine.ledger.contracts import AccountingUnavailable, LedgerBalances, identity
from investment_engine.ledger.lots import exact_decimal
from investment_engine.market.availability import check_utc
from investment_engine.oms.intents import Side
from investment_engine.oms.order_states import OPEN
from investment_engine.portfolio.fingerprint import Reservation, economic_fingerprint
from investment_engine.portfolio.reference import Unavailable


@dataclass(frozen=True)
class LedgerProjection:
    ledger_balances: LedgerBalances
    reservations: tuple[Reservation, ...]
    history_hash: str

    @property
    def cash(self):
        return self.ledger_balances.cash

    @property
    def positions(self):
        return self.ledger_balances.positions

    @property
    def receivables(self):
        return exact_decimal(sum((Fraction(n) for _, n in self.ledger_balances.receivables), Fraction()))

    @property
    def adjustments(self):
        # Ledger transformations live in the referenced book, not M4's provisional list.
        return None

    def fingerprint(self, *, excluding_order=None):
        return economic_fingerprint(cash=self.cash, positions=self.positions,
                                    reservations=tuple(r for r in self.reservations if r.order_id != excluding_order))


def project(value, *, orders, account_id, at):
    check_utc(at, "at")
    if isinstance(value, AccountingUnavailable):
        return Unavailable(str(value))
    if not isinstance(value, LedgerBalances):
        return Unavailable("typed ledger balances required")
    if value.query.account_id != account_id or value.query.effective_at != at or value.query.known_at != at:
        return Unavailable("ledger portfolio account/effective/knowledge cutoffs do not match")
    if not value.complete:
        return Unavailable("ledger incomplete: " + "; ".join(value.reasons))
    if any(i not in dict(value.costs) for i, _ in value.positions):
        return Unavailable("ledger cost missing for a held instrument")
    if orders is None:
        return Unavailable("ledger projection requires explicit OMS as-of reservations")
    rows = orders.as_of(account_id, at)
    reservations = []
    for order, state, filled in rows:
        if order.account_id != account_id:
            return Unavailable("OMS reservation belongs to another account")
        if state not in OPEN:
            continue
        for ref in value.sources:
            if ref.kind == "action" and f"/{order.instrument_id}/" in ref.identity and order.created_at < ref.effective_at <= at:
                return Unavailable("unresolved order crosses an action; its terms/reservation are unchanged")
        remaining = Fraction(order.quantity) - Fraction(filled)
        if remaining < 0:
            return Unavailable("invalid negative remaining OMS quantity")
        if remaining:
            cash = remaining * Fraction(order.limit_price) if order.side is Side.BUY else Fraction()
            reservations.append(Reservation(order.order_id, order.instrument_id, order.side,
                                            exact_decimal(remaining), exact_decimal(cash)))
    reservations = tuple(sorted(reservations, key=lambda r:r.order_id))
    return LedgerProjection(value, reservations, identity((value.query.query_id, reservations)))


class LedgerFingerprints:
    """`balances_provider(account,T)` must check current source/readiness before returning a DTO.

    M5-10 injects that service. This module cannot fall back to a previous head or
    to provisional data when the provider reports an accounting gap.
    """
    def __init__(self, balances_provider, orders):
        self._provider, self._orders = balances_provider, orders

    def at(self, account_id, at, *, excluding_order):
        value = self._provider(account_id, at)
        projection = project(value, orders=self._orders, account_id=account_id, at=at)
        return projection if isinstance(projection, Unavailable) else projection.fingerprint(excluding_order=excluding_order)
