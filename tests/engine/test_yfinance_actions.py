"""Corporate-action imports use verified history, exact money and append-only revisions."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from investment_engine.clock import ReplayClock
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.importers.yahoo_semantics import (
    YAHOO_VERIFICATION,
    FieldBlocked,
    FieldKey,
    SplitHistoryMismatch,
    Transformation,
    load_recording,
)
from investment_engine.market.importers.yfinance_actions import ActionImportReport, import_actions
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.market.symbols import SymbolMapping, SymbolResolver
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)

FIXTURES = Path(__file__).parent / "fixtures" / "yfinance"
NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)


def series(name):
    rec = load_recording(FIXTURES / name)
    return pd.Series([row[1] for row in rec.rows], index=pd.to_datetime([row[0] for row in rec.rows], utc=True))


@pytest.fixture
def setup(tmp_path):
    conn = open_operational_db(tmp_path / "operational.sqlite3")
    apply_schema(conn)
    instruments = SqliteInstrumentRepository(conn)
    instruments.add(Instrument("EQ_US_NVDA", AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                               InstrumentStatus.ACTIVE, date(1999, 1, 22), None))
    resolver = SqliteSymbolResolver(conn)
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "RENAMED", date(1999, 1, 22), None))
    root = tmp_path / "market[x]"
    yield {"clock": ReplayClock(NOW), "resolver": resolver, "instruments": instruments,
           "writer": MarketDataWriter(root)}, MarketDataReader(root)
    conn.close()


def run(setup, *, splits=None, dividends=None, verification=YAHOO_VERIFICATION):
    args, reader = setup
    before = series("nvda_splits_before.json") if splits is None else splits
    divs = series("nvda_dividends.json") if dividends is None else dividends
    calls = []

    def fetch_splits(symbol):
        calls.append(("splits", symbol))
        return before.copy()

    def fetch_dividends(symbol):
        calls.append(("dividends", symbol))
        return divs.copy()

    report = import_actions("EQ_US_NVDA", **args, fetch_split_history=fetch_splits,
                            fetch_dividends=fetch_dividends, verification=verification)
    return report, reader.actions_latest("yfinance", "EQ_US_NVDA", date(2019, 1, 1), date(2027, 1, 1)), calls


@pytest.mark.unit
def test_fixture_import_declared_amounts_range_count_and_symbol(setup):
    report, actions, calls = run(setup)
    assert isinstance(report, ActionImportReport)
    assert report.write.new_records == 33
    assert report.skipped_before_verified_from == 29
    assert calls == [("splits", "RENAMED"), ("dividends", "RENAMED"), ("splits", "RENAMED")]
    splits = [(a.ex_date, a.ratio) for a in actions if a.action_type is ActionType.SPLIT]
    assert tuple(splits) == YAHOO_VERIFICATION.cited_splits
    divs = {a.ex_date: a for a in actions if a.action_type is ActionType.DIVIDEND}
    assert len(divs) == 31
    assert divs[date(2021, 6, 9)].amount.amount == Decimal("0.1600")
    assert divs[date(2024, 3, 5)].amount.amount == Decimal("0.0400")
    for a in actions:
        assert a.source == "yfinance" and a.source_version == "1.7.0"
        assert a.currency == "USD" and a.exchange_timezone == "America/New_York"
        assert a.revision == 1 and a.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED
        assert a.available_from == ex_date_start(a.ex_date, a.exchange_timezone)
        assert a.received_at == NOW and a.processed_at >= a.received_at
    assert all(a.amount_basis is AmountBasis.RECONSTRUCTED_FROM_SPLIT_ADJUSTED for a in divs.values())


@pytest.mark.unit
def test_second_import_writes_nothing(setup):
    run(setup)
    before = set(setup[0]["writer"].root.rglob("*.parquet"))
    report, _, _ = run(setup)
    assert (report.write.new_records, report.write.new_revisions, report.write.unchanged) == (0, 0, 33)
    assert set(setup[0]["writer"].root.rglob("*.parquet")) == before


@pytest.mark.unit
def test_changed_dividend_becomes_observed_revision_without_backdating(setup):
    run(setup)
    setup[0]["clock"].advance_by(timedelta(hours=1))
    divs = series("nvda_dividends.json")
    divs.iloc[-1] = 0.26
    report, actions, _ = run(setup, dividends=divs)
    assert (report.write.new_revisions, report.write.unchanged) == (1, 32)
    latest = next(a for a in actions if a.ex_date == date(2026, 9, 10))
    assert latest.revision == 2 and latest.amount.amount == Decimal("0.2600")
    assert latest.availability_basis is AvailabilityBasis.OBSERVED
    assert latest.available_from == NOW + timedelta(hours=1)
    old = setup[1].actions_visible_at("yfinance", "EQ_US_NVDA", date(2026, 9, 10), date(2026, 9, 11), NOW)
    assert old[0].revision == 1 and old[0].amount.amount == Decimal("0.2500")


@pytest.mark.unit
@pytest.mark.parametrize("change", ["missing", "extra", "ratio", "date"])
def test_bad_in_range_history_writes_nothing(setup, change):
    splits = series("nvda_splits_before.json")
    if change == "missing":
        splits = splits.iloc[:-1]
    elif change == "extra":
        splits.loc[pd.Timestamp("2025-01-02", tz="America/New_York")] = 2.0
    elif change == "ratio":
        splits.iloc[-1] = 11.0
    else:
        index = list(splits.index)
        index[-1] += timedelta(days=1)
        splits.index = index
    with pytest.raises(SplitHistoryMismatch):
        run(setup, splits=splits)
    assert not list(setup[0]["writer"].root.rglob("*.parquet"))


@pytest.mark.unit
def test_pre_range_splits_are_not_compared(setup):
    splits = series("nvda_splits_before.json")
    index = list(splits.index)
    index[1] += timedelta(days=5)
    splits.index = index
    report, actions, _ = run(setup, splits=splits)
    assert report.skipped_before_verified_from == 29 and len(actions) == 33


@pytest.mark.unit
def test_mid_run_history_change_aborts_before_any_write(setup):
    splits = series("nvda_splits_before.json")
    histories = iter([splits, splits.iloc[:-1]])
    with pytest.raises(SplitHistoryMismatch, match="mid-run"):
        import_actions("EQ_US_NVDA", **setup[0], fetch_split_history=lambda symbol: next(histories),
                       fetch_dividends=lambda symbol: series("nvda_dividends.json"))
    assert not list(setup[0]["writer"].root.rglob("*.parquet"))


@pytest.mark.unit
def test_unsupported_instrument_is_refused_before_fetch(setup):
    def forbidden(symbol):
        pytest.fail("must not fetch")

    with pytest.raises(ValueError, match="instrument"):
        import_actions("EQ_US_OTHER", **setup[0], fetch_split_history=forbidden, fetch_dividends=forbidden)


@pytest.mark.unit
@pytest.mark.parametrize("field", [FieldKey.SPLIT_RATIO, FieldKey.DIVIDEND_AMOUNT])
def test_blocked_action_field_refused_before_fetch(setup, field):
    fields = dict(YAHOO_VERIFICATION.fields)
    fields[field] = replace(fields[field], transformation=Transformation.BLOCKED)
    record = replace(YAHOO_VERIFICATION, fields=fields)
    with pytest.raises(FieldBlocked):
        run(setup, verification=record)
    assert not list(setup[0]["writer"].root.rglob("*.parquet"))


@pytest.mark.unit
def test_no_later_split_exception_rejects_earlier_dividend(setup):
    fields = dict(YAHOO_VERIFICATION.fields)
    fields[FieldKey.DIVIDEND_AMOUNT] = replace(fields[FieldKey.DIVIDEND_AMOUNT],
                                              transformation=Transformation.IDENTITY_IF_NO_LATER_SPLIT)
    with pytest.raises(FieldBlocked):
        run(setup, verification=replace(YAHOO_VERIFICATION, fields=fields))
    assert not list(setup[0]["writer"].root.rglob("*.parquet"))


@pytest.mark.unit
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1])
def test_invalid_dividend_aborts_entire_import(setup, bad):
    divs = series("nvda_dividends.json")
    divs.iloc[-1] = bad
    with pytest.raises(ValueError):
        run(setup, dividends=divs)
    assert not list(setup[0]["writer"].root.rglob("*.parquet"))


@pytest.mark.unit
def test_invalid_action_timestamp_is_not_assumed_utc(setup):
    divs = series("nvda_dividends.json")
    divs.index = divs.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        run(setup, dividends=divs)
    assert not list(setup[0]["writer"].root.rglob("*.parquet"))


@pytest.mark.unit
def test_empty_dividend_response_is_reported_as_failure(setup):
    with pytest.raises(ValueError, match="empty dividend"):
        run(setup, dividends=series("nvda_dividends.json").iloc[:0])
    assert not list(setup[0]["writer"].root.rglob("*.parquet"))


@pytest.mark.unit
def test_current_symbol_uses_exchange_date_near_utc_midnight(setup):
    resolver = SymbolResolver()
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "OLD", date(1999, 1, 22), date(2026, 10, 13)))
    resolver.add(SymbolMapping("EQ_US_NVDA", "yfinance", "NEW", date(2026, 10, 13), None))
    setup[0]["resolver"] = resolver
    # UTC October 13 is still October 12 in New York.
    setup[0]["clock"].advance_to(datetime(2026, 10, 13, 1, tzinfo=UTC))
    _, _, calls = run(setup)
    assert {symbol for _, symbol in calls} == {"OLD"}


@pytest.mark.integration
def test_live_full_history_call_is_not_date_filtered():
    from investment_engine.market.importers.yahoo_semantics import series_values
    from investment_engine.market.importers.yfinance_actions import fetch_full_splits

    values = series_values(fetch_full_splits("NVDA"), "America/New_York")
    assert any(d < date(2019, 1, 1) for d, _ in values)
    assert (date(2024, 6, 10), Decimal("10")) in values


@pytest.mark.unit
def test_dividend_factors_use_the_importers_verification_record(setup, monkeypatch):
    import investment_engine.market.importers.yfinance_actions as module

    record = replace(YAHOO_VERIFICATION)  # equal, but a distinct object
    original, seen = module.factor_from_history, []

    def spy(splits, d, download_date, verification):
        seen.append(verification)
        return original(splits, d, download_date, verification)

    monkeypatch.setattr(module, "factor_from_history", spy)
    run(setup, verification=record)
    assert len(seen) == 31 and all(v is record for v in seen)
