"""Instruments with a stable internal ID and a lifecycle (ADR-003).

An instrument ID such as EQ_US_NVDA never changes and is never reused: when a
ticker changes, the ID keeps its original mnemonic, and a later instrument
that reuses a ticker gets a numeric suffix (EQ_US_ABC_2). Nothing here can
remove an instrument, so an ID can never be freed for reuse.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class AssetClass(StrEnum):
    # CRYPTO is reserved for later (architecture Part L) and isn't accepted in M1.
    EQUITY = "EQUITY"
    ETF = "ETF"


class InstrumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELISTED = "DELISTED"
    SUSPENDED = "SUSPENDED"


_ID = re.compile(r"(?P<asset>EQ|ETF)_[A-Z]{2}_[A-Z0-9]+(_[0-9]+)?")
_ID_PREFIX = {AssetClass.EQUITY: "EQ", AssetClass.ETF: "ETF"}
_CURRENCY = re.compile(r"[A-Z]{3}")  # ISO 4217
_MIC = re.compile(r"[A-Z0-9]{4}")  # ISO 10383 market identifier code


def _plain_date(value: object, what: str) -> date:
    # datetime is a subclass of date; a lifecycle boundary is a calendar date.
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return value


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    asset_class: AssetClass
    currency: str
    exchange: str
    timezone: str
    status: InstrumentStatus
    active_from: date
    active_to: date | None

    def __post_init__(self) -> None:
        # Accept enum values given as strings (e.g. read back from a database).
        object.__setattr__(self, "asset_class", AssetClass(self.asset_class))
        object.__setattr__(self, "status", InstrumentStatus(self.status))

        match = _ID.fullmatch(self.instrument_id) if isinstance(self.instrument_id, str) else None
        if match is None:
            raise ValueError(f"instrument_id must look like EQ_US_NVDA, not {self.instrument_id!r}")
        if match["asset"] != _ID_PREFIX[self.asset_class]:
            raise ValueError(f"{self.instrument_id} doesn't match asset class {self.asset_class}")
        if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency):
            raise ValueError(f"currency must be an ISO 4217 code like 'USD', not {self.currency!r}")
        if not isinstance(self.exchange, str) or not _MIC.fullmatch(self.exchange):
            raise ValueError(f"exchange must be an ISO 10383 MIC like 'XNAS', not {self.exchange!r}")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValueError(f"timezone must be an IANA name, not {self.timezone!r}") from exc

        _plain_date(self.active_from, "active_from")
        if self.active_to is not None:
            _plain_date(self.active_to, "active_to")
            if self.active_to <= self.active_from:
                raise ValueError(f"active_to {self.active_to} must be after active_from {self.active_from}")
        if self.status is InstrumentStatus.ACTIVE and self.active_to is not None:
            raise ValueError("an ACTIVE instrument has no active_to")
        if self.status is InstrumentStatus.DELISTED and self.active_to is None:
            raise ValueError("a DELISTED instrument needs active_to")

    def is_active_on(self, d: date) -> bool:
        """Whether `d` falls in the half-open lifecycle [active_from, active_to)."""
        _plain_date(d, "d")
        return self.active_from <= d and (self.active_to is None or d < self.active_to)


class InstrumentRegistry:
    """Instruments in memory, keyed by ID. There is deliberately no way to remove one."""

    def __init__(self) -> None:
        self._instruments: dict[str, Instrument] = {}

    def add(self, instrument: Instrument) -> None:
        if instrument.instrument_id in self._instruments:
            raise ValueError(f"{instrument.instrument_id} is already registered; IDs are never reused")
        self._instruments[instrument.instrument_id] = instrument

    def get(self, instrument_id: str) -> Instrument:
        try:
            return self._instruments[instrument_id]
        except KeyError:
            raise KeyError(f"unknown instrument {instrument_id!r}") from None
