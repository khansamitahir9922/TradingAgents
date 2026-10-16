"""Accounts, operators and autonomy levels (architecture B3; docs/tasks/M3-05.md)."""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.policy.accounts import (
    AccountKind,
    AccountRegistry,
    AutonomySetting,
    NotAuthorized,
    Role,
)
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.conftest import PG_SKIP_REASON, maintenance_dsn, temporary_database

pytestmark = pytest.mark.postgres
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
T2019 = datetime(2019, 1, 2, 21, tzinfo=UTC)


def owner():
    return Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")


@pytest.fixture
def env(pg_database):
    opened = []

    def connect():
        opened.append(open_operational_pg(pg_database))
        return PostgresDatabase(opened[-1])

    db = connect()
    apply_pg_schema(db.connection)
    clock = ReplayClock(NOW)  # stands in for the injected LiveClock: the real command time
    registry = AccountRegistry(db, AuditStore(db), clock)
    registry.bootstrap_admin("owner", os_user="LOQ")
    yield registry, db, clock, connect
    for conn in opened:
        conn.close()


def events(db, target_id):
    return AuditStore(db).for_target("account", target_id) + AuditStore(db).for_target("operator", target_id)


@pytest.mark.unit
def test_a_new_account_starts_advisory_and_levels_3_and_4_are_disabled(env):
    registry, db, *_ = env
    registry.create_account("P1", AccountKind.PAPER, "USD", by=owner(), reason="paper")
    assert registry.autonomy_at("P1", NOW).level == 0
    for level, message in ((3, "disabled in v1"), (4, "disabled in v1"), (-1, "0, 1 or 2"), (5, "0, 1 or 2")):
        with pytest.raises(ValueError, match=message):
            registry.set_autonomy("P1", level, by=owner(), reason="no")
    assert registry.autonomy_at("P1", NOW).level == 0


@pytest.mark.unit
def test_history_answers_the_level_at_any_time_with_sequence_for_equal_times(env):
    registry, db, clock, _ = env
    registry.create_account("R1", AccountKind.RESEARCH, "USD", by=owner(), reason="demo", effective_at=T2019)
    one = registry.set_autonomy("R1", 1, by=owner(), reason="a", effective_at=T2019 + timedelta(days=1))
    two = registry.set_autonomy("R1", 2, by=owner(), reason="b", effective_at=T2019 + timedelta(days=1))
    back = registry.set_autonomy("R1", 1, by=owner(), reason="c", effective_at=T2019 + timedelta(days=2))
    assert registry.autonomy_at("R1", T2019).level == 0
    assert registry.autonomy_at("R1", T2019 + timedelta(days=1)) == two  # equal effective times: sequence decides
    assert registry.autonomy_at("R1", T2019 + timedelta(days=3)) == back
    assert len({one.setting_id, two.setting_id, back.setting_id}) == 3  # 1 -> 2 -> 1 gives three ids
    assert (one.sequence, two.sequence, back.sequence) == (2, 3, 4)
    with pytest.raises(LookupError):
        registry.autonomy_at("R1", T2019 - timedelta(days=1))


@pytest.mark.unit
def test_only_an_active_admin_changes_anything_and_refusals_write_nothing(env):
    registry, db, clock, _ = env
    registry.add_operator("trader", Role.TRADER, by=owner(), reason="t")
    registry.add_operator("viewer", Role.VIEWER, by=owner(), reason="v")
    registry.add_operator("old", Role.ADMIN, by=owner(), reason="o")
    registry.deactivate_operator("old", by=owner(), reason="left")
    before = db.fetchone("SELECT COUNT(*) FROM audit_events")[0]
    for actor in (Actor(ActorKind.OPERATOR, "trader", "TRADER", None),
                  Actor(ActorKind.OPERATOR, "viewer", "VIEWER", None),
                  Actor(ActorKind.OPERATOR, "old", "ADMIN", None),
                  Actor(ActorKind.OPERATOR, "trader", "ADMIN", None),  # claims a role the registry doesn't give
                  Actor(ActorKind.OPERATOR, "nobody", "ADMIN", None),
                  Actor(ActorKind.PROCESS, "core-engine", None, None)):
        with pytest.raises(NotAuthorized):
            registry.create_account("X", AccountKind.PAPER, "USD", by=actor, reason="no")
        with pytest.raises(NotAuthorized):
            registry.add_operator("y", Role.TRADER, by=actor, reason="no")
    assert db.fetchone("SELECT COUNT(*) FROM accounts")[0] == 0
    assert db.fetchone("SELECT COUNT(*) FROM audit_events")[0] == before


@pytest.mark.unit
def test_every_change_writes_one_audit_event_with_before_and_after_in_the_same_transaction(env, monkeypatch):
    registry, db, *_ = env
    registry.create_account("P1", AccountKind.PAPER, "USD", by=owner(), reason="paper")
    setting = registry.set_autonomy("P1", 1, by=owner(), reason="approved paper")
    (created, changed) = AuditStore(db).for_target("account", "P1")
    assert created.action == "account.create" and changed.action == "account.set_autonomy"
    assert created.after[0].account_id == "P1" and created.after[1].level == 0  # the default setting, same event
    assert changed.before.level == 0 and changed.after == setting and changed.business_at is None
    import investment_engine.policy.accounts as accounts

    def broken(*a, **k):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(accounts.AuditStore, "append", broken)
    with pytest.raises(RuntimeError, match="audit write failed"):
        registry.set_autonomy("P1", 2, by=owner(), reason="rolled back")
    assert registry.autonomy_at("P1", NOW + timedelta(days=1)).level == 1  # the change rolled back with its event


@pytest.mark.unit
def test_bootstrap_works_once_and_ids_are_never_reused(env):
    registry, db, *_ = env
    with pytest.raises(ValueError, match="already"):
        registry.bootstrap_admin("second", os_user="LOQ")
    (event,) = AuditStore(db).for_target("operator", "owner")
    assert event.actor.kind is ActorKind.PROCESS and event.actor.actor_id == "admin-cli" and event.actor.os_user == "LOQ"
    registry.create_account("P1", AccountKind.PAPER, "USD", by=owner(), reason="once")
    with pytest.raises(ValueError, match="already exists"):
        registry.create_account("P1", AccountKind.RESEARCH, "USD", by=owner(), reason="again", effective_at=T2019)
    with pytest.raises(ValueError, match="already exists"):
        registry.add_operator("owner", Role.TRADER, by=owner(), reason="reuse")


@pytest.mark.unit
def test_concurrent_bootstraps_give_exactly_one_admin(pg_database):
    conns = [open_operational_pg(pg_database) for _ in range(3)]
    apply_pg_schema(conns[0])
    ports = [PostgresDatabase(c) for c in conns[1:]]
    registries = [AccountRegistry(d, AuditStore(d), ReplayClock(NOW)) for d in ports]
    barrier, results = threading.Barrier(2), []

    def run(registry, name):
        barrier.wait()
        try:
            registry.bootstrap_admin(name, os_user="LOQ")
            results.append("ok")
        except ValueError:
            results.append("refused")

    threads = [threading.Thread(target=run, args=(r, n)) for r, n in zip(registries, ("a", "b"), strict=True)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(results) == ["ok", "refused"]
    assert conns[0].execute("SELECT COUNT(DISTINCT operator_id) FROM operators").fetchone()[0] == 1
    for c in conns:
        c.close()


@pytest.mark.unit
def test_research_settings_live_in_replay_time_and_paper_cannot_be_backdated(env):
    registry, db, clock, _ = env
    account = registry.create_account("R1", AccountKind.RESEARCH, "USD", by=owner(), reason="demo",
                                      effective_at=T2019)
    assert account.effective_at == T2019 and account.recorded_at == NOW
    (created,) = AuditStore(db).for_target("account", "R1")
    assert created.at == NOW and created.business_at == T2019  # both times, never merged
    assert registry.autonomy_at("R1", T2019).level == 0
    with pytest.raises(ValueError, match="effective_at"):
        registry.create_account("R2", AccountKind.RESEARCH, "USD", by=owner(), reason="needs a time")
    with pytest.raises(ValueError, match="backdate"):
        registry.create_account("P1", AccountKind.PAPER, "USD", by=owner(), reason="no", effective_at=T2019)
    registry.create_account("P1", AccountKind.PAPER, "USD", by=owner(), reason="paper")
    with pytest.raises(ValueError, match="backdate"):
        registry.set_autonomy("P1", 1, by=owner(), reason="no", effective_at=T2019)
    registry.set_autonomy("R1", 1, by=owner(), reason="later", effective_at=T2019 + timedelta(days=5))
    with pytest.raises(ValueError, match="earlier"):
        registry.set_autonomy("R1", 2, by=owner(), reason="earlier", effective_at=T2019 + timedelta(days=1))


@pytest.mark.unit
def test_authorization_uses_the_real_command_time_never_the_replay_time(env):
    registry, db, clock, _ = env
    registry.create_account("R1", AccountKind.RESEARCH, "USD", by=owner(), reason="demo", effective_at=T2019)
    registry.set_autonomy("R1", 1, by=owner(), reason="today's admin, 2019 setting",
                          effective_at=T2019 + timedelta(days=1))  # the owner exists only since 2026
    registry.add_operator("ex", Role.ADMIN, by=owner(), reason="temp")
    clock.advance_by(timedelta(minutes=1))
    registry.deactivate_operator("ex", by=owner(), reason="left")
    ex = Actor(ActorKind.OPERATOR, "ex", "ADMIN", None)
    with pytest.raises(NotAuthorized):  # inactive now, whatever replay time is chosen
        registry.set_autonomy("R1", 2, by=ex, reason="no", effective_at=T2019 + timedelta(days=2))


@pytest.mark.unit
def test_identity_excludes_provenance_and_both_parts_are_asserted():
    """Two setups made at different real times with the same replay inputs (Codex acceptance note 2)."""
    dsn = maintenance_dsn()
    if dsn is None:
        pytest.skip(PG_SKIP_REASON)
    made = []
    for real_time in (NOW, NOW + timedelta(days=30)):
        with temporary_database(dsn) as database:
            conn = open_operational_pg(database)
            db = PostgresDatabase(conn)
            apply_pg_schema(conn)
            registry = AccountRegistry(db, AuditStore(db), ReplayClock(real_time))
            registry.bootstrap_admin("owner", os_user="LOQ")
            account = registry.create_account("R1", AccountKind.RESEARCH, "USD", by=owner(), reason="demo",
                                              effective_at=T2019)
            made.append((account, registry.set_autonomy("R1", 1, by=owner(), reason="demo", effective_at=T2019)))
            conn.close()
    (a1, s1), (a2, s2) = made
    assert a1.identity == a2.identity and s1.setting_id == s2.setting_id  # identical deterministic payloads and ids
    assert a1.recorded_at != a2.recorded_at and s1.recorded_at != s2.recorded_at  # provenance differs and is kept
    same = AutonomySetting("R1", 1, T2019, NOW + timedelta(days=99), 2, "someone-else", "demo")
    assert same.setting_id == s1.setting_id  # the id ignores recorded_at and who ran it
    assert same != s1  # full equality includes provenance; it is not the identity requirement


@pytest.mark.unit
def test_a_fresh_process_decodes_account_events_through_the_registry(env, pg_database):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    registry, db, *_ = env
    registry.create_account("R1", AccountKind.RESEARCH, "USD", by=owner(), reason="demo", effective_at=T2019)
    setting = registry.set_autonomy("R1", 1, by=owner(), reason="demo", effective_at=T2019)
    probe = (
        "import json, sys\n"
        "from investment_engine.audit.events import AuditStore\n"  # nothing from policy is imported here
        "from investment_engine.storage.database import PostgresDatabase\n"
        "from investment_engine.storage.postgres import open_operational_pg\n"
        "events = AuditStore(PostgresDatabase(open_operational_pg(sys.argv[1]))).for_target('account', 'R1')\n"
        "print(json.dumps([type(e.after).__name__ for e in events] + [events[-1].after.setting_id]))\n"
    )
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-c", probe, pg_database], capture_output=True, text=True, timeout=120,
                         cwd=root, env={**os.environ, "PYTHONPATH": str(root)})
    assert out.returncode == 0, out.stderr.splitlines()[-1:]
    assert json.loads(out.stdout) == ["tuple", "AutonomySetting", setting.setting_id]
