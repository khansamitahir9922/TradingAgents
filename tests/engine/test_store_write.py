"""Append-only market-data writes (Law 8; ADR-009; docs/tasks/M1-10.md).

The writer is the one place that assigns revision numbers. A first-seen
record is revision 1; identical values change nothing; changed values become
the next revision, always OBSERVED and available from their own observation
time, so a correction is never backdated. Files are only ever created.
"""

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
    WriteResult,
)
from investment_engine.money import Money

START = datetime(2024, 6, 3, 13, 30, tzinfo=UTC)
END = datetime(2024, 6, 3, 20, 0, tzinfo=UTC)
FETCHED = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)  # a later import, after the backfill
EX_DATE = date(2024, 6, 10)


def candle_obs(**changes) -> CandleObservation:
    base = CandleObservation(
        source="yfinance",
        instrument_id="EQ_US_NVDA",
        timeframe=Timeframe.D1,
        start_time=START,
        end_time=END,
        open=Decimal("1150.0000"),
        high=Decimal("1166.7500"),
        low=Decimal("1145.0000"),
        close=Decimal("1150.0000"),
        currency="USD",
        volume=Decimal("41000000"),
        state=BarState.CLOSED,
        source_version="1.7.0",
        price_basis=PriceBasis.RAW_RECONSTRUCTED_FROM_SPLIT_ADJUSTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED,
        event_time=END,
        received_at=FETCHED,
        processed_at=FETCHED,
        backfill_available_from=END,
    )
    return replace(base, **changes) if changes else base


def dividend_obs(**changes) -> ActionObservation:
    base = ActionObservation(
        source="yfinance",
        instrument_id="EQ_US_NVDA",
        currency="USD",
        exchange_timezone="America/New_York",
        action_type=ActionType.DIVIDEND,
        ex_date=EX_DATE,
        ratio=None,
        amount=Money(Decimal("0.0100"), "USD"),
        amount_basis=AmountBasis.RECONSTRUCTED_FROM_SPLIT_ADJUSTED,
        new_symbol=None,
        source_version="1.7.0",
        received_at=FETCHED,
        processed_at=FETCHED,
        backfill_available_from=ex_date_start(EX_DATE, "America/New_York"),
    )
    return replace(base, **changes) if changes else base


def stored(root: Path, kind: str) -> list[dict]:
    """Every stored row, read straight from the Parquet files (not through the writer)."""
    rows = []
    for path in sorted((root / kind).rglob("*.parquet")):
        rows.extend(pq.read_table(path).to_pylist())
    return rows


def digests(root: Path) -> dict[str, tuple[str, int]]:
    return {
        str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in root.rglob("*") if p.is_file()
    }


@pytest.fixture
def writer(tmp_path) -> MarketDataWriter:
    return MarketDataWriter(tmp_path / "market")


# ---------------------------------------------------------------- candles


@pytest.mark.unit
def test_a_first_seen_historical_bar_is_backfill_revision_one(writer):
    result = writer.write_candles([candle_obs()], import_id="import-1")
    assert result == WriteResult(new_records=1, new_revisions=0, unchanged=0, import_id="import-1")
    [row] = stored(writer.root, "candles")
    assert row["revision"] == 1
    assert row["availability_basis"] == "BACKFILL_ASSUMED"
    assert row["available_from"] == END
    assert row["import_id"] == "import-1"


@pytest.mark.unit
def test_a_first_seen_live_bar_is_observed(writer):
    writer.write_candles([candle_obs(backfill_available_from=None)], import_id="live-1")
    [row] = stored(writer.root, "candles")
    assert (row["revision"], row["availability_basis"], row["available_from"]) == (1, "OBSERVED", FETCHED)


@pytest.mark.unit
def test_the_file_layout_puts_the_provider_first(writer):
    writer.write_candles([candle_obs()], import_id="import-1")
    expected = writer.root / "candles" / "source=yfinance" / "instrument_id=EQ_US_NVDA" / "timeframe=D1" / "import=import-1.parquet"
    assert expected.is_file()
    assert [p for p in writer.root.rglob("*") if p.is_file()] == [expected]


@pytest.mark.unit
def test_an_identical_rewrite_changes_nothing(writer):
    writer.write_candles([candle_obs()], import_id="import-1")
    before = digests(writer.root)
    result = writer.write_candles([candle_obs(received_at=LATER, processed_at=LATER, source_version="1.8.0")],
                                  import_id="import-2")
    assert result == WriteResult(new_records=0, new_revisions=0, unchanged=1, import_id="import-2")
    assert digests(writer.root) == before


@pytest.mark.unit
def test_a_changed_value_is_an_observed_correction_never_backdated(writer):
    writer.write_candles([candle_obs()], import_id="import-1")
    first_files = digests(writer.root)
    # The correction arrives with a backfill time attached; it must be ignored.
    result = writer.write_candles(
        [candle_obs(close=Decimal("1151.0000"), received_at=LATER, processed_at=LATER)], import_id="import-2"
    )
    assert result == WriteResult(new_records=0, new_revisions=1, unchanged=0, import_id="import-2")
    rows = sorted(stored(writer.root, "candles"), key=lambda r: r["revision"])
    assert [r["revision"] for r in rows] == [1, 2]
    assert rows[0]["close"] == Decimal("1150.0000")                     # revision 1 kept, unchanged
    assert rows[1]["close"] == Decimal("1151.0000")
    assert rows[1]["availability_basis"] == "OBSERVED"
    assert rows[1]["available_from"] == LATER == rows[1]["received_at"]
    for name, digest in first_files.items():                            # existing files untouched
        assert digests(writer.root)[name] == digest


@pytest.mark.unit
def test_each_further_change_is_the_next_revision(writer):
    writer.write_candles([candle_obs()], import_id="i1")
    writer.write_candles([candle_obs(close=Decimal("1151.0000"), received_at=LATER)], import_id="i2")
    later = LATER + timedelta(days=3)
    writer.write_candles([candle_obs(close=Decimal("1152.0000"), received_at=later)], import_id="i3")
    revisions = sorted((r["revision"], r["close"]) for r in stored(writer.root, "candles"))
    assert revisions == [(1, Decimal("1150.0000")), (2, Decimal("1151.0000")), (3, Decimal("1152.0000"))]


@pytest.mark.unit
@pytest.mark.parametrize(
    "changes",
    [
        {"volume": Decimal("41000001")},
        {"price_basis": PriceBasis.RAW_AS_REPORTED},
        {"volume_basis": VolumeBasis.RAW_NO_LATER_SPLIT},
    ],
)
def test_volume_and_basis_changes_are_corrections_too(writer, changes):
    writer.write_candles([candle_obs()], import_id="i1")
    result = writer.write_candles([candle_obs(received_at=LATER, **changes)], import_id="i2")
    assert result.new_revisions == 1


@pytest.mark.unit
def test_two_providers_never_correct_each_other(writer):
    writer.write_candles([candle_obs()], import_id="y1")
    result = writer.write_candles([candle_obs(source="testvendor", close=Decimal("1149.0000"))], import_id="t1")
    assert result.new_records == 1 and result.new_revisions == 0
    writer.write_candles([candle_obs(source="testvendor", close=Decimal("1148.0000"), received_at=LATER)],
                         import_id="t2")
    by_source = {}
    for row in stored(writer.root, "candles"):
        by_source.setdefault(row["source"], []).append(row["revision"])
    assert sorted(by_source["yfinance"]) == [1]
    assert sorted(by_source["testvendor"]) == [1, 2]


@pytest.mark.unit
def test_a_bad_record_in_a_batch_writes_nothing(writer):
    with pytest.raises(ValueError):
        writer.write_candles([candle_obs(), candle_obs(start_time=START + timedelta(days=1),
                                                       end_time=END + timedelta(days=1),
                                                       event_time=END + timedelta(days=1),
                                                       backfill_available_from=END + timedelta(days=1),
                                                       close=Decimal("1150.00001"))],
                             import_id="i1")
    assert not writer.root.exists() or not any(p.is_file() for p in writer.root.rglob("*"))


@pytest.mark.unit
@pytest.mark.parametrize(
    "changes",
    [
        {"state": BarState.FORMING, "event_time": END - timedelta(hours=1),
         "backfill_available_from": END - timedelta(hours=1)},
        {"close": Decimal("1150.00001")},
        {"source": "resampled:yfinance"},
    ],
)
def test_forming_unquantized_and_non_provider_bars_are_refused(writer, changes):
    with pytest.raises(ValueError):
        writer.write_candles([candle_obs(**changes)], import_id="i1")


@pytest.mark.unit
def test_decimals_round_trip_exactly(writer):
    writer.write_candles([candle_obs(open=Decimal("0.0001"), low=Decimal("0.0001"), close=Decimal("1.2345"),
                                     high=Decimal("99999.9999"), volume=Decimal("123456789012"))],
                         import_id="i1")
    [row] = stored(writer.root, "candles")
    assert (row["open"], row["close"], row["high"], row["volume"]) == (
        Decimal("0.0001"), Decimal("1.2345"), Decimal("99999.9999"), Decimal("123456789012"))


@pytest.mark.unit
def test_an_existing_file_is_never_overwritten(writer):
    writer.write_candles([candle_obs()], import_id="same")
    before = digests(writer.root)
    with pytest.raises(FileExistsError):
        writer.write_candles([candle_obs(close=Decimal("1151.0000"), received_at=LATER)], import_id="same")
    assert digests(writer.root) == before
    assert not [p for p in writer.root.rglob("*") if p.name.endswith(".tmp")]


@pytest.mark.unit
@pytest.mark.parametrize("import_id", ["", "a/b", "..", "has space", "x" * 101])
def test_an_import_id_must_be_a_safe_file_name(writer, import_id):
    with pytest.raises(ValueError):
        writer.write_candles([candle_obs()], import_id=import_id)


@pytest.mark.unit
def test_two_observations_of_one_bar_in_one_batch_are_ordered(writer):
    result = writer.write_candles(
        [candle_obs(), candle_obs(close=Decimal("1151.0000"), received_at=LATER)], import_id="i1"
    )
    assert result == WriteResult(new_records=1, new_revisions=1, unchanged=0, import_id="i1")
    assert sorted(r["revision"] for r in stored(writer.root, "candles")) == [1, 2]


# ---------------------------------------------------------------- corporate actions


@pytest.mark.unit
def test_a_first_seen_dividend_is_backfill_from_the_ex_date_start(writer):
    writer.write_corporate_actions([dividend_obs()], import_id="a1")
    [row] = stored(writer.root, "corporate_actions")
    assert row["revision"] == 1 and row["availability_basis"] == "BACKFILL_ASSUMED"
    assert row["available_from"] == datetime(2024, 6, 10, 4, 0, tzinfo=UTC)
    assert row["amount"] == Decimal("0.0100") and row["amount_currency"] == "USD"
    path = writer.root / "corporate_actions" / "source=yfinance" / "instrument_id=EQ_US_NVDA" / "import=a1.parquet"
    assert path.is_file()


@pytest.mark.unit
def test_a_changed_dividend_amount_is_an_observed_correction(writer):
    writer.write_corporate_actions([dividend_obs()], import_id="a1")
    result = writer.write_corporate_actions(
        [dividend_obs(amount=Money(Decimal("0.0200"), "USD"), received_at=LATER, processed_at=LATER)],
        import_id="a2",
    )
    assert result.new_revisions == 1
    rows = sorted(stored(writer.root, "corporate_actions"), key=lambda r: r["revision"])
    assert [(r["revision"], r["amount"]) for r in rows] == [(1, Decimal("0.0100")), (2, Decimal("0.0200"))]
    assert rows[1]["availability_basis"] == "OBSERVED" and rows[1]["available_from"] == LATER


@pytest.mark.unit
def test_an_identical_action_rewrite_changes_nothing(writer):
    writer.write_corporate_actions([dividend_obs()], import_id="a1")
    result = writer.write_corporate_actions([dividend_obs(received_at=LATER)], import_id="a2")
    assert result.unchanged == 1 and result.new_records == result.new_revisions == 0


@pytest.mark.unit
def test_two_providers_actions_never_correct_each_other(writer):
    writer.write_corporate_actions([dividend_obs()], import_id="y1")
    result = writer.write_corporate_actions(
        [dividend_obs(source="testvendor", amount=Money(Decimal("0.0200"), "USD"))], import_id="t1"
    )
    assert result.new_records == 1 and result.new_revisions == 0


@pytest.mark.unit
def test_split_ratios_round_trip_and_excess_precision_is_refused(writer):
    split = dividend_obs(action_type=ActionType.SPLIT, ratio=Decimal("1.5"), amount=None, amount_basis=None)
    writer.write_corporate_actions([split], import_id="s1")
    [row] = stored(writer.root, "corporate_actions")
    assert row["ratio"] == Decimal("1.5") and row["amount"] is None
    with pytest.raises(ValueError):
        writer.write_corporate_actions([replace(split, ex_date=date(2024, 7, 1),
                                                backfill_available_from=ex_date_start(date(2024, 7, 1), "America/New_York"),
                                                ratio=Decimal("1.0000000000001"))], import_id="s2")


# ---------------------------------------------------------------- self-review fixes


@pytest.mark.unit
@pytest.mark.parametrize("instrument_id", ["../../../../../ESCAPED", "../../../ESCAPED", "EQ_US_NVDA/../../x"])
def test_a_crafted_instrument_id_cannot_write_outside_the_store(tmp_path, instrument_id):
    # Batch-2 self-review: before the fix, '../../../../../ESCAPED' wrote a
    # Parquet file outside the store's root folder.
    root = tmp_path / "store" / "market"
    with pytest.raises(ValueError):
        MarketDataWriter(root).write_candles([candle_obs(instrument_id=instrument_id)], import_id="probe")
    assert list(tmp_path.rglob("*.parquet")) == []


@pytest.mark.unit
def test_a_correction_cannot_be_received_before_what_it_corrects(writer):
    # Batch-2 self-review: revisions are observed in time order; a "correction"
    # received before the stored revision would put the history out of order.
    writer.write_candles([candle_obs(received_at=LATER)], import_id="i1")
    with pytest.raises(ValueError):
        writer.write_candles([candle_obs(close=Decimal("1151.0000"), received_at=LATER - timedelta(hours=1))],
                             import_id="i2")
    assert [r["revision"] for r in stored(writer.root, "candles")] == [1]
