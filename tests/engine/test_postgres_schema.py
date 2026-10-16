"""The PostgreSQL Operational Database schema and migrations (docs/tasks/M3-01.md)."""

import sqlite3
from datetime import UTC, date, datetime

import psycopg
import pytest

from investment_engine.storage import postgres as pg
from investment_engine.storage.sqlite import SchemaVersionError, apply_schema, open_operational_db

TS = datetime(2026, 10, 16, 12, tzinfo=UTC)


@pytest.fixture
def conn(pg_database):
    c = pg.open_operational_pg(pg_database)
    yield c
    c.close()


def tables(c) -> set[str]:
    return {r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


@pytest.mark.postgres
def test_a_fresh_database_migrates_to_version_4_and_reapplying_is_a_no_op(conn):
    assert pg.apply_pg_schema(conn) == 4
    before = tables(conn)
    assert {"schema_version", "instruments", "symbol_mappings", "lineage_records", "evaluation_records"} <= before
    assert pg.apply_pg_schema(conn) == 4
    assert tables(conn) == before
    assert [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY version")] == [1, 2, 3, 4]


@pytest.mark.postgres
def test_the_connection_is_autocommit_and_in_utc(conn):
    assert conn.autocommit
    assert conn.execute("SHOW TIME ZONE").fetchone()[0] == "UTC"
    assert conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


@pytest.mark.postgres
def test_a_database_newer_than_the_code_is_refused(conn):
    pg.apply_pg_schema(conn)
    conn.execute("INSERT INTO schema_version (version) VALUES (5)")
    with pytest.raises(SchemaVersionError, match="version 5"):
        pg.apply_pg_schema(conn)


@pytest.mark.postgres
def test_a_failing_script_leaves_no_partial_schema_and_no_version(conn, monkeypatch):
    pg.apply_pg_schema(conn)
    real = pg._pg_schema_scripts()
    broken = (5, "CREATE TABLE half_made (x int);\nSELECT this_is_not_sql;")
    monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: [*real, broken])
    with pytest.raises(psycopg.Error):
        pg.apply_pg_schema(conn)
    assert "half_made" not in tables(conn)
    assert conn.execute("SELECT max(version) FROM schema_version").fetchone()[0] == 4
    assert conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


def sqlite_columns(path) -> dict[str, list[tuple]]:
    c = open_operational_db(path)
    apply_schema(c)
    out = {}
    for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        out[name] = [(r[1], bool(r[3]), r[5] > 0) for r in c.execute(f"PRAGMA table_info({name})")]
    c.close()
    return out


def pg_columns(c) -> dict[str, list[tuple]]:
    pk = {(t, col) for t, col in c.execute(
        "SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
        "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'")}
    out: dict[str, list[tuple]] = {}
    for table, column, nullable in c.execute(
            "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"):
        out.setdefault(table, []).append((column, nullable == "NO", (table, column) in pk))
    return out


@pytest.mark.postgres
def test_tables_columns_nullability_and_keys_match_sqlite_version_4(conn, tmp_path):
    pg.apply_pg_schema(conn)
    expected = sqlite_columns(tmp_path / "op.sqlite3")
    actual = pg_columns(conn)
    assert actual.keys() == expected.keys()
    for table in expected:
        # SQLite reports a single-column INTEGER PRIMARY KEY as nullable; PostgreSQL never does.
        normalize = [(n, notnull or pk, pk) for n, notnull, pk in expected[table]]
        assert actual[table] == normalize, table


@pytest.mark.postgres
def test_native_types(conn):
    pg.apply_pg_schema(conn)
    types = {(t, c): d for t, c, d in conn.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public'")}
    assert types[("instruments", "active_from")] == "date" and types[("symbol_mappings", "valid_to")] == "date"
    assert types[("lineage_records", "generated_at")] == "timestamp with time zone"
    assert types[("evaluation_records", "as_of")] == "timestamp with time zone"
    assert types[("lineage_records", "content")] == "bytea" and types[("evaluation_records", "content")] == "bytea"


ROUTES = [
    "UPDATE {t} SET instrument_id = 'EQ_US_MSFT'",
    "DELETE FROM {t}",
    "TRUNCATE {t}",
    "INSERT INTO {t} VALUES ('{id}', 'EQ_US_NVDA', %s, '\\x02') ON CONFLICT ({key}) DO UPDATE SET content = excluded.content",
    "INSERT INTO {t} VALUES ('{id}', 'EQ_US_NVDA', %s, '\\x02') ON CONFLICT DO NOTHING",
    "INSERT INTO {t} VALUES ('{id}', 'EQ_US_NVDA', %s, '\\x02')",
]


@pytest.mark.postgres
@pytest.mark.parametrize("table, key", [("lineage_records", "lineage_id"), ("evaluation_records", "record_id")])
@pytest.mark.parametrize("route", ROUTES)
def test_every_replacement_route_is_refused_and_the_original_survives(conn, table, key, route):
    pg.apply_pg_schema(conn)
    conn.execute(f"INSERT INTO {table} VALUES ('a', 'EQ_US_NVDA', %s, '\\x01')", (TS,))
    statement = route.format(t=table, id="a", key=key)
    with pytest.raises(psycopg.Error, match="append-only"):
        conn.execute(statement, (TS,) if "%s" in statement else None)
    assert conn.execute(f"SELECT content, instrument_id FROM {table}").fetchall() == [(b"\x01", "EQ_US_NVDA")]
    conn.execute(f"INSERT INTO {table} VALUES ('b', 'EQ_US_NVDA', %s, '\\x03')", (TS,))  # a new id still inserts
    assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 2


BAD_INSTRUMENTS = [
    ("EQ_US_X", "BOND", "USD", "XNAS", "America/New_York", "ACTIVE", "2020-01-01", None),
    ("EQ_US_X", "EQUITY", "USDX", "XNAS", "America/New_York", "ACTIVE", "2020-01-01", None),
    ("EQ_US_X", "EQUITY", "USD", "NASDAQ", "America/New_York", "ACTIVE", "2020-01-01", None),
    ("EQ_US_X", "EQUITY", "USD", "XNAS", "America/New_York", "UNKNOWN", "2020-01-01", None),
    ("EQ_US_X", "EQUITY", "USD", "XNAS", "America/New_York", "ACTIVE", "2020-01-01", "2021-01-01"),
    ("EQ_US_X", "EQUITY", "USD", "XNAS", "America/New_York", "DELISTED", "2020-01-01", None),
    ("EQ_US_X", "EQUITY", "USD", "XNAS", "America/New_York", "DELISTED", "2020-01-01", "2019-01-01"),
]


@pytest.mark.postgres
@pytest.mark.parametrize("row", BAD_INSTRUMENTS)
def test_instrument_checks_reject_the_same_rows_as_sqlite(conn, tmp_path, row):
    pg.apply_pg_schema(conn)
    lite = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(lite)
    with pytest.raises(sqlite3.IntegrityError):
        lite.execute("INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row)
    lite.close()
    pg_row = (*row[:6], date.fromisoformat(row[6]), date.fromisoformat(row[7]) if row[7] else None)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO instruments VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", pg_row)


@pytest.mark.unit
def test_advisory_lock_keys_are_deterministic_signed_64_bit_and_ordered():
    a = pg.advisory_key("map-symbol|yfinance|NVDA")
    assert a == pg.advisory_key("map-symbol|yfinance|NVDA") and -(2**63) <= a < 2**63
    assert a != pg.advisory_key("map-symbol|yfinance|NVDB")
    keys = pg.advisory_keys("map-symbol|yfinance|NVDA", "map-instrument|yfinance|EQ_US_NVDA")
    assert keys == sorted(keys) and len(keys) == 2
    assert pg.advisory_keys("x", "x") == [pg.advisory_key("x")]
