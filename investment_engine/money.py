"""The Decimal boundary (ADR-007).

Money, prices and quantities are Decimal with an explicit currency or unit.
Quant and ML code works in float64; the two meet only through the converters
here, which always state a quantum and use one rounding rule.
"""

import decimal
import math
import re
from dataclasses import dataclass
from decimal import Decimal

PRICE_QUANTUM = Decimal("0.0001")  # stored US equity prices and per-share amounts
SHARE_QUANTUM = Decimal("1")  # stored share volumes
ROUNDING = decimal.ROUND_HALF_EVEN

_CURRENCY = re.compile(r"[A-Z]{3}")


def _finite_decimal(value: object, what: str) -> Decimal:
    # bool is excluded explicitly: it is an int, and ints aren't Decimals anyway.
    if not isinstance(value, Decimal) or isinstance(value, bool):
        raise TypeError(f"{what} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{what} must be finite, not {value}")
    return value


def quantize(value: Decimal, quantum: Decimal, rounding: str = ROUNDING) -> Decimal:
    """Round `value` to `quantum` with the stated rounding rule (half-even by default)."""
    _finite_decimal(value, "value")
    _finite_decimal(quantum, "quantum")
    return value.quantize(quantum, rounding=rounding)


def from_float64(value: float, quantum: Decimal, rounding: str = ROUNDING) -> Decimal:
    """Convert a float to Decimal at an explicit quantum.

    Uses the float's shortest round-tripping representation (`repr`), not its
    exact binary value, so 0.1 + 0.2 becomes 0.3000 at a 0.0001 quantum.
    """
    if not isinstance(value, float):
        raise TypeError(f"value must be a float, not {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"value must be finite, not {value}")
    return quantize(Decimal(repr(value)), quantum, rounding)


def to_float64(value: Decimal) -> float:
    """Convert a finite Decimal to float, for quant and ML code."""
    return float(_finite_decimal(value, "value"))


@dataclass(frozen=True)
class Money:
    """An amount in one currency. Arithmetic and ordering never mix currencies."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        _finite_decimal(self.amount, "amount")
        if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency):
            raise ValueError(f"currency must be an ISO 4217 code like 'USD', not {self.currency!r}")

    def _same(self, other: object) -> "Money":
        if not isinstance(other, Money):
            raise TypeError(f"cannot combine Money with {type(other).__name__}")
        if other.currency != self.currency:
            raise ValueError(f"cannot combine {self.currency} with {other.currency}")
        return other

    def __add__(self, other: "Money") -> "Money":
        return Money(self.amount + self._same(other).amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self.amount - self._same(other).amount, self.currency)

    def __mul__(self, factor: Decimal) -> "Money":
        if not isinstance(factor, Decimal):
            return NotImplemented
        return Money(self.amount * _finite_decimal(factor, "factor"), self.currency)

    __rmul__ = __mul__

    def __lt__(self, other: "Money") -> bool:
        return self.amount < self._same(other).amount

    def __le__(self, other: "Money") -> bool:
        return self.amount <= self._same(other).amount

    def __gt__(self, other: "Money") -> bool:
        return self.amount > self._same(other).amount

    def __ge__(self, other: "Money") -> bool:
        return self.amount >= self._same(other).amount


@dataclass(frozen=True)
class Quantity:
    """An amount in one unit (e.g. "shares"). Arithmetic and ordering never mix units."""

    amount: Decimal
    unit: str

    def __post_init__(self) -> None:
        _finite_decimal(self.amount, "amount")
        if not isinstance(self.unit, str) or not self.unit or self.unit != self.unit.strip():
            raise ValueError(f"unit must be a non-empty name without surrounding spaces, not {self.unit!r}")

    def _same(self, other: object) -> "Quantity":
        if not isinstance(other, Quantity):
            raise TypeError(f"cannot combine Quantity with {type(other).__name__}")
        if other.unit != self.unit:
            raise ValueError(f"cannot combine {self.unit} with {other.unit}")
        return other

    def __add__(self, other: "Quantity") -> "Quantity":
        return Quantity(self.amount + self._same(other).amount, self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        return Quantity(self.amount - self._same(other).amount, self.unit)

    def __lt__(self, other: "Quantity") -> bool:
        return self.amount < self._same(other).amount

    def __le__(self, other: "Quantity") -> bool:
        return self.amount <= self._same(other).amount

    def __gt__(self, other: "Quantity") -> bool:
        return self.amount > self._same(other).amount

    def __ge__(self, other: "Quantity") -> bool:
        return self.amount >= self._same(other).amount
