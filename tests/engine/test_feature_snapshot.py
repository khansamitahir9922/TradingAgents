"""FeatureSnapshot: everything a strategy may see at T (Part F; docs/tasks/M2-03.md)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import SourceKey, evaluate_health
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import CandleObservation, MarketDataWriter
from investment_engine.market.symbols import SymbolMapping
from investment_engine.quant.adjusted import AdjustedBasis, VerificationEvidence, establish_coverage
from investment_engine.quant.indicators import DEFINITIONS, RSI14, SMA50, SMA200, evaluate
from investment_engine.quant.snapshot import FeatureSnapshot, build_snapshot
from investment_engine.storage.database import SqliteDatabase
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
SESSIONS = [s.date for s in CAL.sessions_between(date(2023, 6, 1), date(2024, 6, 21))]
LAST = SESSIONS[-1]  # Friday 21 June 2024
AT = CAL.session(LAST).close + timedelta(hours=1)
YF_D1 = SourceKey("yfinance", Timeframe.D1)


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def price(i):
    return Decimal(100 + (i % 11) - (i % 4)) + Decimal(i) / 10


def bar(d, close, received_at=None):
    s = CAL.session(d)
    received = received_at or s.close + timedelta(minutes=5)
    return CandleObservation(
        source="yfinance", instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=close, high=close, low=close, close=close, currency="USD", volume=Decimal("1000"),
        state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received, processed_at=received,
        backfill_available_from=s.close)


def coverage(at, first=date(2019, 1, 1)):
    ev = VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                              date(2019, 1, 1), date(2026, 10, 12), "test-verification", "COMPLETE")
    return establish_coverage([ev], source="yfinance", instrument_id=NVDA, types=[ActionType.SPLIT], first=first,
                              last=date(2026, 10, 12), as_of=at, reason="test")


@pytest.fixture
def env(tmp_path):
    conn = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(conn)
    db = SqliteDatabase(conn)
    instruments, resolver = SqliteInstrumentRepository(db), SqliteSymbolResolver(db)
    instruments.add(Instrument(NVDA, AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                               InstrumentStatus.ACTIVE, date(1999, 1, 22), None))
    resolver.add(SymbolMapping(NVDA, "yfinance", "NVDA", date(1999, 1, 22), None))
    root = tmp_path / "market"
    yield {"writer": MarketDataWriter(root), "reader": MarketDataReader(root), "instruments": instruments,
           "resolver": resolver}
    conn.close()


def write(env, days=SESSIONS, import_id="bars"):
    env["writer"].write_candles([bar(d, price(SESSIONS.index(d))) for d in days], import_id=import_id)


def health(env, at=AT, required=(YF_D1,)):
    return evaluate_health(NVDA, list(required), clock=ReplayClock(at), reader=env["reader"],
                           instruments=env["instruments"], resolver=env["resolver"], calendar=CAL)


def snap(env, at=AT, *, features=DEFINITIONS, h=None, cov=None, reader=None):
    return build_snapshot(NVDA, "yfinance", features, at=at, reader=reader or env["reader"], calendar=CAL,
                          health=h if h is not None else health(env, at), coverage=cov or coverage(at))


@pytest.mark.unit
def test_values_match_the_indicators_on_the_last_200_sessions(env):
    write(env)
    s = snap(env)
    closes = [float(price(i)) for i in range(len(SESSIONS))]
    assert isinstance(s, FeatureSnapshot) and s.unavailable_reason == ""
    assert s.session_date == LAST and s.as_of == AT
    for d in DEFINITIONS:
        assert s.values[d.key] == pytest.approx(evaluate(d, closes[-200:]))
        assert s.feature_versions[d.key] == d.version
    assert s.decision_close == pytest.approx(closes[-1])
    assert s.adjusted_basis is AdjustedBasis.SPLIT_ADJUSTED_AS_OF


@pytest.mark.unit
def test_input_refs_cover_exactly_the_bars_used(env):
    write(env)
    s = snap(env)
    expected = [CAL.session(d).open for d in SESSIONS[-200:]]
    assert [r.start_time for r in s.input_refs] == expected
    assert all(r.revision == 1 and r.import_id == "bars" for r in s.input_refs)
    only_sma50 = snap(env, features=(SMA50,))
    assert [r.start_time for r in only_sma50.input_refs] == expected[-50:]


@pytest.mark.unit
def test_same_inputs_give_an_identical_snapshot_and_a_later_correction_differs_only_where_it_applies(env):
    write(env)
    first = snap(env)
    assert snap(env) == first
    fixed = SESSIONS[-3]
    env["writer"].write_candles([bar(fixed, price(SESSIONS.index(fixed)) + 5, received_at=AT + timedelta(days=1))],
                                import_id="fix")
    assert snap(env) == first  # the correction isn't visible at T
    later = AT + timedelta(days=2)
    after = snap(env, later, h=replace(health(env, later), as_of=later))
    assert after.session_date == LAST
    changed = {r.start_time for r, old in zip(after.input_refs, first.input_refs, strict=True) if r != old}
    assert changed == {CAL.session(fixed).open}
    assert after.values[SMA50.key] != first.values[SMA50.key]


@pytest.mark.unit
def test_mappings_are_immutable(env):
    write(env)
    s = snap(env)
    with pytest.raises(TypeError):
        s.values[SMA50.key] = 0.0
    with pytest.raises(TypeError):
        s.feature_versions[SMA50.key] = "9.9.9"


@pytest.mark.unit
def test_a_mismatched_health_time_or_instrument_raises(env):
    write(env)
    h = health(env)
    with pytest.raises(ValueError, match="as_of"):
        snap(env, h=replace(h, as_of=AT + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="instrument"):
        snap(env, h=replace(h, instrument_id="EQ_US_MSFT"))


@pytest.mark.unit
def test_a_missing_health_entry_gives_an_unavailable_snapshot_naming_the_source(env):
    write(env)
    h = health(env)
    s = snap(env, h=replace(h, sources=()))
    assert "yfinance D1" in s.unavailable_reason
    assert all(v is None for v in s.values.values())


@pytest.mark.unit
def test_a_hole_older_than_the_health_lookback_still_makes_the_snapshot_unavailable(env):
    hole = SESSIONS[-100]
    write(env, [d for d in SESSIONS if d != hole])
    h = health(env)
    assert h.required_sources_ok  # M1's 20-session lookback sees no problem
    s = snap(env, h=h)
    assert str(hole) in s.unavailable_reason
    assert all(v is None for v in s.values.values())


@pytest.mark.unit
def test_a_missing_latest_bar_does_not_recycle_yesterdays_signal(env):
    write(env, SESSIONS[:-1])
    s = snap(env)
    assert s.session_date == LAST
    assert "decision" in s.unavailable_reason and str(LAST) in s.unavailable_reason
    assert all(v is None for v in s.values.values()) and s.decision_close is None


@pytest.mark.unit
def test_inside_a_session_its_bar_is_not_used(env):
    write(env)
    during = CAL.session(LAST).open + timedelta(hours=2)
    s = snap(env, during)
    assert s.session_date == SESSIONS[-2]
    assert s.input_refs[-1].start_time == CAL.session(SESSIONS[-2]).open


@pytest.mark.unit
def test_warmup_from_the_history_boundary_is_labelled_separately_from_a_hole(env):
    write(env)
    boundary = SESSIONS[-120]
    s = snap(env, cov=coverage(AT, first=boundary))
    assert s.unavailable_reason == ""
    assert s.values[SMA200.key] is None and s.values[RSI14.key] is None
    assert s.values[SMA50.key] is not None
    assert set(s.warmup) == {SMA200.key, RSI14.key, DEFINITIONS[3].key}
    assert s.input_refs[0].start_time == CAL.session(SESSIONS[-50]).open


@pytest.mark.unit
def test_unestablished_coverage_gives_an_explicit_reason_and_no_values(env):
    write(env)
    unestablished = establish_coverage((), source="yfinance", instrument_id=NVDA, types=[ActionType.SPLIT],
                                       first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=AT, reason="none")
    s = snap(env, cov=unestablished)
    assert "coverage" in s.unavailable_reason
    assert all(v is None for v in s.values.values())
    assert s.action_coverage == unestablished


@pytest.mark.unit
def test_programming_and_data_errors_propagate(env):
    write(env)

    class Broken:
        def candles_visible_at(self, *args):
            raise RuntimeError("database error")

        def actions_visible_at(self, *args, **kwargs):
            return []

    with pytest.raises(RuntimeError):
        snap(env, reader=Broken())


@pytest.mark.unit
def test_features_must_be_distinct_definitions_on_the_split_adjusted_view(env):
    write(env)
    with pytest.raises(ValueError):
        snap(env, features=())
    with pytest.raises(ValueError):
        snap(env, features=(SMA50, SMA50))
    with pytest.raises(TypeError):
        snap(env, features=("sma50",))
