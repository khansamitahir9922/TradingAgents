"""The Candle contract: provider identity, field bases and availability (docs/tasks/M1-08.md).

Each numbered rule from the spec has a passing case and a failing case.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.candles import (
    BarState,
    Candle,
    PriceBasis,
    Timeframe,
    VolumeBasis,
)

START = datetime(2024, 6, 3, 13, 30, tzinfo=UTC)
END = datetime(2024, 6, 3, 20, 0, tzinfo=UTC)
FETCHED = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def bar(**changes) -> Candle:
    base = Candle(
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
        import_id="import-1",
        event_time=END,
        received_at=FETCHED,
        processed_at=FETCHED,
        revision=1,
        available_from=END,
        availability_basis=AvailabilityBasis.BACKFILL_ASSUMED,
    )
    return replace(base, **changes) if changes else base


def correction(**changes) -> Candle:
    """A valid revision 2: observed later, available only from its observation."""
    seen = datetime(2024, 6, 7, 21, 0, tzinfo=UTC)
    values = {
        "revision": 2,
        "close": Decimal("1151.0000"),
        "received_at": seen,
        "processed_at": seen,
        "available_from": seen,
        "availability_basis": AvailabilityBasis.OBSERVED,
    }
    values.update(changes)
    return bar(**values)


@pytest.mark.unit
def test_a_valid_backfilled_bar_and_a_valid_correction():
    assert bar().revision == 1
    assert correction().revision == 2


# ---------------------------------------------------------------- rule 1: aware UTC, start < end


@pytest.mark.unit
@pytest.mark.parametrize("field", ["start_time", "end_time", "event_time", "received_at", "processed_at", "available_from"])
def test_rule1_datetimes_must_be_aware(field):
    naive = getattr(bar(), field).replace(tzinfo=None)
    with pytest.raises(ValueError):
        bar(**{field: naive})


@pytest.mark.unit
def test_rule1_datetimes_must_be_utc_not_merely_aware():
    new_york = END.astimezone(ZoneInfo("America/New_York"))
    assert new_york == END
    with pytest.raises(ValueError):
        bar(end_time=new_york, event_time=new_york, available_from=new_york)


@pytest.mark.unit
@pytest.mark.parametrize("start", [END, END + timedelta(minutes=1)])
def test_rule1_start_must_precede_end(start):
    with pytest.raises(ValueError):
        bar(start_time=start)


# ---------------------------------------------------------------- rule 2: positive prices, OHLC order, volume


@pytest.mark.unit
@pytest.mark.parametrize(
    "changes",
    [
        {"low": Decimal("1151.0000")},                                   # low above the close and open
        {"high": Decimal("1149.0000")},                                  # high below the close and open
        {"low": Decimal("1170.0000"), "high": Decimal("1160.0000")},     # low above high
        {"open": Decimal("0"), "low": Decimal("0")},                     # zero price
        {"open": Decimal("-1"), "low": Decimal("-1")},                   # negative price
        {"volume": Decimal("-1")},                                       # negative volume
    ],
)
def test_rule2_prices_and_volume_are_sane(changes):
    with pytest.raises(ValueError):
        bar(**changes)


@pytest.mark.unit
def test_rule2_a_flat_bar_and_zero_volume_are_allowed():
    flat = Decimal("100.0000")
    assert bar(open=flat, high=flat, low=flat, close=flat, volume=Decimal("0")).volume == 0


@pytest.mark.unit
@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
def test_rule2_numbers_must_be_decimals(field):
    with pytest.raises(TypeError):
        bar(**{field: float(getattr(bar(), field))})


# ---------------------------------------------------------------- rule 3: values already at their quantum


@pytest.mark.unit
def test_rule3_extra_price_precision_is_refused_not_rounded():
    with pytest.raises(ValueError):
        bar(close=Decimal("1150.00001"))


@pytest.mark.unit
def test_rule3_fractional_volume_is_refused():
    with pytest.raises(ValueError):
        bar(volume=Decimal("41000000.5"))


@pytest.mark.unit
def test_rule3_fewer_decimal_places_are_fine():
    assert bar(close=Decimal("1150.5"), high=Decimal("1166.75")).close == Decimal("1150.5")


# ---------------------------------------------------------------- rule 4: nothing before it happened


@pytest.mark.unit
def test_rule4_available_from_cannot_precede_event_time():
    with pytest.raises(ValueError):
        bar(available_from=END - timedelta(seconds=1))


# ---------------------------------------------------------------- rule 5: OBSERVED means available when received


@pytest.mark.unit
def test_rule5_observed_is_available_exactly_when_received():
    observed = correction(revision=1)
    assert observed.available_from == observed.received_at
    with pytest.raises(ValueError):
        correction(revision=1, available_from=datetime(2024, 6, 7, 22, 0, tzinfo=UTC))


# ---------------------------------------------------------------- rule 6: later revisions are never backdated


@pytest.mark.unit
def test_rule6_a_correction_must_be_observed():
    with pytest.raises(ValueError):
        correction(availability_basis=AvailabilityBasis.BACKFILL_ASSUMED)


@pytest.mark.unit
def test_rule6_a_correction_cannot_be_available_before_it_was_received():
    with pytest.raises(ValueError):
        correction(available_from=END)


# ---------------------------------------------------------------- rule 7: BACKFILL_ASSUMED is revision 1 only


@pytest.mark.unit
@pytest.mark.parametrize("revision", [2, 3])
def test_rule7_backfill_assumed_is_only_revision_one(revision):
    with pytest.raises(ValueError):
        bar(revision=revision)


@pytest.mark.unit
@pytest.mark.parametrize("revision", [0, -1, True, 1.0])
def test_revision_is_a_positive_integer(revision):
    with pytest.raises((ValueError, TypeError)):
        bar(revision=revision)


# ---------------------------------------------------------------- rule 8: CLOSED means event_time == end_time


@pytest.mark.unit
def test_rule8_a_closed_bar_happened_at_its_end():
    with pytest.raises(ValueError):
        bar(event_time=END - timedelta(minutes=5))


@pytest.mark.unit
def test_rule8_a_forming_bar_may_be_observed_before_its_end():
    forming = bar(
        state=BarState.FORMING,
        event_time=END - timedelta(hours=1),
        available_from=END - timedelta(hours=1),
    )
    assert forming.state is BarState.FORMING


# ---------------------------------------------------------------- rule 9: source is a provider ID


@pytest.mark.unit
@pytest.mark.parametrize("source", ["resampled:yfinance", "YFinance", "", "1vendor"])
def test_rule9_source_must_be_a_provider_id(source):
    with pytest.raises(ValueError):
        bar(source=source)


# ---------------------------------------------------------------- identity, enums, other fields


@pytest.mark.unit
def test_two_providers_never_share_an_identity():
    assert bar().identity == ("yfinance", "EQ_US_NVDA", Timeframe.D1, START)
    assert bar(source="testvendor").identity != bar().identity


@pytest.mark.unit
def test_enum_values_given_as_strings_are_converted():
    candle = bar(timeframe="H1", state="CLOSED", price_basis="RAW_AS_REPORTED",
                 volume_basis="RAW_NO_LATER_SPLIT", availability_basis="BACKFILL_ASSUMED",
                 end_time=START + timedelta(hours=1), event_time=START + timedelta(hours=1),
                 available_from=START + timedelta(hours=1))
    assert candle.timeframe is Timeframe.H1
    assert candle.price_basis is PriceBasis.RAW_AS_REPORTED
    with pytest.raises(ValueError):
        bar(timeframe="M1")


@pytest.mark.unit
@pytest.mark.parametrize(
    "changes",
    [{"currency": "usd"}, {"instrument_id": ""}, {"source_version": ""}, {"import_id": " x"}],
)
def test_other_fields_are_validated(changes):
    with pytest.raises((ValueError, TypeError)):
        bar(**changes)


@pytest.mark.unit
def test_candles_are_immutable():
    with pytest.raises(AttributeError):
        bar().close = Decimal("1")
