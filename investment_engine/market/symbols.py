"""Effective-dated provider symbol mappings (ADR-003).

Providers name instruments by symbols that change over time and get reused. A
mapping says which instrument a provider meant by a symbol over a half-open
date range [valid_from, valid_to). Every lookup takes a date, and a missing
mapping raises UnknownSymbol: nothing ever guesses that a ticker "probably"
means the same instrument.

The rules for conflicting mappings are module functions, so every resolver
(in memory here; SQLite in M1-05) applies exactly the same ones.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

PROVIDER_YFINANCE = "yfinance"

_PROVIDER = re.compile(r"[a-z][a-z0-9_]*")


class UnknownSymbol(LookupError):
    """No mapping covers the requested provider, symbol (or instrument) and date."""


def _plain_date(value: object, what: str) -> date:
    # datetime is a subclass of date; a validity boundary is a calendar date.
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return value


def _name(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{what} must be a string, not {type(value).__name__}")
    if not value or value != value.strip():
        raise ValueError(f"{what} must be non-empty without surrounding spaces, not {value!r}")
    return value


@dataclass(frozen=True)
class SymbolMapping:
    instrument_id: str
    provider: str
    symbol: str
    valid_from: date
    valid_to: date | None  # exclusive; None means open-ended

    def __post_init__(self) -> None:
        _name(self.instrument_id, "instrument_id")
        _name(self.symbol, "symbol")
        if not isinstance(self.provider, str) or not _PROVIDER.fullmatch(self.provider):
            raise ValueError(f"provider must be a lowercase identifier like 'yfinance', not {self.provider!r}")
        _plain_date(self.valid_from, "valid_from")
        if self.valid_to is not None:
            _plain_date(self.valid_to, "valid_to")
            if self.valid_to <= self.valid_from:
                raise ValueError(f"valid_to {self.valid_to} must be after valid_from {self.valid_from}")


def covers(mapping: SymbolMapping, on: date) -> bool:
    """Whether `on` falls in the mapping's half-open validity."""
    return mapping.valid_from <= on and (mapping.valid_to is None or on < mapping.valid_to)


def overlaps(a: SymbolMapping, b: SymbolMapping) -> bool:
    """Whether two half-open validity ranges share at least one day."""
    a_before_b_ends = b.valid_to is None or a.valid_from < b.valid_to
    b_before_a_ends = a.valid_to is None or b.valid_from < a.valid_to
    return a_before_b_ends and b_before_a_ends


def conflict(new: SymbolMapping, existing: Iterable[SymbolMapping]) -> SymbolMapping | None:
    """The first existing mapping `new` may not coexist with, or None.

    Over overlapping dates, a provider's symbol may mean only one instrument,
    and an instrument may have only one symbol per provider. An identical
    overlapping mapping is refused too: it would make the same claim twice.
    """
    for old in existing:
        if old.provider != new.provider or not overlaps(old, new):
            continue
        if old.symbol == new.symbol or old.instrument_id == new.instrument_id:
            return old
    return None


class SymbolResolver:
    """Symbol mappings in memory. M1-05's SQLite resolver has the same interface and rules."""

    def __init__(self) -> None:
        self._mappings: list[SymbolMapping] = []

    def add(self, mapping: SymbolMapping) -> None:
        clash = conflict(mapping, self._mappings)
        if clash is not None:
            raise ValueError(f"{mapping} overlaps {clash}")
        self._mappings.append(mapping)

    def resolve(self, provider: str, symbol: str, on: date) -> str:
        """The instrument ID `provider` meant by `symbol` on `on`."""
        _plain_date(on, "on")
        for m in self._mappings:
            if m.provider == provider and m.symbol == symbol and covers(m, on):
                return m.instrument_id
        raise UnknownSymbol(f"no {provider} mapping for {symbol!r} on {on}")

    def symbol_for(self, instrument_id: str, provider: str, on: date) -> str:
        """The symbol `provider` used for `instrument_id` on `on`."""
        _plain_date(on, "on")
        for m in self._mappings:
            if m.instrument_id == instrument_id and m.provider == provider and covers(m, on):
                return m.symbol
        raise UnknownSymbol(f"no {provider} symbol for {instrument_id} on {on}")
