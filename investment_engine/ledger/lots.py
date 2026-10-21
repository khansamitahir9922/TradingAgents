"""FIFO acquisition-to-disposal evidence; exact cumulative allocation (ADR-010)."""
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from fractions import Fraction

from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    LotMatch,
    SourceConflict,
    Unit,
    amount,
    identity,
)
from investment_engine.market.availability import check_instrument_id, check_name, check_utc

POLICY = "fifo-cumulative-v1"
QUANTUM = Fraction(1, 10000)


def exact_decimal(value: Fraction) -> Decimal:
    """Convert a terminating rational without Decimal division or caller context."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise ValueError("non-terminating cost cannot be represented exactly")
    scale = max(twos, fives)
    coefficient = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    return Decimal((int(coefficient < 0), tuple(int(c) for c in str(abs(coefficient))), -scale))


def allocate_cost(cost, quantity, disposed, allocated):
    """Return this disposal's cost from an exact, bounded cumulative target."""
    amount(cost, "cost")
    amount(quantity, "quantity", whole=True)
    amount(disposed, "disposed", whole=True)
    amount(allocated, "allocated")
    c, q, d, a = map(Fraction, (cost, quantity, disposed, allocated))
    if q <= 0 or d > q or a > c:
        raise ValueError("invalid allocation epoch")
    if d == q:
        target = c
    else:
        ratio = c * d / q / QUANTUM
        floor, remainder = divmod(ratio.numerator, ratio.denominator)
        if remainder * 2 > ratio.denominator or (remainder * 2 == ratio.denominator and floor % 2):
            floor += 1
        target = min(c, max(a, floor * QUANTUM))
    return exact_decimal(target - a)


@dataclass(frozen=True)
class Lot:
    acquisition: str
    instrument_id: str
    acquired_at: datetime
    original_quantity: Decimal
    original_cost: Decimal
    remaining_quantity: Decimal
    remaining_cost: Decimal
    epoch_quantity: Decimal
    epoch_cost: Decimal
    disposed: Decimal
    allocated: Decimal
    opening: bool = False

    def __post_init__(self):
        check_name(self.acquisition, "acquisition")
        check_instrument_id(self.instrument_id)
        check_utc(self.acquired_at, "acquired_at")
        for name in ("original_quantity", "remaining_quantity", "epoch_quantity", "disposed"):
            amount(getattr(self, name), name, whole=True)
        for name in ("original_cost", "remaining_cost", "epoch_cost", "allocated"):
            amount(getattr(self, name), name)
        if self.original_quantity <= 0 or self.epoch_quantity <= 0:
            raise ValueError("lot acquisition/epoch quantity must be positive")
        if Fraction(self.epoch_quantity) - Fraction(self.disposed) != Fraction(self.remaining_quantity) or (
                Fraction(self.epoch_cost) - Fraction(self.allocated) != Fraction(self.remaining_cost)):
            raise ValueError("lot quantity/cost conservation failed")
        if self.remaining_quantity == 0 and self.remaining_cost != 0:
            raise ValueError("a closed lot must exhaust its cost")


class FifoBook:
    """A rebuildable planning object. Persist only its immutable LotMatch results."""
    def __init__(self, account_id, *, at, book_id="pending", lots=()):
        self.account_id = check_name(account_id, "account_id")
        self.at = check_utc(at, "at")
        self.book_id = check_name(book_id, "book_id")
        self._lots = list(lots)
        self._disposals = {}

    def lots(self, instrument_id=None):
        return tuple(sorted((lot for lot in self._lots if instrument_id is None or lot.instrument_id == instrument_id),
                            key=lambda lot: (not lot.opening, lot.acquired_at, lot.acquisition)))

    def acquire(self, instrument_id, quantity, cost, acquisition, *, at, opening=False):
        check_utc(at, "acquired_at")
        if at > self.at:
            raise AccountingUnavailable(self.account_id, self.at, ("acquisition not effective at cutoff",))
        lot = Lot(acquisition, instrument_id, at, quantity, cost, quantity, cost, quantity, cost, Decimal(0), Decimal(0), opening)
        prior = [v for v in self._lots if v.acquisition == acquisition]
        if prior:
            keys = ("instrument_id", "acquired_at", "original_quantity", "original_cost", "opening")
            if any(getattr(prior[0], k) != getattr(lot, k) for k in keys):
                raise SourceConflict("acquisition identity has conflicting content")
            return prior[0]
        self._lots.append(lot)
        return lot

    def consume(self, instrument_id, quantity, disposal):
        check_instrument_id(instrument_id)
        check_name(disposal, "disposal")
        amount(quantity, "quantity", whole=True)
        if quantity <= 0:
            raise ValueError("disposal quantity must be positive")
        if disposal in self._disposals:
            key, matches = self._disposals[disposal]
            if key != (instrument_id, quantity):
                raise SourceConflict("disposal identity has conflicting content")
            return matches
        available = self.lots(instrument_id)
        if sum((Fraction(lot.remaining_quantity) for lot in available), Fraction()) < Fraction(quantity):
            raise AccountingUnavailable(self.account_id, self.at, ("insufficient established FIFO cost/quantity",))
        remaining = int(quantity)
        updated = {lot.acquisition: lot for lot in self._lots}
        matches = []
        for lot in available:
            take = min(remaining, int(lot.remaining_quantity))
            if not take:
                continue
            cumulative = Decimal(int(lot.disposed) + take)
            allocation = allocate_cost(lot.epoch_cost, lot.epoch_quantity, cumulative, lot.allocated)
            cumulative_cost = exact_decimal(Fraction(lot.allocated) + Fraction(allocation))
            updated[lot.acquisition] = replace(lot, remaining_quantity=Decimal(int(lot.remaining_quantity) - take),
                remaining_cost=exact_decimal(Fraction(lot.epoch_cost) - Fraction(cumulative_cost)),
                disposed=cumulative, allocated=cumulative_cost)
            mid = identity((self.account_id, lot.acquisition, disposal, take, allocation, POLICY))
            matches.append(LotMatch(mid, self.book_id, lot.acquisition, disposal, Decimal(take), allocation,
                                    Unit("CURRENCY", "USD"), POLICY))
            remaining -= take
            if not remaining:
                break
        self._lots = list(updated.values())
        result = tuple(matches)
        self._disposals[disposal] = ((instrument_id, quantity), result)
        return result
