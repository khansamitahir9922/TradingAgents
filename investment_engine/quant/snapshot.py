"""FeatureSnapshot: everything a strategy may see at T (Part F; docs/tasks/M2-03.md).

One T for everything: the adjusted bars, split actions, feature values and the
DataHealth are all as of the same `at`. The decision bar is the bar of the
latest session that closed at or before T; a session still open at T is never
used. Features read the calendar-consecutive sessions ending at it, at most
the longest declared warm-up, and never earlier than the verified history
boundary (the action coverage's first date):
- a window cut short by that boundary is warm-up: those features are None and
  listed in `warmup`;
- a missing session anywhere in the window, a missing decision bar, unavailable
  adjustment coverage or a missing health entry for the required source make
  the snapshot unavailable, with the reason and no feature values.
The snapshot only reports; the abstention decision is M2-06's. Only
AdjustmentUnavailable is caught; programming, data and database errors
propagate.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType

from investment_engine.market.availability import check_utc
from investment_engine.market.candles import Timeframe
from investment_engine.market.data_health import DataHealth, SourceKey
from investment_engine.quant.adjusted import (
    ActionCoverage,
    ActionRef,
    AdjustedBar,
    AdjustedBasis,
    AdjustmentUnavailable,
    BarRef,
    adjusted_daily,
    local_date,
)
from investment_engine.quant.features import FeatureDefinition
from investment_engine.quant.indicators import evaluate


@dataclass(frozen=True)
class FeatureSnapshot:
    instrument_id: str
    source: str
    as_of: datetime  # T, UTC
    session_date: date  # the latest session closed at T
    values: Mapping[str, float | None]  # feature key -> value (None during warm-up or when unavailable)
    feature_versions: Mapping[str, str]  # feature key -> version
    input_refs: tuple[BarRef, ...]  # every raw bar used (all bars examined when unavailable)
    action_refs: tuple[ActionRef, ...]
    action_coverage: ActionCoverage
    unavailable_reason: str  # "" when available
    adjusted_basis: AdjustedBasis
    data_health: DataHealth  # M1-16, at the same T
    warmup: tuple[str, ...]  # feature keys in warm-up from the history boundary
    decision_close: float | None  # the decision bar's adjusted close (as of T)


def decision_session(calendar, at: datetime):
    """The latest session whose close is at or before T."""
    d = local_date(at, calendar)
    if calendar.is_session(d) and calendar.session(d).close <= at:
        return calendar.session(d)
    return calendar.previous_session(d)


def window_sessions(calendar, last: date, count: int, boundary: date) -> list:
    """Up to `count` consecutive sessions ending at `last`, none before `boundary`."""
    start = max(boundary, last - timedelta(days=count * 7 // 5 + 30))
    sessions = calendar.sessions_between(start, last)
    if len(sessions) < count and start > boundary:
        sessions = calendar.sessions_between(boundary, last)
    return sessions[-count:]


def _check_features(features: Sequence[FeatureDefinition]) -> tuple[FeatureDefinition, ...]:
    features = tuple(features)
    if not features:
        raise ValueError("a snapshot needs at least one feature")
    for f in features:
        if not isinstance(f, FeatureDefinition):
            raise TypeError(f"features must be FeatureDefinitions, not {type(f).__name__}")
        if f.input_basis is not AdjustedBasis.SPLIT_ADJUSTED_AS_OF:
            raise ValueError(f"{f.key} reads {f.input_basis}, which this snapshot doesn't provide")
    if len({f.key for f in features}) != len(features):
        raise ValueError("features must be distinct")
    return features


def build_snapshot(instrument_id: str, source: str, features: Sequence[FeatureDefinition], *, at: datetime, reader,
                   calendar, health: DataHealth, coverage: ActionCoverage) -> FeatureSnapshot:
    at = check_utc(at, "at")
    features = _check_features(features)
    if not isinstance(health, DataHealth):
        raise TypeError(f"health must be DataHealth, not {type(health).__name__}")
    if health.as_of != at:
        raise ValueError(f"health.as_of {health.as_of} is not T {at}")
    if health.instrument_id != instrument_id:
        raise ValueError(f"health is for instrument {health.instrument_id}, not {instrument_id}")

    session = decision_session(calendar, at)
    keys = [f.key for f in features]

    def result(reason: str, *, bars: Sequence[AdjustedBar] = (), values=None, warmup=(),
               decision: AdjustedBar | None = None) -> FeatureSnapshot:
        refs = tuple(b.raw_ref for b in bars)
        action_refs = tuple(sorted({a for b in bars for a in b.action_refs}, key=lambda a: (a.ex_date, a.revision)))
        values = values if values is not None else dict.fromkeys(keys)
        return FeatureSnapshot(
            instrument_id=instrument_id, source=source, as_of=at, session_date=session.date,
            values=MappingProxyType(dict(values)),
            feature_versions=MappingProxyType({f.key: f.version for f in features}),
            input_refs=refs, action_refs=action_refs, action_coverage=coverage, unavailable_reason=reason,
            adjusted_basis=AdjustedBasis.SPLIT_ADJUSTED_AS_OF, data_health=health, warmup=tuple(warmup),
            decision_close=None if decision is None else decision.close)

    required = SourceKey(source, Timeframe.D1)
    if required not in {s.source for s in health.sources}:
        return result(f"required source {source} D1 has no entry in DataHealth")

    longest = max(f.warmup_sessions for f in features)
    window = window_sessions(calendar, session.date, longest, coverage.first)
    if not window:
        return result("", warmup=keys)
    try:
        bars = adjusted_daily(reader, source, instrument_id, window[0].date, session.date, at=at, calendar=calendar,
                              coverage=coverage)
    except AdjustmentUnavailable as exc:
        return result(f"adjustment unavailable: {exc}")

    by_date = {b.session_date: b for b in bars}
    if session.date not in by_date:
        return result(f"no bar for the decision session {session.date}", bars=bars)
    holes = [s.date for s in window if s.date not in by_date]
    if holes:
        shown = ", ".join(str(d) for d in holes[:5]) + (f" and {len(holes) - 5} more" if len(holes) > 5 else "")
        return result(f"missing sessions in the feature window: {shown}", bars=bars)

    closes = [by_date[s.date].close for s in window]
    values, warmup, used = {}, [], 0
    for f in features:
        if len(closes) < f.warmup_sessions:
            values[f.key] = None
            warmup.append(f.key)
        else:
            values[f.key] = evaluate(f, closes[-f.warmup_sessions:])
            used = max(used, f.warmup_sessions)
    used_bars = [by_date[s.date] for s in window[len(window) - max(used, 1):]]
    return result("", bars=used_bars, values=values, warmup=warmup, decision=by_date[session.date])
