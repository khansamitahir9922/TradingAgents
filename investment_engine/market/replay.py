"""The replay feed (Law 5; Law 7; ADR-005; docs/tasks/M1-14.md).

Each event delivers exactly one stored revision, unmodified:
- candle revision 1 → BAR_CLOSED;
- candle revision ≥ 2 → CANDLE_REVISED;
- any corporate-action revision → CORPORATE_ACTION.

An event's own times follow Law 5 exactly and are computed here, never stored:
event_time is the revision's available_from, received_at is event_time +
latency, and processed_at equals received_at. Revisions are selected by their
identity, not by delivery time, so a correction can never ride inside an
earlier event, whatever the latency. Events are delivered iff
start <= received_at < end, ordered by a key holding the payload's full
identity plus revision, so the order never depends on how the reader returns
rows. Replay only reads.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from investment_engine.clock import ReplayClock
from investment_engine.market.availability import check_utc
from investment_engine.market.candles import BarState, Candle, Timeframe
from investment_engine.market.corporate_actions import ActionType, CorporateAction

Kind = Literal["CORPORATE_ACTION", "CANDLE_REVISED", "BAR_CLOSED"]

_KIND_RANK = {"CORPORATE_ACTION": 0, "CANDLE_REVISED": 1, "BAR_CLOSED": 2}
_ACTION_RANK = {t: rank for rank, t in enumerate(ActionType)}
_TIMEFRAME_RANK = {t: rank for rank, t in enumerate(Timeframe)}


@dataclass(frozen=True)
class ReplayEvent:
    kind: Kind
    source: str  # provider of the payload
    event_time: datetime  # == payload.available_from
    received_at: datetime  # == event_time + latency
    processed_at: datetime  # == received_at
    sequence: int  # strictly increasing across the whole replay
    payload: Candle | CorporateAction  # exactly one stored revision, unmodified


def _distinct(values: Sequence, what: str) -> list:
    values = list(values)
    if not values:
        raise ValueError(f"{what} must not be empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{what} contains duplicates: {values}")
    return values


class ReplayFeed:
    def __init__(self, reader, clock: ReplayClock, *, sources: Sequence[str], instrument_ids: Sequence[str],
                 timeframes: Sequence[Timeframe], start: datetime, end: datetime,
                 latency: timedelta = timedelta(0)) -> None:
        self.start, self.end = check_utc(start, "start"), check_utc(end, "end")
        if not start < end:
            raise ValueError(f"replay window {start} .. {end} is empty or runs backwards")
        if not isinstance(latency, timedelta):
            raise TypeError(f"latency must be a timedelta, not {type(latency).__name__}")
        if latency < timedelta(0):
            raise ValueError(f"latency must not be negative, not {latency}")
        self.reader, self.clock, self.latency = reader, clock, latency
        self.sources = _distinct(sources, "sources")
        self.instrument_ids = _distinct(instrument_ids, "instrument_ids")
        self.timeframes = [Timeframe(t) for t in _distinct(timeframes, "timeframes")]

    def _candidates(self) -> list[ReplayEvent]:
        # A revision is delivered at available_from + latency, so start <= received_at < end
        # is exactly start - latency <= available_from < end - latency.
        lo, hi = self.start - self.latency, self.end - self.latency
        events = []
        for source in self.sources:
            for instrument_id in self.instrument_ids:
                for timeframe in self.timeframes:
                    for candle in self.reader.candle_revisions_available_between(
                            source, instrument_id, timeframe, lo, hi):
                        self._check_identity(candle, source, instrument_id, timeframe)
                        if candle.state is not BarState.CLOSED:
                            raise ValueError(f"replay delivers only CLOSED bars (Law 7), not {candle.state}: "
                                             f"{candle.identity}")
                        kind = "BAR_CLOSED" if candle.revision == 1 else "CANDLE_REVISED"
                        events.append(self._event(kind, candle))
                for action in self.reader.action_revisions_available_between(source, instrument_id, lo, hi):
                    self._check_identity(action, source, instrument_id)
                    events.append(self._event("CORPORATE_ACTION", action))
        return events

    @staticmethod
    def _check_identity(payload, source: str, instrument_id: str, timeframe: Timeframe | None = None) -> None:
        """Providers never mix: a revision for another provider, instrument or timeframe than requested is refused."""
        got = (payload.source, payload.instrument_id, getattr(payload, "timeframe", None))
        want = (source, instrument_id, timeframe if timeframe is not None else got[2])
        if got != want:
            raise ValueError(f"the reader returned a revision for {got}, not the requested {want}")

    def _event(self, kind: Kind, payload) -> ReplayEvent:
        received = payload.available_from + self.latency
        return ReplayEvent(kind, payload.source, payload.available_from, received, received, -1, payload)

    @staticmethod
    def _key(event: ReplayEvent) -> tuple:
        p = event.payload
        if event.kind == "CORPORATE_ACTION":
            return (event.received_at, 0, p.source, p.instrument_id, p.ex_date, _ACTION_RANK[p.action_type],
                    p.revision)
        return (event.received_at, _KIND_RANK[event.kind], p.source, p.instrument_id, _TIMEFRAME_RANK[p.timeframe],
                p.start_time, p.revision)

    def __iter__(self) -> Iterator[ReplayEvent]:
        events = [e for e in self._candidates() if self.start <= e.received_at < self.end]
        keyed = sorted(((self._key(e), e) for e in events), key=lambda pair: pair[0])
        keys = [k for k, _ in keyed]
        if len(set(keys)) != len(keys):
            raise ValueError("the reader returned the same stored revision twice")
        for sequence, (_, event) in enumerate(keyed):
            self.clock.advance_to(event.received_at)  # refuses to move backwards
            yield replace(event, sequence=sequence)
