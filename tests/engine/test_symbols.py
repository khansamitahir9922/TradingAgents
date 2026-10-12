"""Effective-dated provider symbol mappings (ADR-003; docs/tasks/M1-04.md).

The behaviour every resolver must have is written once, in
SymbolResolverContract, and run here against the in-memory SymbolResolver.
M1-05 runs the same contract against the SQLite-backed resolver by
subclassing it, so both implementations are held to identical cases.
"""

from datetime import date, datetime

import pytest

from investment_engine.market.symbols import (
    PROVIDER_YFINANCE,
    SymbolMapping,
    SymbolResolver,
    UnknownSymbol,
)

# A ticker change: Meta traded as FB until 2022-06-08 and as META from 2022-06-09.
# The instrument keeps the mnemonic it was created with (ADR-003).
FB, META_DAY = "EQ_US_FB", date(2022, 6, 9)


def mapping(instrument_id: str, symbol: str, valid_from: date, valid_to: date | None = None,
            provider: str = PROVIDER_YFINANCE) -> SymbolMapping:
    return SymbolMapping(instrument_id, provider, symbol, valid_from, valid_to)


class SymbolResolverContract:
    """Cases every resolver implementation must pass. Subclasses supply make_resolver()."""

    # Every instrument ID the cases use, for implementations that need them registered first.
    INSTRUMENT_IDS = ("EQ_US_NVDA", "EQ_US_FB", "EQ_US_ABC", "EQ_US_ABC_2", "EQ_US_XYZ")

    def make_resolver(self):
        raise NotImplementedError

    # -- lookups across a mapping's validity --------------------------------

    @pytest.mark.unit
    def test_lookups_respect_the_half_open_validity(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1), date(2025, 1, 1)))
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2018, 12, 31))      # before
        assert resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2019, 1, 1)) == "EQ_US_NVDA"   # start
        assert resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2022, 6, 1)) == "EQ_US_NVDA"   # inside
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2025, 1, 1))        # end (exclusive)
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2026, 1, 1))        # after

    @pytest.mark.unit
    def test_an_open_ended_mapping_never_expires(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)))
        assert resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2099, 12, 31)) == "EQ_US_NVDA"
        assert resolver.symbol_for("EQ_US_NVDA", PROVIDER_YFINANCE, date(2099, 12, 31)) == "NVDA"

    @pytest.mark.unit
    def test_a_reused_symbol_resolves_by_date(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_ABC", "ABC", date(2010, 1, 1), date(2015, 1, 1)))
        resolver.add(mapping("EQ_US_ABC_2", "ABC", date(2018, 1, 1)))
        assert resolver.resolve(PROVIDER_YFINANCE, "ABC", date(2012, 1, 1)) == "EQ_US_ABC"
        assert resolver.resolve(PROVIDER_YFINANCE, "ABC", date(2020, 1, 1)) == "EQ_US_ABC_2"
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "ABC", date(2016, 1, 1))         # the gap

    @pytest.mark.unit
    def test_a_ticker_change_resolves_on_both_sides_in_both_directions(self):
        resolver = self.make_resolver()
        resolver.add(mapping(FB, "FB", date(2012, 5, 18), META_DAY))
        resolver.add(mapping(FB, "META", META_DAY))
        before, on = date(2022, 6, 8), META_DAY
        assert resolver.resolve(PROVIDER_YFINANCE, "FB", before) == FB
        assert resolver.resolve(PROVIDER_YFINANCE, "META", on) == FB
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "FB", on)
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "META", before)
        assert resolver.symbol_for(FB, PROVIDER_YFINANCE, before) == "FB"
        assert resolver.symbol_for(FB, PROVIDER_YFINANCE, on) == "META"

    @pytest.mark.unit
    def test_providers_are_independent(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)))
        resolver.add(mapping("EQ_US_XYZ", "NVDA", date(2019, 1, 1), provider="testvendor"))
        assert resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2020, 1, 1)) == "EQ_US_NVDA"
        assert resolver.resolve("testvendor", "NVDA", date(2020, 1, 1)) == "EQ_US_XYZ"

    @pytest.mark.unit
    def test_symbols_are_matched_exactly(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)))
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "nvda", date(2020, 1, 1))

    # -- unknown lookups ------------------------------------------------------

    @pytest.mark.unit
    def test_unknown_lookups_raise_unknown_symbol(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)))
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "AMD", date(2020, 1, 1))
        with pytest.raises(UnknownSymbol):
            resolver.resolve("testvendor", "NVDA", date(2020, 1, 1))
        with pytest.raises(UnknownSymbol):
            resolver.symbol_for("EQ_US_XYZ", PROVIDER_YFINANCE, date(2020, 1, 1))
        with pytest.raises(UnknownSymbol):
            resolver.symbol_for("EQ_US_NVDA", "testvendor", date(2020, 1, 1))
        assert issubclass(UnknownSymbol, LookupError)

    @pytest.mark.unit
    def test_lookup_dates_must_be_dates(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)))
        with pytest.raises(TypeError):
            resolver.resolve(PROVIDER_YFINANCE, "NVDA", datetime(2020, 1, 1))

    # -- overlap rules ----------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "second",
        [
            mapping("EQ_US_XYZ", "NVDA", date(2024, 1, 1)),                     # inside an open end
            mapping("EQ_US_XYZ", "NVDA", date(2010, 1, 1), date(2019, 1, 2)),   # overlaps the start
        ],
    )
    def test_one_symbol_cannot_mean_two_instruments_at_once(self, second):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)))
        with pytest.raises(ValueError):
            resolver.add(second)
        assert resolver.resolve(PROVIDER_YFINANCE, "NVDA", date(2024, 6, 1)) == "EQ_US_NVDA"

    @pytest.mark.unit
    def test_one_instrument_cannot_have_two_symbols_at_once(self):
        resolver = self.make_resolver()
        resolver.add(mapping(FB, "FB", date(2012, 5, 18), date(2022, 6, 10)))
        with pytest.raises(ValueError):
            resolver.add(mapping(FB, "META", META_DAY))      # overlaps by one day
        with pytest.raises(UnknownSymbol):
            resolver.resolve(PROVIDER_YFINANCE, "META", date(2023, 1, 1))

    @pytest.mark.unit
    def test_an_identical_overlapping_mapping_is_refused(self):
        resolver = self.make_resolver()
        resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)))
        with pytest.raises(ValueError):
            resolver.add(mapping("EQ_US_NVDA", "NVDA", date(2020, 1, 1)))

    @pytest.mark.unit
    def test_touching_intervals_do_not_overlap(self):
        resolver = self.make_resolver()
        resolver.add(mapping(FB, "FB", date(2012, 5, 18), META_DAY))
        resolver.add(mapping(FB, "META", META_DAY))                           # starts where FB ends
        resolver.add(mapping("EQ_US_XYZ", "FB", META_DAY))                    # FB is free again
        assert resolver.resolve(PROVIDER_YFINANCE, "FB", META_DAY) == "EQ_US_XYZ"


class TestInMemorySymbolResolver(SymbolResolverContract):
    def make_resolver(self):
        return SymbolResolver()


# -- the mapping record itself ------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["YFinance", "", "y finance", "1vendor", "yfinance "])
def test_a_provider_must_be_a_lowercase_identifier(provider):
    with pytest.raises(ValueError):
        mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1), provider=provider)


@pytest.mark.unit
@pytest.mark.parametrize("symbol", ["", " NVDA", "NVDA ", None])
def test_a_symbol_must_be_non_empty_without_surrounding_spaces(symbol):
    with pytest.raises((ValueError, TypeError)):
        mapping("EQ_US_NVDA", symbol, date(2019, 1, 1))


@pytest.mark.unit
@pytest.mark.parametrize("instrument_id", ["", " EQ_US_NVDA", None])
def test_an_instrument_id_must_be_given(instrument_id):
    with pytest.raises((ValueError, TypeError)):
        mapping(instrument_id, "NVDA", date(2019, 1, 1))


@pytest.mark.unit
@pytest.mark.parametrize("valid_to", [date(2019, 1, 1), date(2018, 1, 1)])
def test_valid_to_must_follow_valid_from(valid_to):
    with pytest.raises(ValueError):
        mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1), valid_to)


@pytest.mark.unit
def test_validity_dates_must_be_dates_not_datetimes():
    with pytest.raises(TypeError):
        mapping("EQ_US_NVDA", "NVDA", datetime(2019, 1, 1))


@pytest.mark.unit
def test_a_mapping_is_immutable():
    with pytest.raises(AttributeError):
        mapping("EQ_US_NVDA", "NVDA", date(2019, 1, 1)).symbol = "AMD"
