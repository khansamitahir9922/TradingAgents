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
