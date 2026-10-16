"""The Admin CLI's accounts and operators commands (docs/tasks/M3-05.md rule 7)."""

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from investment_engine.clock import ReplayClock
from investment_engine.config import ENV_PG_DSN

pytestmark = pytest.mark.postgres
RUNNER = CliRunner()
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


@pytest.fixture
def cli(pg_database, monkeypatch, tmp_path):
    from investment_engine import admin_cli, cli

    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(admin_cli, "LiveClock", lambda: ReplayClock(NOW))
    monkeypatch.setattr(admin_cli, "_os_user", lambda: "LOQ")
    assert RUNNER.invoke(cli.app, ["init"]).exit_code == 0
    return cli


def run(cli, *args):
    result = RUNNER.invoke(cli.app, list(args))
    assert all(ord(ch) < 128 for ch in result.output), "CLI output is plain ASCII"
    return result


@pytest.mark.unit
def test_bootstrap_add_and_list_operators(cli):
    assert run(cli, "operators", "bootstrap-admin", "owner").exit_code == 0
    again = run(cli, "operators", "bootstrap-admin", "second")
    assert again.exit_code != 0 and "only once" in again.output
    assert run(cli, "operators", "add", "trader", "--role", "TRADER", "--operator", "owner",
               "--reason", "trader").exit_code == 0
    listed = run(cli, "operators", "list")
    assert listed.exit_code == 0 and "owner ADMIN active" in listed.output and "trader TRADER active" in listed.output
    assert run(cli, "operators", "deactivate", "trader", "--operator", "owner", "--reason", "left").exit_code == 0
    assert "trader TRADER inactive" in run(cli, "operators", "list").output


@pytest.mark.unit
def test_research_accounts_take_a_replay_time_and_show_both_times(cli):
    run(cli, "operators", "bootstrap-admin", "owner")
    created = run(cli, "accounts", "create", "R1", "--kind", "RESEARCH", "--operator", "owner", "--reason", "demo",
                  "--effective-at", "2019-01-02T21:00:00Z")
    assert created.exit_code == 0, created.output
    changed = run(cli, "accounts", "set-autonomy", "R1", "--level", "1", "--operator", "owner", "--reason", "demo",
                  "--effective-at", "2019-01-03T21:00:00Z")
    assert changed.exit_code == 0 and "Level 1 (Approved paper)" in changed.output
    shown = run(cli, "accounts", "show", "R1")
    for text in ("R1 RESEARCH", "Level 1 (Approved paper)", "effective 2019-01-03T21:00:00+00:00 (simulated)",
                 "recorded 2026-10-16T12:00:00+00:00"):
        assert text in shown.output
    assert "R1 RESEARCH" in run(cli, "accounts", "list").output


@pytest.mark.unit
def test_paper_refuses_replay_times_and_research_requires_one(cli):
    run(cli, "operators", "bootstrap-admin", "owner")
    backdated = run(cli, "accounts", "create", "P1", "--kind", "PAPER", "--operator", "owner", "--reason", "x",
                    "--effective-at", "2019-01-02T21:00:00Z")
    assert backdated.exit_code != 0 and "backdate" in backdated.output
    missing = run(cli, "accounts", "create", "R1", "--kind", "RESEARCH", "--operator", "owner", "--reason", "x")
    assert missing.exit_code != 0 and "effective_at" in missing.output
    paper = run(cli, "accounts", "create", "P1", "--kind", "PAPER", "--operator", "owner", "--reason", "paper")
    assert paper.exit_code == 0 and "Level 0 (Advisory)" in run(cli, "accounts", "show", "P1").output


@pytest.mark.unit
def test_refusals_change_nothing(cli):
    run(cli, "operators", "bootstrap-admin", "owner")
    run(cli, "operators", "add", "trader", "--role", "TRADER", "--operator", "owner", "--reason", "t")
    refused = run(cli, "accounts", "create", "P1", "--kind", "PAPER", "--operator", "trader", "--reason", "no")
    assert refused.exit_code != 0 and "may not" in refused.output
    level = run(cli, "accounts", "set-autonomy", "P1", "--level", "3", "--operator", "owner", "--reason", "no")
    assert level.exit_code != 0
    assert "no accounts" in run(cli, "accounts", "list").output
