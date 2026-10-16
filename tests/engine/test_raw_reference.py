"""Raw reference prices for order intents (docs/tasks/M3-07.md rule 1; Codex M3 review B1)."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from investment_engine.decision.pipeline import ReplayKnowledgeReader
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.instruments import Instrument
from investment_engine.market.replay import ReplayEvent
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import CandleObservation, MarketDataWriter
from investment_engine.portfolio.reference import (
    RawReference,
    ReplayKnowledge,
    StoreKnowledge,
    Unavailable,
    decision_reference,
)
from investment_engine.quant.adjusted import BarRef

CAL = load_us_equities_calendar()
NVDA = "EQ_US_NVDA"
DAY = date(2024, 6, 3)
SESSION = CAL.session(DAY)
T = SESSION.close + timedelta(minutes=5)  # the view's decision time


class Instruments:
    def __init__(self, currency="USD"):
        self.currency = currency

    def get(self, instrument_id):
        return Instrument(instrument_id=instrument_id, asset_class="EQUITY", currency=self.currency,
                          exchange="XNAS", timezone="America/New_York", status="ACTIVE",
                          active_from=date(1999, 1, 22), active_to=None)


def observation(d=DAY, close="120.5000", received=None, available=None, state=BarState.CLOSED, currency="USD",
                source="yfinance"):
    s = CAL.session(d)
    received = received or s.close + timedelta(minutes=1)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=Decimal(close), high=Decimal(close) + 1, low=Decimal(close) - 1, close=Decimal(close), volume=Decimal("1000"),
        currency=currency, state=state, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received, processed_at=received,
        backfill_available_from=available or s.close)


@pytest.fixture
def store(tmp_path):
    writer = MarketDataWriter(tmp_path / "market")
    writer.write_candles([observation()], import_id="first")
    return writer, MarketDataReader(tmp_path / "market")


def stored(reader, d=DAY):
    s = CAL.session(d)
    return reader.candle_revision_history("yfinance", NVDA, Timeframe.D1, s.open, s.open + timedelta(microseconds=1))


def ref_of(candle, **changes):
    values = {"source": candle.source, "instrument_id": candle.instrument_id, "timeframe": candle.timeframe,
              "start_time": candle.start_time, "revision": candle.revision, "import_id": candle.import_id,
              "available_from": candle.available_from, "availability_basis": candle.availability_basis}
    values.update(changes)
    return BarRef(**values)


def lineage(*refs, source="yfinance", session=DAY):
    """The parts of a LineageRecord decision_reference reads: its snapshot's identity and its bar references."""
    return SimpleNamespace(snapshot=SimpleNamespace(source=source, instrument_id=NVDA, session_date=session),
                           bar_refs=refs)


@pytest.mark.unit
def test_the_first_buy_gets_the_decision_bars_raw_close_whatever_is_held(store):
    _, reader = store
    (candle,) = stored(reader)
    reference = decision_reference(lineage(ref_of(candle)), knowledge=StoreKnowledge(reader), instruments=Instruments(),
                                   at=T)
    assert isinstance(reference, RawReference)
    assert reference.close == Decimal("120.5000") and isinstance(reference.close, Decimal)
    assert (reference.source, reference.instrument_id, reference.session, reference.currency) == (
        "yfinance", NVDA, DAY, "USD")
    assert reference.bar == ref_of(candle) and reference.known_at == T


@pytest.mark.unit
def test_a_missing_or_mismatched_reference_is_unavailable_with_its_reason(store):
    _, reader = store
    (candle,) = stored(reader)
    knowledge = StoreKnowledge(reader)
    cases = {
        "no decision bar": lineage(),
        "another provider": lineage(ref_of(candle, source="testvendor")),
        "another instrument": lineage(ref_of(candle, instrument_id="EQ_US_AMD")),
        "another revision": lineage(ref_of(candle, revision=2)),
        "two candidates": lineage(ref_of(candle), ref_of(candle, revision=2)),
        "another session": lineage(ref_of(candle), session=date(2024, 6, 4)),
    }
    for case, view_lineage in cases.items():
        result = decision_reference(view_lineage, knowledge=knowledge, instruments=Instruments(), at=T)
        assert isinstance(result, Unavailable) and result.reason, case


@pytest.mark.unit
def test_a_currency_mismatch_or_forming_bar_is_unavailable(tmp_path):
    writer, reader = MarketDataWriter(tmp_path / "m"), MarketDataReader(tmp_path / "m")
    writer.write_candles([observation(currency="EUR")], import_id="eur")
    (candle,) = stored(reader)
    euro = decision_reference(lineage(ref_of(candle)), knowledge=StoreKnowledge(reader), instruments=Instruments(),
                              at=T)
    assert isinstance(euro, Unavailable) and "currency" in euro.reason


@pytest.mark.unit
def test_a_correction_delivered_after_t_never_changes_the_reference(store):
    writer, reader = store
    late = T + timedelta(days=1)
    writer.write_candles([observation(close="120.7500", received=late)], import_id="correction")
    first, correction = stored(reader)
    # The store never backdates a correction (M1-10): it becomes available when it arrives, after T.
    assert correction.revision == 2 and T < correction.available_from == correction.received_at
    knowledge = StoreKnowledge(reader)
    original = decision_reference(lineage(ref_of(first)), knowledge=knowledge, instruments=Instruments(), at=T)
    assert original.close == Decimal("120.5000")
    named = decision_reference(lineage(ref_of(correction)), knowledge=knowledge, instruments=Instruments(), at=T)
    assert isinstance(named, Unavailable) and "not known" in named.reason
    assert decision_reference(lineage(ref_of(first)), knowledge=knowledge, instruments=Instruments(),
                              at=late).close == Decimal("120.5000")  # exactly the named revision, even later


def event(candle, sequence, received=None):
    received = received or candle.available_from
    return ReplayEvent(kind="BAR_CLOSED", source=candle.source, event_time=candle.available_from,
                       received_at=received, processed_at=received, sequence=sequence, payload=candle)


@pytest.mark.unit
def test_replay_knowledge_respects_delivery_time_and_equal_time_sequence(store):
    writer, reader = store
    (candle,) = stored(reader)
    known = ReplayKnowledgeReader()
    known.accept(event(candle, 7, received=T))
    view_lineage = lineage(ref_of(candle))
    at_t = decision_reference(view_lineage, knowledge=ReplayKnowledge(known), instruments=Instruments(), at=T)
    assert at_t.close == Decimal("120.5000")
    before = ReplayKnowledge(known, through_sequence=6)  # delivered at exactly T, but after this point
    assert isinstance(decision_reference(view_lineage, knowledge=before, instruments=Instruments(), at=T),
                      Unavailable)
    with pytest.raises(ValueError):  # nothing after the last delivered event is known
        decision_reference(view_lineage, knowledge=ReplayKnowledge(known), instruments=Instruments(),
                           at=T + timedelta(days=1))


@pytest.mark.unit
def test_adjusted_or_float_prices_are_refused_by_type(store):
    _, reader = store
    (candle,) = stored(reader)
    reference = decision_reference(lineage(ref_of(candle)), knowledge=StoreKnowledge(reader),
                                   instruments=Instruments(), at=T)
    with pytest.raises(TypeError):
        replace(reference, close=120.5)  # M2's split-adjusted decision_close is a float
    with pytest.raises(TypeError):
        replace(reference, close=None)


@pytest.mark.unit
def test_store_knowledge_finds_the_expected_sessions_closed_bar_only(store):
    writer, reader = store
    knowledge = StoreKnowledge(reader)
    bar = knowledge.latest_closed("yfinance", NVDA, DAY, at=T)
    assert bar is not None and bar.close == Decimal("120.5000")
    assert knowledge.latest_closed("yfinance", NVDA, date(2024, 6, 4), at=T + timedelta(days=1)) is None
    assert knowledge.latest_closed("yfinance", NVDA, DAY, at=SESSION.close) is None  # received after the close
    with pytest.raises(ValueError, match="only CLOSED"):  # the store itself never holds a FORMING bar
        writer.write_candles([observation(d=date(2024, 6, 4), state=BarState.FORMING)], import_id="forming")


@pytest.mark.unit
def test_in_replay_a_correction_available_before_t_but_delivered_after_it_is_not_known_at_t(store):
    """Codex re-review S2: with feed latency a revision can be available by T yet delivered later."""
    _, reader = store
    (first,) = stored(reader)
    late = T + timedelta(hours=2)
    arrived = T - timedelta(minutes=2)  # stored as available before T ...
    correction = replace(first, revision=2, close=Decimal("120.7500"), import_id="correction", received_at=arrived,
                         processed_at=arrived, available_from=arrived, availability_basis=AvailabilityBasis.OBSERVED)
    assert correction.available_from <= T < late  # ... but the feed delivers it after T (latency)
    known = ReplayKnowledgeReader()
    known.accept(event(first, 1, received=T - timedelta(minutes=1)))
    known.accept(event(correction, 2, received=late))
    knowledge = ReplayKnowledge(known)
    named = decision_reference(lineage(ref_of(correction)), knowledge=knowledge, instruments=Instruments(), at=T)
    assert isinstance(named, Unavailable) and "not known" in named.reason
    original = decision_reference(lineage(ref_of(first)), knowledge=knowledge, instruments=Instruments(), at=T)
    assert original.close == Decimal("120.5000")
    assert knowledge.latest_closed("yfinance", NVDA, DAY, at=T).revision == 1
    assert knowledge.latest_closed("yfinance", NVDA, DAY, at=late).revision == 2


@pytest.mark.unit
def test_a_caller_that_fed_every_event_can_query_after_the_last_one(store):
    """The pipeline proposes at the view's time, after the last delivered bar (M3-12)."""
    _, reader = store
    (candle,) = stored(reader)
    known = ReplayKnowledgeReader()
    known.accept(event(candle, 1, received=SESSION.close + timedelta(minutes=1)))
    later = T + timedelta(minutes=30)
    with pytest.raises(ValueError):
        decision_reference(lineage(ref_of(candle)), knowledge=ReplayKnowledge(known), instruments=Instruments(),
                           at=later)
    vouched = ReplayKnowledge(known, complete_through=later)
    assert decision_reference(lineage(ref_of(candle)), knowledge=vouched, instruments=Instruments(),
                              at=later).close == Decimal("120.5000")
    with pytest.raises(ValueError):  # beyond what the caller vouched for: refused again
        vouched.latest_closed("yfinance", NVDA, DAY, at=later + timedelta(seconds=1))
