"""Hourly → daily resampling within calendar sessions, as of a cutoff (docs/tasks/M1-15.md).

A resampled day uses only one provider's hourly bars that were available at
`at`. A closed session with every expected hour gives a CLOSED bar; a session
still open gives a FORMING bar, but only when every hour that has ended is
present; anything else is a SessionGap, never a partial day shown as whole.
Every input revision is referenced. A ResampledBar isn't a Candle and is never
stored. Differences from the vendor's daily series are reported, not resolved.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from investment_engine.market.availability import AvailabilityBasis, check_utc
from investment_engine.market.calendar.base import Session, TradingCalendar
from investment_engine.market.candles import BarState, Candle, PriceBasis, Timeframe, VolumeBasis

DERIVATION = "H1->D1"
_HOUR = timedelta(hours=1)
_FIELDS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class InputRef:
    """A complete reference to one input revision."""

    source: str
    instrument_id: str
    timeframe: Timeframe
    start_time: datetime
    revision: int
    import_id: str
    available_from: datetime


@dataclass(frozen=True)
class ResampledBar:
    source: str  # the single input provider
    derivation: str  # "H1->D1"
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    currency: str
    price_basis: PriceBasis
    volume_basis: VolumeBasis
    state: BarState  # CLOSED or FORMING
    start_time: datetime  # the session's open (UTC)
    end_time: datetime  # the session's close (UTC)
    as_of: datetime  # the cutoff used
    available_from: datetime  # the latest input's available_from
    availability_basis: AvailabilityBasis  # BACKFILL_ASSUMED if any input is
    inputs: tuple[InputRef, ...]  # every input, in start_time order


@dataclass(frozen=True)
class SessionGap:
    source: str
    session_date: date
    as_of: datetime
    missing_starts: tuple[datetime, ...]  # expected hourly starts with no input visible at `as_of`


@dataclass(frozen=True)
class DailyDifference:
    session_date: date
    field: str  # "open" | "high" | "low" | "close" | "volume" | "missing_vendor" | "missing_resampled"
    vendor: Decimal | None
    resampled: Decimal | None


def expected_starts(session: Session) -> list[datetime]:
    """Hourly bar starts from the open in one-hour steps; the last bar ends at the (half-day) close."""
    starts, start = [], session.open
    while start < session.close:
        starts.append(start)
        start += _HOUR
    return starts


def _check_inputs(inputs: Sequence[Candle], session: Session, at: datetime) -> list[Candle]:
    inputs = list(inputs)
    grid = {start: min(start + _HOUR, session.close) for start in expected_starts(session)}
    seen = set()
    for c in inputs:
        if not isinstance(c, Candle):
            raise TypeError(f"inputs must be Candles, not {type(c).__name__}")
        if c.timeframe is not Timeframe.H1:
            raise ValueError(f"inputs must be H1 bars, not {c.timeframe}")
        if c.state is not BarState.CLOSED:
            raise ValueError("inputs must be CLOSED bars")
        if c.end_time > at:
            raise ValueError(f"input {c.identity} ends at {c.end_time}, after the cutoff {at}")
        if c.available_from > at:
            raise ValueError(f"input {c.identity} revision {c.revision} is not available at {at}")
        if c.start_time not in grid or c.end_time != grid[c.start_time]:
            raise ValueError(f"input starting {c.start_time} isn't an expected hourly start of session {session.date}")
        if c.start_time in seen:
            raise ValueError(f"duplicate input for {c.start_time}")
        seen.add(c.start_time)
    if inputs:
        for name, what in (("source", "one provider"), ("instrument_id", "one instrument"), ("currency", "one currency"),
                           ("price_basis", "one price basis"), ("volume_basis", "one volume basis")):
            if len({getattr(c, name) for c in inputs}) != 1:
                raise ValueError(f"inputs must come from {what}; got {sorted({str(getattr(c, name)) for c in inputs})}")
    return sorted(inputs, key=lambda c: c.start_time)


def aggregate_session(inputs: Sequence[Candle], session: Session, *, at: datetime,
                      source: str | None = None) -> ResampledBar | SessionGap:
    """One session's daily bar or gap, from its hourly inputs available at `at` (rules 1 – 9).

    `source` names the provider for a gap with no inputs at all; with inputs, it must match theirs.
    """
    check_utc(at, "at")
    inputs = _check_inputs(inputs, session, at)
    provider = inputs[0].source if inputs else source
    if provider is None:
        raise ValueError("a session with no inputs needs `source` to report its gap")
    if source is not None and inputs and source != provider:
        raise ValueError(f"inputs come from {provider}, not {source}")
    present = {c.start_time for c in inputs}
    closed = session.close <= at
    due = [s for s in expected_starts(session) if closed or min(s + _HOUR, session.close) <= at]
    missing = tuple(s for s in due if s not in present)
    if missing or not inputs:
        return SessionGap(provider, session.date, at, missing)
    return ResampledBar(
        source=provider, derivation=DERIVATION, session_date=session.date,
        open=inputs[0].open, high=max(c.high for c in inputs), low=min(c.low for c in inputs),
        close=inputs[-1].close, volume=sum((c.volume for c in inputs), Decimal(0)),
        currency=inputs[0].currency, price_basis=inputs[0].price_basis, volume_basis=inputs[0].volume_basis,
        state=BarState.CLOSED if closed else BarState.FORMING,
        start_time=session.open, end_time=session.close, as_of=at,
        available_from=max(c.available_from for c in inputs),
        availability_basis=(AvailabilityBasis.BACKFILL_ASSUMED
                            if any(c.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED for c in inputs)
                            else AvailabilityBasis.OBSERVED),
        inputs=tuple(InputRef(c.source, c.instrument_id, c.timeframe, c.start_time, c.revision, c.import_id,
                              c.available_from) for c in inputs),
    )


def resample_daily(reader, source: str, instrument_id: str, first_session: date, last_session: date, *,
                   calendar: TradingCalendar, at: datetime) -> list[ResampledBar | SessionGap]:
    """Every session from `first_session` to `last_session` that has opened by `at`, as a bar or a gap.
    Inputs are read with candles_visible_at(at), so the cutoff is enforced at the source."""
    check_utc(at, "at")
    sessions = [s for s in calendar.sessions_between(first_session, last_session) if s.open < at]
    if not sessions:
        return []
    candles = reader.candles_visible_at(source, instrument_id, Timeframe.H1, sessions[0].open,
                                        sessions[-1].close, at)
    by_session: dict[date, list[Candle]] = {s.date: [] for s in sessions}
    bounds = [(s.open, s.close, s.date) for s in sessions]
    for c in candles:
        if (c.source, c.instrument_id, c.timeframe) != (source, instrument_id, Timeframe.H1):
            raise ValueError("reader row identity does not match the requested provider, instrument and timeframe")
        home = next((d for open_, close, d in bounds if open_ <= c.start_time < close), None)
        if home is None:
            raise ValueError(f"stored H1 bar starting {c.start_time} is outside every calendar session")
        by_session[home].append(c)
    return [aggregate_session(by_session[s.date], s, at=at, source=source) for s in sessions]


def compare_daily(reader, source: str, instrument_id: str, resampled: Sequence[ResampledBar], *, at: datetime,
                  first_session: date | None = None, last_session: date | None = None,
                  calendar: TradingCalendar | None = None) -> list[DailyDifference]:
    """Report how the vendor's daily bars (same provider, same cutoff) differ from CLOSED resampled bars.

    The range defaults to the resampled bars' sessions. Given `first_session`, `last_session` and
    `calendar`, every session in that range is checked, so a vendor day whose resampled side is a
    gap is reported as `missing_resampled`. FORMING bars are not compared.
    """
    check_utc(at, "at")
    bars = list(resampled)
    seen = set()
    for bar in bars:
        if bar.source != source:
            raise ValueError(f"resampled bars come from provider {bar.source}, not {source}")
        if bar.as_of != at:
            raise ValueError(f"resampled with cutoff {bar.as_of}, compared at {at}: the cutoff must be the same")
        if not bar.inputs or any((ref.source, ref.instrument_id, ref.timeframe) !=
                                 (source, instrument_id, Timeframe.H1) for ref in bar.inputs):
            raise ValueError("resampled input identity does not match the requested provider and instrument")
        # A matching as_of label is not proof that the referenced revisions were visible then.
        available = check_utc(bar.available_from, "resampled available_from")
        input_availability = [check_utc(ref.available_from, "input available_from") for ref in bar.inputs]
        if available > at or any(value > at for value in input_availability):
            raise ValueError("resampled bar and every input must be available at the comparison cutoff")
        if available != max(input_availability):
            raise ValueError("resampled availability must equal the latest input available_from")
        if bar.session_date in seen:
            raise ValueError(f"duplicate resampled session {bar.session_date}")
        seen.add(bar.session_date)
    closed = {bar.session_date: bar for bar in bars if bar.state is BarState.CLOSED}
    if first_session is not None or last_session is not None or calendar is not None:
        if first_session is None or last_session is None or calendar is None:
            raise ValueError("a session range needs first_session, last_session and calendar")
        sessions = [s for s in calendar.sessions_between(first_session, last_session) if s.close <= at]
    else:
        sessions = list(closed.values())
    if not sessions:
        return []
    spans = {s.session_date if isinstance(s, ResampledBar) else s.date:
             (s.start_time, s.end_time) if isinstance(s, ResampledBar) else (s.open, s.close) for s in sessions}
    lo = min(start for start, _ in spans.values())
    hi = max(end for _, end in spans.values())
    vendor = {}
    for c in reader.candles_visible_at(source, instrument_id, Timeframe.D1, lo, hi, at):
        if (c.source, c.instrument_id, c.timeframe) != (source, instrument_id, Timeframe.D1):
            raise ValueError("vendor row identity does not match the requested provider, instrument and timeframe")
        if c.state is not BarState.CLOSED or c.end_time > at or c.available_from > at:
            raise ValueError("vendor row must be closed and available at the comparison cutoff")
        if c.start_time in vendor:
            raise ValueError(f"duplicate vendor session starting {c.start_time}")
        vendor[c.start_time] = c
    differences = []
    for d in sorted(spans):
        start = spans[d][0]
        bar, v = closed.get(d), vendor.get(start)
        if bar is None and v is None:
            continue
        if bar is None:
            differences.append(DailyDifference(d, "missing_resampled", None, None))
        elif v is None:
            differences.append(DailyDifference(d, "missing_vendor", None, None))
        else:
            # Candle's permitted field bases all describe as-traded units.
            # Reconstruction provenance may differ between daily and hourly data.
            if v.currency != bar.currency:
                raise ValueError("vendor and resampled currency must match before comparing values")
            if (v.start_time, v.end_time) != (bar.start_time, bar.end_time):
                raise ValueError("vendor and resampled session boundaries must match")
            for name in _FIELDS:
                if getattr(v, name) != getattr(bar, name):
                    differences.append(DailyDifference(d, name, getattr(v, name), getattr(bar, name)))
    return differences
