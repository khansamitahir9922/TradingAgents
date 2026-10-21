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
