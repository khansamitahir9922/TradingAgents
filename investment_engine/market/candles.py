"""The Candle contract (architecture Part H; Laws 5, 7, 8; docs/tasks/M1-08.md).

A candle is one revision of one provider's bar. Its identity is
(source, instrument_id, timeframe, start_time), so two providers' bars never
share revision numbering. Prices and volume each carry the basis they were
obtained on, and availability follows the shared rules in availability.py.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from investment_engine.market.availability import (
    AvailabilityBasis,
    check_availability,
    check_instrument_id,
    check_name,
    check_provider,
    check_revision,
    check_utc,
)
from investment_engine.money import PRICE_QUANTUM, SHARE_QUANTUM

_CURRENCY = re.compile(r"[A-Z]{3}")


class Timeframe(StrEnum):
    D1 = "D1"
    H1 = "H1"


class BarState(StrEnum):
    FORMING = "FORMING"
    CLOSED = "CLOSED"


class PriceBasis(StrEnum):
    RAW_AS_REPORTED = "RAW_AS_REPORTED"  # the provider's values are verified as-traded
    RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED = "RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED"  # verified reconstruction
    RAW_NO_LATER_SPLIT = "RAW_NO_LATER_SPLIT"  # unchanged; no split between bar and download


class VolumeBasis(StrEnum):
    RAW_AS_REPORTED = "RAW_AS_REPORTED"
    RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED = "RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED"
    RAW_NO_LATER_SPLIT = "RAW_NO_LATER_SPLIT"


def _at_quantum(value: object, quantum: Decimal, what: str) -> Decimal:
    """A finite Decimal already at `quantum`: extra precision is refused, never rounded."""
    if not isinstance(value, Decimal):
        raise TypeError(f"{what} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{what} must be finite, not {value}")
    if value.as_tuple().exponent < quantum.as_tuple().exponent:
        raise ValueError(f"{what} {value} has more precision than {quantum}")
    return value


@dataclass(frozen=True)
class Candle:
    source: str
    instrument_id: str
    timeframe: Timeframe
    start_time: datetime
    end_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    currency: str
    volume: Decimal
    state: BarState
    source_version: str
    price_basis: PriceBasis
    volume_basis: VolumeBasis
    import_id: str
    event_time: datetime
    received_at: datetime
    processed_at: datetime
    revision: int
    available_from: datetime
    availability_basis: AvailabilityBasis

    def __post_init__(self) -> None:
        for name, enum in (
            ("timeframe", Timeframe),
            ("state", BarState),
            ("price_basis", PriceBasis),
            ("volume_basis", VolumeBasis),
            ("availability_basis", AvailabilityBasis),
        ):
            object.__setattr__(self, name, enum(getattr(self, name)))

        # Rule 9: the source is a provider id, so derived bars can't pose as provider data.
        check_provider(self.source)
        check_instrument_id(self.instrument_id)
        check_name(self.source_version, "source_version")
        check_name(self.import_id, "import_id")
        if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency):
            raise ValueError(f"currency must be an ISO 4217 code like 'USD', not {self.currency!r}")

        # Rule 1: aware UTC, start before end.
        for name in ("start_time", "end_time", "event_time", "received_at", "processed_at", "available_from"):
            check_utc(getattr(self, name), name)
        if not self.start_time < self.end_time:
            raise ValueError(f"start_time {self.start_time} must be before end_time {self.end_time}")

        # Rules 2 and 3: positive, ordered prices and non-negative volume, already at their quantum.
        o, h, lo, c = (_at_quantum(getattr(self, n), PRICE_QUANTUM, n) for n in ("open", "high", "low", "close"))
        _at_quantum(self.volume, SHARE_QUANTUM, "volume")
        if lo <= 0:
            raise ValueError(f"prices must be positive; low is {lo}")
        if not lo <= min(o, c) <= max(o, c) <= h:
            raise ValueError(f"prices are out of order: open {o}, high {h}, low {lo}, close {c}")
        if self.volume < 0:
            raise ValueError(f"volume must not be negative, not {self.volume}")

        # Rule 8: a closed bar happened at its end.
        if self.state is BarState.CLOSED and self.event_time != self.end_time:
            raise ValueError("a CLOSED bar's event_time is its end_time")

        # Rules 4 – 7: availability.
        check_revision(self.revision)
        check_availability(
            revision=self.revision,
            basis=self.availability_basis,
            event_time=self.event_time,
            received_at=self.received_at,
            available_from=self.available_from,
        )

    @property
    def identity(self) -> tuple[str, str, Timeframe, datetime]:
        return (self.source, self.instrument_id, self.timeframe, self.start_time)
