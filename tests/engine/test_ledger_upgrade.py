"""M5-01: populated schema 0015 is upgraded additively."""
from datetime import UTC, datetime

import pytest

from investment_engine.storage import postgres as pg


@pytest.mark.postgres
def test_upgrade_from_populated_0015_preserves_existing_rows(pg_database, monkeypatch):
    conn = pg.open_operational_pg(pg_database)
    try:
        scripts = pg._pg_schema_scripts()
        monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: [(n, s) for n, s in scripts if n <= 15])
        assert pg.apply_pg_schema(conn) == 15
        t = datetime(2024, 1, 2, tzinfo=UTC)
        conn.execute("INSERT INTO accounts VALUES('retained','RESEARCH','USD',%s,%s)", (t, t))
        before = conn.execute("SELECT * FROM accounts ORDER BY account_id").fetchall()
        monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: scripts)
        assert pg.apply_pg_schema(conn) >= 16
        assert conn.execute("SELECT * FROM accounts ORDER BY account_id").fetchall() == before
        assert conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0] == 0
        assert pg.apply_pg_schema(conn) == scripts[-1][0]
    finally:
        conn.close()


@pytest.mark.postgres
@pytest.mark.parametrize("old_version,new_version", [(18, 19), (19, 20)])
def test_payload_seal_upgrades_preserve_books_and_enforce_future_batches(
        pg_database, monkeypatch, old_version, new_version):
    from psycopg import Error as PgError

    from tests.engine.test_ledger_store import _divergent_sql_batch, make_batch, open_store

    scripts = pg._pg_schema_scripts()
    monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: [(n, s) for n, s in scripts if n <= old_version])
    conn, db, store = open_store(pg_database)
    try:
        first = store.append_batch(make_batch())
        tables = ("ledger_batches", "ledger_transactions", "ledger_entries", "ledger_source_receipts")
        before = {table: db.fetchall(f"SELECT * FROM {table} ORDER BY 1") for table in tables}
        monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: [(n, s) for n, s in scripts if n <= new_version])
        assert pg.apply_pg_schema(conn) == new_version
        assert {table: db.fetchall(f"SELECT * FROM {table} ORDER BY 1") for table in tables} == before
        assert store.get(first.book_id) == first
        from investment_engine.storage.database import IntegrityViolation
        with pytest.raises((IntegrityViolation, PgError), match="payload/manifest"):
            _divergent_sql_batch(db, first, "transaction")
    finally:
        conn.close()
