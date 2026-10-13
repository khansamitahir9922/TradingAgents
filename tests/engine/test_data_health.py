"""DataHealth per provider and timeframe, with the four frozen statuses (Part H; Law 9; docs/tasks/M1-16.md).

Applicability is reported apart from status, staleness is counted in expected
bars (so nights, weekends and holidays never count), providers never fill each
other's gaps, and everything is read as visible at the injected clock's time.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.data_health import (
    Applicability,
    DataHealth,
    HealthStatus,
    HealthThresholds,
    SourceKey,
    evaluate_health,
)
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import CandleObservation, MarketDataWriter
from investment_engine.market.symbols import SymbolMapping
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)

NVDA = "EQ_US_NVDA"
D1, H1 = Timeframe.D1, Timeframe.H1
CAL = load_us_equities_calendar()
YF_D1, YF_H1, TV_D1 = SourceKey("yfinance", D1), SourceKey("yfinance", H1), SourceKey("testvendor", D1)
# Sessions from 1 May to 21 June 2024, so a 20-session lookback is always full of data. In June:
# Mon 3 – Fri 7, Mon 10 – Fri 14, Mon 17 – Tue 18, (Wed 19 holiday), Thu 20 – Fri 21.
JUNE = [s.date for s in CAL.sessions_between(date(2024, 5, 1), date(2024, 6, 21))]


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def bar(d, timeframe=D1, k=0, *, source="yfinance", close="100", received_at=None):
    session = CAL.session(d)
    start = session.open if timeframe is D1 else session.open + timedelta(hours=k)
    end = session.close if timeframe is D1 else min(start + timedelta(hours=1), session.close)
    received_at = received_at or end + timedelta(minutes=5)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=timeframe, start_time=start, end_time=end,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal(close), currency="USD",
        volume=Decimal("1000"), state=BarState.CLOSED, source_version="1.7.0",
        price_basis=PriceBasis.RAW_AS_REPORTED, volume_basis=VolumeBasis.RAW_AS_REPORTED,
        event_time=end, received_at=received_at, processed_at=received_at, backfill_available_from=end,
    )


@pytest.fixture
def env(tmp_path):
    conn = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(conn)
    instruments, resolver = SqliteInstrumentRepository(conn), SqliteSymbolResolver(conn)
    instruments.add(Instrument(NVDA, AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                               InstrumentStatus.ACTIVE, date(1999, 1, 22), None))
    resolver.add(SymbolMapping(NVDA, "yfinance", "NVDA", date(1999, 1, 22), None))
    resolver.add(SymbolMapping(NVDA, "testvendor", "NVDA.US", date(1999, 1, 22), None))
    root = tmp_path / "market"
    yield {"writer": MarketDataWriter(root), "reader": MarketDataReader(root), "instruments": instruments,
           "resolver": resolver, "conn": conn}
    conn.close()


def health(env, required, at, *, instrument_id=NVDA, thresholds=None):
    kwargs = {} if thresholds is None else {"thresholds": thresholds}
    return evaluate_health(instrument_id, required, clock=ReplayClock(at), reader=env["reader"],
                           instruments=env["instruments"], resolver=env["resolver"], calendar=CAL, **kwargs)


def only(result: DataHealth, key: SourceKey):
    [source] = [s for s in result.sources if s.source == key]
    return source


def daily_series(env, days=JUNE, source="yfinance", import_id="d"):
    env["writer"].write_candles([bar(d, source=source) for d in days], import_id=import_id)


AFTER_FRI_14 = utc(2024, 6, 14, 21, 0)  # after Friday 14 June's close


# ------------------------------------------------------------------ statuses


@pytest.mark.unit
def test_a_complete_recent_series_is_ok(env):
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 14)])
    s = only(health(env, [YF_D1], AFTER_FRI_14), YF_D1)
    assert s.status is HealthStatus.OK and s.bars_behind == 0 and s.missing_in_window == () and s.detail == ""
    assert s.latest_bar_end == CAL.session(date(2024, 6, 14)).close
    assert s.age == AFTER_FRI_14 - s.latest_bar_end


@pytest.mark.unit
def test_one_bar_behind_is_still_ok_and_beyond_the_threshold_is_stale(env):
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 12)])  # last bar: Wed 12
    one_behind = only(health(env, [YF_D1], utc(2024, 6, 13, 21)), YF_D1)  # Thu 13 closed, not received
    assert one_behind.status is HealthStatus.OK and one_behind.bars_behind == 1
    two_behind = only(health(env, [YF_D1], utc(2024, 6, 14, 21)), YF_D1)
    assert two_behind.status is HealthStatus.STALE and two_behind.bars_behind == 2
    assert "2 expected bars behind" in two_behind.detail
    relaxed = HealthThresholds(stale_after_bars={D1: 2, H1: 1}, lookback_sessions=20)
    assert only(health(env, [YF_D1], utc(2024, 6, 14, 21), thresholds=relaxed), YF_D1).status is HealthStatus.OK


@pytest.mark.unit
def test_a_weekend_and_a_holiday_never_count_as_behind(env):
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 18)])  # last bar: Tue 18; Wed 19 is a holiday
    s = only(health(env, [YF_D1], utc(2024, 6, 20, 12)), YF_D1)  # Thursday, before its close
    assert s.status is HealthStatus.OK and s.bars_behind == 0
    weekend = only(health(env, [YF_D1], utc(2024, 6, 16, 12)), YF_D1)  # Sunday after Fri 14
    assert weekend.bars_behind == 0 and weekend.status is HealthStatus.OK


@pytest.mark.unit
def test_a_removed_session_inside_the_lookback_is_degraded_and_listed(env):
    hole = date(2024, 6, 11)
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 14) and d != hole])
    s = only(health(env, [YF_D1], AFTER_FRI_14), YF_D1)
    assert s.status is HealthStatus.DEGRADED and s.missing_in_window == (CAL.session(hole).open,)
    assert "1 expected bar missing" in s.detail


@pytest.mark.unit
def test_no_bars_is_missing(env):
    s = only(health(env, [YF_D1], AFTER_FRI_14), YF_D1)
    assert s.status is HealthStatus.MISSING and s.latest_bar_end is None and s.age is None and s.bars_behind is None
    assert "no yfinance D1 bar" in s.detail


@pytest.mark.unit
def test_no_mapping_for_the_provider_is_missing_with_that_detail(env):
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 14)], source="othervendor")
    s = only(health(env, [SourceKey("othervendor", D1)], AFTER_FRI_14), SourceKey("othervendor", D1))
    assert s.status is HealthStatus.MISSING and s.detail == "no symbol mapping for othervendor on 2024-06-14"


@pytest.mark.unit
def test_hourly_health_counts_hours_and_half_open_sessions(env):
    thu = date(2024, 6, 13)
    env["writer"].write_candles([bar(thu, H1, k) for k in range(7)], import_id="h")
    two_sessions = HealthThresholds(stale_after_bars={D1: 1, H1: 1}, lookback_sessions=2)  # Thu and Fri
    at = utc(2024, 6, 14, 15, 40)  # Friday: two hours have ended
    s = only(health(env, [YF_H1], at, thresholds=two_sessions), YF_H1)
    assert s.bars_behind == 2 and s.status is HealthStatus.STALE
    env["writer"].write_candles([bar(date(2024, 6, 14), H1, 0)], import_id="h2")
    assert only(health(env, [YF_H1], at, thresholds=two_sessions), YF_H1).status is HealthStatus.OK


# ------------------------------------------------------------------ applicability


@pytest.mark.unit
def test_an_inactive_instrument_is_not_applicable_and_gets_no_statuses(env):
    env["instruments"].add(Instrument("EQ_US_NEWCO", AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                                      InstrumentStatus.ACTIVE, date(2024, 7, 1), None))
    result = health(env, [YF_D1], AFTER_FRI_14, instrument_id="EQ_US_NEWCO")
    assert result.applicability == Applicability(False, "EQ_US_NEWCO not active before 2024-07-01")
    assert result.sources == () and result.required_sources_ok is False


@pytest.mark.unit
def test_a_delisted_instrument_is_not_applicable_on_or_after_active_to(env):
    env["instruments"].add(Instrument("EQ_US_OLDCO", AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                                      InstrumentStatus.DELISTED, date(2001, 1, 2), date(2024, 6, 14)))
    result = health(env, [YF_D1], AFTER_FRI_14, instrument_id="EQ_US_OLDCO")
    assert result.applicability == Applicability(False, "EQ_US_OLDCO not active on or after 2024-06-14")


@pytest.mark.unit
def test_statuses_are_only_the_four_frozen_states_on_every_path(env):
    assert {s.value for s in HealthStatus} == {"OK", "STALE", "MISSING", "DEGRADED"}
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 12)])  # yfinance: complete to Wed 12
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 12) and d != date(2024, 6, 5)], source="testvendor",
                 import_id="t")  # testvendor: a hole on Wed 5
    required = [YF_D1, YF_H1, TV_D1, SourceKey("othervendor", D1)]
    seen = {}
    for at in (utc(2024, 6, 12, 21), utc(2024, 6, 21, 21)):
        for s in health(env, required, at).sources:
            assert isinstance(s.status, HealthStatus)
            assert (s.detail == "") == (s.status is HealthStatus.OK)
            seen.setdefault(s.status, s.source)
    assert set(seen) == set(HealthStatus)  # OK, STALE, DEGRADED and MISSING all reached; nothing else produced
    assert seen[HealthStatus.OK] == YF_D1 and seen[HealthStatus.DEGRADED] == TV_D1


# ------------------------------------------------------------------ two providers


@pytest.mark.unit
def test_providers_are_evaluated_independently(env):
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 14)])
    result = health(env, [YF_D1, TV_D1], AFTER_FRI_14)
    assert only(result, YF_D1).status is HealthStatus.OK and only(result, TV_D1).status is HealthStatus.MISSING
    assert health(env, [YF_D1], AFTER_FRI_14).required_sources_ok is True
    assert result.required_sources_ok is False


@pytest.mark.unit
def test_a_testvendor_bar_never_fills_a_yfinance_gap(env):
    hole = date(2024, 6, 11)
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 14) and d != hole])
    env["writer"].write_candles([bar(hole, source="testvendor")], import_id="tv")
    assert only(health(env, [YF_D1], AFTER_FRI_14), YF_D1).status is HealthStatus.DEGRADED


# ------------------------------------------------------------------ other cases


@pytest.mark.unit
def test_bars_and_corrections_available_after_t_are_not_used(env):
    from dataclasses import replace

    late = utc(2024, 6, 30)
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 13)])
    # Friday 14 June's bar is first observed on 30 June (no backfill time): at AFTER_FRI_14 it isn't visible.
    env["writer"].write_candles([replace(bar(date(2024, 6, 14), received_at=late), backfill_available_from=None)],
                                import_id="late")
    s = only(health(env, [YF_D1], AFTER_FRI_14), YF_D1)
    assert s.bars_behind == 1 and s.latest_bar_end == CAL.session(date(2024, 6, 13)).close
    assert only(health(env, [YF_D1], late), YF_D1).bars_behind == 9  # 17, 18, 20, 21, 24 – 28 June (19th a holiday)
    # A correction available after T changes nothing at T.
    env["writer"].write_candles([bar(date(2024, 6, 13), close="100.5", received_at=utc(2024, 7, 1))], import_id="fix")
    assert only(health(env, [YF_D1], AFTER_FRI_14), YF_D1) == s


@pytest.mark.unit
def test_the_injected_clock_is_used(env):
    daily_series(env, [d for d in JUNE if d <= date(2024, 6, 14)])
    for at in (AFTER_FRI_14, utc(2024, 6, 21, 21)):
        assert health(env, [YF_D1], at).as_of == at


@pytest.mark.unit
@pytest.mark.parametrize("required", [[], [YF_D1, YF_D1]], ids=["empty", "duplicate"])
def test_the_required_set_must_be_non_empty_and_distinct(env, required):
    with pytest.raises(ValueError):
        health(env, required, AFTER_FRI_14)


@pytest.mark.unit
def test_default_thresholds_are_documented_and_immutable():
    t = HealthThresholds()
    assert dict(t.stale_after_bars) == {D1: 1, H1: 1} and t.lookback_sessions == 20
    with pytest.raises(TypeError):
        t.stale_after_bars[D1] = 5
    with pytest.raises(ValueError):
        HealthThresholds(stale_after_bars={D1: 1}, lookback_sessions=20)  # every timeframe needs a threshold
    with pytest.raises(ValueError):
        HealthThresholds(lookback_sessions=0)


@pytest.mark.unit
def test_a_daily_bar_with_the_wrong_session_end_cannot_report_ok(env):
    # Candle deliberately doesn't validate calendar duration. Health must not
    # mistake a shortened vendor day for the expected complete daily bar.
    from dataclasses import replace

    session = CAL.session(date(2024, 6, 14))
    malformed = replace(bar(session.date), end_time=session.close - timedelta(minutes=1),
                        event_time=session.close - timedelta(minutes=1))
    env["writer"].write_candles([malformed], import_id="short-day")
    with pytest.raises(ValueError, match="expected"):
        health(env, [YF_D1], AFTER_FRI_14, thresholds=HealthThresholds(lookback_sessions=1))


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"source": "testvendor"}, {"instrument_id": "EQ_US_MSFT"}, {"timeframe": H1},
], ids=["provider", "instrument", "timeframe"])
def test_health_refuses_reader_rows_for_another_identity(env, change):
    from dataclasses import replace

    daily_series(env)
    actual_reader = env["reader"]

    class WrongReader:
        def candles_visible_at(self, *args):
            return [replace(c, **change) for c in actual_reader.candles_visible_at(*args)]

    env["reader"] = WrongReader()
    with pytest.raises(ValueError, match="identity"):
        health(env, [YF_D1], AFTER_FRI_14)


@pytest.mark.unit
@pytest.mark.parametrize("at", [utc(2030, 1, 7, 15), utc(2018, 12, 31, 15)], ids=["after", "before"])
def test_a_time_outside_the_calendars_coverage_raises_instead_of_reporting(env, at):
    # Self-review probe: expected bars can't be established there, so no status is reported.
    from investment_engine.market.calendar.base import CalendarRangeError

    with pytest.raises(CalendarRangeError):
        health(env, [YF_D1], at)
