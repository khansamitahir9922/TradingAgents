"""Instruments with a stable internal ID and a lifecycle (ADR-003; docs/tasks/M1-03.md)."""

from dataclasses import replace
from datetime import date, datetime

import pytest

from investment_engine.market.instruments import (
    AssetClass,
    Instrument,
    InstrumentRegistry,
    InstrumentStatus,
)


def nvda(**changes) -> Instrument:
    base = Instrument(
        instrument_id="EQ_US_NVDA",
        asset_class=AssetClass.EQUITY,
        currency="USD",
        exchange="XNAS",
        timezone="America/New_York",
        status=InstrumentStatus.ACTIVE,
        active_from=date(2019, 1, 1),
        active_to=None,
    )
    return replace(base, **changes) if changes else base


@pytest.mark.unit
def test_a_valid_instrument_is_built():
    instrument = nvda()
    assert instrument.instrument_id == "EQ_US_NVDA"
    assert instrument.asset_class is AssetClass.EQUITY


@pytest.mark.unit
@pytest.mark.parametrize(
    "instrument_id",
    ["EQ_US_ABC_2", "ETF_US_SPY", "EQ_GB_VOD", "EQ_US_BRKB", "EQ_US_A1"],
)
def test_valid_id_formats(instrument_id):
    asset = AssetClass.ETF if instrument_id.startswith("ETF_") else AssetClass.EQUITY
    assert nvda(instrument_id=instrument_id, asset_class=asset).instrument_id == instrument_id


@pytest.mark.unit
@pytest.mark.parametrize(
    "instrument_id",
    [
        "NVDA",            # a ticker is not an ID
        "eq_us_nvda",      # lowercase
        "EQ_USA_NVDA",     # country must be two letters
        "EQ_US_",          # no mnemonic
        "EQ_US_NV.DA",     # punctuation
        "EQ_US_NVDA_X",    # suffix must be a number
        "FX_US_NVDA",      # unknown asset prefix
        " EQ_US_NVDA",
    ],
)
def test_a_bad_id_format_is_refused(instrument_id):
    with pytest.raises(ValueError):
        nvda(instrument_id=instrument_id)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("instrument_id", "asset_class"),
    [("EQ_US_SPY", AssetClass.ETF), ("ETF_US_NVDA", AssetClass.EQUITY)],
)
def test_the_id_prefix_must_match_the_asset_class(instrument_id, asset_class):
    with pytest.raises(ValueError):
        nvda(instrument_id=instrument_id, asset_class=asset_class)


@pytest.mark.unit
def test_crypto_is_refused_in_m1():
    with pytest.raises(ValueError):
        nvda(asset_class="CRYPTO")


@pytest.mark.unit
def test_enum_values_given_as_strings_are_accepted():
    instrument = nvda(asset_class="EQUITY", status="DELISTED", active_to=date(2024, 1, 1))
    assert instrument.asset_class is AssetClass.EQUITY
    assert instrument.status is InstrumentStatus.DELISTED


@pytest.mark.unit
@pytest.mark.parametrize("timezone", ["America/NewYork", "America/Nowhere", "", "Mars/Olympus"])
def test_an_invalid_timezone_is_refused(timezone):
    with pytest.raises(ValueError):
        nvda(timezone=timezone)


@pytest.mark.unit
@pytest.mark.parametrize("currency", ["usd", "US", "DOLLAR", ""])
def test_an_invalid_currency_is_refused(currency):
    with pytest.raises(ValueError):
        nvda(currency=currency)


@pytest.mark.unit
@pytest.mark.parametrize("exchange", ["NASDAQ", "xnas", "XNA", ""])
def test_an_invalid_exchange_code_is_refused(exchange):
    with pytest.raises(ValueError):
        nvda(exchange=exchange)


@pytest.mark.unit
def test_active_means_no_end_date():
    with pytest.raises(ValueError):
        nvda(status=InstrumentStatus.ACTIVE, active_to=date(2024, 1, 1))


@pytest.mark.unit
def test_delisted_needs_an_end_date():
    with pytest.raises(ValueError):
        nvda(status=InstrumentStatus.DELISTED, active_to=None)
    delisted = nvda(status=InstrumentStatus.DELISTED, active_to=date(2024, 1, 1))
    assert delisted.active_to == date(2024, 1, 1)


@pytest.mark.unit
@pytest.mark.parametrize("active_to", [date(2019, 1, 1), date(2018, 12, 31)])
def test_the_end_date_must_follow_the_start(active_to):
    with pytest.raises(ValueError):
        nvda(status=InstrumentStatus.DELISTED, active_to=active_to)


@pytest.mark.unit
def test_suspended_may_have_either_form():
    assert nvda(status=InstrumentStatus.SUSPENDED).active_to is None
    assert nvda(status=InstrumentStatus.SUSPENDED, active_to=date(2024, 1, 1)).active_to


@pytest.mark.unit
def test_lifecycle_dates_must_be_dates_not_datetimes():
    with pytest.raises(TypeError):
        nvda(active_from=datetime(2019, 1, 1))
    with pytest.raises(TypeError):
        nvda(status=InstrumentStatus.DELISTED, active_to=datetime(2024, 1, 1))


@pytest.mark.unit
def test_is_active_on_is_half_open():
    delisted = nvda(status=InstrumentStatus.DELISTED, active_to=date(2024, 1, 1))
    assert not delisted.is_active_on(date(2018, 12, 31))
    assert delisted.is_active_on(date(2019, 1, 1))       # first day included
    assert delisted.is_active_on(date(2023, 12, 31))
    assert not delisted.is_active_on(date(2024, 1, 1))   # end date excluded
    assert nvda().is_active_on(date(2099, 1, 1))         # open-ended


@pytest.mark.unit
def test_instruments_are_immutable():
    with pytest.raises(AttributeError):
        nvda().status = InstrumentStatus.DELISTED


@pytest.mark.unit
def test_the_registry_stores_and_returns_instruments():
    registry = InstrumentRegistry()
    registry.add(nvda())
    assert registry.get("EQ_US_NVDA") == nvda()
    with pytest.raises(KeyError):
        registry.get("EQ_US_AMD")


@pytest.mark.unit
def test_the_registry_refuses_a_duplicate_id():
    registry = InstrumentRegistry()
    registry.add(nvda())
    with pytest.raises(ValueError):
        registry.add(nvda(exchange="XNYS"))
    assert registry.get("EQ_US_NVDA").exchange == "XNAS"


@pytest.mark.unit
def test_the_registry_has_no_way_to_remove_an_instrument():
    registry = InstrumentRegistry()
    for name in ("remove", "delete", "pop", "discard", "clear", "__delitem__", "__setitem__"):
        assert not hasattr(registry, name), name
