"""M5-11: read-only command registration and narrow Admin writes."""
import json

import pytest
from typer.testing import CliRunner

from investment_engine.cli import app

runner = CliRunner()


def test_accounting_and_admin_groups_are_registered():
    for group in ("accounting", "ledger", "incidents"):
        value = runner.invoke(app, [group, "--help"])
        assert value.exit_code == 0, value.output


def test_report_command_opens_read_only_and_never_migrates_or_synchronizes(monkeypatch):
    from investment_engine import accounting_cli
    observed = []
    class Connection:
        def close(self): observed.append("closed")
    class Report:
        def to_json(self): return json.dumps({"label": "LEDGER | SIMULATED | RESEARCH | NOT PROMOTED"})
    def open_db(*, read_only):
        observed.append(read_only)
        return Connection(), object()
    monkeypatch.setattr("investment_engine.cli._open_db", open_db)
    monkeypatch.setattr(accounting_cli, "read_report", lambda *a, **kw: Report())
    result = runner.invoke(app, ["accounting", "report", "R1", "--book", "pinned-book", "--effective-at",
        "2024-01-02T00:00:00Z", "--known-at", "2024-01-02T00:00:00Z", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert observed == [True, "closed"]
    assert "NOT PROMOTED" in result.output


@pytest.mark.postgres
def test_viewer_cannot_activate_or_publish_opening_balances(pg_database, monkeypatch):
    from investment_engine.policy.accounts import Role
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from tests.engine.test_reconciliation_incidents import OWNER, Env
    e = Env(pg_database)
    try:
        e.accounts.add_operator("viewer", Role.VIEWER, by=OWNER, reason="read-only operator")
        before = e.db.fetchone("SELECT count(*) FROM ledger_entries")[0]
        def open_db(*, read_only):
            assert not read_only
            conn = open_operational_pg(pg_database)
            return conn, PostgresDatabase(conn)
        monkeypatch.setattr("investment_engine.cli._open_db", open_db)
        result = runner.invoke(app, ["ledger", "activate", "R1", "--operator", "viewer", "--reason", "not authorized",
                                    "--at", e.clock.now().isoformat()])
        assert result.exit_code == 1 and "NotAuthorized" in result.output
        assert e.db.fetchone("SELECT count(*) FROM ledger_entries")[0] == before
        allowed = runner.invoke(app, ["ledger", "activate", "R1", "--operator", "owner", "--reason", "explicit retry",
                                      "--at", e.clock.now().isoformat()])
        assert allowed.exit_code == 0 and "LEDGER activated" in allowed.output
        assert e.db.fetchone("SELECT count(*) FROM ledger_entries")[0] == before
    finally:
        e.conn.close()


@pytest.mark.postgres
def test_real_read_only_report_keeps_all_accounting_counts_unchanged(pg_database, monkeypatch):
    from investment_engine.storage.database import PostgresDatabase
    from investment_engine.storage.postgres import open_operational_pg
    from tests.engine.test_reconciliation_incidents import Env
    e = Env(pg_database)
    try:
        tables = ("ledger_batches", "ledger_transactions", "ledger_entries", "audit_events", "outbox",
                  "reconciliation_results", "reconciliation_transitions")
        before = tuple(e.db.fetchone("SELECT count(*) FROM " + t)[0] for t in tables)
        book = e.ledger.read_head("R1", known_at=e.clock.now())
        def open_db(*, read_only):
            assert read_only
            conn = open_operational_pg(pg_database)
            conn.execute("SET default_transaction_read_only=on")
            return conn, PostgresDatabase(conn)
        monkeypatch.setattr("investment_engine.cli._open_db", open_db)
        result = runner.invoke(app, ["accounting", "report", "R1", "--book", book.book_id, "--effective-at",
            e.clock.now().isoformat(), "--known-at", e.clock.now().isoformat(), "--format", "json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["metrics"]["cash"] == "100"
        assert tuple(e.db.fetchone("SELECT count(*) FROM " + t)[0] for t in tables) == before
    finally:
        e.conn.close()
