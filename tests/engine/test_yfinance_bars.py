"""Daily Yahoo bars: verified reconstruction, dated symbols and honest revisions.

Actual hourly imports stay blocked. Hourly-specific acceptance cases remain
pending independent evidence; these tests do not silently enable that path.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from investment_engine.clock import ReplayClock
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.importers import (
    yfinance_actions as actions_module,
    yfinance_bars as bars_module,
)
from investment_engine.market.importers.yahoo_semantics import (
    YAHOO_VERIFICATION,
    FieldBlocked,
    FieldKey,
    OutsideVerifiedRange,
    SplitHistoryMismatch,
    Transformation,
    VersionMismatch,
    load_recording,
)
from investment_engine.market.importers.yfinance_actions import import_actions
from investment_engine.market.importers.yfinance_bars import import_bars
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import ActionObservation, MarketDataWriter
from investment_engine.market.symbols import SymbolMapping, SymbolResolver
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)

FIXTURES = Path(__file__).parent / "fixtures" / "yfinance"
NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)


def installed(yfinance_version):
    """A stand-in for importlib.metadata.version that reports `yfinance_version`."""
    def version(name):
        assert name == "yfinance"
        return yfinance_version
    return version


@pytest.fixture(autouse=True)
def verified_yfinance(monkeypatch):
    """Recorded-data tests run as if the verified yfinance were installed, whatever actually is."""
    for module in (actions_module, bars_module):
        monkeypatch.setattr(module, "version", installed(YAHOO_VERIFICATION.yfinance_version))



def frame(name="nvda_1d_2019_2026.json"):
    rec = load_recording(FIXTURES / name)
    return pd.DataFrame([r[1:] for r in rec.rows], columns=rec.columns,
                        index=pd.to_datetime([r[0] for r in rec.rows], utc=True).tz_convert("America/New_York"))


def action_series(name):
    return frame(name).iloc[:, 0]


@pytest.fixture
def market(tmp_path):
    conn = open_operational_db(tmp_path / "operational.sqlite3")
    apply_schema(conn)
    instruments = SqliteInstrumentRepository(conn)
    instruments.add(Instrument("EQ_US_NVDA", AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                               InstrumentStatus.ACTIVE, date(1999, 1, 22), None))
    resolver = SqliteSymbolResolver(conn)
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "NVDA", date(1999, 1, 22), None))
    root = tmp_path / "market[x]"
    args = {"clock": ReplayClock(NOW), "resolver": resolver, "instruments": instruments,
            "writer": MarketDataWriter(root), "reader": MarketDataReader(root),
            "calendar": load_us_equities_calendar()}
    import_actions("EQ_US_NVDA", **{k: args[k] for k in ("clock", "resolver", "instruments", "writer")},
                   fetch_split_history=lambda symbol: action_series("nvda_splits_before.json"),
                   fetch_dividends=lambda symbol: action_series("nvda_dividends.json"))
    yield args
    conn.close()


def rows(market, start=date(2019, 1, 1), end=date(2027, 1, 1)):
    return market["reader"].candles_latest("yfinance", "EQ_US_NVDA", Timeframe.D1,
                                           datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                                           datetime.combine(end, datetime.min.time(), tzinfo=UTC))


def run(market, start=date(2021, 7, 1), end=date(2021, 7, 20), *, data=None, splits=None,
        verification=YAHOO_VERIFICATION, backfill_latency=timedelta(0), filter_response=True):
    data = frame() if data is None else data
    splits = action_series("nvda_splits_before.json") if splits is None else splits
    calls = []

    def fetch_bars(symbol, **kwargs):
        calls.append(("bars", symbol, kwargs))
        if not filter_response:
            return data.copy()
        dates = data.index.date
        return data[(dates >= kwargs["start"]) & (dates < kwargs["end"])].copy()

    def fetch_splits(symbol):
        calls.append(("splits", symbol))
        return splits.copy()

    report = import_bars("EQ_US_NVDA", Timeframe.D1, start, end, **market, fetch_bars=fetch_bars,
                         fetch_split_history=fetch_splits, verification=verification, backfill_latency=backfill_latency)
    return report, calls


@pytest.mark.unit
def test_july_window_uses_later_splits_and_excludes_july_twenty(market):
    report, calls = run(market)
    candles = rows(market)
    assert report.write.new_records == len(candles) == 12
    assert report.max_split_factor_applied == Decimal("40")
    assert report.split_history == YAHOO_VERIFICATION.cited_splits
    assert candles[-1].start_time.astimezone(ZoneInfo("America/New_York")).date() == date(2021, 7, 19)
    assert candles[-1].close == Decimal("751.1900")
    assert report.covered == (candles[0].start_time, candles[-1].end_time)
    assert [c[0] for c in calls] == ["splits", "bars", "splits"]
    assert calls[1][2] == {"start": date(2021, 7, 1), "end": date(2021, 7, 20), "interval": "1d",
                           "auto_adjust": False, "actions": False, "repair": False,
                           "back_adjust": False, "prepost": False}
    for candle in candles:
        assert candle.currency == "USD" and candle.source == "yfinance"
        assert candle.price_basis is PriceBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED
        assert candle.volume_basis is VolumeBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED
        assert candle.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED
        assert candle.available_from == candle.end_time and candle.received_at == NOW
        assert candle.source_version == "1.7.0" and candle.revision == 1


@pytest.mark.unit
def test_daily_window_across_split_and_fake_response_actions(market):
    data = frame()
    data["Stock Splits"] = 1000.0  # ignored, never the source of reconstruction
    report, _ = run(market, date(2024, 6, 6), date(2024, 6, 12), data=data)
    candles = rows(market)
    assert len(candles) == 4 and report.max_split_factor_applied == 10
    assert candles[1].close == Decimal("1208.8800")
    assert candles[2].close == Decimal("121.7900")
    assert candles[1].close / candles[2].close > 9


@pytest.mark.unit
def test_identical_reimport_creates_no_files(market):
    run(market)
    files = set(market["writer"].root.rglob("*.parquet"))
    report, _ = run(market)
    assert (report.write.new_records, report.write.new_revisions, report.write.unchanged) == (0, 0, 12)
    assert set(market["writer"].root.rglob("*.parquet")) == files


@pytest.mark.unit
def test_changed_close_is_observed_and_earlier_view_stays_original(market):
    run(market)
    market["clock"].advance_by(timedelta(hours=1))
    data = frame()
    index = pd.Timestamp("2021-07-19", tz="America/New_York")
    data.loc[index, "Close"] += 0.01
    report, _ = run(market, data=data)
    assert (report.write.new_revisions, report.write.unchanged) == (1, 11)
    latest = rows(market)[-1]
    assert latest.revision == 2 and latest.close == Decimal("751.5900")
    assert latest.availability_basis is AvailabilityBasis.OBSERVED
    assert latest.available_from == NOW + timedelta(hours=1)
    old = market["reader"].candles_visible_at("yfinance", "EQ_US_NVDA", Timeframe.D1,
                                              rows(market)[0].start_time, NOW, NOW)
    assert old[-1].close == Decimal("751.1900") and old[-1].revision == 1


@pytest.mark.unit
def test_new_uncited_split_aborts_even_if_store_agrees(market):
    splits = action_series("nvda_splits_before.json")
    splits.loc[pd.Timestamp("2026-10-10", tz="America/New_York")] = 2.0
    a = market["reader"].actions_latest("yfinance", "EQ_US_NVDA", date(2024, 6, 10), date(2024, 6, 11), {ActionType.SPLIT})[0]
    extra = ActionObservation(a.source, a.instrument_id, a.currency, a.exchange_timezone, a.action_type,
                             date(2026, 10, 10), Decimal("2"), None, None, None, a.source_version, NOW, NOW, None)
    market["writer"].write_corporate_actions([extra], "uncited-store-agrees")
    with pytest.raises(SplitHistoryMismatch, match="extra"):
        run(market, splits=splits)
    assert rows(market) == []


@pytest.mark.unit
def test_reimport_after_reviewed_new_split_is_unchanged(market):
    run(market)
    splits = action_series("nvda_splits_before.json")
    splits.loc[pd.Timestamp("2026-10-10", tz="America/New_York")] = 2.0
    record = replace(YAHOO_VERIFICATION, cited_splits=(*YAHOO_VERIFICATION.cited_splits,
                                                      (date(2026, 10, 10), Decimal("2"))))
    import_actions("EQ_US_NVDA", **{k: market[k] for k in ("clock", "resolver", "instruments", "writer")},
                   fetch_split_history=lambda symbol: splits,
                   fetch_dividends=lambda symbol: action_series("nvda_dividends.json") / 2,
                   verification=record)
    data = frame()
    data[["Open", "High", "Low", "Close"]] /= 2
    data["Volume"] *= 2
    report, _ = run(market, data=data, splits=splits, verification=record)
    assert report.max_split_factor_applied == 80
    assert (report.write.new_records, report.write.new_revisions, report.write.unchanged) == (0, 0, 12)


@pytest.mark.unit
def test_vendor_and_store_in_range_mismatch_aborts(market):
    splits = action_series("nvda_splits_before.json")
    splits.loc[pd.Timestamp("2025-01-02", tz="America/New_York")] = 2.0
    record = replace(YAHOO_VERIFICATION, cited_splits=tuple(sorted((*YAHOO_VERIFICATION.cited_splits,
                                                                 (date(2025, 1, 2), Decimal("2"))))))
    with pytest.raises(SplitHistoryMismatch, match="action import"):
        run(market, splits=splits, verification=record)
    assert rows(market) == []


@pytest.mark.unit
def test_missing_or_changed_stored_split_aborts(market):
    a = market["reader"].actions_latest("yfinance", "EQ_US_NVDA", date(2024, 6, 10), date(2024, 6, 11), {ActionType.SPLIT})[0]
    observation = ActionObservation(a.source, a.instrument_id, a.currency, a.exchange_timezone, a.action_type,
                                    a.ex_date, Decimal("11"), None, None, None, a.source_version, NOW, NOW, None)
    market["writer"].write_corporate_actions([observation], "changed-split")
    with pytest.raises(SplitHistoryMismatch, match="action import"):
        run(market)
    assert rows(market) == []


@pytest.mark.unit
def test_missing_stored_split_aborts_without_writing(market, tmp_path):
    market["reader"] = MarketDataReader(tmp_path / "empty")
    with pytest.raises(SplitHistoryMismatch, match="action import"):
        run(market)
    assert not list((market["writer"].root / "candles").rglob("*.parquet"))


@pytest.mark.unit
def test_history_changed_during_download_aborts(market):
    splits = action_series("nvda_splits_before.json")
    history = iter([splits, splits.iloc[:-1]])
    with pytest.raises(SplitHistoryMismatch, match="mid-run"):
        import_bars("EQ_US_NVDA", Timeframe.D1, date(2021, 7, 1), date(2021, 7, 20), **market,
                    fetch_split_history=lambda symbol: next(history), fetch_bars=lambda symbol, **kw: frame())
    assert rows(market) == []


@pytest.mark.unit
def test_old_vendor_split_discrepancy_does_not_block_daily_import(market):
    splits = action_series("nvda_splits_before.json")
    index = list(splits.index)
    index[1] += timedelta(days=5)
    splits.index = index
    report, _ = run(market, splits=splits)
    assert report.write.new_records == 12


@pytest.mark.unit
@pytest.mark.parametrize("case", ["range", "blocked-price", "blocked-volume", "hourly", "version", "instrument"])
def test_invalid_request_stops_before_any_fetch(market, case):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid request must not fetch")

    record = YAHOO_VERIFICATION
    start, end, timeframe, instrument = date(2021, 7, 1), date(2021, 7, 20), Timeframe.D1, "EQ_US_NVDA"
    error = FieldBlocked
    if case == "range":
        start, error = date(2018, 12, 31), OutsideVerifiedRange
    elif case.startswith("blocked"):
        key = FieldKey.D1_PRICE if case.endswith("price") else FieldKey.D1_VOLUME
        fields = dict(record.fields)
        fields[key] = replace(fields[key], transformation=Transformation.BLOCKED)
        record = replace(record, fields=fields)
    elif case == "hourly":
        timeframe = Timeframe.H1
    elif case == "version":
        record, error = replace(record, yfinance_version="0.0.0"), VersionMismatch
    elif case == "instrument":
        instrument, error = "EQ_US_OTHER", ValueError
    with pytest.raises(error):
        import_bars(instrument, timeframe, start, end, **market, fetch_split_history=forbidden,
                    fetch_bars=forbidden, verification=record)
    assert rows(market) == []


@pytest.mark.unit
def test_price_reconstruction_with_identity_volume_has_separate_bases(market):
    fields = dict(YAHOO_VERIFICATION.fields)
    fields[FieldKey.D1_VOLUME] = replace(fields[FieldKey.D1_VOLUME], transformation=Transformation.IDENTITY)
    run(market, verification=replace(YAHOO_VERIFICATION, fields=fields))
    first = rows(market)[0]
    original = frame().loc[pd.Timestamp("2021-07-01", tz="America/New_York"), "Volume"]
    assert first.volume == Decimal(int(original))
    assert first.price_basis is PriceBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED
    assert first.volume_basis is VolumeBasis.RAW_AS_REPORTED


@pytest.mark.unit
def test_identity_if_no_later_split_rejects_and_reports_earlier_bars(market):
    fields = dict(YAHOO_VERIFICATION.fields)
    fields[FieldKey.D1_PRICE] = replace(fields[FieldKey.D1_PRICE], transformation=Transformation.IDENTITY_IF_NO_LATER_SPLIT)
    record = replace(YAHOO_VERIFICATION, fields=fields)
    report, _ = run(market, date(2024, 6, 6), date(2024, 6, 12), verification=record)
    assert len(report.rejected) == 2
    assert len(rows(market)) == 2
    assert all(c.price_basis is PriceBasis.RAW_NO_LATER_SPLIT for c in rows(market))


CLOSE_2026_10_09 = datetime(2026, 10, 9, 20, tzinfo=UTC)  # 16:00 New York


def run_received_at(market, received_at, processing):
    """Import 2026-10-09's bar, downloaded at `received_at`; the follow-up split request ends `processing` later."""
    clock = market["clock"] = ReplayClock(received_at)
    splits = action_series("nvda_splits_before.json")
    split_requests = []

    def fetch_splits(symbol):
        split_requests.append(symbol)
        if len(split_requests) == 2:
            clock.advance_by(processing)
        return splits.copy()

    def fetch_bars(symbol, **kwargs):
        data = frame()
        dates = data.index.date
        return data[(dates >= kwargs["start"]) & (dates < kwargs["end"])].copy()

    return import_bars("EQ_US_NVDA", Timeframe.D1, date(2026, 10, 9), date(2026, 10, 10), **market,
                       fetch_bars=fetch_bars, fetch_split_history=fetch_splits)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("received_at", "processing", "kept"),
    [
        (CLOSE_2026_10_09 - timedelta(seconds=2), timedelta(0), False),  # received before the close
        (CLOSE_2026_10_09 - timedelta(seconds=2), timedelta(seconds=3), False),  # processing crosses the close
        (CLOSE_2026_10_09, timedelta(0), True),  # received exactly at the close
        (CLOSE_2026_10_09 + timedelta(seconds=1), timedelta(seconds=3), True),  # received after the close
    ],
    ids=["before-close", "processing-crosses-close", "at-close", "after-close"],
)
def test_forming_is_decided_by_the_downloads_receipt_time(market, received_at, processing, kept):
    report = run_received_at(market, received_at, processing)
    stored = rows(market, date(2026, 10, 9), date(2026, 10, 10))
    assert report.dropped_forming == (0 if kept else 1)
    assert len(stored) == (1 if kept else 0)
    if kept:
        assert stored[0].received_at == received_at >= stored[0].end_time == CLOSE_2026_10_09
    else:
        assert report.covered is None


@pytest.mark.unit
def test_non_session_out_of_request_and_forming_rows_are_reported(market):
    data = frame().loc["2024-06-07":"2024-06-10"].copy()
    data.loc[pd.Timestamp("2024-06-08", tz="America/New_York")] = data.iloc[0]
    data.loc[pd.Timestamp("2024-06-06", tz="America/New_York")] = data.iloc[0]
    market["clock"] = ReplayClock(datetime(2024, 6, 10, 15, tzinfo=UTC))
    report, _ = run(market, date(2024, 6, 7), date(2024, 6, 11), data=data, filter_response=False)
    assert report.dropped_forming == 1 and len(report.rejected) == 2
    assert len(rows(market)) == 1
    assert rows(market)[0].end_time == datetime(2024, 6, 7, 20, tzinfo=UTC)


@pytest.mark.unit
def test_dated_symbol_changes_split_requests_and_end_is_exclusive(market):
    resolver = SymbolResolver()
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "OLD", date(1999, 1, 22), date(2021, 7, 12)))
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "NEW", date(2021, 7, 12), date(2021, 7, 20)))
    market["resolver"] = resolver
    report, calls = run(market)
    requests = [c for c in calls if c[0] == "bars"]
    assert [(r[1], r[2]["start"], r[2]["end"]) for r in requests] == [
        ("OLD", date(2021, 7, 1), date(2021, 7, 12)), ("NEW", date(2021, 7, 12), date(2021, 7, 20))]
    assert report.write.new_records == 12


@pytest.mark.unit
def test_daily_sessions_follow_calendar_dst_and_early_close(market):
    report, _ = run(market, date(2024, 11, 27), date(2024, 11, 30), backfill_latency=timedelta(seconds=2))
    candles = rows(market)
    assert report.write.new_records == 2
    assert candles[0].start_time == datetime(2024, 11, 27, 14, 30, tzinfo=UTC)
    assert candles[-1].end_time == datetime(2024, 11, 29, 18, tzinfo=UTC)
    assert all(c.available_from == c.end_time + timedelta(seconds=2) for c in candles)


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["nan", "negative-volume", "bad-ohlc", "missing-column", "naive-index", "duplicate"])
def test_bad_data_aborts_entire_write(market, bad):
    data = frame().loc["2021-07-01":"2021-07-19"].copy()
    if bad == "nan":
        data.iloc[-1, data.columns.get_loc("Close")] = float("nan")
    elif bad == "negative-volume":
        data.iloc[-1, data.columns.get_loc("Volume")] = -1
    elif bad == "bad-ohlc":
        data.iloc[-1, data.columns.get_loc("High")] = 1.0
    elif bad == "missing-column":
        data = data.drop(columns=["Volume"])
    elif bad == "naive-index":
        data.index = data.index.tz_localize(None)
    else:
        data = pd.concat([data, data.iloc[-1:]])
    with pytest.raises((ValueError, TypeError)):
        run(market, data=data, filter_response=False)
    assert rows(market) == []


@pytest.mark.unit
def test_negative_backfill_latency_is_refused_before_fetch(market):
    with pytest.raises(ValueError, match="latency"):
        run(market, backfill_latency=timedelta(seconds=-1))
    assert rows(market) == []


@pytest.mark.unit
def test_weekend_only_symbol_segment_needs_no_bar_fetch(market):
    resolver = SymbolResolver()
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "OLD", date(1999, 1, 22), date(2021, 7, 10)))
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "WEEKEND", date(2021, 7, 10), date(2021, 7, 12)))
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "NEW", date(2021, 7, 12), None))
    market["resolver"] = resolver
    report, calls = run(market)
    assert report.write.new_records == 12
    assert "WEEKEND" not in {c[1] for c in calls}


@pytest.mark.unit
def test_window_with_no_sessions_has_no_fetch_and_no_coverage(market):
    report, calls = run(market, date(2021, 7, 10), date(2021, 7, 12))
    assert report.write.new_records == 0 and report.covered is None
    assert calls == [] and rows(market) == []


@pytest.mark.integration
def test_live_daily_columns_match_recorded_contract():
    from investment_engine.market.importers.yfinance_bars import fetch_daily_bars

    bars = fetch_daily_bars("NVDA", start=date(2024, 6, 6), end=date(2024, 6, 12), interval="1d",
                           auto_adjust=False, actions=False, repair=False, back_adjust=False, prepost=False)
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(bars.columns)
    assert len(bars) == 4


@pytest.mark.unit
def test_bar_factors_use_the_importers_verification_record(market, monkeypatch):
    import investment_engine.market.importers.yfinance_bars as module

    record = replace(YAHOO_VERIFICATION)  # equal, but a distinct object
    original, seen = module.factor_from_history, []

    def spy(splits, d, download_date, verification):
        seen.append(verification)
        return original(splits, d, download_date, verification)

    monkeypatch.setattr(module, "factor_from_history", spy)
    run(market, verification=record)
    assert len(seen) == 12 and all(v is record for v in seen)


@pytest.mark.unit
def test_an_unverified_installed_yfinance_is_refused_before_fetching(market, monkeypatch):
    monkeypatch.setattr(bars_module, "version", installed("1.7.1"))

    def forbidden(*args, **kwargs):
        pytest.fail("an unverified yfinance must not fetch")

    with pytest.raises(VersionMismatch, match="1.7.1"):
        import_bars("EQ_US_NVDA", Timeframe.D1, date(2021, 7, 1), date(2021, 7, 20), **market,
                    fetch_bars=forbidden, fetch_split_history=forbidden)
    assert rows(market) == []


@pytest.mark.unit
def test_the_importers_read_the_installed_yfinance_version(monkeypatch):
    # The real check stays in place: the other tests replace only this lookup.
    from importlib.metadata import version

    monkeypatch.undo()  # remove the autouse stand-in
    assert actions_module.version is version and bars_module.version is version
