"""The intent store and the G2 state machine (docs/tasks/M3-09.md)."""

import threading
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.oms import intent_states
from investment_engine.oms.intent_store import IntentStore, StaleWrite
from investment_engine.oms.intents import IntentState as S
from investment_engine.policy.accounts import AccountKind, AccountRegistry
from investment_engine.storage.database import AppendOnlyViolation, PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.test_sizer import sized

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")
CORE = Actor(ActorKind.PROCESS, "core-engine", None, None)
G2 = {  # the frozen edges, written out independently of ALLOWED (architecture G2)
    (S.PROPOSED, S.POLICY_REJECTED), (S.PROPOSED, S.RISK_REJECTED), (S.PROPOSED, S.SUPERSEDED),
    (S.PROPOSED, S.AWAITING_APPROVAL), (S.PROPOSED, S.APPROVED),
    (S.AWAITING_APPROVAL, S.APPROVED), (S.AWAITING_APPROVAL, S.DECLINED), (S.AWAITING_APPROVAL, S.EXPIRED),
    (S.APPROVED, S.CONVERTED), (S.APPROVED, S.EXPIRED), (S.APPROVED, S.SUPERSEDED),
}


def intent(account="R1", **changes):
    return replace(sized().intent, account_id=account, **changes)


@pytest.fixture
def env(pg_database):
    opened = []

    def connect():
        opened.append(open_operational_pg(pg_database))
        db = PostgresDatabase(opened[-1])
        audit = AuditStore(db)
        accounts = AccountRegistry(db, audit, ReplayClock(NOW))
        return db, IntentStore(db, audit, accounts, ReplayClock(NOW)), accounts

    db, store, accounts = connect()
    apply_pg_schema(db.connection)
    accounts.bootstrap_admin("owner", os_user="LOQ")
    accounts.create_account("R1", AccountKind.RESEARCH, "USD", by=OWNER, reason="demo",
                            effective_at=datetime(2019, 1, 2, tzinfo=UTC))
    yield db, store, connect
    for c in opened:
        c.close()


# ---------------------------------------------------------------- the table


@pytest.mark.unit
def test_allowed_is_exactly_the_frozen_g2_table_conversion_included():
    table = {(a, b) for a, targets in intent_states.ALLOWED.items() for b in targets}
    assert table == G2
    assert {S.POLICY_REJECTED, S.RISK_REJECTED, S.SUPERSEDED, S.DECLINED, S.EXPIRED,
                                   S.CONVERTED} == intent_states.FINAL


@pytest.mark.unit
@pytest.mark.parametrize("a", list(S))
@pytest.mark.parametrize("b", list(S))
def test_every_pair_is_allowed_guarded_or_illegal(a, b):
    if (a, b) == (S.APPROVED, S.CONVERTED):
        with pytest.raises(intent_states.OrdersNotBuilt, match="M4"):
            intent_states.check(a, b)
    elif (a, b) in G2:
        intent_states.check(a, b)
    else:
        with pytest.raises(intent_states.IllegalTransition):
            intent_states.check(a, b)


# ---------------------------------------------------------------- the store


def walk(store, path):
    """Create an intent and move it along `path`; returns the stored intent."""
    stored = store.create(intent(), by=CORE, correlation_id="c")
    for to in path:
        stored = store.transition(stored.intent.intent_id, stored.intent.version, to,
                                  expected_aggregate_version=stored.aggregate_version, at=NOW, by=CORE, reason="walk")
    return stored


@pytest.mark.postgres
@pytest.mark.unit
@pytest.mark.parametrize("path", [[S.POLICY_REJECTED], [S.RISK_REJECTED], [S.AWAITING_APPROVAL, S.APPROVED],
                                  [S.AWAITING_APPROVAL, S.DECLINED], [S.AWAITING_APPROVAL, S.EXPIRED],
                                  [S.APPROVED, S.EXPIRED]])
def test_every_allowed_edge_succeeds_through_the_store(env, path):
    _, store, _ = env
    stored = walk(store, path)
    assert stored.state is path[-1] and stored.aggregate_version == 1 + len(path)
    assert [t.to_state for t in store.history(stored.intent.intent_id)] == [S.PROPOSED, *path]


@pytest.mark.postgres
@pytest.mark.unit
def test_conversion_is_refused_in_m3_and_illegal_moves_write_nothing(env):
    db, store, _ = env
    approved = walk(store, [S.APPROVED])
    with pytest.raises(intent_states.OrdersNotBuilt):
        store.transition(approved.intent.intent_id, 1, S.CONVERTED, expected_aggregate_version=2, at=NOW, by=CORE,
                         reason="no orders in M3")
    rejected = store.transition(approved.intent.intent_id, 1, S.EXPIRED, expected_aggregate_version=2, at=NOW,
                                by=CORE, reason="expired")
    for to in S:
        with pytest.raises(intent_states.IllegalTransition):
            store.transition(rejected.intent.intent_id, 1, to, expected_aggregate_version=3, at=NOW, by=CORE,
                             reason="from a final state")
    assert store.get(rejected.intent.intent_id).aggregate_version == 3
    assert len(store.history(rejected.intent.intent_id)) == 3


@pytest.mark.postgres
@pytest.mark.unit
def test_a_stale_aggregate_version_raises_and_changes_nothing(env):
    _, store, _ = env
    stored = store.create(intent(), by=CORE, correlation_id="c")
    with pytest.raises(StaleWrite):
        store.transition(stored.intent.intent_id, 1, S.AWAITING_APPROVAL, expected_aggregate_version=7, at=NOW,
                         by=CORE, reason="stale")
    assert store.get(stored.intent.intent_id).state is S.PROPOSED


@pytest.mark.postgres
@pytest.mark.unit
def test_supersede_creates_the_next_version_atomically_and_only_the_quantity_may_change(env):
    _, store, _ = env
    stored = store.create(intent(), by=CORE, correlation_id="c")
    reduced = replace(stored.intent, version=2, supersedes=1, quantity=Decimal("64"))
    v2 = store.supersede(stored.intent.intent_id, 1, reduced, expected_aggregate_version=1, at=NOW, by=CORE,
                         reason="position 12.4% > 10%: reduce 82 -> 64")
    assert v2.intent == reduced and v2.state is S.PROPOSED and store.get(reduced.intent_id).intent.version == 2
    assert store.get(reduced.intent_id, 1).state is S.SUPERSEDED
    with pytest.raises(intent_states.IllegalTransition):  # only the latest version moves
        store.transition(reduced.intent_id, 1, S.AWAITING_APPROVAL, expected_aggregate_version=2, at=NOW, by=CORE,
                         reason="old version")
    other = store.create(intent(account="R1", intent_id="int-other"), by=CORE, correlation_id="c")
    with pytest.raises(ValueError, match="only the quantity"):
        store.supersede("int-other", 1, replace(other.intent, version=2, supersedes=1, limit_price=Decimal("1")),
                        expected_aggregate_version=1, at=NOW, by=CORE, reason="no")


@pytest.mark.postgres
@pytest.mark.unit
def test_material_fields_and_the_log_are_immutable_in_sql(env):
    db, store, _ = env
    stored = store.create(intent(), by=CORE, correlation_id="c")
    for statement in ("UPDATE intent_versions SET quantity = 1", "UPDATE intent_versions SET limit_price = 1",
                      "UPDATE intent_versions SET side = 'SELL'", "UPDATE intent_versions SET content = '\\x00'",
                      "UPDATE intents SET aggregate_version = 9", "DELETE FROM intent_versions",
                      "UPDATE intent_transitions SET reason = 'x'", "DELETE FROM intent_transitions",
                      "TRUNCATE intent_transitions"):
        with pytest.raises(AppendOnlyViolation):
            db.execute(statement)
    assert store.get(stored.intent.intent_id) == stored


@pytest.mark.postgres
@pytest.mark.unit
def test_create_is_idempotent_and_refuses_a_different_intent_under_the_id(env):
    _, store, _ = env
    a = store.create(intent(), by=CORE, correlation_id="c")
    assert store.create(intent(), by=CORE, correlation_id="c") == a
    with pytest.raises(ValueError, match="different content"):
        store.create(intent(quantity=Decimal("5")), by=CORE, correlation_id="c")


@pytest.mark.postgres
@pytest.mark.unit
def test_every_change_writes_one_audit_event_with_business_time_for_research(env):
    db, store, _ = env
    stored = walk(store, [S.AWAITING_APPROVAL])
    events = AuditStore(db).for_target("intent", stored.intent.intent_id)
    assert sorted(e.action for e in events) == ["intent.awaiting_approval", "intent.create"]  # same command time
    created = next(e for e in events if e.action == "intent.create")
    moved = next(e for e in events if e.action != "intent.create")
    assert all(e.at == NOW for e in events)  # the command time
    assert created.business_at == stored.intent.created_at and moved.business_at == NOW  # replay times (RESEARCH)


def race(connect, intent_id, moves):
    """Run two transitions from the same expected version at once; return their outcomes."""
    barrier, results = threading.Barrier(2), []

    def run(to, fields):
        db, store, _ = connect()
        barrier.wait()
        try:
            if to is S.SUPERSEDED:
                current = store.get(intent_id)
                store.supersede(intent_id, current.intent.version,
                                replace(current.intent, version=current.intent.version + 1,
                                        supersedes=current.intent.version, quantity=Decimal("1")),
                                expected_aggregate_version=current.aggregate_version, at=NOW, by=CORE, reason="race")
            else:
                current = store.get(intent_id)
                store.transition(intent_id, current.intent.version, to,
                                 expected_aggregate_version=current.aggregate_version, at=NOW, by=CORE, reason="race",
                                 **fields)
            results.append("won")
        except StaleWrite:
            results.append("stale")
        finally:
            db.connection.close()

    threads = [threading.Thread(target=run, args=m) for m in moves]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return sorted(results)


@pytest.mark.postgres
@pytest.mark.unit
@pytest.mark.parametrize("start, moves", [
    ([S.AWAITING_APPROVAL], [(S.APPROVED, {}), (S.EXPIRED, {})]),
    ([S.AWAITING_APPROVAL], [(S.APPROVED, {}), (S.DECLINED, {})]),
    ([S.APPROVED], [(S.EXPIRED, {}), (S.SUPERSEDED, {})]),
    ([], [(S.RISK_REJECTED, {}), (S.SUPERSEDED, {})]),
], ids=["approve-vs-expire", "approve-vs-decline", "expire-vs-supersede", "reject-vs-supersede"])
def test_concurrent_legal_moves_have_exactly_one_winner(env, start, moves):
    db, store, connect = env
    for i in range(50):
        stored = store.create(intent(intent_id=f"int-race-{i}"), by=CORE, correlation_id="c")
        for to in start:
            stored = store.transition(stored.intent.intent_id, 1, to, expected_aggregate_version=stored.aggregate_version,
                                      at=NOW, by=CORE, reason="set up")
        assert race(connect, stored.intent.intent_id, moves) == ["stale", "won"], i
        final = store.get(stored.intent.intent_id)
        assert final.aggregate_version == stored.aggregate_version + 1  # no lost update


@pytest.mark.postgres
@pytest.mark.unit
def test_admission_counts_distinct_buy_intents_per_session_and_expiry_is_per_account(env):
    db, store, _ = env
    a = walk(store, [S.AWAITING_APPROVAL])
    assert store.admitted_buys("R1", a.intent.target_session) == 1 and store.was_admitted(a.intent.intent_id)
    store.transition(a.intent.intent_id, 1, S.APPROVED, expected_aggregate_version=2, at=NOW, by=CORE, reason="ok")
    assert store.admitted_buys("R1", a.intent.target_session) == 1  # one intent, counted once
    assert store.admitted_buys("R1", a.intent.target_session, excluding=a.intent.intent_id) == 0
    b = store.create(intent(intent_id="int-b"), by=CORE, correlation_id="c")
    store.supersede("int-b", 1, replace(b.intent, version=2, supersedes=1, quantity=Decimal("3")),
                    expected_aggregate_version=1, at=NOW, by=CORE, reason="reduce")
    assert not store.was_admitted("int-b")  # a reduced v2 never yet admitted
    assert store.admitted_buys("R1", a.intent.target_session) == 1
    store.transition(a.intent.intent_id, 1, S.EXPIRED, expected_aggregate_version=3, at=NOW, by=CORE, reason="late")
    assert store.admitted_buys("R1", a.intent.target_session) == 1  # expiry doesn't free the slot (D5)
    assert store.admitted_buys("R1", date(2030, 1, 2)) == 0


@pytest.mark.postgres
@pytest.mark.unit
def test_due_for_expiry_is_per_account_and_uses_the_deadlines(env):
    db, store, connect = env
    _, _, accounts = connect()
    accounts.create_account("R2", AccountKind.RESEARCH, "USD", by=OWNER, reason="second timeline",
                            effective_at=datetime(2019, 1, 2, tzinfo=UTC))
    deadline = NOW + timedelta(hours=1)
    for account, intent_id in (("R1", "int-r1"), ("R2", "int-r2")):
        stored = store.create(intent(account, intent_id=intent_id), by=CORE, correlation_id="c")
        store.transition(intent_id, 1, S.AWAITING_APPROVAL, expected_aggregate_version=stored.aggregate_version,
                         at=NOW, by=CORE, reason="wait", approval_deadline=deadline)
    proposed = store.create(intent(intent_id="int-p"), by=CORE, correlation_id="c")  # PROPOSED: no deadline
    assert store.due_for_expiry("R1", NOW) == []
    assert [s.intent.intent_id for s in store.due_for_expiry("R1", deadline)] == ["int-r1"]  # exactly at: due
    assert [s.intent.intent_id for s in store.due_for_expiry("R2", deadline)] == ["int-r2"]  # never another account's
    assert proposed.state is S.PROPOSED


@pytest.mark.postgres
@pytest.mark.unit
def test_a_fresh_process_decodes_intent_events_through_the_registry(env, pg_database):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    _, store, _ = env
    stored = store.create(intent(), by=CORE, correlation_id="c")
    probe = (
        "import json, os, sys\n"
        "from investment_engine.audit.events import AuditStore\n"
        "from investment_engine.storage.database import PostgresDatabase\n"
        "from investment_engine.storage.postgres import open_operational_pg\n"
        "(e,) = AuditStore(PostgresDatabase(open_operational_pg(os.environ['IE_PROBE_DSN']))).for_target('intent', sys.argv[1])\n"
        "print(json.dumps([type(e.after).__name__, e.after.intent_id, str(e.after.quantity)]))\n"
    )
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-c", probe, stored.intent.intent_id], capture_output=True,
                         text=True, timeout=120, cwd=root, env={**os.environ, "IE_PROBE_DSN": pg_database, "PYTHONPATH": str(root)})
    assert out.returncode == 0, out.stderr.splitlines()[-1:]
    assert json.loads(out.stdout) == ["OrderIntent", stored.intent.intent_id, str(stored.intent.quantity)]
