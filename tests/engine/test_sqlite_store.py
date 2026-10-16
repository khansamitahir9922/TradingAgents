"""The reference-data stores for instruments and symbol mappings (ADR-008; docs/tasks/M1-05.md, M3-02.md).

The store tests run on both backends through the database port; the schema
and migration tests are SQLite's own. The stored resolver is held to exactly
the cases the in-memory one passes: it runs M1-04's SymbolResolverContract.
"""

import re
import sqlite3
from datetime import date
from importlib.resources import files

import pytest

from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.symbols import PROVIDER_YFINANCE, SymbolMapping, UnknownSymbol
from investment_engine.storage.database import IntegrityViolation, SqliteDatabase
from investment_engine.storage.sqlite import (
    SchemaVersionError,
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)
from tests.engine.test_symbols import SymbolResolverContract

SCHEMA_SCRIPTS = sorted(
    entry for entry in files("investment_engine.storage").joinpath("schema").iterdir()
    if entry.name.endswith(".sql")
)


def instrument(instrument_id: str = "EQ_US_NVDA", **changes) -> Instrument:
    values = {
        "instrument_id": instrument_id,
        "asset_class": AssetClass.ETF if instrument_id.startswith("ETF_") else AssetClass.EQUITY,
        "currency": "USD",
        "exchange": "XNAS",
        "timezone": "America/New_York",
        "status": InstrumentStatus.ACTIVE,
        "active_from": date(2019, 1, 1),
        "active_to": None,
    }
    values.update(changes)
    return Instrument(**values)


@pytest.fixture
def db(tmp_path):
    conn = open_operational_db(tmp_path / "db" / "operational.sqlite3")
    apply_schema(conn)
    yield conn
    conn.close()


def count(database, table: str) -> int:
    return database.fetchone(f"SELECT COUNT(*) FROM {table}")[0]


# ---------------------------------------------------------------- schema


@pytest.mark.unit
def test_opening_creates_the_parent_folder_and_enforces_foreign_keys(tmp_path):
    conn = open_operational_db(tmp_path / "a" / "b" / "operational.sqlite3")
    assert (tmp_path / "a" / "b").is_dir()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


@pytest.mark.unit
def test_applying_the_schema_twice_is_idempotent(tmp_path):
    conn = open_operational_db(tmp_path / "operational.sqlite3")
    first = apply_schema(conn)
    second = apply_schema(conn)
    assert first == second == len(SCHEMA_SCRIPTS) >= 1
    assert [row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")] == list(
        range(1, first + 1)
    )
    conn.close()


@pytest.mark.unit
def test_a_database_newer_than_the_code_is_refused(db):
    db.execute("INSERT INTO schema_version (version) VALUES (999)")
    with pytest.raises(SchemaVersionError):
        apply_schema(db)


@pytest.mark.unit
def test_schema_scripts_are_numbered_from_one_without_gaps():
    numbers = [int(script.name.split("_")[0]) for script in SCHEMA_SCRIPTS]
    assert numbers == list(range(1, len(numbers) + 1))


NON_PORTABLE = [
    r"\bINSERT\s+OR\s+(REPLACE|IGNORE)\b",
    r"\bREPLACE\s+INTO\b",
    r"\bAUTOINCREMENT\b",
    r"\bWITHOUT\s+ROWID\b",
    r"\bPRAGMA\b",
    r"\bATTACH\b",
    r"\bGLOB\b",
    r"\b(datetime|julianday|strftime|date|time)\s*\(",
]


@pytest.mark.unit
@pytest.mark.parametrize("script", SCHEMA_SCRIPTS, ids=lambda s: s.name)
def test_schema_scripts_use_portable_sql(script):
    # M3 moves to PostgreSQL (ADR-008); the move should be mechanical.
    text = script.read_text(encoding="utf-8")
    found = [pattern for pattern in NON_PORTABLE if re.search(pattern, text, re.IGNORECASE)]
    assert found == []


# ---------------------------------------------------------------- instruments


@pytest.mark.unit
def test_an_instrument_round_trips(database):
    repo = SqliteInstrumentRepository(database)
    original = instrument(status=InstrumentStatus.DELISTED, active_to=date(2024, 1, 1))
    repo.add(original)
    assert repo.get("EQ_US_NVDA") == original
    assert repo.get("EQ_US_NVDA").status is InstrumentStatus.DELISTED


@pytest.mark.unit
def test_instruments_persist_across_connections(backend):
    SqliteInstrumentRepository(backend.first).add(instrument())
    assert SqliteInstrumentRepository(backend.make()).get("EQ_US_NVDA") == instrument()


@pytest.mark.unit
def test_list_returns_every_instrument_sorted_by_id(database):
    repo = SqliteInstrumentRepository(database)
    for instrument_id in ["EQ_US_NVDA", "ETF_US_SPY", "EQ_US_AMD"]:
        repo.add(instrument(instrument_id))
    assert [i.instrument_id for i in repo.list()] == ["EQ_US_AMD", "EQ_US_NVDA", "ETF_US_SPY"]


@pytest.mark.unit
def test_a_duplicate_instrument_id_is_refused(database):
    repo = SqliteInstrumentRepository(database)
    repo.add(instrument())
    with pytest.raises(ValueError):
        repo.add(instrument(exchange="XNYS"))
    assert repo.get("EQ_US_NVDA").exchange == "XNAS"
    assert count(database, "instruments") == 1


@pytest.mark.unit
def test_an_unknown_instrument_raises_key_error(database):
    with pytest.raises(KeyError):
        SqliteInstrumentRepository(database).get("EQ_US_AMD")


@pytest.mark.unit
def test_update_lifecycle_changes_only_status_and_end_date(database):
    repo = SqliteInstrumentRepository(database)
    repo.add(instrument())
    repo.update_lifecycle("EQ_US_NVDA", InstrumentStatus.DELISTED, date(2025, 1, 1))
    updated = repo.get("EQ_US_NVDA")
    assert (updated.status, updated.active_to) == (InstrumentStatus.DELISTED, date(2025, 1, 1))
    assert updated.exchange == "XNAS" and updated.active_from == date(2019, 1, 1)


@pytest.mark.unit
def test_update_lifecycle_enforces_the_lifecycle_rules(database):
    repo = SqliteInstrumentRepository(database)
    repo.add(instrument())
    with pytest.raises(ValueError):
        repo.update_lifecycle("EQ_US_NVDA", InstrumentStatus.DELISTED, None)
    with pytest.raises(ValueError):
        repo.update_lifecycle("EQ_US_NVDA", InstrumentStatus.DELISTED, date(2018, 1, 1))
    assert repo.get("EQ_US_NVDA") == instrument()
    with pytest.raises(KeyError):
        repo.update_lifecycle("EQ_US_AMD", InstrumentStatus.DELISTED, date(2025, 1, 1))


@pytest.mark.unit
def test_the_schema_itself_refuses_an_invalid_lifecycle(database):
    # Defence in depth: the CHECK constraints mirror M1-03 for writes that
    # bypass the repository.
    with pytest.raises(IntegrityViolation):
        database.execute(
            "INSERT INTO instruments VALUES ('EQ_US_AMD', 'EQUITY', 'USD', 'XNAS', 'America/New_York',"
            " 'ACTIVE', '2019-01-01', '2020-01-01')"
        )


@pytest.mark.unit
def test_there_is_no_way_to_delete_an_instrument(database):
    repo = SqliteInstrumentRepository(database)
    for name in ("remove", "delete", "pop", "discard", "clear", "__delitem__"):
        assert not hasattr(repo, name), name


# ---------------------------------------------------------------- symbol mappings


class TestSqliteSymbolResolver(SymbolResolverContract):
    """M1-04's resolver cases, run against both backends."""

    @pytest.fixture(autouse=True)
    def _database(self, backend):
        self.db = backend.first
        repo = SqliteInstrumentRepository(self.db)
        for instrument_id in self.INSTRUMENT_IDS:
            repo.add(instrument(instrument_id))

    def make_resolver(self):
        return SqliteSymbolResolver(self.db)


@pytest.mark.unit
def test_a_refused_mapping_leaves_no_partial_rows(database):
    SqliteInstrumentRepository(database).add(instrument())
    SqliteInstrumentRepository(database).add(instrument("EQ_US_AMD"))
    resolver = SqliteSymbolResolver(database)
    resolver.add(SymbolMapping("EQ_US_NVDA", PROVIDER_YFINANCE, "NVDA", date(2019, 1, 1), None))
    with pytest.raises(ValueError):
        resolver.add(SymbolMapping("EQ_US_AMD", PROVIDER_YFINANCE, "NVDA", date(2020, 1, 1), None))
    assert count(database, "symbol_mappings") == 1
    assert not database.in_transaction


@pytest.mark.unit
def test_a_mapping_needs_a_known_instrument(database):
    resolver = SqliteSymbolResolver(database)
    with pytest.raises(ValueError):
        resolver.add(SymbolMapping("EQ_US_NVDA", PROVIDER_YFINANCE, "NVDA", date(2019, 1, 1), None))
    assert count(database, "symbol_mappings") == 0
    assert not database.in_transaction


@pytest.mark.unit
def test_mappings_persist_across_connections(backend):
    SqliteInstrumentRepository(backend.first).add(instrument())
    SqliteSymbolResolver(backend.first).add(
        SymbolMapping("EQ_US_NVDA", PROVIDER_YFINANCE, "NVDA", date(2019, 1, 1), None))
    other = backend.make()
    assert SqliteSymbolResolver(other).resolve(PROVIDER_YFINANCE, "NVDA", date(2024, 1, 1)) == "EQ_US_NVDA"
    with pytest.raises(UnknownSymbol):
        SqliteSymbolResolver(other).resolve(PROVIDER_YFINANCE, "NVDA", date(2018, 1, 1))


@pytest.mark.unit
def test_there_is_no_way_to_delete_a_mapping(database):
    resolver = SqliteSymbolResolver(database)
    for name in ("remove", "delete", "pop", "discard", "clear", "__delitem__"):
        assert not hasattr(resolver, name), name


@pytest.mark.unit
def test_later_migrations_upgrade_an_existing_m1_database_without_touching_its_tables(tmp_path):
    # An M1 database: only script 0001 applied, holding reference data.
    path = tmp_path / "operational.sqlite3"
    conn = open_operational_db(path)
    first_script = SCHEMA_SCRIPTS[0].read_text(encoding="utf-8")
    conn.executescript(f"BEGIN;\n{first_script}\nINSERT INTO schema_version (version) VALUES (1);\nCOMMIT;")
    SqliteInstrumentRepository(SqliteDatabase(conn)).add(instrument())
    before = conn.execute("SELECT sql FROM sqlite_master WHERE name IN ('instruments', 'symbol_mappings')"
                          " ORDER BY name").fetchall()
    assert apply_schema(conn) == len(SCHEMA_SCRIPTS) >= 2
    assert SqliteInstrumentRepository(SqliteDatabase(conn)).get("EQ_US_NVDA") == instrument()
    assert conn.execute("SELECT sql FROM sqlite_master WHERE name IN ('instruments', 'symbol_mappings')"
                        " ORDER BY name").fetchall() == before
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"lineage_records", "evaluation_records"} <= tables
    conn.close()


@pytest.mark.unit
def test_a_database_at_schema_2_upgrades_to_the_evaluation_records(tmp_path):
    path = tmp_path / "operational.sqlite3"
    conn = open_operational_db(path)
    for number, script in enumerate(SCHEMA_SCRIPTS[:2], start=1):
        sql = script.read_text(encoding="utf-8")
        conn.executescript(f"BEGIN;\n{sql}\nINSERT INTO schema_version (version) VALUES ({number});\nCOMMIT;")
    SqliteInstrumentRepository(SqliteDatabase(conn)).add(instrument())
    assert apply_schema(conn) == len(SCHEMA_SCRIPTS) >= 3
    assert SqliteInstrumentRepository(SqliteDatabase(conn)).get("EQ_US_NVDA") == instrument()
    assert conn.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0] == 0
    conn.close()


@pytest.mark.unit
def test_a_schema_3_database_gains_the_insert_guards_on_upgrade(tmp_path):
    conn = open_operational_db(tmp_path / "operational.sqlite3")
    for number, script in enumerate(SCHEMA_SCRIPTS[:3], start=1):
        sql = script.read_text(encoding="utf-8")
        conn.executescript(f"BEGIN;\n{sql}\nINSERT INTO schema_version (version) VALUES ({number});\nCOMMIT;")
    conn.execute("INSERT INTO lineage_records VALUES ('lin-a', 'EQ_US_NVDA', 't', x'01')")
    conn.execute("INSERT OR REPLACE INTO lineage_records VALUES ('lin-a', 'EQ_US_NVDA', 't', x'02')")  # schema 3: unguarded
    assert apply_schema(conn) == len(SCHEMA_SCRIPTS) >= 4
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("INSERT OR REPLACE INTO lineage_records VALUES ('lin-a', 'EQ_US_NVDA', 't', x'03')")
    conn.execute("INSERT INTO evaluation_records VALUES ('e', 'EQ_US_NVDA', 't', x'01')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("REPLACE INTO evaluation_records VALUES ('e', 'EQ_US_NVDA', 't', x'02')")
    assert conn.execute("SELECT content FROM evaluation_records").fetchone()[0] == b"\x01"
    conn.execute("INSERT INTO lineage_records VALUES ('lin-b', 'EQ_US_NVDA', 't', x'01')")  # new ids still insert
    conn.close()
