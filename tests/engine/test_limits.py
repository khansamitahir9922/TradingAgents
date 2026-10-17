"""Versioned risk limits, policy rules and drawdown halts (docs/tasks/M3-06.md)."""

import json
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.resources import files

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.policy.accounts import AccountKind, AccountRegistry, NotAuthorized, Role
from investment_engine.policy.rules import PolicyRules
from investment_engine.risk.limits import LimitStore, NoLimits, load_limits_file
from investment_engine.storage.database import AppendOnlyViolation, PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
T2019 = datetime(2019, 1, 2, 21, tzinfo=UTC)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")
TRADER = Actor(ActorKind.OPERATOR, "trader", "TRADER", None)
PROPOSED = files("investment_engine.risk").joinpath("proposed_limits.json")


@pytest.fixture
def env(pg_database):
    conn = open_operational_pg(pg_database)
    db = PostgresDatabase(conn)
    apply_pg_schema(conn)
    clock = ReplayClock(NOW)
    audit = AuditStore(db)
    accounts = AccountRegistry(db, audit, clock)
    accounts.bootstrap_admin("owner", os_user="LOQ")
    accounts.add_operator("trader", Role.TRADER, by=OWNER, reason="t")
    accounts.create_account("P1", AccountKind.PAPER, "USD", by=OWNER, reason="paper")
    accounts.create_account("R1", AccountKind.RESEARCH, "USD", by=OWNER, reason="demo", effective_at=T2019)
    store = LimitStore(db, audit, accounts, clock)
    yield store, db, clock, audit
    conn.close()


def publish_proposed(store, account="P1", **kw):
    risk, policy = load_limits_file(PROPOSED.read_text(encoding="utf-8"))
    return (store.publish_risk(account, risk, by=OWNER, reason="proposal D1-D9, D13", **kw),
            store.publish_policy(account, policy, by=OWNER, reason="proposal D7, D8, D12, D13", **kw))


@pytest.mark.unit
def test_without_published_limits_lookups_raise_and_the_proposed_file_gives_the_d_values(env):
    store, *_ = env
    with pytest.raises(NoLimits):
        store.risk_at("P1", NOW)
    with pytest.raises(NoLimits):
        store.policy_at("P1", NOW)
    risk, policy = publish_proposed(store)
    assert risk.version == "risk-1" and policy.version == "policy-1"
    assert (risk.max_position_fraction, risk.max_gross_exposure_fraction, risk.long_only,
            risk.drawdown_halt_fraction, risk.max_order_adv_fraction, risk.adv_sessions,
            risk.max_new_buys_per_session, risk.min_price, risk.min_quantity) == (
        Decimal("0.10"), Decimal("1.00"), True, Decimal("0.15"), Decimal("0.01"), 20, 5, Decimal("5"), Decimal("1"))
    assert (policy.restricted, policy.session, policy.order_type, policy.time_in_force, policy.limit_band_fraction,
            policy.view_timeframes) == ((), "REGULAR_ONLY", "LIMIT", "DAY", Decimal("0.01"), ("D1",))
    assert store.risk_at("P1", NOW) == risk and store.policy_at("P1", NOW) == policy
    header = json.loads(PROPOSED.read_text(encoding="utf-8"))["header"]
    assert "D1" in header and "D13" in header and "explicit" in header


@pytest.mark.unit
def test_versions_answer_what_was_effective_and_never_change(env):
    store, db, clock, _ = env
    first, _ = publish_proposed(store)
    clock.advance_by(timedelta(hours=1))
    risk, _ = load_limits_file(PROPOSED.read_text(encoding="utf-8"))
    second = store.publish_risk("P1", {**risk, "max_position_fraction": Decimal("0.05")}, by=OWNER, reason="tighter")
    assert second.version == "risk-2"
    assert store.risk_at("P1", NOW) == first and store.risk_at("P1", NOW + timedelta(hours=2)) == second
    for statement in ("UPDATE risk_limit_versions SET effective_at = effective_at",
                      "DELETE FROM risk_limit_versions", "TRUNCATE policy_rule_versions", "TRUNCATE halts"):  # empty: statement trigger
        with pytest.raises(AppendOnlyViolation):
            db.execute(statement)


@pytest.mark.unit
@pytest.mark.parametrize("text, message", [
    ('{"risk": {"max_position_fraction": 0.1}}', "float"),
    ('{"header": "x", "risk": {}, "policy": {}, "extra": 1}', "unknown"),
])
def test_files_with_floats_or_unknown_keys_are_refused(text, message):
    with pytest.raises(ValueError, match=message):
        load_limits_file(text)


@pytest.mark.unit
@pytest.mark.parametrize("change, message", [
    ({"max_position_fraction": Decimal("0")}, "max_position_fraction"),
    ({"max_position_fraction": Decimal("1.5")}, "max_position_fraction"),
    ({"max_gross_exposure_fraction": Decimal("1.01")}, "max_gross_exposure_fraction"),
    ({"long_only": False}, "long_only"),
    ({"adv_sessions": 0}, "adv_sessions"),
    ({"max_new_buys_per_session": -1}, "max_new_buys_per_session"),
    ({"min_quantity": Decimal("0.5")}, "whole shares"),
    ({"unknown_key": 1}, "unknown"),
    ({"min_price": 5.0}, "Decimal"),
])
def test_each_risk_validation_refusal_publishes_nothing_and_writes_no_event(env, change, message):
    store, db, *_ = env
    risk, _ = load_limits_file(PROPOSED.read_text(encoding="utf-8"))
    before = db.fetchone("SELECT COUNT(*) FROM audit_events")[0]
    with pytest.raises((ValueError, TypeError), match=message):
        store.publish_risk("P1", {**risk, **change}, by=OWNER, reason="bad")
    assert db.fetchone("SELECT COUNT(*) FROM risk_limit_versions")[0] == 0
    assert db.fetchone("SELECT COUNT(*) FROM audit_events")[0] == before


@pytest.mark.unit
def test_policy_rules_normalize_sets_into_sorted_tuples():
    base = {"session": "REGULAR_ONLY", "order_type": "LIMIT", "time_in_force": "DAY",
            "limit_band_fraction": Decimal("0.01")}
    a = PolicyRules("policy-1", ("EQ_US_NVDA", "EQ_US_AMD", "EQ_US_NVDA"), view_timeframes=("D1", "D1"), **base)
    b = PolicyRules("policy-1", ("EQ_US_AMD", "EQ_US_NVDA"), view_timeframes=("D1",), **base)
    assert a == b and a.restricted == ("EQ_US_AMD", "EQ_US_NVDA")
    with pytest.raises(ValueError, match="H1"):
        PolicyRules("policy-1", (), view_timeframes=("D1", "H1"), **base)  # D12: hourly not set


@pytest.mark.unit
def test_restricted_add_and_remove_publish_new_policy_versions_with_events(env):
    store, db, clock, audit = env
    publish_proposed(store)
    clock.advance_by(timedelta(minutes=1))
    added = store.restrict("P1", "EQ_US_NVDA", by=OWNER, reason="earnings blackout")
    assert added.version == "policy-2" and added.restricted == ("EQ_US_NVDA",)
    clock.advance_by(timedelta(minutes=1))
    removed = store.unrestrict("P1", "EQ_US_NVDA", by=OWNER, reason="lifted")
    assert removed.version == "policy-3" and removed.restricted == ()
    assert store.policy_at("P1", NOW + timedelta(seconds=90)).restricted == ("EQ_US_NVDA",)
    actions = [e.action for e in audit.for_target("account", "P1")]
    assert actions.count("policy.publish") == 3 and actions.count("risk.publish") == 1
    with pytest.raises(NotAuthorized):
        store.restrict("P1", "EQ_US_AMD", by=TRADER, reason="no")


@pytest.mark.unit
def test_a_halt_is_latched_until_an_admin_clears_it_and_clearing_resets_the_baseline(env):
    store, db, clock, audit = env
    risk, _ = publish_proposed(store)
    halt = store.set_halt("P1", at=NOW, limits_version=risk.version, reason="drawdown 16% >= 15%")
    assert halt.halted and store.halt_at("P1", NOW + timedelta(days=3)).halted  # recovery doesn't clear it
    with pytest.raises(NotAuthorized):
        store.clear_halt("P1", by=TRADER, reason="no", equity_now=Decimal("99000"))
    clock.advance_by(timedelta(days=3))
    cleared = store.clear_halt("P1", by=OWNER, reason="reviewed", equity_now=Decimal("84000"))
    assert not cleared.halted and cleared.baseline_equity == Decimal("84000")
    assert store.halt_at("P1", NOW + timedelta(days=4)) == cleared
    assert store.halt_at("P1", NOW - timedelta(days=1)) is None
    halt_events = [e.action for e in audit.for_target("account", "P1") if e.action.startswith("risk.") and "halt" in e.action]
    assert halt_events == ["risk.halt", "risk.clear_halt"]  # equal command times order by id, so filter


@pytest.mark.unit
def test_research_limits_are_effective_in_replay_time_and_paper_refuses_a_backdate(env):
    store, *_ = env
    risk, policy = publish_proposed(store, "R1", effective_at=T2019)
    assert store.risk_at("R1", T2019 + timedelta(days=365)) == risk
    with pytest.raises(NoLimits):
        store.risk_at("R1", T2019 - timedelta(days=1))
    with pytest.raises(ValueError, match="backdate"):
        publish_proposed(store, "P1", effective_at=T2019)
    with pytest.raises(ValueError, match="effective_at"):
        publish_proposed(store, "R1")


@pytest.mark.unit
def test_concurrent_publishes_get_consecutive_versions(pg_database, env):
    store, db, clock, _ = env
    risk, _ = load_limits_file(PROPOSED.read_text(encoding="utf-8"))
    conns = [open_operational_pg(pg_database) for _ in range(4)]
    stores = []
    for c in conns:
        d = PostgresDatabase(c)
        audit = AuditStore(d)
        stores.append(LimitStore(d, audit, AccountRegistry(d, audit, ReplayClock(NOW)), ReplayClock(NOW)))
    barrier, versions = threading.Barrier(4), []

    def run(s):
        barrier.wait()
        versions.append(s.publish_risk("P1", risk, by=OWNER, reason="race").version)

    threads = [threading.Thread(target=run, args=(s,)) for s in stores]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(versions) == ["risk-1", "risk-2", "risk-3", "risk-4"]
    for c in conns:
        c.close()


# ---------------------------------------------------------------- concurrent restricted-list changes (Codex B1)


def _gated_store(pg_database, barrier, opened):
    """A LimitStore on its own connection whose first account-control lock waits at `barrier`: both racers have
    done everything they do before the lock, then race for it."""
    conn = open_operational_pg(pg_database)
    opened.append(conn)
    db = PostgresDatabase(conn)
    real, first = db.lock, [True]

    def lock(*names):
        if first[0] and any(n.startswith("account-control|") for n in names):
            first[0] = False
            barrier.wait(30)
        real(*names)

    db.lock = lock
    audit = AuditStore(db)
    return LimitStore(db, audit, AccountRegistry(db, audit, ReplayClock(NOW)), ReplayClock(NOW))


@pytest.mark.unit
@pytest.mark.parametrize("start, changes, final", [
    ((), (("EQ_US_NVDA", True), ("EQ_US_AMD", True)), ("EQ_US_AMD", "EQ_US_NVDA")),
    (("EQ_US_NVDA",), (("EQ_US_AMD", True), ("EQ_US_NVDA", False)), ("EQ_US_AMD",)),
], ids=["add-add", "add-remove"])
def test_concurrent_restriction_changes_both_survive(pg_database, env, start, changes, final):
    store, db, _, audit = env
    publish_proposed(store)
    for instrument in start:
        store.restrict("P1", instrument, by=OWNER, reason="start")
    for rep in range(20):
        if rep:  # back to the starting list, as an ordinary change
            current = set(store.policy_at("P1", NOW).restricted)
            for instrument in sorted(current - set(start)):
                store.unrestrict("P1", instrument, by=OWNER, reason="reset")
            for instrument in sorted(set(start) - current):
                store.restrict("P1", instrument, by=OWNER, reason="reset")
        barrier, opened, errors = threading.Barrier(2), [], []
        racers = [_gated_store(pg_database, barrier, opened) for _ in changes]

        def run(s, instrument, add, rep=rep, errors=errors):
            try:
                (s.restrict if add else s.unrestrict)("P1", instrument, by=OWNER, reason=f"race {rep}")
            except Exception as exc:  # surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(s, *change)) for s, change in zip(racers, changes,
                                                                                         strict=True)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        for c in opened:
            c.close()
        assert not errors, (rep, errors)
        assert store.policy_at("P1", NOW).restricted == final, rep  # neither change was lost
    # Every published version is exactly its predecessor plus or minus one instrument: no version was built on a
    # stale read.
    events = [e.after for e in audit.for_target("account", "P1") if e.action == "policy.publish"]
    published = [r.restricted for r in sorted(events, key=lambda r: int(r.version.split("-")[1]))]
    for before, after in zip(published, published[1:], strict=False):
        assert len(set(before) ^ set(after)) == 1, (before, after)


# ---------------------------------------------------------------- clearing a halt records its equity (Codex B4)


@pytest.mark.unit
def test_clearing_requires_the_equity_at_the_clear_and_its_epoch_survives_a_later_halt(env):
    store, _, clock, _ = env
    publish_proposed(store)
    store.set_halt("P1", at=NOW, limits_version="risk-1", reason="drawdown 15.0%")
    with pytest.raises(TypeError):
        store.clear_halt("P1", by=OWNER, reason="no equity given")  # required, not optional (D3)
    for missing in (None, Decimal("NaN"), 85000):
        with pytest.raises(TypeError, match="equity at the clear"):
            store.clear_halt("P1", by=OWNER, reason="unknown equity", equity_now=missing)
    assert store.halt_at("P1", NOW).halted and store.last_clear_at("P1", NOW) is None  # nothing was cleared
    cleared = store.clear_halt("P1", by=OWNER, reason="reviewed", equity_now=Decimal("85000"))
    assert cleared.baseline_equity == Decimal("85000") and store.last_clear_at("P1", NOW) == cleared
    clock.advance_by(timedelta(hours=1))
    store.set_halt("P1", at=clock.now(), limits_version="risk-1", reason="drawdown again")
    assert store.halt_at("P1", clock.now()).halted
    assert store.last_clear_at("P1", clock.now()) == cleared  # the re-halt doesn't end the clear's epoch


# ---------------------------------------------------------------- fresh-process decoding and the Admin CLI


@pytest.mark.unit
def test_a_fresh_process_decodes_limit_and_halt_events_through_the_registry(env, pg_database):
    import os
    import subprocess
    import sys
    from pathlib import Path

    store, db, clock, audit = env
    risk, policy = publish_proposed(store)
    store.restrict("P1", "EQ_US_NVDA", by=OWNER, reason="non-empty list")
    store.set_halt("P1", at=NOW, limits_version=risk.version, reason="drawdown")
    probe = (
        "import json, os, sys\n"
        "from investment_engine.audit.events import AuditStore\n"
        "from investment_engine.storage.database import PostgresDatabase\n"
        "from investment_engine.storage.postgres import open_operational_pg\n"
        "events = AuditStore(PostgresDatabase(open_operational_pg(os.environ['IE_PROBE_DSN']))).for_target('account', 'P1')\n"
        "print(json.dumps(sorted({type(e.after).__name__ for e in events})))\n"
        "print(json.dumps(sorted({tuple(e.after.restricted) for e in events if hasattr(e.after, 'restricted')})))\n"
    )
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120,
                         cwd=root, env={**os.environ, "IE_PROBE_DSN": pg_database, "PYTHONPATH": str(root)})
    assert out.returncode == 0, out.stderr.splitlines()[-1:]
    kinds, lists = out.stdout.splitlines()
    assert json.loads(kinds) == ["Halt", "PolicyRules", "RiskLimits", "tuple"]
    assert json.loads(lists) == [[], ["EQ_US_NVDA"]]


@pytest.fixture
def cli(pg_database, monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from investment_engine import admin_cli, cli
    from investment_engine.config import ENV_PG_DSN

    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(admin_cli, "LiveClock", lambda: ReplayClock(NOW))
    runner = CliRunner()

    def run(*args):
        result = runner.invoke(cli.app, list(args))
        assert all(ord(ch) < 128 for ch in result.output)
        return result

    assert run("init").exit_code == 0
    assert run("operators", "bootstrap-admin", "owner").exit_code == 0
    assert run("accounts", "create", "R1", "--kind", "RESEARCH", "--operator", "owner", "--reason", "demo",
               "--effective-at", "2019-01-02T21:00:00Z").exit_code == 0
    return run


@pytest.mark.unit
def test_the_cli_publishes_the_packaged_proposal_and_shows_it(cli):
    published = cli("limits", "publish", "R1", "--operator", "owner", "--reason", "D1-D9, D13",
                    "--effective-at", "2019-01-02T21:00:00Z")
    assert published.exit_code == 0, published.output
    assert "risk-1" in published.output and "policy-1" in published.output
    shown = cli("limits", "show", "R1", "--at", "2020-01-01T00:00:00Z")
    for text in ("position <= 0.10", "drawdown halt at 0.15", "20-session ADV", "<= 5 new buys/session",
                 "REGULAR_ONLY LIMIT DAY", "band 0.01", "timeframes D1", "restricted none", "halt: none"):
        assert text in shown.output
    early = cli("limits", "show", "R1", "--at", "2018-01-01T00:00:00Z")
    assert early.exit_code != 0 and "no risk limit versions are effective" in early.output


@pytest.mark.unit
def test_the_cli_restricts_and_refuses_bad_files(cli, tmp_path):
    cli("limits", "publish", "R1", "--operator", "owner", "--reason", "p", "--effective-at", "2019-01-02T21:00:00Z")
    added = cli("restricted", "add", "R1", "EQ_US_NVDA", "--operator", "owner", "--reason", "blackout",
                "--effective-at", "2019-02-01T21:00:00Z")
    assert added.exit_code == 0 and "policy-2: restricted EQ_US_NVDA" in added.output
    bad = tmp_path / "bad.json"
    bad.write_text('{"risk": {"max_position_fraction": 0.1}}', encoding="utf-8")
    refused = cli("limits", "publish", "R1", "--file", str(bad), "--operator", "owner", "--reason", "bad",
                  "--effective-at", "2019-03-01T21:00:00Z")
    assert refused.exit_code != 0 and "floats are refused" in refused.output


@pytest.mark.unit
def test_the_cli_clears_a_halt_at_the_equity_valued_at_the_clear(cli, pg_database):
    cli("limits", "publish", "R1", "--operator", "owner", "--reason", "p", "--effective-at", "2019-01-02T21:00:00Z")
    conn = open_operational_pg(pg_database)
    try:
        db = PostgresDatabase(conn)
        audit = AuditStore(db)
        store = LimitStore(db, audit, AccountRegistry(db, audit, ReplayClock(NOW)), ReplayClock(NOW))
        store.set_halt("R1", at=datetime(2019, 2, 1, 21, tzinfo=UTC), limits_version="risk-1", reason="drawdown")
        at = "2019-03-01T21:00:00Z"
        clear = ("limits", "clear-halt", "R1", "--operator", "owner", "--reason", "reviewed", "--effective-at", at)
        refused = cli(*clear)  # no declared start: the equity at the clear can't be established
        assert refused.exit_code != 0 and "starting state" in refused.output
        when = datetime(2019, 3, 1, 21, tzinfo=UTC)
        assert store.halt_at("R1", when).halted and store.last_clear_at("R1", when) is None
        no_time = cli("limits", "clear-halt", "R1", "--operator", "owner", "--reason", "reviewed")
        assert no_time.exit_code != 0 and "--effective-at" in no_time.output
        assert cli("accounts", "declare-start", "R1", "--operator", "owner", "--reason", "D14",
                   "--effective-at", "2019-01-02T21:00:00Z").exit_code == 0
        cleared = cli(*clear)
        assert cleared.exit_code == 0, cleared.output
        assert "equity 100000" in cleared.output and "valued at the clear" in cleared.output
        assert store.last_clear_at("R1", when).baseline_equity == Decimal("100000")
    finally:
        conn.close()
