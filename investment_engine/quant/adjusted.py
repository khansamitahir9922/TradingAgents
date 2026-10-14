"""The point-in-time split-adjusted daily view (ADR-007, ADR-009; docs/tasks/M2-00.md).

Stored prices stay raw. For a bar on session d, viewed as of T, the factor
F_T(d) is the exact Decimal product of the ratios of the SPLIT actions that
are visible at T (their revision's available_from <= T), effective by T
(ex_date on or before T's exchange-local date) and after the bar
(d < ex_date). Prices are divided by F_T(d) and volume multiplied by it, so
the latest bars are as traded at T and earlier ones are scaled to them.

Everything is read as visible at T, from one provider. A split is applied
only when established ActionCoverage, backed by completed exhaustive
verification references, covers that provider, instrument, SPLIT type and the
whole range up to T: an empty action query proves nothing by itself. Only
completed bars are used (CLOSED, ended and available by T); malformed input
raises rather than being dropped. The result is never stored and is not a
Candle.
"""

import decimal
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from investment_engine.market.availability import (
    AvailabilityBasis,
    check_instrument_id,
    check_name,
    check_provider,
    check_utc,
)
from investment_engine.market.candles import BarState, Candle, Timeframe
from investment_engine.market.corporate_actions import ActionType, CorporateAction
from investment_engine.money import to_float64


def _context() -> decimal.Context:
    """A fresh context per calculation, so no flag or setting is shared between calls.

    Price / factor isn't exact in Decimal; at 60 significant digits the only
    rounding that matters is the single conversion to float64.
    """
    return decimal.Context(prec=60, rounding=decimal.ROUND_HALF_EVEN)


class AdjustedBasis(StrEnum):
    SPLIT_ADJUSTED_AS_OF = "SPLIT_ADJUSTED_AS_OF"  # price return only; total return is M2-08


class AdjustmentUnavailable(ValueError):
    """Declared coverage or an adjustment input is unavailable; the policy must abstain."""


@dataclass(frozen=True)
class BarRef:
    source: str
    instrument_id: str
    timeframe: Timeframe
    start_time: datetime
    revision: int
    import_id: str
    available_from: datetime
    availability_basis: AvailabilityBasis


@dataclass(frozen=True)
class ActionRef:
    source: str
    instrument_id: str
    action_type: ActionType
    ex_date: date
    revision: int
    import_id: str
    available_from: datetime
    availability_basis: AvailabilityBasis


def bar_ref(c: Candle) -> BarRef:
    return BarRef(c.source, c.instrument_id, c.timeframe, c.start_time, c.revision, c.import_id, c.available_from,
                  c.availability_basis)


def action_ref(a: CorporateAction) -> ActionRef:
    return ActionRef(a.source, a.instrument_id, a.action_type, a.ex_date, a.revision, a.import_id, a.available_from,
                     a.availability_basis)


# ---------------------------------------------------------------- coverage evidence

_STATUSES = ("COMPLETE", "PARTIAL", "FAILED")
_REF = re.compile(
    r"verification:(?P<provider>[^|]+)\|(?P<instrument_id>[^|]+)\|(?P<action_type>[A-Z_]+)"
    r"\|verified=(?P<first>\d{4}-\d{2}-\d{2})\.\.(?P<last>\d{4}-\d{2}-\d{2})"
    r"\|request=(?P<request_first>\d{4}-\d{2}-\d{2})\.\.(?P<request_last>\d{4}-\d{2}-\d{2})"
    r"\|version=(?P<verification>[^|]+)\|status=(?P<status>[A-Z]+)"
)


def _plain_date(value: object, what: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return value


@dataclass(frozen=True)
class VerificationEvidence:
    """One completed (or partial/failed) verification of a provider's action history.

    `first`..`last` is the range the verification established as exhaustive for one
    action type; `request_first`..`request_last` are the bounds of the request that
    produced it; `verification` names the versioned verification record. Only a
    COMPLETE verification can establish coverage, including coverage with zero events.
    """

    provider: str
    instrument_id: str
    action_type: ActionType
    first: date
    last: date
    request_first: date
    request_last: date
    verification: str
    status: str

    def __post_init__(self) -> None:
        check_provider(self.provider)
        check_instrument_id(self.instrument_id)
        object.__setattr__(self, "action_type", ActionType(self.action_type))
        for name in ("first", "last", "request_first", "request_last"):
            _plain_date(getattr(self, name), name)
        check_name(self.verification, "verification")
        if "|" in self.verification:
            raise ValueError("the verification version must not contain '|'")
        if self.status not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}, not {self.status!r}")
        if not self.first <= self.last:
            raise ValueError("the verified range runs backwards")
        if not (self.request_first <= self.first and self.last <= self.request_last):
            raise ValueError("the verified range must lie within the completed request's bounds")

    @property
    def ref(self) -> str:
        return (f"verification:{self.provider}|{self.instrument_id}|{self.action_type}"
                f"|verified={self.first}..{self.last}|request={self.request_first}..{self.request_last}"
                f"|version={self.verification}|status={self.status}")

    @classmethod
    def parse(cls, ref: str) -> "VerificationEvidence":
        match = _REF.fullmatch(ref) if isinstance(ref, str) else None
        if match is None:
            raise ValueError(f"not a verification evidence reference: {ref!r}")
        g = match.groupdict()
        dates = {k: date.fromisoformat(g[k]) for k in ("first", "last", "request_first", "request_last")}
        return cls(provider=g["provider"], instrument_id=g["instrument_id"], action_type=ActionType(g["action_type"]),
                   verification=g["verification"], status=g["status"], **dates)


@dataclass(frozen=True)
class ActionCoverage:
    source: str
    instrument_id: str
    types: tuple[ActionType, ...]
    first: date
    last: date
    as_of: datetime
    established: bool
    evidence_refs: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "types", tuple(ActionType(t) for t in self.types))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        check_utc(self.as_of, "as_of")
        _plain_date(self.first, "first")
        _plain_date(self.last, "last")
        if not isinstance(self.established, bool):
            raise TypeError("established must be a bool")


def _supports(ev: VerificationEvidence, source: str, instrument_id: str, action_type: ActionType,
              first: date, last: date) -> bool:
    return (ev.status == "COMPLETE" and ev.provider == source and ev.instrument_id == instrument_id
            and ev.action_type is action_type and ev.first <= first and last <= ev.last)


def establish_coverage(evidence: Sequence[VerificationEvidence], *, source: str, instrument_id: str,
                       types: Sequence[ActionType], first: date, last: date, as_of: datetime,
                       reason: str) -> ActionCoverage:
    """ActionCoverage that is established only if completed evidence covers every type over the whole range.

    The coverage is an explicit, versioned research assumption based on the
    verification record; it is not a claim that the history was observed at as_of.
    Every evidence reference is kept, so it survives into lineage.
    """
    check_provider(source)
    check_instrument_id(instrument_id)
    types = tuple(ActionType(t) for t in types)
    if not types:
        raise ValueError("coverage needs at least one action type")
    evidence = tuple(evidence)
    missing = [t for t in types
               if not any(_supports(ev, source, instrument_id, t, first, last) for ev in evidence)]
    established = bool(evidence) and not missing
    if not established:
        reason = (f"{reason}; not established: no completed verification covers "
                  f"{', '.join(str(t) for t in missing or types)} for {source} {instrument_id} {first}..{last}")
    return ActionCoverage(source, instrument_id, types, first, last, check_utc(as_of, "as_of"), established,
                          tuple(ev.ref for ev in evidence), reason)


def require_coverage(coverage: ActionCoverage, *, source: str, instrument_id: str, action_type: ActionType,
                     first: date, last: date, at: datetime) -> None:
    """Raise AdjustmentUnavailable unless `coverage` really establishes `action_type` over first..last at T."""
    if not isinstance(coverage, ActionCoverage):
        raise TypeError(f"coverage must be ActionCoverage, not {type(coverage).__name__}")
    if not coverage.established:
        raise AdjustmentUnavailable(f"action coverage is not established: {coverage.reason}")
    problems = []
    if (coverage.source, coverage.instrument_id) != (source, instrument_id):
        problems.append(f"coverage is for {coverage.source} {coverage.instrument_id}")
    if action_type not in coverage.types:
        problems.append(f"coverage doesn't include {action_type}")
    if coverage.as_of != at:
        problems.append(f"coverage is as of {coverage.as_of}, not T {at}")
    if not (coverage.first <= first and last <= coverage.last):
        problems.append(f"coverage {coverage.first}..{coverage.last} doesn't include {first}..{last}")
    if problems:
        raise AdjustmentUnavailable("action coverage doesn't match the request: " + "; ".join(problems))
    supported = False
    for ref in coverage.evidence_refs:
        try:
            ev = VerificationEvidence.parse(ref)
        except ValueError:
            continue
        supported = supported or _supports(ev, source, instrument_id, action_type, first, last)
    if not supported:
        raise AdjustmentUnavailable(
            f"no completed verification evidence covers {action_type} for {source} {instrument_id} {first}..{last}")


# ---------------------------------------------------------------- the view


@dataclass(frozen=True)
class AdjustedBar:  # quant domain: float64 (ADR-007), never stored, never a Candle
    source: str
    instrument_id: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    basis: AdjustedBasis
    as_of: datetime  # T
    factor: Decimal  # the cumulative split factor applied, exact
    raw_ref: BarRef
    action_refs: tuple[ActionRef, ...]  # every split revision used


def local_date(at: datetime, calendar) -> date:
    return at.astimezone(ZoneInfo(calendar.timezone)).date()


def completed_daily_bars(reader, source: str, instrument_id: str, sessions, *, at: datetime) -> dict[date, Candle]:
    """The visible daily bars of `sessions` at T, each checked to be a completed, well-formed bar of this identity.

    Shared with the other point-in-time readers of M2: CLOSED, exact session
    boundaries, ended and available by T, received no earlier than its end, one
    currency, no duplicates. Malformed rows raise; missing sessions are simply absent.
    """
    if not sessions:
        return {}
    by_open = {s.open: s for s in sessions}
    rows = reader.candles_visible_at(source, instrument_id, Timeframe.D1, sessions[0].open, sessions[-1].close, at)
    bars: dict[date, Candle] = {}
    currencies = set()
    for c in rows:
        if not isinstance(c, Candle):
            raise TypeError(f"the reader returned {type(c).__name__}, not a Candle")
        if (c.source, c.instrument_id, c.timeframe) != (source, instrument_id, Timeframe.D1):
            raise ValueError(f"the reader returned a bar for {(c.source, c.instrument_id, c.timeframe)}, "
                             f"not {(source, instrument_id, Timeframe.D1)}")
        if c.state is not BarState.CLOSED:
            raise ValueError(f"only CLOSED bars may be used, not {c.state}: {c.identity}")
        session = by_open.get(c.start_time)
        if session is None or c.end_time != session.close:
            raise ValueError(f"bar {c.start_time}..{c.end_time} doesn't match an expected session")
        if c.end_time > at or c.available_from > at:
            raise ValueError(f"bar {c.identity} ends or becomes available after T {at}")
        if c.received_at < c.end_time:
            raise ValueError(f"bar {c.identity} was received at {c.received_at}, before it ended: malformed")
        if session.date in bars:
            raise ValueError(f"the reader returned session {session.date} twice")
        currencies.add(c.currency)
        bars[session.date] = c
    if len(currencies) > 1:
        raise ValueError(f"bars of one series must share a currency, not {sorted(currencies)}")
    return bars


def visible_actions(reader, source: str, instrument_id: str, action_type: ActionType, first: date, *,
                    at: datetime, calendar) -> list[CorporateAction]:
    """Actions of one type visible at T and effective by T's session date, each checked."""
    t_date = local_date(at, calendar)
    rows = reader.actions_visible_at(source, instrument_id, first, t_date + timedelta(days=1), at, types={action_type})
    seen = set()
    for a in rows:
        if not isinstance(a, CorporateAction):
            raise TypeError(f"the reader returned {type(a).__name__}, not a CorporateAction")
        if (a.source, a.instrument_id, a.action_type) != (source, instrument_id, action_type):
            raise ValueError(f"the reader returned an action for {(a.source, a.instrument_id, a.action_type)}")
        if a.available_from > at:
            raise ValueError(f"action {a.identity} becomes available after T {at}")
        if not first <= a.ex_date <= t_date:
            raise ValueError(f"action {a.identity} is outside {first}..{t_date}")
        if a.identity in seen:
            raise ValueError(f"the reader returned action {a.identity} twice")
        seen.add(a.identity)
    return sorted(rows, key=lambda a: a.ex_date)


def split_factor(splits: Sequence[CorporateAction], d: date) -> tuple[Decimal, tuple[CorporateAction, ...]]:
    """F(d): the exact product of the ratios of `splits` with d < ex_date, and those splits."""
    used = tuple(a for a in splits if d < a.ex_date)
    context = _context()
    factor = Decimal(1)
    for a in used:
        factor = context.multiply(factor, a.ratio)
    if context.flags[decimal.Inexact]:
        raise ValueError("the cumulative split factor is not exact")
    return factor, used


def _scaled(value: Decimal, factor: Decimal, *, divide: bool, what: str) -> float:
    context = _context()
    result = to_float64(context.divide(value, factor) if divide else context.multiply(value, factor))
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"adjusted {what} is not finite")
    return result


def adjusted_daily(reader, source: str, instrument_id: str, first: date, last: date, *, at: datetime, calendar,
                   coverage: ActionCoverage,
                   basis: AdjustedBasis = AdjustedBasis.SPLIT_ADJUSTED_AS_OF) -> list[AdjustedBar]:
    """The split-adjusted daily bars of sessions first..last (both inclusive) as of T = `at`."""
    check_provider(source)
    check_instrument_id(instrument_id)
    _plain_date(first, "first")
    _plain_date(last, "last")
    at = check_utc(at, "at")
    basis = AdjustedBasis(basis)
    if last < first:
        raise ValueError(f"the range {first}..{last} runs backwards")
    t_date = local_date(at, calendar)
    require_coverage(coverage, source=source, instrument_id=instrument_id, action_type=ActionType.SPLIT,
                     first=first, last=max(last, t_date), at=at)

    sessions = calendar.sessions_between(first, last)  # a session still open at T yields no bar, or raises
    bars = completed_daily_bars(reader, source, instrument_id, sessions, at=at)
    splits = visible_actions(reader, source, instrument_id, ActionType.SPLIT, first, at=at, calendar=calendar)
    currencies = {c.currency for c in bars.values()}
    if splits and currencies and {a.currency for a in splits} != currencies:
        raise ValueError("split actions and bars disagree on the instrument's currency")

    out = []
    for d in sorted(bars):
        c = bars[d]
        factor, used = split_factor(splits, d)
        out.append(AdjustedBar(
            source=source, instrument_id=instrument_id, session_date=d,
            open=_scaled(c.open, factor, divide=True, what="open"),
            high=_scaled(c.high, factor, divide=True, what="high"),
            low=_scaled(c.low, factor, divide=True, what="low"),
            close=_scaled(c.close, factor, divide=True, what="close"),
            volume=_scaled(c.volume, factor, divide=False, what="volume"),
            basis=basis, as_of=at, factor=factor, raw_ref=bar_ref(c),
            action_refs=tuple(action_ref(a) for a in used),
        ))
    return out
