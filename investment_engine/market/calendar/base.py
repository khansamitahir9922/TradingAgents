"""The trading-calendar port (architecture Law 6: calendars are explicit)."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable


class CalendarRangeError(LookupError):
    """The date is outside the calendar's covered range; the calendar won't guess."""


@dataclass(frozen=True)
class Session:
    date: date  # exchange-local date
    open: datetime  # UTC
    close: datetime  # UTC
    is_half_day: bool


@runtime_checkable
class TradingCalendar(Protocol):
    timezone: str
    covered_from: date
    covered_to: date  # inclusive

    def is_session(self, d: date) -> bool: ...

    def session(self, d: date) -> Session:
        """The session on `d`; ValueError if `d` isn't a session."""
        ...

    def sessions_between(self, start: date, end: date) -> list[Session]:
        """Every session from `start` to `end`, both inclusive."""
        ...

    def next_session(self, d: date) -> Session:
        """The first session strictly after `d`."""
        ...

    def previous_session(self, d: date) -> Session:
        """The last session strictly before `d`."""
        ...
