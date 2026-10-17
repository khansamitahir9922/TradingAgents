"""The Admin CLI's intents approve, decline and expire commands (docs/tasks/M3-13.md)."""

from datetime import date, timedelta

import pytest
from typer.testing import CliRunner

from investment_engine.clock import ReplayClock
from investment_engine.config import ENV_PG_DSN
from investment_engine.oms.intents import IntentState
from investment_engine.policy.accounts import AccountKind, Role
from tests.engine.test_intent_pipeline import CAL, LIVE, NOW, OWNER, Env, t_of, view_for, write_bars

pytestmark = pytest.mark.postgres
RUNNER = CliRunner()
SESSIONS_2021 = [s.date for s in CAL.sessions_between(date(2021, 1, 4), date(2021, 6, 30))]
DAY_2021 = SESSIONS_2021[60]


def _cli(monkeypatch, dsn, tmp_path, now):
    from investment_engine import admin_cli, cli

    monkeypatch.setenv(ENV_PG_DSN, dsn)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(admin_cli, "LiveClock", lambda: ReplayClock(now))
    monkeypatch.setattr(admin_cli, "_os_user", lambda: "LOQ")
    return cli


def run(cli, *args):
    result = RUNNER.invoke(cli.app, [str(a) for a in args])
    assert all(ord(ch) < 128 for ch in result.output), "CLI output is plain ASCII"
    return result


def operators(env):
    env.stores.accounts.add_operator("trader", Role.TRADER, by=OWNER, reason="added today")
    env.stores.accounts.add_operator("viewer", Role.VIEWER, by=OWNER, reason="v")
    env.stores.accounts.add_operator("gone", Role.TRADER, by=OWNER, reason="g")
    env.stores.accounts.deactivate_operator("gone", by=OWNER, reason="deactivated today")


@pytest.fixture
def research(pg_database, tmp_path, monkeypatch):
    """A 2021 research replay: accounts A and B, each with an intent awaiting approval; operators added today."""
    env = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "market", SESSIONS_2021))
    operators(env)
    intents = {}
    for account, day in (("A", DAY_2021), ("B", SESSIONS_2021[80])):
        env.account(account)
        record = env.propose(account, view_for(env.stores, env.reader, day, tag=account))
        assert record.outcome.value == "AWAITING_APPROVAL"
        intents[account] = env.stores.intents.get(record.intent_id)
    yield env, _cli(monkeypatch, pg_database, tmp_path, NOW), intents
    env.close()


def state(env, stored):
    return env.stores.intents.get(stored.intent.intent_id).state


@pytest.mark.unit
def test_an_operator_added_today_approves_a_2021_intent_before_its_simulated_deadline(research):
    env, cli, intents = research
    a = intents["A"]
    at = a.intent.created_at + timedelta(hours=1)
    result = run(cli, "intents", "approve", a.intent.intent_id, "--version", 1, "--operator", "trader",
                 "--at", at.isoformat())
    assert result.exit_code == 0, result.output
    i = a.intent
    for text in ("SIMULATED (replay time)", f"intent {i.intent_id} v1", f"{i.side} {i.quantity} {i.instrument_id}",
                 f"reference {i.reference_price} USD", f"target session {i.target_session}", "policy: PASSED",
                 "risk: APPROVE", "approval deadline", "exchange)", "APPROVED (SIMULATED (replay time)) by trader",
                 f"at {at.isoformat()}", f"recorded {NOW.isoformat()} (real command time)",
                 "No order is created in M3."):
        assert text in result.output, text
    assert state(env, a) is IntentState.APPROVED
    (event,) = [e for e in env.stores.audit.for_target("intent", i.intent_id) if e.action == "intent.approved"]
    assert event.at == NOW and event.business_at == at and event.actor.os_user == "LOQ"


@pytest.mark.unit
@pytest.mark.parametrize("operator, why", [("gone", "not an active operator now"), ("viewer", "may not approve")])
def test_an_inactive_operator_or_a_viewer_is_refused_whatever_the_replay_time(research, operator, why):
    env, cli, intents = research
    a = intents["A"]
    early = a.intent.created_at + timedelta(minutes=1)  # 2021: long before "gone" was deactivated
    result = run(cli, "intents", "approve", a.intent.intent_id, "--version", 1, "--operator", operator,
                 "--at", early.isoformat())
    assert result.exit_code == 1 and "Refused:" in result.output and why in result.output
    assert state(env, a) is IntentState.AWAITING_APPROVAL
    (refusal,) = [e for e in env.stores.audit.for_target("intent", a.intent.intent_id)
                  if e.action == "intent.approve_refused"]
    assert refusal.at == NOW and refusal.business_at == early


@pytest.mark.unit
def test_a_research_approval_needs_a_replay_time_and_the_exact_version(research):
    env, cli, intents = research
    a = intents["A"]
    missing = run(cli, "intents", "approve", a.intent.intent_id, "--version", 1, "--operator", "trader")
    assert missing.exit_code != 0 and "needs --at" in missing.output
    no_version = run(cli, "intents", "approve", a.intent.intent_id, "--operator", "trader", "--at",
                     a.intent.created_at.isoformat())
    assert no_version.exit_code == 1 and "--version N is required" in no_version.output
    wrong = run(cli, "intents", "approve", a.intent.intent_id, "--version", 2, "--operator", "trader", "--at",
                a.intent.created_at.isoformat())
    assert wrong.exit_code == 1 and "not the latest version" in wrong.output
    assert state(env, a) is IntentState.AWAITING_APPROVAL


@pytest.mark.unit
def test_decline_needs_a_reason_and_is_recorded(research):
    env, cli, intents = research
    a = intents["A"]
    at = (a.intent.created_at + timedelta(minutes=5)).isoformat()
    no_reason = run(cli, "intents", "decline", a.intent.intent_id, "--version", 1, "--operator", "trader", "--at", at)
    assert no_reason.exit_code == 1 and "needs a reason" in no_reason.output
    assert state(env, a) is IntentState.AWAITING_APPROVAL
    blank = run(cli, "intents", "decline", a.intent.intent_id, "--version", 1, "--operator", "trader", "--at", at,
                "--reason", " ")
    assert blank.exit_code == 1 and "needs a reason" in blank.output
    done = run(cli, "intents", "decline", a.intent.intent_id, "--version", 1, "--operator", "trader", "--at", at,
               "--reason", "not convinced")
    assert done.exit_code == 0 and "DECLINED (SIMULATED (replay time))" in done.output
    assert "not convinced" in done.output and state(env, a) is IntentState.DECLINED


@pytest.mark.unit
def test_expire_changes_only_the_named_research_account_and_paper_never_touches_research(research):
    env, cli, intents = research
    a, b = intents["A"], intents["B"]
    b_events = env.stores.audit.for_target("intent", b.intent.intent_id)
    no_at = run(cli, "intents", "expire", "--account", "A")
    assert no_at.exit_code != 0 and "needs --at" in no_at.output
    result = run(cli, "intents", "expire", "--account", "A", "--at", a.approval_deadline.isoformat())
    assert result.exit_code == 0 and f"EXPIRED intent {a.intent.intent_id} v1" in result.output
    assert "1 intent(s) expired" in result.output
    assert state(env, a) is IntentState.EXPIRED and state(env, b) is IntentState.AWAITING_APPROVAL
    assert env.stores.audit.for_target("intent", b.intent.intent_id) == b_events
    paper = run(cli, "intents", "expire", "--paper")  # live time is far past B's 2021 deadline
    assert paper.exit_code == 0 and "0 intent(s) expired" in paper.output
    assert state(env, b) is IntentState.AWAITING_APPROVAL
    both = run(cli, "intents", "expire", "--paper", "--account", "B")
    assert both.exit_code != 0 and state(env, b) is IntentState.AWAITING_APPROVAL


@pytest.mark.unit
def test_paper_refuses_a_supplied_time_for_approval_and_expiry(pg_database, tmp_path, monkeypatch):
    day = SESSIONS_2021[60]
    live = t_of(day)
    env = Env(pg_database, tmp_path / "market", now=live,
              reader=write_bars(tmp_path / "market", SESSIONS_2021))
    try:
        operators(env)
        env.account("P1", kind=AccountKind.PAPER)
        record = env.propose("P1", view_for(env.stores, env.reader, day), at=LIVE)  # PAPER: no promotion yet
        cli = _cli(monkeypatch, pg_database, tmp_path, live)
        supplied = run(cli, "intents", "approve", record.intent_id, "--version", 1, "--operator", "trader", "--at",
                       live.isoformat())
        assert supplied.exit_code == 1 and "--at is refused" in supplied.output  # even when it equals live time
        at_live = run(cli, "intents", "approve", record.intent_id, "--version", 1, "--operator", "trader")
        assert at_live.exit_code == 1 and "POLICY_REJECTED, not AWAITING_APPROVAL" in at_live.output
        refusals = [e for e in env.stores.audit.for_target("intent", record.intent_id)
                    if e.action == "intent.approve_refused"]
        assert len(refusals) == 2 and all(e.business_at is None for e in refusals)
        expire = run(cli, "intents", "expire", "--account", "P1", "--at", live.isoformat())
        assert expire.exit_code != 0 and "--at is refused" in expire.output
        assert "0 intent(s) expired" in run(cli, "intents", "expire", "--account", "P1").output
    finally:
        env.close()
