"""The CorporateAction contract (architecture Part H; ADR-009; docs/tasks/M1-09.md).

An action is one revision of one provider's record of a split, dividend,
symbol change or delisting. Its identity is
(source, instrument_id, action_type, ex_date).

Each action carries its instrument context explicitly: the instrument's
currency and its exchange time zone. Nothing defaults to USD or New York.
That lets the record check itself (a dividend is in the instrument's
currency; a backfilled action becomes available at 00:00 of its ex-date in
exchange time) and lets check_context() confirm it matches the instrument it
belongs to.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import StrEnum
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

from investment_engine.market.availability import (
    AvailabilityBasis,
    check_availability,
    check_name,
    check_provider,
    check_revision,
    check_utc,
)
from investment_engine.market.instruments import Instrument
from investment_engine.money import PRICE_QUANTUM, Money

_CURRENCY = re.compile(r"[A-Z]{3}")


class ActionType(StrEnum):
    SPLIT = "SPLIT"
    DIVIDEND = "DIVIDEND"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    DELISTING = "DELISTING"


class AmountBasis(StrEnum):
    AS_REPORTED = "AS_REPORTED"  # verified as declared (as-paid)
    RECONSTRUCTED_FROM_SPLIT_ADJUSTED = "RECONSTRUCTED_FROM_SPLIT_ADJUSTED"  # verified reconstruction (M1-12)
    NO_LATER_SPLIT = "NO_LATER_SPLIT"  # unchanged; no split between ex-date and download


# Which optional fields each action type sets; every other optional field must be None.
_TYPE_FIELDS = {
    ActionType.SPLIT: {"ratio"},
    ActionType.DIVIDEND: {"amount", "amount_basis"},
    ActionType.SYMBOL_CHANGE: {"new_symbol"},
    ActionType.DELISTING: set(),
}
_OPTIONAL = ("ratio", "amount", "amount_basis", "new_symbol")


@cache
def _timezone_names() -> frozenset[str]:
    # Exact IANA keys, the same on every platform (see instruments.py).
    return frozenset(available_timezones())


def ex_date_start(ex_date: date, exchange_timezone: str) -> datetime:
    """00:00 of `ex_date` in the exchange's time zone, in UTC: when a backfilled action becomes available."""
    return datetime.combine(ex_date, time(0, 0), tzinfo=ZoneInfo(exchange_timezone)).astimezone(UTC)


@dataclass(frozen=True)
class CorporateAction:
    source: str
    instrument_id: str
    currency: str  # the instrument's currency (explicit context)
    exchange_timezone: str  # the instrument's exchange time zone (explicit context)
    action_type: ActionType
    ex_date: date
    ratio: Decimal | None
    amount: Money | None
    amount_basis: AmountBasis | None
    new_symbol: str | None
    source_version: str
    import_id: str
    received_at: datetime
    processed_at: datetime
    revision: int
    available_from: datetime
    availability_basis: AvailabilityBasis

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_type", ActionType(self.action_type))
        object.__setattr__(self, "availability_basis", AvailabilityBasis(self.availability_basis))
        if self.amount_basis is not None:
            object.__setattr__(self, "amount_basis", AmountBasis(self.amount_basis))

        check_provider(self.source)
        check_name(self.instrument_id, "instrument_id")
        check_name(self.source_version, "source_version")
        check_name(self.import_id, "import_id")
        if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency):
            raise ValueError(f"currency must be an ISO 4217 code like 'USD', not {self.currency!r}")
        if self.exchange_timezone not in _timezone_names():
            raise ValueError(f"exchange_timezone must be an exact IANA name, not {self.exchange_timezone!r}")
        if not isinstance(self.ex_date, date) or isinstance(self.ex_date, datetime):
            raise TypeError(f"ex_date must be a date, not {type(self.ex_date).__name__}")
        for name in ("received_at", "processed_at", "available_from"):
            check_utc(getattr(self, name), name)

        self._check_type_fields()

        check_revision(self.revision)
        # An action may legitimately be observed before its ex-date (it's
        # announced in advance), so the event time for the shared rules is the
        # observation itself; backfill is pinned to the ex-date start below.
        check_availability(
            revision=self.revision,
            basis=self.availability_basis,
            event_time=min(self.available_from, self.received_at),
            received_at=self.received_at,
            available_from=self.available_from,
        )
        if self.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED:
            expected = ex_date_start(self.ex_date, self.exchange_timezone)
            if self.available_from != expected:
                raise ValueError(
                    f"a BACKFILL_ASSUMED action is available from the start of its ex-date in exchange "
                    f"time ({expected}), not {self.available_from}"
                )

    def _check_type_fields(self) -> None:
        wanted = _TYPE_FIELDS[self.action_type]
        for name in _OPTIONAL:
            present = getattr(self, name) is not None
            if present != (name in wanted):
                raise ValueError(
                    f"a {self.action_type} action {'needs' if name in wanted else 'has no'} {name}"
                )
        if self.action_type is ActionType.SPLIT:
            if not isinstance(self.ratio, Decimal):
                raise TypeError(f"ratio must be a Decimal, not {type(self.ratio).__name__}")
            if not self.ratio.is_finite() or self.ratio <= 0 or self.ratio == 1:
                raise ValueError(f"a split ratio must be positive and not 1, not {self.ratio}")
        elif self.action_type is ActionType.DIVIDEND:
            if not isinstance(self.amount, Money):
                raise TypeError(f"amount must be Money, not {type(self.amount).__name__}")
            if self.amount.currency != self.currency:
                raise ValueError(f"dividend in {self.amount.currency}, but the instrument trades in {self.currency}")
            if self.amount.amount <= 0:
                raise ValueError(f"a dividend amount must be positive, not {self.amount.amount}")
            if self.amount.amount.as_tuple().exponent < PRICE_QUANTUM.as_tuple().exponent:
                raise ValueError(f"dividend amount {self.amount.amount} has more precision than {PRICE_QUANTUM}")
        elif self.action_type is ActionType.SYMBOL_CHANGE:
            check_name(self.new_symbol, "new_symbol")

    def check_context(self, instrument: Instrument) -> None:
        """Confirm this action's explicit context matches the instrument it belongs to."""
        if instrument.instrument_id != self.instrument_id:
            raise ValueError(f"action is for {self.instrument_id}, not {instrument.instrument_id}")
        if instrument.currency != self.currency:
            raise ValueError(f"action currency {self.currency} doesn't match {instrument.currency}")
        if instrument.timezone != self.exchange_timezone:
            raise ValueError(f"action time zone {self.exchange_timezone} doesn't match {instrument.timezone}")

    @property
    def identity(self) -> tuple[str, str, ActionType, date]:
        return (self.source, self.instrument_id, self.action_type, self.ex_date)
