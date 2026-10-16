"""Concurrent symbol-mapping inserts on PostgreSQL (docs/tasks/M3-01.md rule 4, M3-02.md rule 6; Codex B4)."""

import threading
from datetime import date

import pytest

from investment_engine.market.instruments import Instrument
from investment_engine.market.symbols import SymbolMapping
from investment_engine.storage.sqlite import SqliteInstrumentRepository, SqliteSymbolResolver

REPEATS = 50


def instrument(instrument_id):
    return Instrument(instrument_id=instrument_id, asset_class="EQUITY", currency="USD", exchange="XNAS",
                      timezone="America/New_York", status="ACTIVE", active_from=date(2019, 1, 2), active_to=None)


def race(backend, first_mapping, second_mapping):
    """Two connections insert at the same moment; returns how many committed."""
    databases = [backend.make(), backend.make()]
    resolvers = [SqliteSymbolResolver(d) for d in databases]
    barrier, results = threading.Barrier(2), []

    def run(resolver, mapping):
        barrier.wait()
        try:
            resolver.add(mapping)
            results.append("ok")
        except ValueError:
            results.append("refused")

    threads = [threading.Thread(target=run, args=(r, m)) for r, m in zip(resolvers, (first_mapping, second_mapping),
                                                                         strict=True)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    for database in databases:
        database.connection.close()
    assert len(results) == 2
    return results.count("ok")


@pytest.fixture
def pg_backend(backend):
    if backend.kind != "postgresql":
        pytest.skip("a PostgreSQL concurrency test; SQLite serializes writers with BEGIN IMMEDIATE")
    repo = SqliteInstrumentRepository(backend.first)
    for i in range(REPEATS):
        repo.add(instrument(f"EQ_US_A{i}"))
        repo.add(instrument(f"EQ_US_B{i}"))
    return backend


@pytest.mark.unit
def test_one_symbol_can_never_map_to_two_instruments_at_once(pg_backend):
    for i in range(REPEATS):
        committed = race(pg_backend,
                         SymbolMapping(f"EQ_US_A{i}", "yfinance", f"S{i}", date(2020, 1, 1), None),
                         SymbolMapping(f"EQ_US_B{i}", "yfinance", f"S{i}", date(2021, 1, 1), None))
        assert committed == 1, i


@pytest.mark.unit
def test_one_instrument_can_never_have_two_symbols_at_once(pg_backend):
    for i in range(REPEATS):
        committed = race(pg_backend,
                         SymbolMapping(f"EQ_US_A{i}", "yfinance", f"X{i}", date(2020, 1, 1), None),
                         SymbolMapping(f"EQ_US_A{i}", "yfinance", f"Y{i}", date(2021, 1, 1), None))
        assert committed == 1, i


@pytest.mark.unit
def test_non_overlapping_reuse_and_other_providers_still_commit(pg_backend):
    first = SqliteSymbolResolver(pg_backend.first)
    first.add(SymbolMapping("EQ_US_A0", "yfinance", "R", date(2020, 1, 1), date(2021, 1, 1)))
    assert race(pg_backend,
                SymbolMapping("EQ_US_B0", "yfinance", "R", date(2021, 1, 1), None),
                SymbolMapping("EQ_US_B1", "testvendor", "R", date(2020, 1, 1), None)) == 2
