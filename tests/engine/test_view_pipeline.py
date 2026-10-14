"""The view pipeline over a replay (Law 5; Law 9; docs/tasks/M2-07.md)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.decision.market_view import ViewDirection
from investment_engine.decision.pipeline import ReplayKnowledgeReader, run_views
from investment_engine.lineage.records import LineageStore
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, ex_date_start
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.replay import ReplayFeed
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
)
from investment_engine.market.symbols import SymbolMapping
from investment_engine.quant.adjusted import VerificationEvidence
from investment_engine.quant.strategies.pullback import PullbackStrategy
from investment_engine.quant.strategies.trend import TrendStrategy
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
SESSIONS = [s.date for s in CAL.sessions_between(date(2023, 6, 1), date(2024, 6, 28))]
EX = date(2024, 6, 10)
EVIDENCE = (VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                                 date(2019, 1, 1), date(2026, 10, 12), "test-verification", "COMPLETE"),)


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def raw(i, d):
    value = Decimal(1000 + 3 * (i % 13) + i) / (10 if d >= EX else 1)
    return value.quantize(Decimal("0.0001"))


def bar(d, close, received_at=None):
    s = CAL.session(d)
    received = received_at or s.close  # received at the close, so a correction can follow seconds later
    return CandleObservation(
        source="yfinance", instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=close, high=close, low=close, close=close, currency="USD", volume=Decimal("1000"),
        state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received, processed_at=received,
        backfill_available_from=s.close)


@pytest.fixture
def env(tmp_path):
    conn = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(conn)
    instruments, resolver = SqliteInstrumentRepository(conn), SqliteSymbolResolver(conn)
    instruments.add(Instrument(NVDA, AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                               InstrumentStatus.ACTIVE, date(1999, 1, 22), None))
    resolver.add(SymbolMapping(NVDA, "yfinance", "NVDA", date(1999, 1, 22), None))
    root = tmp_path / "market"
    writer = MarketDataWriter(root)
    writer.write_candles([bar(d, raw(i, d)) for i, d in enumerate(SESSIONS)], import_id="bars")
    t = utc(2026, 10, 12, 20)
    writer.write_corporate_actions([ActionObservation(
        source="yfinance", instrument_id=NVDA, currency="USD", exchange_timezone="America/New_York",
        action_type=ActionType.SPLIT, ex_date=EX, ratio=Decimal("10"), amount=None, amount_basis=None,
        new_symbol=None, source_version="1.7.0", received_at=t, processed_at=t,
        backfill_available_from=ex_date_start(EX, "America/New_York"))], import_id="actions")
    yield {"conn": conn, "writer": writer, "reader": MarketDataReader(root), "instruments": instruments,
           "resolver": resolver, "lineage": LineageStore(conn)}
    conn.close()


def views(env, start=SESSIONS[0], end=SESSIONS[-1], latency=timedelta(0), reader=None):
    s, e = CAL.session(start).open - timedelta(days=1), CAL.session(end).close + timedelta(hours=1)
    feed = ReplayFeed(reader or env["reader"], ReplayClock(s), sources=["yfinance"], instrument_ids=[NVDA],
                      timeframes=[Timeframe.D1], start=s, end=e, latency=latency)
    return list(run_views(feed, instrument_id=NVDA, source="yfinance", strategies=(TrendStrategy(), PullbackStrategy()),
                          policy_version="0.1.0", calendar=CAL, instruments=env["instruments"],
                          resolver=env["resolver"], lineage_store=env["lineage"], coverage_evidence=EVIDENCE,
                          coverage_first=SESSIONS[0], coverage_last=date(2026, 10, 12),
                          coverage_reason="test coverage", calendar_version="test-cal", code_version="test-code"))


@pytest.mark.unit
def test_one_view_per_closed_daily_bar_each_with_stored_lineage(env):
    vs = views(env)
    assert len(vs) == len(SESSIONS)
    assert [v.generated_at for v in vs] == [CAL.session(d).close for d in SESSIONS]
    for v in vs[::50]:
        [lineage_id] = v.evidence_refs
        stored = env["lineage"].get(lineage_id)
        assert stored.decision == replace(v, evidence_refs=())
    early, warming, late = vs[10], vs[30], vs[-1]
    # Before 20 stored sessions exist, the health lookback reaches past the first bar: Law 9 abstains first.
    assert early.direction is ViewDirection.ABSTAIN and "DEGRADED" in early.abstain_reason
    assert warming.direction is ViewDirection.ABSTAIN and warming.abstain_reason == "warm-up"
    assert late.direction is not ViewDirection.ABSTAIN


@pytest.mark.unit
def test_lineage_lists_the_bars_and_split_used(env):
    v = views(env)[-1]
    record = env["lineage"].get(v.evidence_refs[0])
    used = {r.start_time for r in record.snapshot.input_refs}
    assert used == {CAL.session(d).open for d in SESSIONS[-200:]}
    assert used <= {r.start_time for r in record.bar_refs}
    [split] = record.action_refs
    assert (split.action_type, split.ex_date) == (ActionType.SPLIT, EX)
    assert record.action_coverage.established and record.action_coverage.evidence_refs == (EVIDENCE[0].ref,)
    assert record.code_version == "test-code" and record.calendar_version == "test-cal"


@pytest.mark.unit
def test_an_abstain_view_still_has_full_lineage_including_its_health(env):
    v = views(env, start=SESSIONS[-5])[0]
    assert v.direction is ViewDirection.ABSTAIN
    record = env["lineage"].get(v.evidence_refs[0])
    assert record.data_health == v.data_health and record.decision.abstain_reason == v.abstain_reason


@pytest.mark.unit
def test_a_feed_that_starts_too_late_gives_explicit_unavailable_views_not_a_hidden_preload(env):
    vs = views(env, start=SESSIONS[-5])
    assert all(v.direction is ViewDirection.ABSTAIN for v in vs)
    record = env["lineage"].get(vs[-1].evidence_refs[0])
    assert record.snapshot.unavailable_reason or record.decision.abstain_reason


@pytest.mark.unit
def test_two_replays_give_identical_views_and_lineage_ids(env):
    first = views(env, start=SESSIONS[-230])
    second = views(env, start=SESSIONS[-230])
    assert first == second
    assert env["conn"].execute("SELECT COUNT(*) FROM lineage_records").fetchone()[0] == len(first)


@pytest.mark.unit
def test_a_correction_available_after_t_is_not_in_that_views_lineage(env):
    fixed = SESSIONS[-10]
    after = CAL.session(SESSIONS[-1]).close + timedelta(days=2)
    env["writer"].write_candles([bar(fixed, raw(SESSIONS.index(fixed), fixed) + 1, received_at=after)], import_id="fix")
    v = views(env, start=SESSIONS[-230])[-1]
    record = env["lineage"].get(v.evidence_refs[0])
    assert all(r.revision == 1 for r in record.bar_refs)


class _Reversed:
    """The store's rows, in reverse order: the feed's own ordering must decide."""

    def __init__(self, reader):
        self.reader = reader

    def candle_revisions_available_between(self, *args):
        return self.reader.candle_revisions_available_between(*args)[::-1]

    def action_revisions_available_between(self, *args, **kwargs):
        return self.reader.action_revisions_available_between(*args, **kwargs)[::-1]


@pytest.mark.unit
@pytest.mark.parametrize("reverse", [False, True])
def test_latency_cannot_leak_a_correction_through_a_second_read(env, reverse):
    # Revision 1 of the last-but-one bar is available at E (its close); revision 2 at E + 3 s.
    # With 5 s latency the view at E + 5 s must use revision 1 only; revision 2 is delivered at E + 8 s.
    target = SESSIONS[-2]
    e = CAL.session(target).close
    env["writer"].write_candles([bar(target, raw(SESSIONS.index(target), target) + 7,
                                     received_at=e + timedelta(seconds=3))], import_id="rev2")
    reader = _Reversed(env["reader"]) if reverse else env["reader"]
    vs = views(env, start=SESSIONS[-230], latency=timedelta(seconds=5), reader=reader)
    at_target = next(v for v in vs if v.generated_at == e + timedelta(seconds=5))
    record = env["lineage"].get(at_target.evidence_refs[0])
    revisions = {r.revision for r in record.bar_refs if r.start_time == CAL.session(target).open}
    assert revisions == {1}
    assert all(r.revision == 1 for r in record.snapshot.input_refs)
    later = env["lineage"].get(vs[-1].evidence_refs[0])
    assert {r.revision for r in later.bar_refs if r.start_time == CAL.session(target).open} == {2}


@pytest.mark.unit
def test_the_knowledge_reader_only_knows_delivered_revisions_and_refuses_later_times():
    reader = ReplayKnowledgeReader()
    with pytest.raises(ValueError):
        reader.candles_visible_at("yfinance", NVDA, Timeframe.D1, utc(2024, 1, 1), utc(2025, 1, 1),
                                  utc(2024, 6, 1))
