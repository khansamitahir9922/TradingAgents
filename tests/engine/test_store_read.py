"""Point-in-time reads and revision histories (ADR-009; docs/tasks/M1-11.md).

Every read is for one provider and names its view: latest, visible_at(T) by
availability, or recorded_by(T) by observation. Data is written through the
real MarketDataWriter.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
)
from investment_engine.money import Money

NVDA = "EQ_US_NVDA"
D1 = Timeframe.D1
MONDAY = date(2024, 6, 3)
MON_OPEN = datetime(2024, 6, 3, 13, 30, tzinfo=UTC)
MON_CLOSE = datetime(2024, 6, 3, 20, 0, tzinfo=UTC)
FRIDAY_2100 = datetime(2024, 6, 7, 21, 0, tzinfo=UTC)
WEEK_START, WEEK_END = datetime(2024, 6, 3, tzinfo=UTC), datetime(2024, 6, 8, tzinfo=UTC)


def utc(*parts) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def candle_obs(day: int = 3, close: str = "1150.0000", source: str = "yfinance", *,
               received_at: datetime, backfill: bool = True) -> CandleObservation:
    start, end = utc(2024, 6, day, 13, 30), utc(2024, 6, day, 20, 0)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=D1, start_time=start, end_time=end,
        open=Decimal("1150.0000"), high=Decimal("1170.0000"), low=Decimal("1140.0000"), close=Decimal(close),
        currency="USD", volume=Decimal("41000000"), state=BarState.CLOSED, source_version="1.7.0",
        price_basis=PriceBasis.RAW_AS_REPORTED, volume_basis=VolumeBasis.RAW_AS_REPORTED,
        event_time=end, received_at=received_at, processed_at=received_at,
        backfill_available_from=end if backfill else None,
    )


def action_obs(action_type=ActionType.DIVIDEND, ex: date = date(2024, 6, 11), source: str = "yfinance", *,
               received_at: datetime, amount: str = "0.0100", ratio: str = "10") -> ActionObservation:
    fields = {
        ActionType.DIVIDEND: {"ratio": None, "amount": Money(Decimal(amount), "USD"),
                              "amount_basis": AmountBasis.AS_REPORTED},
        ActionType.SPLIT: {"ratio": Decimal(ratio), "amount": None, "amount_basis": None},
    }[action_type]
    return ActionObservation(
        source=source, instrument_id=NVDA, currency="USD", exchange_timezone="America/New_York",
        action_type=action_type, ex_date=ex, new_symbol=None, source_version="1.7.0",
        received_at=received_at, processed_at=received_at,
        backfill_available_from=ex_date_start(ex, "America/New_York"), **fields,
    )


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "market"
    return MarketDataWriter(root), MarketDataReader(root)


@pytest.fixture
def friday_correction(store):
    """Monday's bar backfilled (seen Tuesday), then corrected on Friday at 21:00 UTC."""
    writer, reader = store
    writer.write_candles([candle_obs(received_at=utc(2024, 6, 4, 0, 0))], import_id="backfill-1")
    writer.write_candles([candle_obs(close="1151.0000", received_at=FRIDAY_2100)], import_id="correction-1")
    return reader


def revisions(candles) -> list[int]:
    return [c.revision for c in candles]


# ---------------------------------------------------------------- the Friday correction


@pytest.mark.unit
@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (MON_CLOSE, [1]),                         # visible from Monday's close
        (utc(2024, 6, 6, 20, 0), [1]),            # Thursday: the correction isn't known yet
        (FRIDAY_2100, [2]),                       # Friday 21:00: the correction is known
        (utc(2024, 6, 10), [2]),
        (MON_CLOSE - timedelta(seconds=1), []),   # before Monday's close: no bar at all
    ],
)
def test_visible_at_never_shows_a_correction_early(friday_correction, at, expected):
    got = friday_correction.candles_visible_at("yfinance", NVDA, D1, WEEK_START, WEEK_END, at)
    assert revisions(got) == expected


@pytest.mark.unit
def test_latest_and_full_history(friday_correction):
    [latest] = friday_correction.candles_latest("yfinance", NVDA, D1, WEEK_START, WEEK_END)
    assert (latest.revision, latest.close) == (2, Decimal("1151.0000"))
    history = friday_correction.candle_revision_history("yfinance", NVDA, D1, WEEK_START, WEEK_END)
    assert [(c.revision, c.close) for c in history] == [(1, Decimal("1150.0000")), (2, Decimal("1151.0000"))]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ((utc(2024, 6, 7), utc(2024, 6, 8)), [2]),   # Friday: only the correction became available
        ((utc(2024, 6, 3), utc(2024, 6, 4)), [1]),   # Monday: only the original
        ((utc(2024, 6, 4), utc(2024, 6, 7)), []),
    ],
)
def test_revisions_available_between(friday_correction, window, expected):
    got = friday_correction.candle_revisions_available_between("yfinance", NVDA, D1, *window)
    assert revisions(got) == expected


# ---------------------------------------------------------------- observation vs availability


@pytest.mark.unit
def test_recorded_by_uses_observation_and_visible_at_uses_availability(store):
    writer, reader = store
    writer.write_candles([candle_obs(received_at=utc(2026, 10, 10, 12, 0))], import_id="backfill-2026")
    assert reader.candles_recorded_by("yfinance", NVDA, D1, WEEK_START, WEEK_END, utc(2024, 6, 4)) == []
    [seen] = reader.candles_visible_at("yfinance", NVDA, D1, WEEK_START, WEEK_END, utc(2024, 6, 4))
    assert seen.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED
    assert reader.candles_recorded_by("yfinance", NVDA, D1, WEEK_START, WEEK_END, utc(2026, 10, 11))[0].revision == 1


@pytest.mark.unit
def test_recorded_by_follows_each_revisions_receipt(friday_correction):
    assert revisions(friday_correction.candles_recorded_by("yfinance", NVDA, D1, WEEK_START, WEEK_END,
                                                          utc(2024, 6, 5))) == [1]
    assert revisions(friday_correction.candles_recorded_by("yfinance", NVDA, D1, WEEK_START, WEEK_END,
                                                          FRIDAY_2100)) == [2]


# ---------------------------------------------------------------- ranges, ordering, values


@pytest.mark.unit
def test_bar_ranges_are_half_open_and_sorted(store):
    writer, reader = store
    seen = utc(2024, 6, 10)
    writer.write_candles([candle_obs(day, received_at=seen) for day in (7, 3, 5, 4, 6)], import_id="week")
    got = reader.candles_latest("yfinance", NVDA, D1, utc(2024, 6, 4, 13, 30), utc(2024, 6, 6, 13, 30))
    assert [c.start_time.day for c in got] == [4, 5]          # start inclusive, end exclusive
    assert [c.start_time.day for c in reader.candles_latest("yfinance", NVDA, D1, WEEK_START, WEEK_END)] == [3, 4, 5, 6, 7]


@pytest.mark.unit
def test_values_come_back_as_exact_contract_objects(friday_correction):
    [c] = friday_correction.candles_latest("yfinance", NVDA, D1, WEEK_START, WEEK_END)
    assert c.close == Decimal("1151.0000") and c.close.as_tuple().exponent == -4
    assert c.start_time == MON_OPEN and c.start_time.tzinfo is UTC
    assert c.timeframe is Timeframe.D1 and c.price_basis is PriceBasis.RAW_AS_REPORTED


@pytest.mark.unit
def test_an_empty_store_returns_empty_lists(store):
    _, reader = store
    assert reader.candles_latest("yfinance", NVDA, D1, WEEK_START, WEEK_END) == []
    assert reader.actions_latest("yfinance", NVDA, date(2024, 1, 1), date(2025, 1, 1)) == []


@pytest.mark.unit
@pytest.mark.parametrize("method", ["candles_visible_at", "candles_recorded_by"])
def test_a_naive_time_is_refused(friday_correction, method):
    with pytest.raises(ValueError):
        getattr(friday_correction, method)("yfinance", NVDA, D1, WEEK_START, WEEK_END, datetime(2024, 6, 4))
    with pytest.raises(ValueError):
        friday_correction.candles_latest("yfinance", NVDA, D1, datetime(2024, 6, 3), WEEK_END)


@pytest.mark.unit
def test_there_is_no_default_view(store):
    _, reader = store
    for name in ("get", "get_candles", "candles", "actions", "read"):
        assert not hasattr(reader, name), name


# ---------------------------------------------------------------- providers stay separate


@pytest.mark.unit
def test_each_provider_is_read_on_its_own(store):
    writer, reader = store
    seen = utc(2024, 6, 4)
    writer.write_candles([candle_obs(received_at=seen)], import_id="y1")
    writer.write_candles([candle_obs(close="1149.0000", source="testvendor", received_at=seen)], import_id="t1")
    writer.write_candles([candle_obs(close="1148.0000", source="testvendor", received_at=FRIDAY_2100)], import_id="t2")
    yf = reader.candle_revision_history("yfinance", NVDA, D1, WEEK_START, WEEK_END)
    tv = reader.candle_revision_history("testvendor", NVDA, D1, WEEK_START, WEEK_END)
    assert {c.source for c in yf} == {"yfinance"} and revisions(yf) == [1]
    assert {c.source for c in tv} == {"testvendor"} and revisions(tv) == [1, 2]
    assert reader.candles_latest("yfinance", NVDA, D1, WEEK_START, WEEK_END)[0].close == Decimal("1150.0000")


# ---------------------------------------------------------------- corporate actions


@pytest.mark.unit
def test_action_views_mirror_the_candle_views(store):
    # A historical download (backfill) on 2026-10-10, corrected by a later import on 2026-10-11.
    writer, reader = store
    backfilled, corrected = utc(2026, 10, 10, 12, 0), utc(2026, 10, 11, 9, 0)
    writer.write_corporate_actions([action_obs(received_at=backfilled)], import_id="a1")
    writer.write_corporate_actions([action_obs(amount="0.0200", received_at=corrected)], import_id="a2")
    window = (date(2024, 6, 1), date(2024, 7, 1))
    ex_start = ex_date_start(date(2024, 6, 11), "America/New_York")
    assert [a.revision for a in reader.actions_visible_at("yfinance", NVDA, *window, ex_start - timedelta(seconds=1))] == []
    assert [a.revision for a in reader.actions_visible_at("yfinance", NVDA, *window, ex_start)] == [1]
    assert [a.revision for a in reader.actions_visible_at("yfinance", NVDA, *window, corrected)] == [2]
    assert [a.amount.amount for a in reader.actions_latest("yfinance", NVDA, *window)] == [Decimal("0.0200")]
    assert reader.actions_recorded_by("yfinance", NVDA, *window, utc(2024, 6, 12)) == []
    assert [a.revision for a in reader.actions_recorded_by("yfinance", NVDA, *window, backfilled)] == [1]
    assert [a.revision for a in reader.action_revision_history("yfinance", NVDA, *window)] == [1, 2]
    assert [a.revision for a in reader.action_revisions_available_between(
        "yfinance", NVDA, utc(2026, 10, 11), utc(2026, 10, 12))] == [2]


@pytest.mark.unit
def test_a_backfilled_split_is_visible_from_the_start_of_its_ex_date(store):
    writer, reader = store
    ex = date(2024, 6, 10)
    writer.write_corporate_actions([action_obs(ActionType.SPLIT, ex, received_at=utc(2026, 10, 10))], import_id="s1")
    start = ex_date_start(ex, "America/New_York")
    window = (date(2024, 6, 1), date(2024, 7, 1))
    assert reader.actions_visible_at("yfinance", NVDA, *window, start - timedelta(microseconds=1)) == []
    [split] = reader.actions_visible_at("yfinance", NVDA, *window, start)
    assert split.ratio == Decimal("10")


@pytest.mark.unit
def test_the_types_filter(store):
    writer, reader = store
    seen = utc(2026, 10, 10)
    writer.write_corporate_actions([action_obs(ActionType.SPLIT, date(2024, 6, 10), received_at=seen),
                                    action_obs(ActionType.DIVIDEND, date(2024, 6, 11), received_at=seen)],
                                   import_id="mix")
    window = (date(2024, 1, 1), date(2025, 1, 1))
    assert [a.action_type for a in reader.actions_latest("yfinance", NVDA, *window, types={ActionType.SPLIT})] == [
        ActionType.SPLIT
    ]
    assert len(reader.actions_latest("yfinance", NVDA, *window)) == 2


@pytest.mark.unit
@pytest.mark.parametrize("split_first", [True, False])
def test_a_same_day_split_and_dividend_always_come_back_split_first(store, split_first):
    writer, reader = store
    ex, seen = date(2024, 6, 10), utc(2026, 10, 10)
    split = action_obs(ActionType.SPLIT, ex, received_at=seen)
    dividend = action_obs(ActionType.DIVIDEND, ex, received_at=seen)
    first, second = (split, dividend) if split_first else (dividend, split)
    writer.write_corporate_actions([first], import_id="first")
    writer.write_corporate_actions([second], import_id="second")
    window = (date(2024, 6, 1), date(2024, 7, 1))
    expected = [ActionType.SPLIT, ActionType.DIVIDEND]
    assert [a.action_type for a in reader.actions_latest("yfinance", NVDA, *window)] == expected
    assert [a.action_type for a in reader.action_revision_history("yfinance", NVDA, *window)] == expected
    start = ex_date_start(ex, "America/New_York")
    assert [a.action_type for a in reader.action_revisions_available_between(
        "yfinance", NVDA, start, start + timedelta(seconds=1))] == expected
