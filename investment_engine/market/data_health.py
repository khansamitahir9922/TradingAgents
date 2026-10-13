"""DataHealth per provider and timeframe (architecture Part H; Law 9; docs/tasks/M1-16.md).

Only the four frozen statuses exist: OK, STALE, MISSING and DEGRADED. Whether a
check applies at all (the instrument isn't active at T) is reported separately,
and then no status is invented. Everything is read as visible at T, the
injected clock's time:
- MISSING: no symbol mapping for the provider at T, or no bar of that provider
  and timeframe visible in the lookback window;
- STALE: more expected bars have closed after the latest visible bar than the
  timeframe's threshold allows (expected bars come from the calendar, so
  nights, weekends and holidays never count);
- DEGRADED: not stale, but expected bars up to the latest visible one are
  missing (holes);
- OK: none of these.
Providers are evaluated independently; one never fills another's gap. Nothing
is written or persisted.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from zoneinfo import ZoneInfo

from investment_engine.clock import Clock
from investment_engine.market.availability import check_utc
from investment_engine.market.calendar.base import CalendarRangeError, Session, TradingCalendar
from investment_engine.market.candles import BarState, Timeframe
from investment_engine.market.symbols import UnknownSymbol

_HOUR = timedelta(hours=1)


class HealthStatus(StrEnum):  # exactly the four frozen states (Part H)
    OK = "OK"
    STALE = "STALE"
    MISSING = "MISSING"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class SourceKey:
    provider: str
    timeframe: Timeframe

    def __post_init__(self) -> None:
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))


@dataclass(frozen=True)
class SourceHealth:
    source: SourceKey
    status: HealthStatus
    as_of: datetime  # the evaluation time T (UTC)
    latest_bar_end: datetime | None
    age: timedelta | None  # as_of - latest_bar_end; None when there's no bar
    bars_behind: int | None  # expected closed bars after latest_bar_end, up to as_of
    missing_in_window: tuple[datetime, ...]
    detail: str  # the reason; empty only when OK


@dataclass(frozen=True)
class Applicability:  # separate from the four statuses
    applicable: bool
    reason: str  # "" when applicable


@dataclass(frozen=True)
class DataHealth:
    instrument_id: str
    as_of: datetime
    applicability: Applicability
    sources: tuple[SourceHealth, ...]  # empty when not applicable: no status is invented
    required_sources_ok: bool  # False when not applicable


def _default_stale_after() -> Mapping[Timeframe, int]:
    return MappingProxyType({Timeframe.D1: 1, Timeframe.H1: 1})


@dataclass(frozen=True)
class HealthThresholds:
    """Configuration with documented defaults; callers and the CLI may override it."""

    stale_after_bars: Mapping[Timeframe, int] = field(default_factory=_default_stale_after)
    lookback_sessions: int = 20

    def __post_init__(self) -> None:
        values = MappingProxyType({Timeframe(k): v for k, v in dict(self.stale_after_bars).items()})
        if set(values) != set(Timeframe):
            raise ValueError(f"stale_after_bars needs a threshold for every timeframe: {sorted(Timeframe)}")
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values.values()):
            raise ValueError("stale thresholds must be non-negative integers")
        if not isinstance(self.lookback_sessions, int) or self.lookback_sessions < 1:
            raise ValueError("lookback_sessions must be a positive integer")
        object.__setattr__(self, "stale_after_bars", values)


def _expected(sessions: Sequence[Session], timeframe: Timeframe, at: datetime) -> list[tuple[datetime, datetime]]:
    """(start, end) of every bar expected to have closed by `at`, in order."""
    bars = []
    for s in sessions:
        if timeframe is Timeframe.D1:
            candidates = [(s.open, s.close)]
        else:
            candidates, start = [], s.open
            while start < s.close:
                candidates.append((start, min(start + _HOUR, s.close)))
                start += _HOUR
        bars.extend((start, end) for start, end in candidates if end <= at)
    return bars


def _lookback(calendar: TradingCalendar, at: datetime, n: int) -> list[Session]:
    """The last `n` sessions that opened before `at`, oldest first, within the calendar's coverage.

    A time outside the coverage raises CalendarRangeError: the expected bars can't be established, so no
    status is reported. Inside it, the window may be shorter where the coverage begins.
    """
    d = at.astimezone(ZoneInfo(calendar.timezone)).date()
    sessions: list[Session] = []
    current = calendar.session(d) if calendar.is_session(d) else calendar.previous_session(d)
    try:
        while len(sessions) < n:
            if current.open < at:
                sessions.append(current)
            current = calendar.previous_session(current.date)
    except CalendarRangeError:
        pass  # the calendar's start bounds the window; it never guesses earlier sessions
    return sessions[::-1]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _source_health(key: SourceKey, *, instrument_id: str, at: datetime, local: date, reader, resolver,
                   sessions: Sequence[Session], threshold: int) -> SourceHealth:
    def result(status, detail="", latest=None, behind=None, missing=()):
        age = None if latest is None else at - latest
        return SourceHealth(key, status, at, latest, age, behind, tuple(missing), detail)

    try:
        resolver.symbol_for(instrument_id, key.provider, local)
    except UnknownSymbol:
        return result(HealthStatus.MISSING, f"no symbol mapping for {key.provider} on {local}")
    expected = _expected(sessions, key.timeframe, at)
    visible = []
    if sessions:
        visible = reader.candles_visible_at(key.provider, instrument_id, key.timeframe, sessions[0].open, at, at)
    if not visible:
        return result(HealthStatus.MISSING,
                      f"no {key.provider} {key.timeframe} bar visible in the last {_plural(len(sessions), 'session')}")
    expected_pairs = set(expected)
    for c in visible:
        if (c.source, c.instrument_id, c.timeframe) != (key.provider, instrument_id, key.timeframe):
            raise ValueError("reader row identity does not match the requested provider, instrument and timeframe")
        if (c.state is not BarState.CLOSED or c.available_from > at or
                (c.start_time, c.end_time) not in expected_pairs):
            raise ValueError("health inputs must be available, closed bars with the expected session boundaries")
    latest = max(visible, key=lambda c: c.end_time)
    present = {c.start_time for c in visible}
    behind = sum(1 for _, end in expected if end > latest.end_time)
    holes = tuple(start for start, end in expected if end <= latest.end_time and start not in present)
    if behind > threshold:
        return result(HealthStatus.STALE, f"{_plural(behind, 'expected bar')} behind (threshold {threshold})",
                      latest.end_time, behind, holes)
    if holes:
        return result(HealthStatus.DEGRADED, f"{_plural(len(holes), 'expected bar')} missing in the lookback window",
                      latest.end_time, behind, holes)
    return result(HealthStatus.OK, "", latest.end_time, behind, holes)


def evaluate_health(instrument_id: str, required: Sequence[SourceKey], *, clock: Clock, reader, instruments,
                    resolver, calendar: TradingCalendar,
                    thresholds: HealthThresholds | None = None) -> DataHealth:
    """DataHealth for `instrument_id` at T = clock.now(), one entry per required source."""
    thresholds = thresholds or HealthThresholds()
    required = [k if isinstance(k, SourceKey) else SourceKey(*k) for k in required]
    if not required:
        raise ValueError("the required source set must not be empty")
    if len(set(required)) != len(required):
        raise ValueError(f"the required source set has duplicates: {required}")
    at = check_utc(clock.now(), "clock.now()")
    local = at.astimezone(ZoneInfo(calendar.timezone)).date()

    instrument = instruments.get(instrument_id)  # an unknown instrument raises: nothing is invented
    if not instrument.is_active_on(local):
        if local < instrument.active_from:
            reason = f"{instrument_id} not active before {instrument.active_from}"
        else:
            reason = f"{instrument_id} not active on or after {instrument.active_to}"
        return DataHealth(instrument_id, at, Applicability(False, reason), (), False)

    sessions = _lookback(calendar, at, thresholds.lookback_sessions)
    sources = tuple(
        _source_health(k, instrument_id=instrument_id, at=at, local=local, reader=reader, resolver=resolver,
                       sessions=sessions, threshold=thresholds.stale_after_bars[k.timeframe])
        for k in required)
    ok = all(s.status is HealthStatus.OK for s in sources)
    return DataHealth(instrument_id, at, Applicability(True, ""), sources, ok)
