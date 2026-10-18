"""The Admin CLI's kill-switch commands (docs/tasks/M4-04.md rules 3, 5, 7, 9; PRD UC-06)."""

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.config import ENV_PG_DSN
from investment_engine.policy.accounts import AccountRegistry, Role
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")
RUNNER = CliRunner()


@pytest.fixture
def cli(pg_database, tmp_path, monkeypatch):
    from investment_engine import admin_cli, cli

    conn = open_operational_pg(pg_database)
    apply_pg_schema(conn)
    db = PostgresDatabase(conn)
    registry = AccountRegistry(db, AuditStore(db), ReplayClock(NOW))
    registry.bootstrap_admin("owner", os_user="LOQ")
    registry.add_operator("trader", Role.TRADER, by=OWNER, reason="t")
    registry.add_operator("viewer", Role.VIEWER, by=OWNER, reason="v")
    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(admin_cli, "LiveClock", lambda: ReplayClock(NOW))
    yield cli, db
    conn.close()


def run(cli, *args):
    result = RUNNER.invoke(cli.app, list(args))
    assert all(ord(ch) < 128 for ch in result.output), "CLI output is plain ASCII"
    return result


def audited(db):
    return sorted((e.action, e.idempotency_key) for e in AuditStore(db).for_target("kill_switch", "trading"))


@pytest.mark.unit
def test_an_admin_halts_and_resumes_each_audited_once(cli):
    app, db = cli
    assert "TRADING DISABLED: missing" in run(app, "kill-switch", "status").output
    halt = run(app, "kill-switch", "halt", "--operator", "owner", "--reason", "stop")
    assert halt.exit_code == 0 and "TRADING DISABLED (halted): sequence 1" in halt.output and "Audit: recorded" in halt.output
    resume = run(app, "kill-switch", "resume", "--operator", "owner", "--reason", "go")
    assert resume.exit_code == 0 and "TRADING ENABLED: sequence 2" in resume.output
    assert audited(db) == [("killswitch.halt", "killswitch:1:APPLIED"), ("killswitch.resume", "killswitch:2:APPLIED")]
    assert "TRADING ENABLED: sequence 2" in run(app, "kill-switch", "status").output


@pytest.mark.unit
@pytest.mark.parametrize("operator", ["trader", "viewer", "nobody"])
def test_only_an_admin_may_halt_or_resume(cli, operator):
    app, db = cli
    for command in ("halt", "resume"):
        result = run(app, "kill-switch", command, "--operator", operator, "--reason", "x")
        assert result.exit_code == 1 and "Refused" in result.output and "Nothing was changed" in result.output
    assert "TRADING DISABLED: missing" in run(app, "kill-switch", "status").output
    assert audited(db) == []


@pytest.mark.unit
def test_with_the_database_down_a_halt_applies_unverified_and_a_resume_is_refused(cli, monkeypatch, pg_database):
    app, db = cli
    monkeypatch.delenv(ENV_PG_DSN)
    halt = run(app, "kill-switch", "halt", "--operator", "owner", "--reason", "db down")
    assert halt.exit_code == 0 and "identity unverified" in halt.output and "Audit: pending" in halt.output
    resume = run(app, "kill-switch", "resume", "--operator", "owner", "--reason", "go")
    assert resume.exit_code == 1 and "verified" in resume.output
    status = run(app, "kill-switch", "status").output
    assert "TRADING DISABLED (halted): sequence 1, by owner (identity unverified)" in status
    assert audited(db) == []
    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    synced = run(app, "kill-switch", "sync-audit")
    assert synced.exit_code == 0
    assert audited(db) == [("killswitch.halt", "killswitch:1:APPLIED")]
    run(app, "kill-switch", "sync-audit")
    assert len(audited(db)) == 1  # idempotent
    (event,) = AuditStore(db).for_target("kill_switch", "trading")
    assert "identity unverified" in event.reason and event.actor.kind is ActorKind.PROCESS
