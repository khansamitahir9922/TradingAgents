"""US equities regular sessions: 09:30-16:00 America/New_York (docs/tasks/M1-06.md).

Wall-clock session times are converted to UTC with zoneinfo, so daylight
saving is handled by the time-zone database. Holidays and early closes are
supplied by the caller (M1-07 loads the cited data); any date outside the
covered range raises CalendarRangeError instead of being guessed.
"""

from collections.abc import Collection, Mapping
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from investment_engine.market.calendar.base import CalendarRangeError, Session

TIMEZONE = "America/New_York"
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)


def _plain_date(value: object, what: str) -> date:
    # datetime is a subclass of date; calendar questions are about days.
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return value


class UsEquitiesCalendar:
    timezone = TIMEZONE

    def __init__(
        self,
        *,
        covered_from: date,
        covered_to: date,
        holidays: Collection[date] = frozenset(),
        half_days: Mapping[date, time] | None = None,
    ) -> None:
        self.covered_from = _plain_date(covered_from, "covered_from")
        self.covered_to = _plain_date(covered_to, "covered_to")
        if covered_to < covered_from:
            raise ValueError(f"coverage {covered_from} .. {covered_to} runs backwards")
        self._zone = ZoneInfo(TIMEZONE)
        self._holidays = frozenset(holidays)
        self._half_days = dict(half_days or {})

        for d in self._holidays | self._half_days.keys():
            _plain_date(d, "closure date")
            if not covered_from <= d <= covered_to:
                raise ValueError(f"closure {d} is outside the covered range")
            if d.weekday() >= 5:
                raise ValueError(f"closure {d} falls on a weekend")
        if both := self._holidays & self._half_days.keys():
            raise ValueError(f"dates both closed and half-days: {sorted(both)}")
        for d, close in self._half_days.items():
            if not REGULAR_OPEN < close < REGULAR_CLOSE:
                raise ValueError(f"half-day close {close} on {d} isn't within regular hours")

    def _check(self, d: object) -> date:
        d = _plain_date(d, "date")
        if not self.covered_from <= d <= self.covered_to:
            raise CalendarRangeError(f"{d} is outside {self.covered_from} .. {self.covered_to}")
        return d

    def _utc(self, d: date, t: time) -> datetime:
        return datetime.combine(d, t, tzinfo=self._zone).astimezone(UTC)

    def is_session(self, d: date) -> bool:
        d = self._check(d)
        return d.weekday() < 5 and d not in self._holidays

    def session(self, d: date) -> Session:
        if not self.is_session(d):
            raise ValueError(f"{d} is not a trading session")
        close = self._half_days.get(d, REGULAR_CLOSE)
        return Session(
            date=d,
            open=self._utc(d, REGULAR_OPEN),
            close=self._utc(d, close),
            is_half_day=d in self._half_days,
        )

    def sessions_between(self, start: date, end: date) -> list[Session]:
        start, end = self._check(start), self._check(end)
        if end < start:
            raise ValueError(f"range {start} .. {end} runs backwards")
        days = (start + timedelta(days=n) for n in range((end - start).days + 1))
        return [self.session(d) for d in days if self.is_session(d)]

    def next_session(self, d: date) -> Session:
        d = self._check(d) + timedelta(days=1)
        while not self.is_session(d):  # raises CalendarRangeError past coverage
            d += timedelta(days=1)
        return self.session(d)

    def previous_session(self, d: date) -> Session:
        d = self._check(d) - timedelta(days=1)
        while not self.is_session(d):
            d -= timedelta(days=1)
        return self.session(d)
