"""The CorporateAction contract (architecture Part H; ADR-009; docs/tasks/M1-09.md).

Each action carries its instrument context explicitly (currency and exchange
time zone), so the contract can check a dividend's currency and the
exchange-local ex-date without assuming defaults (owner's batch-2 condition).
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.corporate_actions import (
    ActionType,
    AmountBasis,
    CorporateAction,
    ex_date_start,
)
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.money import Money

EX_DATE = date(2024, 6, 10)
# 00:00 on 10 June 2024 in New York (EDT, UTC-4) is 04:00 UTC.
EX_START = datetime(2024, 6, 10, 4, 0, tzinfo=UTC)
FETCHED = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

NVDA = Instrument("EQ_US_NVDA", AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                  InstrumentStatus.ACTIVE, date(2019, 1, 1), None)


def action(action_type=ActionType.SPLIT, **changes) -> CorporateAction:
    type_fields = {
        ActionType.SPLIT: {"ratio": Decimal("10")},
        ActionType.DIVIDEND: {"amount": Money(Decimal("0.0100"), "USD"),
                              "amount_basis": AmountBasis.RECONSTRUCTED_FROM_SPLIT_ADJUSTED},
        ActionType.SYMBOL_CHANGE: {"new_symbol": "NVDX"},
        ActionType.DELISTING: {},
    }[ActionType(action_type)]
    values = {
        "source": "yfinance",
        "instrument_id": "EQ_US_NVDA",
        "currency": "USD",
        "exchange_timezone": "America/New_York",
        "action_type": action_type,
        "ex_date": EX_DATE,
        "ratio": None,
        "amount": None,
        "amount_basis": None,
        "new_symbol": None,
        "source_version": "1.7.0",
        "import_id": "import-1",
        "received_at": FETCHED,
        "processed_at": FETCHED,
        "revision": 1,
        "available_from": EX_START,
        "availability_basis": AvailabilityBasis.BACKFILL_ASSUMED,
    }
    values.update(type_fields)
    values.update(changes)
    return CorporateAction(**values)


def correction(action_type=ActionType.DIVIDEND, **changes) -> CorporateAction:
    seen = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)
    values = {"revision": 2, "received_at": seen, "processed_at": seen, "available_from": seen,
              "availability_basis": AvailabilityBasis.OBSERVED}
    values.update(changes)
    return action(action_type, **values)


# ---------------------------------------------------------------- one valid action of each type


@pytest.mark.unit
@pytest.mark.parametrize("action_type", list(ActionType))
def test_a_valid_action_of_each_type(action_type):
    assert action(action_type).action_type is action_type


# ---------------------------------------------------------------- type-specific fields


@pytest.mark.unit
@pytest.mark.parametrize(
    ("action_type", "extra"),
    [
        (ActionType.SPLIT, {"amount": Money(Decimal("1"), "USD")}),
        (ActionType.SPLIT, {"new_symbol": "X"}),
        (ActionType.SPLIT, {"ratio": None}),
        (ActionType.DIVIDEND, {"ratio": Decimal("2")}),
        (ActionType.DIVIDEND, {"amount_basis": None}),
        (ActionType.DIVIDEND, {"amount": None}),
        (ActionType.SYMBOL_CHANGE, {"ratio": Decimal("2")}),
        (ActionType.SYMBOL_CHANGE, {"new_symbol": None}),
        (ActionType.DELISTING, {"new_symbol": "X"}),
        (ActionType.DELISTING, {"amount_basis": AmountBasis.AS_REPORTED}),
    ],
)
def test_only_the_fields_of_the_type_are_set(action_type, extra):
    with pytest.raises(ValueError):
        action(action_type, **extra)


@pytest.mark.unit
@pytest.mark.parametrize("ratio", [Decimal("1"), Decimal("0"), Decimal("-2"), Decimal("NaN")])
def test_a_split_ratio_is_positive_and_not_one(ratio):
    with pytest.raises(ValueError):
        action(ratio=ratio)


@pytest.mark.unit
def test_reverse_and_fractional_splits_are_allowed():
    assert action(ratio=Decimal("0.1")).ratio == Decimal("0.1")     # 1-for-10 reverse split
    assert action(ratio=Decimal("1.5")).ratio == Decimal("1.5")     # 3-for-2


@pytest.mark.unit
@pytest.mark.parametrize("ratio", [10, 10.0])
def test_a_split_ratio_is_a_decimal(ratio):
    with pytest.raises(TypeError):
        action(ratio=ratio)


@pytest.mark.unit
@pytest.mark.parametrize(
    "amount",
    [
        Money(Decimal("0"), "USD"),
        Money(Decimal("-0.0100"), "USD"),
        Money(Decimal("0.01001"), "USD"),      # more precision than PRICE_QUANTUM
        Money(Decimal("0.0100"), "EUR"),       # not the instrument's currency
    ],
)
def test_a_dividend_amount_is_positive_in_the_instruments_currency_at_price_quantum(amount):
    with pytest.raises(ValueError):
        action(ActionType.DIVIDEND, amount=amount)


@pytest.mark.unit
def test_a_dividend_amount_is_money():
    with pytest.raises(TypeError):
        action(ActionType.DIVIDEND, amount=Decimal("0.0100"))


# ---------------------------------------------------------------- explicit instrument context


@pytest.mark.unit
def test_backfill_availability_is_the_start_of_the_ex_date_in_exchange_time():
    assert ex_date_start(EX_DATE, "America/New_York") == EX_START
    assert ex_date_start(date(2024, 1, 10), "America/New_York") == datetime(2024, 1, 10, 5, 0, tzinfo=UTC)  # EST
    with pytest.raises(ValueError):
        action(available_from=EX_START + timedelta(hours=1))      # not the ex-date start
    with pytest.raises(ValueError):
        action(available_from=datetime(2024, 6, 10, 0, 0, tzinfo=UTC))  # midnight UTC isn't exchange-local


@pytest.mark.unit
def test_an_observed_action_may_be_seen_before_its_ex_date():
    # Announcements come before the ex-date: an action observed live weeks
    # earlier is available from when it was seen.
    seen = datetime(2024, 5, 22, 21, 0, tzinfo=UTC)
    early = action(received_at=seen, processed_at=seen, available_from=seen,
                   availability_basis=AvailabilityBasis.OBSERVED)
    assert early.available_from < EX_START


@pytest.mark.unit
@pytest.mark.parametrize("timezone", ["", "America/New_York ", "america/new_york", "Mars/Olympus"])
def test_the_exchange_timezone_must_be_an_exact_iana_name(timezone):
    with pytest.raises(ValueError):
        action(exchange_timezone=timezone)


@pytest.mark.unit
@pytest.mark.parametrize("currency", ["usd", "US", ""])
def test_the_currency_must_be_an_iso_code(currency):
    with pytest.raises(ValueError):
        action(currency=currency)


@pytest.mark.unit
def test_the_context_is_checked_against_the_instrument():
    action(ActionType.DIVIDEND).check_context(NVDA)
    with pytest.raises(ValueError):
        action(instrument_id="EQ_US_AMD").check_context(NVDA)
    with pytest.raises(ValueError):
        action(ActionType.DIVIDEND, currency="EUR", amount=Money(Decimal("0.0100"), "EUR")).check_context(NVDA)
    with pytest.raises(ValueError):
        action(exchange_timezone="Europe/London",
               available_from=ex_date_start(EX_DATE, "Europe/London")).check_context(NVDA)


# ---------------------------------------------------------------- availability (M1-08 rules 5 – 7)


@pytest.mark.unit
def test_a_backdated_correction_is_refused():
    assert correction().revision == 2
    with pytest.raises(ValueError):
        correction(available_from=EX_START)


@pytest.mark.unit
def test_backfill_assumed_is_only_revision_one():
    with pytest.raises(ValueError):
        action(revision=2)


@pytest.mark.unit
def test_observed_is_available_exactly_when_received():
    with pytest.raises(ValueError):
        correction(available_from=datetime(2026, 10, 11, 10, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.parametrize("field", ["received_at", "processed_at", "available_from"])
def test_times_must_be_aware_utc(field):
    naive = getattr(action(), field).replace(tzinfo=None)
    with pytest.raises(ValueError):
        action(**{field: naive})


# ---------------------------------------------------------------- identity and other fields


@pytest.mark.unit
def test_two_providers_never_share_an_identity():
    assert action().identity == ("yfinance", "EQ_US_NVDA", ActionType.SPLIT, EX_DATE)
    assert action(source="testvendor").identity != action().identity


@pytest.mark.unit
@pytest.mark.parametrize("source", ["resampled:yfinance", "YFinance", ""])
def test_the_source_is_a_provider_id(source):
    with pytest.raises(ValueError):
        action(source=source)


@pytest.mark.unit
def test_the_ex_date_is_a_date_not_a_datetime():
    with pytest.raises(TypeError):
        action(ex_date=datetime(2024, 6, 10))


@pytest.mark.unit
def test_enum_values_given_as_strings_are_converted():
    dividend = action("DIVIDEND", amount_basis="AS_REPORTED", availability_basis="BACKFILL_ASSUMED")
    assert dividend.action_type is ActionType.DIVIDEND and dividend.amount_basis is AmountBasis.AS_REPORTED


@pytest.mark.unit
def test_actions_are_immutable():
    with pytest.raises(AttributeError):
        replace(action(), ratio=Decimal("4")).ratio = Decimal("2")
