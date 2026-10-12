"""Availability types shared by candles and corporate actions (docs/tasks/M1-08.md)."""

import re

import pytest

from investment_engine.market.availability import PROVIDER_ID_PATTERN, AvailabilityBasis


@pytest.mark.unit
def test_the_two_availability_bases():
    assert {b.value for b in AvailabilityBasis} == {"OBSERVED", "BACKFILL_ASSUMED"}


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["yfinance", "testvendor", "alpha_vantage", "a1"])
def test_provider_ids_that_match(provider):
    assert re.fullmatch(PROVIDER_ID_PATTERN.strip("^$"), provider)


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["YFinance", "resampled:yfinance", "1vendor", "", "y finance"])
def test_provider_ids_that_dont_match(provider):
    assert not re.fullmatch(PROVIDER_ID_PATTERN.strip("^$"), provider)


@pytest.mark.unit
@pytest.mark.parametrize(
    "instrument_id",
    ["EQ_US_NVDA", "ETF_US_SPY", "EQ_US_ABC_2", "NVDA", "EQ_US_", "../x", "EQ_US_NVDA/x", "eq_us_nvda", "FX_US_X"],
)
def test_the_instrument_id_check_agrees_with_instrument(instrument_id):
    # The market-data contracts and Instrument must accept exactly the same IDs.
    from datetime import date

    from investment_engine.market.availability import check_instrument_id
    from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus

    asset = AssetClass.ETF if instrument_id.startswith("ETF_") else AssetClass.EQUITY
    try:
        Instrument(instrument_id, asset, "USD", "XNAS", "America/New_York", InstrumentStatus.ACTIVE, date(2019, 1, 1), None)
        instrument_ok = True
    except ValueError:
        instrument_ok = False
    try:
        check_instrument_id(instrument_id)
        contract_ok = True
    except ValueError:
        contract_ok = False
    assert contract_ok == instrument_ok
