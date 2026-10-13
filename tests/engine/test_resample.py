"""Hourly → daily resampling within calendar sessions, as of a cutoff (docs/tasks/M1-15.md).

Only inputs available at `at` may enter; one provider only; a closed session with
a missing hour is a gap, never a bar; every input is referenced; and differences
from the vendor's daily series are reported, never reconciled.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.resample import (
    DailyDifference,
    InputRef,
    ResampledBar,
    SessionGap,
    aggregate_session,
    compare_daily,
    expected_starts,
    resample_daily,
)
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import CandleObservation, MarketDataWriter

NVDA = "EQ_US_NVDA"
H1, D1 = Timeframe.H1, Timeframe.D1
CAL = load_us_equities_calendar()
FRI = date(2024, 6, 7)  # regular session, 13:30 – 20:00 UTC
HALF = date(2024, 7, 3)  # half-day, 13:30 – 17:00 UTC
LATER = datetime(2024, 7, 10, tzinfo=UTC)


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def hourly(d, k, *, source="yfinance", o="100", h="101", lo="99", c="100.5", v="1000", received_at=None,
           backfill=True, currency="USD", price_basis=PriceBasis.RAW_AS_REPORTED):
    session = CAL.session(d)
    start = session.open + timedelta(hours=k)
    end = min(start + timedelta(hours=1), session.close)
    received_at = received_at or end + timedelta(days=3)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=H1, start_time=start, end_time=end,
        open=Decimal(o), high=Decimal(h), low=Decimal(lo), close=Decimal(c), currency=currency,
        volume=Decimal(v), state=BarState.CLOSED, source_version="1.7.0", price_basis=price_basis,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=end, received_at=received_at,
        processed_at=received_at, backfill_available_from=end if backfill else None,
    )


def daily(d, *, source="yfinance", o="100", h="107", lo="93", c="106.5", v="7000", received_at=None,
          backfill=True):
    session = CAL.session(d)
    received_at = received_at or session.close + timedelta(days=3)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=D1, start_time=session.open, end_time=session.close,
        open=Decimal(o), high=Decimal(h), low=Decimal(lo), close=Decimal(c), currency="USD",
        volume=Decimal(v), state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=session.close, received_at=received_at,
        processed_at=received_at, backfill_available_from=session.close if backfill else None,
    )


def friday_bars(source="yfinance", skip=()):
    """Seven hours with rising prices: open 100 (hour 0) ... close 106.5 (hour 6)."""
    return [hourly(FRI, k, source=source, o=str(100 + k), h=str(101 + k), lo=str(99 - k), c=str(100.5 + k),
                   v=str(1000)) for k in range(7) if k not in skip]


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "market"
    return MarketDataWriter(root), MarketDataReader(root)


def stored(store, observations, import_id="imp-1"):
    writer, reader = store
    writer.write_candles(observations, import_id=import_id)
    return reader


def visible(reader, d, at, source="yfinance"):
    session = CAL.session(d)
    return reader.candles_visible_at(source, NVDA, H1, session.open, session.close, at)


@pytest.mark.unit
def test_resample_refuses_another_instruments_reader_rows(store):
    reader = stored(store, friday_bars())
    rows = [replace(c, instrument_id="EQ_US_MSFT") for c in visible(reader, FRI, LATER)]

    class WrongReader:
        def candles_visible_at(self, *args):
            return rows

    with pytest.raises(ValueError, match="identity"):
        resample_daily(WrongReader(), "yfinance", NVDA, FRI, FRI, calendar=CAL, at=LATER)


@pytest.mark.unit
def test_comparison_refuses_resampled_bars_for_another_instrument(store):
    reader = stored(store, friday_bars())
    rows = [replace(c, instrument_id="EQ_US_MSFT") for c in visible(reader, FRI, LATER)]
    result = aggregate_session(rows, CAL.session(FRI), at=LATER)
    with pytest.raises(ValueError, match="identity"):
        compare_daily(reader, "yfinance", NVDA, [result], at=LATER)


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"source": "testvendor"}, {"instrument_id": "EQ_US_MSFT"},
    {"timeframe": H1}, {"currency": "EUR"},
], ids=["provider", "instrument", "timeframe", "currency"])
def test_comparison_refuses_vendor_rows_that_cannot_be_compared(store, change):
    reader = stored(store, friday_bars())
    result = aggregate_session(visible(reader, FRI, LATER), CAL.session(FRI), at=LATER)
    stored(store, [daily(FRI)], import_id="daily")
    session = CAL.session(FRI)
    [vendor] = reader.candles_visible_at("yfinance", NVDA, D1, session.open, session.close, LATER)

    class WrongReader:
        def candles_visible_at(self, *args):
            return [replace(vendor, **change)]

    with pytest.raises(ValueError, match="identity|currency"):
        compare_daily(WrongReader(), "yfinance", NVDA, [result], at=LATER)


@pytest.mark.unit
def test_comparison_refuses_duplicate_resampled_sessions(store):
    reader = stored(store, friday_bars())
    result = aggregate_session(visible(reader, FRI, LATER), CAL.session(FRI), at=LATER)
    with pytest.raises(ValueError, match="duplicate"):
        compare_daily(reader, "yfinance", NVDA, [result, result], at=LATER)


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"price_basis": PriceBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED},
    {"volume_basis": VolumeBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED},
], ids=["price-provenance", "volume-provenance"])
def test_raw_vendor_values_are_comparable_despite_different_reconstruction_provenance(store, change):
    # Daily volume may be reconstructed while hourly volume is already raw.
    # Both labels name as-traded units, so their provenance isn't a unit mismatch.
    reader = stored(store, friday_bars())
    result = aggregate_session(visible(reader, FRI, LATER), CAL.session(FRI), at=LATER)
    stored(store, [daily(FRI)], import_id="daily")
    session = CAL.session(FRI)
    [vendor] = reader.candles_visible_at("yfinance", NVDA, D1, session.open, session.close, LATER)

    class ReconstructedReader:
        def candles_visible_at(self, *args):
            return [replace(vendor, **change)]

    assert compare_daily(ReconstructedReader(), "yfinance", NVDA, [result], at=LATER) == []


# ------------------------------------------------------------------ basic sessions


@pytest.mark.unit
def test_a_full_regular_session_gives_a_closed_bar_field_by_field(store):
    reader = stored(store, friday_bars())
    [bar] = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=LATER)
    assert isinstance(bar, ResampledBar) and bar.state is BarState.CLOSED
    assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
        Decimal(100), Decimal(107), Decimal(93), Decimal("106.5"), Decimal(7000))
    assert (bar.source, bar.derivation, bar.session_date, bar.as_of) == ("yfinance", "H1->D1", FRI, LATER)
    session = CAL.session(FRI)
    assert (bar.start_time, bar.end_time) == (session.open, session.close)
    assert (bar.currency, bar.price_basis, bar.volume_basis) == ("USD", PriceBasis.RAW_AS_REPORTED,
                                                                 VolumeBasis.RAW_AS_REPORTED)


@pytest.mark.unit
def test_a_half_day_expects_inputs_only_until_13_00():
    session = CAL.session(HALF)
    starts = expected_starts(session)
    assert [s.astimezone(UTC).hour for s in starts] == [13, 14, 15, 16]  # 09:30 – 12:30 New York
    assert min(starts[-1] + timedelta(hours=1), session.close) == utc(2024, 7, 3, 17, 0)


@pytest.mark.unit
def test_a_full_half_day_gives_a_closed_bar(store):
    reader = stored(store, [hourly(HALF, k) for k in range(4)])
    [bar] = resample_daily(reader, "yfinance", NVDA, HALF, HALF, calendar=CAL, at=LATER)
    assert bar.state is BarState.CLOSED and bar.end_time == utc(2024, 7, 3, 17, 0) and len(bar.inputs) == 4


# ------------------------------------------------------------------ gaps and forming bars


@pytest.mark.unit
def test_a_missing_middle_hour_in_a_closed_session_is_a_gap_not_a_bar(store):
    reader = stored(store, friday_bars(skip={3}))
    [gap] = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=LATER)
    assert isinstance(gap, SessionGap)
    assert gap.missing_starts == (CAL.session(FRI).open + timedelta(hours=3),)
    assert (gap.source, gap.session_date, gap.as_of) == ("yfinance", FRI, LATER)


@pytest.mark.unit
def test_during_the_session_a_forming_bar_uses_only_bars_ended_by_at(store):
    bars = [hourly(FRI, k, o=str(100 + k), h=str(101 + k), lo=str(99 - k), c=str(100.5 + k),
                   received_at=None, backfill=False) for k in range(7)]
    # each hour observed live at its end
    bars = [replace(b, received_at=b.end_time, processed_at=b.end_time) for b in bars]
    reader = stored(store, bars)
    at = CAL.session(FRI).open + timedelta(hours=3, minutes=10)  # three hours ended
    [bar] = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=at)
    assert bar.state is BarState.FORMING and len(bar.inputs) == 3
    assert (bar.open, bar.high, bar.close) == (Decimal(100), Decimal(103), Decimal("102.5"))
    assert bar.availability_basis is AvailabilityBasis.OBSERVED


@pytest.mark.unit
def test_a_forming_session_with_an_earlier_hour_missing_is_a_gap(store):
    bars = [replace(b, received_at=b.end_time, processed_at=b.end_time, backfill_available_from=None)
            for b in friday_bars(skip={1})]
    reader = stored(store, bars)
    at = CAL.session(FRI).open + timedelta(hours=3, minutes=10)
    [gap] = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=at)
    assert isinstance(gap, SessionGap) and gap.missing_starts == (CAL.session(FRI).open + timedelta(hours=1),)


@pytest.mark.unit
def test_sessions_not_yet_open_at_at_give_nothing(store):
    reader = stored(store, friday_bars())
    assert resample_daily(reader, "yfinance", NVDA, FRI, date(2024, 6, 10), calendar=CAL,
                          at=CAL.session(FRI).close + timedelta(days=4)) != []
    assert resample_daily(reader, "yfinance", NVDA, date(2024, 6, 10), date(2024, 6, 10), calendar=CAL,
                          at=utc(2024, 6, 9)) == []


# ------------------------------------------------------------------ the cutoff


@pytest.mark.unit
def test_a_bar_ending_after_at_passed_directly_raises(store):
    reader = stored(store, friday_bars())
    inputs = visible(reader, FRI, LATER)
    at = inputs[2].end_time  # bars 3 – 6 end after this
    with pytest.raises(ValueError, match="after the cutoff"):
        aggregate_session(inputs, CAL.session(FRI), at=at)


@pytest.mark.unit
def test_a_correction_not_available_at_at_is_not_used_and_one_available_is(store):
    writer, reader = store
    writer.write_candles(friday_bars(), import_id="backfill")
    fixed_at = utc(2024, 6, 20)
    writer.write_candles([hourly(FRI, 6, c="200", h="201", received_at=fixed_at)], import_id="fix")
    [before] = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=fixed_at - timedelta(seconds=1))
    [after] = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=fixed_at)
    assert before.close == Decimal("106.5") and before.inputs[-1].revision == 1
    assert after.close == Decimal(200) and after.inputs[-1].revision == 2
    assert after.available_from == fixed_at and after.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED


@pytest.mark.unit
def test_an_input_not_yet_available_passed_directly_raises(store):
    reader = stored(store, friday_bars())
    inputs = visible(reader, FRI, LATER)
    late = replace(inputs[0], available_from=LATER + timedelta(days=1))
    with pytest.raises(ValueError, match="not available"):
        aggregate_session([late, *inputs[1:]], CAL.session(FRI), at=LATER)


# ------------------------------------------------------------------ providers and consistency


@pytest.mark.unit
def test_mixed_providers_raise(store):
    writer, reader = store
    writer.write_candles(friday_bars(), import_id="y")
    writer.write_candles(friday_bars(source="testvendor"), import_id="t")
    mixed = visible(reader, FRI, LATER)[:3] + visible(reader, FRI, LATER, source="testvendor")[3:]
    with pytest.raises(ValueError, match="one provider"):
        aggregate_session(mixed, CAL.session(FRI), at=LATER)


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"currency": "EUR"},
    {"price_basis": PriceBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED},
    {"volume_basis": VolumeBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED},
    {"instrument_id": "EQ_US_AMD"},
    {"timeframe": D1},
], ids=["currency", "price-basis", "volume-basis", "instrument", "timeframe"])
def test_inconsistent_inputs_raise(store, change):
    inputs = visible(stored(store, friday_bars()), FRI, LATER)
    with pytest.raises(ValueError):
        aggregate_session([replace(inputs[0], **change), *inputs[1:]], CAL.session(FRI), at=LATER)


@pytest.mark.unit
def test_a_duplicate_start_time_raises(store):
    inputs = visible(stored(store, friday_bars()), FRI, LATER)
    with pytest.raises(ValueError, match="duplicate"):
        aggregate_session([*inputs, replace(inputs[2], revision=2, availability_basis=AvailabilityBasis.OBSERVED,
                                            available_from=inputs[2].received_at)], CAL.session(FRI), at=LATER)


@pytest.mark.unit
def test_an_input_off_the_session_grid_raises(store):
    inputs = visible(stored(store, friday_bars()), FRI, LATER)
    shifted = replace(inputs[0], start_time=inputs[0].start_time + timedelta(minutes=30))
    with pytest.raises(ValueError, match="expected hourly start"):
        aggregate_session([shifted, *inputs[1:]], CAL.session(FRI), at=LATER)


@pytest.mark.unit
def test_compare_daily_reads_only_the_same_provider(store):
    writer, reader = store
    writer.write_candles(friday_bars(source="testvendor"), import_id="t")
    writer.write_candles([daily(FRI, c="95")], import_id="yd")  # yfinance daily, different: must be ignored
    writer.write_candles([daily(FRI, source="testvendor")], import_id="td")
    resampled = resample_daily(reader, "testvendor", NVDA, FRI, FRI, calendar=CAL, at=LATER)
    assert compare_daily(reader, "testvendor", NVDA, resampled, at=LATER) == []
    with pytest.raises(ValueError, match="provider"):
        compare_daily(reader, "yfinance", NVDA, resampled, at=LATER)


# ------------------------------------------------------------------ lineage


@pytest.mark.unit
def test_inputs_reference_every_input_revision_completely(store):
    reader = stored(store, friday_bars(), import_id="imp-77")
    [bar] = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=LATER)
    session = CAL.session(FRI)
    assert bar.inputs == tuple(
        InputRef("yfinance", NVDA, H1, session.open + timedelta(hours=k), 1, "imp-77",
                 min(session.open + timedelta(hours=k + 1), session.close))
        for k in range(7))
    assert bar.available_from == session.close and bar.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED


# ------------------------------------------------------------------ compare_daily


@pytest.mark.unit
def test_identical_daily_bars_have_no_differences(store):
    reader = stored(store, [*friday_bars(), daily(FRI)])
    resampled = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=LATER)
    assert compare_daily(reader, "yfinance", NVDA, resampled, at=LATER) == []


@pytest.mark.unit
def test_a_different_close_is_one_difference(store):
    reader = stored(store, [*friday_bars(), daily(FRI, c="106.75")])
    resampled = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=LATER)
    assert compare_daily(reader, "yfinance", NVDA, resampled, at=LATER) == [
        DailyDifference(FRI, "close", Decimal("106.75"), Decimal("106.5"))]


@pytest.mark.unit
def test_a_missing_vendor_day_and_a_missing_resampled_day(store):
    thu = date(2024, 6, 6)
    reader = stored(store, [*friday_bars(), *[hourly(thu, k) for k in range(7) if k != 2], daily(thu)])
    resampled = resample_daily(reader, "yfinance", NVDA, thu, FRI, calendar=CAL, at=LATER)
    bars = [r for r in resampled if isinstance(r, ResampledBar)]
    assert [type(r).__name__ for r in resampled] == ["SessionGap", "ResampledBar"]
    diffs = compare_daily(reader, "yfinance", NVDA, bars, at=LATER, first_session=thu, last_session=FRI,
                          calendar=CAL)
    assert diffs == [DailyDifference(thu, "missing_resampled", None, None),
                     DailyDifference(FRI, "missing_vendor", None, None)]


@pytest.mark.unit
def test_vendor_bars_not_yet_available_at_at_are_missing(store):
    vendor_seen = utc(2024, 6, 20)
    reader = stored(store, [*friday_bars(), daily(FRI, received_at=vendor_seen, backfill=False)])  # observed late
    before = vendor_seen - timedelta(seconds=1)
    resampled = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=before)
    assert compare_daily(reader, "yfinance", NVDA, resampled, at=before) == [
        DailyDifference(FRI, "missing_vendor", None, None)]
    resampled = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=vendor_seen)
    assert compare_daily(reader, "yfinance", NVDA, resampled, at=vendor_seen) == []


@pytest.mark.unit
def test_forming_bars_are_not_compared(store):
    reader = stored(store, [*friday_bars(), daily(FRI)])
    early = CAL.session(FRI).close - timedelta(seconds=1)
    forming = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=early)
    assert forming[0].state is BarState.FORMING
    assert compare_daily(reader, "yfinance", NVDA, forming, at=early) == []


@pytest.mark.unit
def test_compare_daily_needs_the_same_cutoff(store):
    reader = stored(store, [*friday_bars(), daily(FRI)])
    resampled = resample_daily(reader, "yfinance", NVDA, FRI, FRI, calendar=CAL, at=LATER)
    with pytest.raises(ValueError, match="cutoff"):
        compare_daily(reader, "yfinance", NVDA, resampled, at=LATER + timedelta(days=1))
