"""Raw reference prices for order intents (docs/tasks/M3-07.md rule 1; Codex M3 review B1).

An intent's reference price is the raw, as-traded Decimal close of exactly the
bar its view decided on: the D1 bar of the view snapshot's session, from the
snapshot's own provider and instrument, in the revision the lineage names. It
exists whether or not anything is held, so a cash-only account can size its
first buy. Split-adjusted values (M2's float `decision_close`) never become
order prices (ADR-009).

What is known at T comes from a Knowledge port, which respects delivery as
well as availability (the M2 B2 cutoff):
- StoreKnowledge, for live use over the market-data store: a revision is known
  once it is available and was received by T;
- ReplayKnowledge, for replays: M2's ReplayKnowledgeReader, fed by the same
  ReplayFeed, so delivery time and equal-time sequence are respected
  (feed latency is already in its delivery times).

Anything missing or inconsistent gives Unavailable with its reason, never a
substitute price.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from investment_engine.lineage.records import register
from investment_engine.market.availability import check_utc
from investment_engine.market.candles import BarState, Candle, Timeframe
from investment_engine.quant.adjusted import BarRef

_TICK = timedelta(microseconds=1)


@dataclass(frozen=True)
class Unavailable:
    """No usable value, and why; never a default."""

    reason: str


class Knowledge(Protocol):
    """Raw bar revisions known at T: available and delivered by T (M2-07 B2)."""

    def candle_revision(self, ref: BarRef, *, at: datetime) -> Candle | None: ...

    def latest_closed(self, source: str, instrument_id: str, session: date, *, at: datetime,
                      calendar=None) -> Candle | None: ...

    def actions_between(self, source: str, instrument_id: str, first: date, last: date, *,
                        at: datetime) -> list: ...


def _identity(candle: Candle, ref: BarRef) -> bool:
    return ((candle.source, candle.instrument_id, candle.timeframe, candle.start_time, candle.revision)
            == (ref.source, ref.instrument_id, ref.timeframe, ref.start_time, ref.revision))


class StoreKnowledge:
    """Live knowledge over the market-data store: available_from <= T and received_at <= T."""

    def __init__(self, reader, calendar=None) -> None:
        self._reader, self._calendar = reader, calendar

    def candle_revision(self, ref: BarRef, *, at: datetime) -> Candle | None:
        at = check_utc(at, "at")
        history = self._reader.candle_revision_history(ref.source, ref.instrument_id, ref.timeframe,
                                                       ref.start_time, ref.start_time + _TICK)
        for candle in history:
            if _identity(candle, ref) and candle.available_from <= at and candle.received_at <= at:
                return candle
        return None

    def latest_closed(self, source: str, instrument_id: str, session: date, *, at: datetime,
                      calendar=None) -> Candle | None:
        """The highest revision of the session's D1 bar known at T, if it is CLOSED."""
        from investment_engine.market.calendar.us_equities import load_us_equities_calendar

        at = check_utc(at, "at")
        opening = (calendar or self._calendar or load_us_equities_calendar()).session(session).open
        history = self._reader.candle_revision_history(source, instrument_id, Timeframe.D1, opening, opening + _TICK)
        known = [c for c in history if c.available_from <= at and c.received_at <= at]
        latest = max(known, key=lambda c: c.revision) if known else None
        return latest if latest is not None and latest.state is BarState.CLOSED else None

    def actions_between(self, source: str, instrument_id: str, first: date, last: date, *, at: datetime) -> list:
        """Corporate actions with ex-dates in [first, last] known at T (available and received by T)."""
        at = check_utc(at, "at")
        return [a for a in self._reader.actions_visible_at(source, instrument_id, first, last + timedelta(days=1), at)
                if a.received_at <= at]


class ReplayKnowledge:
    """Replay knowledge over M2's ReplayKnowledgeReader, optionally up to an equal-time feed sequence.

    The reader refuses a T later than its last delivered event, since later events may still be coming.
    A caller that has fed every event delivered up to some time (the intent pipeline does, before proposing
    at that time) says so with `complete_through`; queries up to that time are then answered from what was
    delivered."""

    def __init__(self, reader, *, through_sequence: int | None = None, calendar=None,
                 complete_through: datetime | None = None) -> None:
        self._reader, self._through, self._calendar = reader, through_sequence, calendar
        self._complete = None if complete_through is None else check_utc(complete_through, "complete_through")

    def _known(self, identity: tuple, at: datetime) -> list[Candle]:
        if self._complete is not None and check_utc(at, "at") <= self._complete:
            at = check_utc(at, "at")
        else:
            at = self._reader._check_at(at)  # refuses a T later than the last delivered event
        revisions = self._reader._candles.get(identity, {})  # M2's projection; read-only use
        return [p for p, delivered, sequence in revisions.values()
                if p.available_from <= at and delivered <= at
                and (self._through is None or delivered < at or sequence <= self._through)]

    def candle_revision(self, ref: BarRef, *, at: datetime) -> Candle | None:
        identity = (ref.source, ref.instrument_id, Timeframe(ref.timeframe), ref.start_time)
        return next((c for c in self._known(identity, at) if _identity(c, ref)), None)

    def latest_closed(self, source: str, instrument_id: str, session: date, *, at: datetime,
                      calendar=None) -> Candle | None:
        from investment_engine.market.calendar.us_equities import load_us_equities_calendar

        opening = (calendar or self._calendar or load_us_equities_calendar()).session(session).open
        known = self._known((source, instrument_id, Timeframe.D1, opening), at)
        latest = max(known, key=lambda c: c.revision) if known else None
        return latest if latest is not None and latest.state is BarState.CLOSED else None

    def actions_between(self, source: str, instrument_id: str, first: date, last: date, *, at: datetime) -> list:
        query_at = at
        if self._complete is not None and check_utc(at, "at") <= self._complete \
                and self._reader._delivered_until is not None:
            query_at = min(at, self._reader._delivered_until)  # nothing was delivered between the two
        return self._reader.actions_visible_at(source, instrument_id, first, last + timedelta(days=1), query_at,
                                               through_sequence=self._through)


@dataclass(frozen=True)
class RawReference:
    """An order-price input: the decision bar's raw close. Never an adjusted or float value."""

    source: str
    instrument_id: str
    session: date
    bar: BarRef  # exactly the view's decision bar revision
    close: Decimal  # raw as-traded close
    currency: str  # equals the instrument's currency
    known_at: datetime

    def __post_init__(self) -> None:
        if isinstance(self.close, bool) or not isinstance(self.close, Decimal):
            raise TypeError(f"a reference price is a raw Decimal, not {type(self.close).__name__}")
        if not self.close.is_finite() or self.close <= 0:
            raise ValueError(f"a reference price must be positive, not {self.close}")
        check_utc(self.known_at, "known_at")


register(RawReference)


def decision_reference(view_lineage, *, knowledge: Knowledge, instruments, at: datetime) -> RawReference | Unavailable:
    """The raw reference of a view's decision bar, exactly as its lineage names it, known at `at`."""
    snapshot = view_lineage.snapshot
    source, instrument_id, session = snapshot.source, snapshot.instrument_id, snapshot.session_date
    instrument = instruments.get(instrument_id)
    zone = ZoneInfo(instrument.timezone)
    candidates = [r for r in view_lineage.bar_refs
                  if r.source == source and r.instrument_id == instrument_id
                  and Timeframe(r.timeframe) is Timeframe.D1 and r.start_time.astimezone(zone).date() == session]
    if len(candidates) != 1:
        return Unavailable(f"the view's lineage names {len(candidates)} decision bars for {source} {instrument_id} "
                           f"D1 {session}; exactly one is needed")
    (ref,) = candidates
    candle = knowledge.candle_revision(ref, at=at)
    if candle is None:
        return Unavailable(f"decision bar {source} {instrument_id} {session} revision {ref.revision} is not known "
                           f"at {at.isoformat()}")
    if not _identity(candle, ref):
        return Unavailable("the stored decision bar doesn't match the lineage's reference")
    if candle.state is not BarState.CLOSED:
        return Unavailable(f"decision bar {session} is {candle.state}, not CLOSED")
    if candle.currency != instrument.currency:
        return Unavailable(f"decision bar is in {candle.currency}, but {instrument_id} trades in "
                           f"{instrument.currency} (currency mismatch)")
    return RawReference(source, instrument_id, session, ref, candle.close, candle.currency, check_utc(at, "at"))
