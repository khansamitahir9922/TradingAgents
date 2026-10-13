"""The replay feed (Law 5; Law 7; docs/tasks/M1-14.md).

Each event delivers exactly one stored revision, at that revision's
availability plus a simulated latency, and never earlier. Events are ordered
by a key that holds the payload's full identity, so the order never depends
on how the reader returns rows. Replay never writes to the store.
"""

import hashlib
import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.replay import ReplayEvent, ReplayFeed
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
)
from investment_engine.money import Money

NVDA = "EQ_US_NVDA"
D1, H1 = Timeframe.D1, Timeframe.H1


def utc(*parts) -> datetime:
    return datetime(*parts, tzinfo=UTC)


MON_CLOSE = utc(2024, 6, 3, 20, 0)
FRIDAY_2100 = utc(2024, 6, 7, 21, 0)


def candle_obs(day=3, close="1150.0000", source="yfinance", *, received_at, backfill=True, timeframe=D1,
               start=None, end=None):
    start = start or utc(2024, 6, day, 13, 30)
    end = end or utc(2024, 6, day, 20, 0)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=timeframe, start_time=start, end_time=end,
        open=Decimal("1150.0000"), high=Decimal("1170.0000"), low=Decimal("1140.0000"), close=Decimal(close),
        currency="USD", volume=Decimal("41000000"), state=BarState.CLOSED, source_version="1.7.0",
        price_basis=PriceBasis.RAW_AS_REPORTED, volume_basis=VolumeBasis.RAW_AS_REPORTED,
        event_time=end, received_at=received_at, processed_at=received_at,
        backfill_available_from=end if backfill else None,
    )


def action_obs(action_type=ActionType.DIVIDEND, ex=date(2024, 6, 11), source="yfinance", *, received_at,
               amount="0.0100", ratio="10", backfill=True):
    fields = {
        ActionType.DIVIDEND: {"ratio": None, "amount": Money(Decimal(amount), "USD"),
                              "amount_basis": AmountBasis.AS_REPORTED},
        ActionType.SPLIT: {"ratio": Decimal(ratio), "amount": None, "amount_basis": None},
    }[action_type]
    return ActionObservation(
        source=source, instrument_id=NVDA, currency="USD", exchange_timezone="America/New_York",
        action_type=action_type, ex_date=ex, new_symbol=None, source_version="1.7.0",
        received_at=received_at, processed_at=received_at,
        backfill_available_from=ex_date_start(ex, "America/New_York") if backfill else None, **fields,
    )


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "market"
    return MarketDataWriter(root), MarketDataReader(root), root


@pytest.fixture
def friday_correction(store):
    """The M1-11 fixture: Monday's bar backfilled (seen Tuesday), then corrected on Friday at 21:00 UTC."""
    writer, reader, _ = store
    writer.write_candles([candle_obs(received_at=utc(2024, 6, 4, 0, 0))], import_id="backfill-1")
    writer.write_candles([candle_obs(close="1151.0000", received_at=FRIDAY_2100)], import_id="correction-1")
    return reader


def replay(reader, start, end, *, latency=timedelta(0), sources=("yfinance",), timeframes=(D1,), clock=None):
    clock = clock or ReplayClock(start)
    feed = ReplayFeed(reader, clock, sources=list(sources), instrument_ids=[NVDA], timeframes=list(timeframes),
                      start=start, end=end, latency=latency)
    return list(feed)


def summary(events):
    return [(e.kind, getattr(e.payload, "revision", None), e.received_at) for e in events]


# ------------------------------------------------------------------ the Friday correction


@pytest.mark.unit
@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ((utc(2024, 6, 3), utc(2024, 6, 7)), [("BAR_CLOSED", 1, MON_CLOSE)]),  # Monday → Thursday
        ((utc(2024, 6, 3), utc(2024, 6, 8)), [("BAR_CLOSED", 1, MON_CLOSE),
                                              ("CANDLE_REVISED", 2, FRIDAY_2100)]),  # Monday → Saturday
        ((utc(2024, 6, 8), utc(2024, 6, 15)), []),  # Saturday → next week: both arrived before
        ((utc(2024, 6, 6), utc(2024, 6, 8)), [("CANDLE_REVISED", 2, FRIDAY_2100)]),  # Thursday → Saturday
    ],
    ids=["mon-thu", "mon-sat", "sat-next-week", "thu-sat"],
)
def test_friday_correction_windows(friday_correction, window, expected):
    assert summary(replay(friday_correction, *window)) == expected


# ------------------------------------------------------------------ latency can't leak a correction


@pytest.mark.unit
def test_latency_never_pulls_a_correction_into_the_bar_closed_event(store):
    writer, reader, _ = store
    writer.write_candles([candle_obs(received_at=MON_CLOSE)], import_id="b")  # revision 1: received and available at E
    writer.write_candles([candle_obs(close="1151.0000", received_at=MON_CLOSE + timedelta(seconds=3))],
                         import_id="c")  # revision 2 available at E + 3 s
    events = replay(reader, utc(2024, 6, 3), utc(2024, 6, 8), latency=timedelta(seconds=5))
    assert summary(events) == [("BAR_CLOSED", 1, MON_CLOSE + timedelta(seconds=5)),
                               ("CANDLE_REVISED", 2, MON_CLOSE + timedelta(seconds=8))]
    assert events[0].payload.close == Decimal("1150.0000")


@pytest.mark.unit
def test_late_first_observation_is_delivered_when_it_became_known(store):
    writer, reader, _ = store
    late = MON_CLOSE + timedelta(hours=2)
    writer.write_candles([candle_obs(received_at=late, backfill=False)], import_id="late")
    [event] = replay(reader, utc(2024, 6, 3), utc(2024, 6, 8), latency=timedelta(seconds=7))
    assert event.kind == "BAR_CLOSED" and event.event_time == late
    assert event.received_at == event.processed_at == late + timedelta(seconds=7)
    assert event.payload.end_time == MON_CLOSE and event.payload.availability_basis is AvailabilityBasis.OBSERVED


@pytest.mark.unit
@pytest.mark.parametrize(("latency", "delivered"), [(timedelta(seconds=5), 0), (timedelta(0), 1)])
def test_window_edge_is_half_open_by_delivery_time(store, latency, delivered):
    writer, reader, _ = store
    end = MON_CLOSE + timedelta(seconds=1)  # the bar ends at end - 1 s
    writer.write_candles([candle_obs(received_at=utc(2024, 6, 4))], import_id="b")
    assert len(replay(reader, utc(2024, 6, 3), end, latency=latency)) == delivered


# ------------------------------------------------------------------ corporate actions


@pytest.mark.unit
def test_a_backfilled_split_arrives_at_its_ex_date_start_before_that_days_bar(store):
    writer, reader, _ = store
    ex = date(2024, 6, 10)
    writer.write_corporate_actions([action_obs(ActionType.SPLIT, ex, received_at=utc(2024, 6, 12))], import_id="a")
    writer.write_candles([candle_obs(day=10, received_at=utc(2024, 6, 12))], import_id="b")
    events = replay(reader, utc(2024, 6, 9), utc(2024, 6, 11))
    assert [e.kind for e in events] == ["CORPORATE_ACTION", "BAR_CLOSED"]
    assert events[0].received_at == ex_date_start(ex, "America/New_York")


@pytest.mark.unit
def test_at_equal_times_corporate_actions_come_before_bars(store):
    writer, reader, _ = store
    ex = date(2024, 6, 10)
    at = ex_date_start(ex, "America/New_York")
    writer.write_corporate_actions([action_obs(ActionType.SPLIT, ex, received_at=utc(2024, 6, 12))], import_id="a")
    writer.write_candles([candle_obs(day=7, received_at=at, backfill=False)], import_id="b")  # Friday's bar, seen late
    events = replay(reader, utc(2024, 6, 9), utc(2024, 6, 11))
    assert [(e.kind, e.received_at) for e in events] == [("CORPORATE_ACTION", at), ("BAR_CLOSED", at)]
    assert [e.sequence for e in events] == [0, 1]


@pytest.mark.unit
def test_a_dividend_correction_arrives_only_at_its_own_availability(store):
    writer, reader, _ = store
    writer.write_corporate_actions([action_obs(received_at=utc(2024, 6, 12))], import_id="a")
    fixed = utc(2024, 6, 20, 15, 0)
    writer.write_corporate_actions([action_obs(amount="0.0200", received_at=fixed)], import_id="b")
    events = replay(reader, utc(2024, 6, 10), utc(2024, 6, 30), latency=timedelta(minutes=1))
    assert [(e.payload.revision, e.received_at) for e in events] == [
        (1, ex_date_start(date(2024, 6, 11), "America/New_York") + timedelta(minutes=1)),
        (2, fixed + timedelta(minutes=1)),
    ]
    assert [e.payload.revision for e in replay(reader, utc(2024, 6, 10), fixed)] == [1]  # ends before it


# ------------------------------------------------------------------ providers


@pytest.mark.unit
def test_two_providers_are_separate_events_and_never_mix(store):
    writer, reader, _ = store
    writer.write_candles([candle_obs(received_at=utc(2024, 6, 4))], import_id="y")
    writer.write_candles([candle_obs(source="testvendor", received_at=utc(2024, 6, 4))], import_id="t")
    writer.write_candles([candle_obs(source="testvendor", close="1149.0000", received_at=FRIDAY_2100)],
                         import_id="t2")
    events = replay(reader, utc(2024, 6, 3), utc(2024, 6, 8), sources=("yfinance", "testvendor"))
    assert [(e.kind, e.source) for e in events] == [
        ("BAR_CLOSED", "testvendor"), ("BAR_CLOSED", "yfinance"), ("CANDLE_REVISED", "testvendor")]
    assert all(e.source == e.payload.source for e in events)
    yf_only = replay(reader, utc(2024, 6, 3), utc(2024, 6, 8))
    assert [e.kind for e in yf_only] == ["BAR_CLOSED"]  # the vendor's correction is never a yfinance event


# ------------------------------------------------------------------ shuffled input


class ShufflingReader:
    """Returns the real reader's rows in a chosen order: original, reversed or a seeded permutation."""

    def __init__(self, reader, order):
        self.reader, self.order = reader, order

    def _arrange(self, rows):
        rows = list(rows)
        if self.order == "reversed":
            return rows[::-1]
        if isinstance(self.order, int):
            random.Random(self.order).shuffle(rows)
        return rows

    def candle_revisions_available_between(self, *args, **kwargs):
        return self._arrange(self.reader.candle_revisions_available_between(*args, **kwargs))

    def action_revisions_available_between(self, *args, **kwargs):
        return self._arrange(self.reader.action_revisions_available_between(*args, **kwargs))


@pytest.mark.unit
def test_order_never_depends_on_how_the_reader_returns_rows(store):
    writer, reader, _ = store
    seen = utc(2024, 6, 11)
    ex = date(2024, 6, 10)
    writer.write_corporate_actions([action_obs(ActionType.SPLIT, ex, received_at=seen),
                                    action_obs(ActionType.DIVIDEND, ex, received_at=seen)], import_id="a")
    writer.write_candles([candle_obs(day=d, received_at=seen) for d in (6, 7, 10)], import_id="b")
    writer.write_candles([candle_obs(day=d, source="testvendor", received_at=seen) for d in (7, 10)], import_id="c")
    writer.write_candles([candle_obs(day=7, close="1152.0000", received_at=utc(2024, 6, 11, 12))], import_id="d")

    def run(order):
        clock = ReplayClock(utc(2024, 6, 5))
        feed = ReplayFeed(ShufflingReader(reader, order), clock, sources=["yfinance", "testvendor"],
                          instrument_ids=[NVDA], timeframes=[D1], start=utc(2024, 6, 5), end=utc(2024, 6, 12))
        return list(feed)

    baseline = run("original")
    for order in ["reversed", *range(20)]:
        assert run(order) == baseline
    actions = [e.payload.action_type for e in baseline if e.kind == "CORPORATE_ACTION"]
    assert actions == [ActionType.SPLIT, ActionType.DIVIDEND]
    assert [e.sequence for e in baseline] == list(range(len(baseline)))


# ------------------------------------------------------------------ other cases


@pytest.mark.unit
def test_replay_is_deterministic(friday_correction):
    window = (utc(2024, 6, 3), utc(2024, 6, 8))
    assert replay(friday_correction, *window) == replay(friday_correction, *window)


@pytest.mark.unit
def test_the_clock_is_at_each_events_received_at_when_it_is_yielded(friday_correction):
    clock = ReplayClock(utc(2024, 6, 3))
    feed = ReplayFeed(friday_correction, clock, sources=["yfinance"], instrument_ids=[NVDA], timeframes=[D1],
                      start=utc(2024, 6, 3), end=utc(2024, 6, 8), latency=timedelta(seconds=2))
    seen = []
    for event in feed:
        assert clock.now() == event.received_at == event.processed_at
        assert event.received_at == event.event_time + timedelta(seconds=2)
        assert event.event_time == event.payload.available_from
        seen.append(clock.now())
    assert seen == sorted(seen) and len(seen) == 2


@pytest.mark.unit
def test_a_clock_already_past_an_event_refuses_to_move_backwards(friday_correction):
    clock = ReplayClock(utc(2024, 6, 6))  # after Monday's close
    with pytest.raises(ValueError, match="backwards"):
        replay(friday_correction, utc(2024, 6, 3), utc(2024, 6, 8), clock=clock)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [
    {"latency": timedelta(seconds=-1)},
    {"start": utc(2024, 6, 8), "end": utc(2024, 6, 3)},
    {"start": utc(2024, 6, 3), "end": utc(2024, 6, 3)},
    {"start": datetime(2024, 6, 3), "end": utc(2024, 6, 8)},  # naive
    {"sources": ["yfinance", "yfinance"]},
    {"sources": []},
    {"timeframes": [D1, D1]},
], ids=["negative-latency", "backwards", "empty-window", "naive", "duplicate-source", "no-source", "duplicate-tf"])
def test_invalid_arguments_raise(friday_correction, bad):
    args = {"sources": ["yfinance"], "instrument_ids": [NVDA], "timeframes": [D1], "start": utc(2024, 6, 3),
            "end": utc(2024, 6, 8), "latency": timedelta(0), **bad}
    with pytest.raises((ValueError, TypeError)):
        list(ReplayFeed(friday_correction, ReplayClock(utc(2024, 6, 3)), **args))


class FormingReader:
    def __init__(self, candle):
        self.candle = candle

    def candle_revisions_available_between(self, *args, **kwargs):
        return [self.candle]

    def action_revisions_available_between(self, *args, **kwargs):
        return []


@pytest.mark.unit
def test_a_forming_bar_from_the_reader_is_an_error_and_never_delivered(friday_correction):
    [closed] = friday_correction.candle_revision_history("yfinance", NVDA, D1, utc(2024, 6, 3), utc(2024, 6, 4))[:1]
    forming = replace(closed, state=BarState.FORMING)
    feed = ReplayFeed(FormingReader(forming), ReplayClock(utc(2024, 6, 3)), sources=["yfinance"],
                      instrument_ids=[NVDA], timeframes=[D1], start=utc(2024, 6, 3), end=utc(2024, 6, 8))
    with pytest.raises(ValueError, match="CLOSED"):
        list(feed)


@pytest.mark.unit
def test_replay_never_changes_the_store(store, friday_correction):
    _, _, root = store

    def hashes():
        return {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*"))
                if p.is_file()}

    before = hashes()
    replay(friday_correction, utc(2024, 6, 3), utc(2024, 6, 8))
    assert hashes() == before and before


@pytest.mark.unit
def test_payloads_are_the_stored_revisions_with_their_labels(friday_correction):
    events = replay(friday_correction, utc(2024, 6, 3), utc(2024, 6, 8))
    history = friday_correction.candle_revision_history("yfinance", NVDA, D1, utc(2024, 6, 3), utc(2024, 6, 4))
    assert [e.payload for e in events] == history
    assert events[0].payload.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED
    assert events[1].payload.availability_basis is AvailabilityBasis.OBSERVED
    assert isinstance(events[0], ReplayEvent)


@pytest.mark.unit
def test_hourly_and_daily_bars_replay_together_in_timeframe_order(store):
    writer, reader, _ = store
    end = utc(2024, 6, 3, 20, 0)
    writer.write_candles([candle_obs(received_at=utc(2024, 6, 4))], import_id="d")
    writer.write_candles([candle_obs(timeframe=H1, start=utc(2024, 6, 3, 19, 30), end=end,
                                     received_at=utc(2024, 6, 4))], import_id="h")
    events = replay(reader, utc(2024, 6, 3), utc(2024, 6, 4), timeframes=(H1, D1))
    assert [e.payload.timeframe for e in events] == [D1, H1]  # same delivery time: D1 ranks before H1
