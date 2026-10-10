"""Explicit time (architecture Law 5).

Business code never reads the system clock: it is handed a Clock. LiveClock
reads the system clock (this module is the only place allowed to, enforced by
tests/engine/test_no_system_clock.py); ReplayClock replays history and only
moves forward. Every datetime a contract carries is timezone-aware UTC.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol


def ensure_utc(dt: datetime) -> datetime:
    """Return `dt` converted to UTC. A naive datetime is refused, not assumed."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"naive datetime {dt!r}: a time zone is required")
    return dt.astimezone(UTC)


class Clock(Protocol):
    def now(self) -> datetime:
        """The current time, timezone-aware UTC."""
        ...


class LiveClock:
    """The system clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class ReplayClock:
    """A clock that replays history. It moves only forward, and only when told to."""

    def __init__(self, start: datetime) -> None:
        self._now = ensure_utc(start)

    def now(self) -> datetime:
        return self._now

    def advance_to(self, t: datetime) -> None:
        t = ensure_utc(t)
        if t < self._now:
            raise ValueError(f"replay clock cannot move backwards: {t} is before {self._now}")
        self._now = t

    def advance_by(self, delta: timedelta) -> None:
        if delta < timedelta(0):
            raise ValueError(f"replay clock cannot move backwards: {delta} is negative")
        self._now += delta
