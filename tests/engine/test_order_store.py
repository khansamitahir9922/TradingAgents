"""The order store: compare-and-set, ownership, fills, events and history (docs/tasks/M4-00.md)."""

import json
import os
import subprocess
import sys
import threading
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal, Inexact, Rounded, localcontext
from pathlib import Path

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.oms import order_states
from investment_engine.oms.intent_store import IntentStore, StaleWrite
from investment_engine.oms.order_states import OrderState as S, ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.oms.orders import (
    CancelProgress,
    CancelRequest,
    Fill,
    FillOutcome,
    GateDecision,
    Order,
    order_ids,
)
from investment_engine.policy.accounts import AccountKind, AccountRegistry
from investment_engine.policy.decisions import CheckResult
from investment_engine.storage.database import AppendOnlyViolation, PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.recording_outbox import RecordingOutbox
from tests.engine.test_order_states import G3
from tests.engine.test_sizer import sized

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")
CORE_ACTOR = Actor(ActorKind.PROCESS, "core-engine", None, None)
PASS = GateDecision("x", 1, True, (CheckResult("kill_switch", True, "enabled"),), NOW, "{}")
HOSTILE = [{"prec": 1, "rounding": ROUND_DOWN}, {"prec": 3, "rounding": ROUND_CEILING},
           {"prec": 6, "trap": (Inexact, Rounded)}]  # caller contexts that must change nothing (B2)


def hostile_context(context, hostile):
    for key, value in hostile.items():
        if key == "trap":
            for signal in value:
                context.traps[signal] = True
        else:
            setattr(context, key, value)


class Env:
    """One test database; `stores(role)` opens a connection for that process role."""

    def __init__(self, dsn: str) -> None:
        self.dsn, self.opened, self.clock = dsn, [], ReplayClock(NOW)
        db, *_ = self.connect()
        apply_pg_schema(db.connection)
        self.db = db
        audit = AuditStore(db)
        self.accounts = AccountRegistry(db, audit, ReplayClock(NOW))
        self.accounts.bootstrap_admin("owner", os_user="LOQ")
        self.accounts.create_account("R1", AccountKind.RESEARCH, "USD", by=OWNER, reason="demo",
                                     effective_at=datetime(2019, 1, 2, tzinfo=UTC))
        self.intents = IntentStore(db, audit, self.accounts, ReplayClock(NOW))
        self.core, self.core_outbox = self.store(ProcessRole.CORE)
        self.worker, self.worker_outbox = self.store(ProcessRole.EXECUTION)
        self._n = 0

    def connect(self):
        self.opened.append(open_operational_pg(self.dsn))
        return (PostgresDatabase(self.opened[-1]),)

    def store(self, role):
        (db,) = self.connect()
        outbox = RecordingOutbox(db)
        return OrderStore(db, role=role, audit=AuditStore(db), outbox=outbox, clock=self.clock), outbox

    def order(self, quantity="10", side="BUY") -> Order:
        """A fresh intent (stored, so the order's reference holds) and its order."""
        self._n += 1
        intent = replace(sized().intent, intent_id=f"int-{self._n}", account_id="R1")
        self.intents.create(intent, by=CORE_ACTOR, correlation_id="c")
        oid, cid = order_ids(intent.intent_id, 1)
        return Order(oid, cid, intent.intent_id, 1, f"content-{self._n}", "pfp-x", "R1", AccountKind.RESEARCH,
                     intent.instrument_id, side, Decimal(quantity), "LIMIT", Decimal("101.00"), "DAY",
                     date(2026, 10, 19), NOW)

    def created(self, **kw) -> Order:
        order = self.order(**kw)
        self.core.create(order, by=CORE_ACTOR, correlation_id="c")
        return order

    def walk(self, order: Order, *path: S):
        """Move an order along state edges (the first from NEW records a gate decision)."""
        status = self.worker.get(order.order_id)[1]
        for to in path:
            gate = None
            if status.state is S.NEW:
                gate = replace(PASS, order_id=order.order_id, passed=to is S.SUBMITTING,
                               checks=(CheckResult("kill_switch", to is S.SUBMITTING, "r"),))
            status = self.worker.transition(order.order_id, to, expected_aggregate_version=status.aggregate_version,
                                            at=NOW, reason="walk", gate=gate)
        return status

    def fill(self, order: Order, quantity="10", fill_id="f1", price="100.00", **kw) -> FillOutcome:
        status = self.worker.get(order.order_id)[1]
        f = Fill(order.order_id, Decimal(quantity), Decimal(price), Decimal("0"), "USD", NOW, NOW, NOW, fill_id,
                 kw.pop("provenance", "{}"))
        return self.worker.record_fill(f, expected_aggregate_version=status.aggregate_version)

    def close(self):
        for c in self.opened:
            c.close()


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    yield e
    e.close()


# ---------------------------------------------------------------- creation, edges and ownership


@pytest.mark.postgres
@pytest.mark.unit
def test_the_schema_edge_table_matches_the_shared_module(env):
    rows = set(env.db.fetchall("SELECT from_state, to_state, owner FROM order_edges"))
    expected = {(None, "NEW", "core-engine")} | {(a.value, b.value, "execution-worker") for a, b in G3}
    assert rows == expected


@pytest.mark.postgres
@pytest.mark.unit
def test_create_is_version_one_with_one_event_and_identical_recreation_is_a_no_op(env):
    order = env.order()
    status = env.core.create(order, by=CORE_ACTOR, correlation_id="c")
    assert (status.state, status.aggregate_version, status.filled_qty) == (S.NEW, 1, Decimal(0))
    assert env.core.create(order, by=CORE_ACTOR, correlation_id="c") == status
    assert env.core_outbox.of(order.order_id) == [(1, "order.created")]
    with pytest.raises(ValueError, match="already has another order"):
        env.core.create(replace(order, position_fingerprint="pfp-other"), by=CORE_ACTOR, correlation_id="c")


@pytest.mark.postgres
@pytest.mark.unit
def test_each_role_writes_only_its_own_edges(env):
    order = env.order()
    with pytest.raises(order_states.WrongProcess):
        env.worker.create(order, by=CORE_ACTOR, correlation_id="c")
    env.core.create(order, by=CORE_ACTOR, correlation_id="c")
    with pytest.raises(order_states.WrongProcess):
        env.core.transition(order.order_id, S.SUBMITTING, expected_aggregate_version=1, at=NOW, reason="x",
                            gate=replace(PASS, order_id=order.order_id))
    with pytest.raises(order_states.IllegalTransition):
        env.worker.transition(order.order_id, S.SUBMITTED, expected_aggregate_version=1, at=NOW, reason="x")
    with pytest.raises(ValueError, match="gate decision"):
        env.worker.transition(order.order_id, S.SUBMITTING, expected_aggregate_version=1, at=NOW, reason="x")
    with pytest.raises(order_states.IllegalTransition, match="recording a fill"):
        env.worker.transition(order.order_id, S.FILLED, expected_aggregate_version=1, at=NOW, reason="x")
    assert env.worker.get(order.order_id)[1].aggregate_version == 1  # nothing was written


@pytest.mark.postgres
@pytest.mark.unit
@pytest.mark.parametrize("role", [None, "", "analysis", "core-engine"])
def test_the_trigger_refuses_a_raw_write_without_the_owning_role(env, role):
    order = env.created()
    (db,) = env.connect()
    with pytest.raises(Exception, match="process role|written only by"), db.transaction():
        if role is not None:
            db.execute("SELECT set_config('investment_engine.process_role', :r, true)", {"r": role})
        db.execute("UPDATE orders SET state = 'SUBMITTING', aggregate_version = 2 WHERE order_id = :id",
                   {"id": order.order_id})
    with pytest.raises(Exception, match="process role|written only by"), db.transaction():
        if role is not None:
            db.execute("SELECT set_config('investment_engine.process_role', :r, true)", {"r": role})
        db.execute("INSERT INTO broker_anomalies VALUES (:id, 1, 'k', 'd', :t, :t, 'b', 1)",
                   {"id": order.order_id, "t": NOW})


@pytest.mark.postgres
@pytest.mark.unit
def test_the_role_setting_never_leaks_past_its_transaction(env):
    order = env.created()
    env.walk(order, S.SUBMITTING)
    value = env.worker._db.fetchone("SELECT current_setting('investment_engine.process_role', true)")[0]
    assert value in (None, "")


@pytest.mark.postgres
@pytest.mark.unit
def test_the_trigger_refuses_term_changes_version_jumps_illegal_edges_and_history_rewrites(env):
    order = env.created()
    (db,) = env.connect()

    def as_worker(sql, params=None):
        with db.transaction():
            db.execute("SELECT set_config('investment_engine.process_role', 'execution-worker', true)")
            db.execute(sql, params or {})

    with pytest.raises(Exception, match="immutable"):
        as_worker("UPDATE orders SET limit_price = 1, aggregate_version = 2 WHERE order_id = :id", {"id": order.order_id})
    with pytest.raises(Exception, match="exactly one version"):
        as_worker("UPDATE orders SET state = 'SUBMITTING', aggregate_version = 5 WHERE order_id = :id",
                  {"id": order.order_id})
    with pytest.raises(Exception, match="not an order transition"):
        as_worker("UPDATE orders SET state = 'FILLED', aggregate_version = 2 WHERE order_id = :id",
                  {"id": order.order_id})
    for sql in ("UPDATE order_versions SET reason = 'x'", "DELETE FROM order_versions", "DELETE FROM orders"):
        with pytest.raises(AppendOnlyViolation):
            as_worker(sql)


# ---------------------------------------------------------------- compare-and-set


@pytest.mark.postgres
@pytest.mark.unit
def test_concurrent_writers_on_one_order_one_wins(env):
    for _ in range(20):
        order = env.created()
        status = env.walk(order, S.SUBMITTING, S.SUBMITTED)
        a, _ = env.store(ProcessRole.EXECUTION)
        b, _ = env.store(ProcessRole.EXECUTION)
        barrier, results = threading.Barrier(2), []

        def write(store, to, barrier=barrier, results=results, order=order, status=status):
            barrier.wait()
            try:
                store.transition(order.order_id, to, expected_aggregate_version=status.aggregate_version, at=NOW,
                                 reason="race")
                results.append("ok")
            except StaleWrite:
                results.append("stale")

        threads = [threading.Thread(target=write, args=(a, S.CANCEL_PENDING)),
                   threading.Thread(target=write, args=(b, S.EXPIRED))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == ["ok", "stale"]
        assert env.worker.get(order.order_id)[1].aggregate_version == status.aggregate_version + 1


# ---------------------------------------------------------------- the fill matrix (rule 4)


@pytest.mark.postgres
@pytest.mark.unit
def test_partial_fills_update_totals_without_self_edges_then_complete(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    assert env.fill(order, "3", "f1", "100.00") is FillOutcome.RECORDED
    assert env.fill(order, "3", "f2", "102.00") is FillOutcome.RECORDED
    status = env.worker.get(order.order_id)[1]
    assert (status.state, status.filled_qty, status.avg_price) == (S.PARTIALLY_FILLED, Decimal(6), Decimal("101.0000000000"))
    assert env.fill(order, "4", "f3", "101.00") is FillOutcome.RECORDED
    status = env.worker.get(order.order_id)[1]
    assert (status.state, status.filled_qty) == (S.FILLED, Decimal(10))
    history = [(t.from_state, t.to_state) for t in env.worker.history(order.order_id)]
    assert history[-3:] == [(S.SUBMITTED, S.PARTIALLY_FILLED), (S.PARTIALLY_FILLED, S.PARTIALLY_FILLED),
                            (S.PARTIALLY_FILLED, S.FILLED)]


@pytest.mark.postgres
@pytest.mark.unit
def test_a_delayed_fill_on_a_cancelled_order_is_accounting_only(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED, S.CANCEL_PENDING, S.CANCELLED)  # the CANCELLED ack came first
    assert env.fill(order, "4", "late") is FillOutcome.RECORDED
    status = env.worker.get(order.order_id)[1]
    assert (status.state, status.filled_qty, status.anomalies) == (S.CANCELLED, Decimal(4), 0)
    assert env.fill(order, "6", "late2") is FillOutcome.RECORDED  # completes it: recorded, with an anomaly
    status = env.worker.get(order.order_id)[1]
    assert (status.state, status.filled_qty) == (S.CANCELLED, Decimal(10))
    assert [a.kind for a in env.worker.anomalies(order.order_id)] == ["fill_after_final"]


@pytest.mark.postgres
@pytest.mark.unit
@pytest.mark.parametrize("path", [(), (S.GATE_REJECTED,), (S.SUBMITTING, S.REJECTED)])
def test_a_fill_on_an_order_that_never_reached_the_broker_or_was_rejected_is_refused(env, path):
    order = env.created()
    env.walk(order, *path)
    assert env.fill(order) is FillOutcome.REFUSED
    status = env.worker.get(order.order_id)[1]
    assert status.filled_qty == 0 and status.state is not S.FILLED and env.worker.fills(order.order_id) == []
    assert [a.kind for a in env.worker.anomalies(order.order_id)] == ["fill_refused"]


@pytest.mark.postgres
@pytest.mark.unit
def test_a_fill_before_the_ack_writes_two_versions_and_two_events(env):
    order = env.created()
    env.walk(order, S.SUBMITTING)
    assert env.fill(order, "4") is FillOutcome.RECORDED
    assert env.worker_outbox.of(order.order_id) == [(2, "order.state_changed"), (3, "order.state_changed"),
                                                    (4, "order.fill_recorded")]
    assert env.worker.get(order.order_id)[1].state is S.PARTIALLY_FILLED


@pytest.mark.postgres
@pytest.mark.unit
def test_one_fill_that_changes_the_state_is_one_version_and_one_event(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    assert env.fill(order, "4") is FillOutcome.RECORDED
    assert env.worker_outbox.of(order.order_id)[-1] == (4, "order.fill_recorded")
    versions = [t.aggregate_version for t in env.worker.history(order.order_id)]
    assert versions == [1, 2, 3, 4]


@pytest.mark.postgres
@pytest.mark.unit
def test_duplicates_conflicts_and_overfills(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    assert env.fill(order, "4", "f1") is FillOutcome.RECORDED
    events = len(env.worker_outbox.events)
    assert env.fill(order, "4", "f1") is FillOutcome.DUPLICATE
    assert env.fill(order, "5", "f1") is FillOutcome.CONFLICT
    assert env.fill(order, "7", "f2") is FillOutcome.REFUSED  # 4 + 7 > 10
    assert len(env.worker_outbox.events) == events  # anomalies publish nothing
    assert len(env.worker.fills(order.order_id)) == 1
    assert [a.kind for a in env.worker.anomalies(order.order_id)] == ["conflicting_duplicate_fill", "overfill"]
    assert env.worker.get(order.order_id)[1].filled_qty == Decimal(4)


# ---------------------------------------------------------------- gate decisions and cancel requests


@pytest.mark.postgres
@pytest.mark.unit
def test_a_gate_decision_is_part_of_its_edge(env):
    order = env.created()
    env.walk(order, S.GATE_REJECTED)
    (decision,) = env.worker.gate_decisions(order.order_id)
    assert (decision.attempt, decision.passed) == (1, False)
    assert env.worker_outbox.of(order.order_id) == [(2, "order.state_changed")]


@pytest.mark.postgres
@pytest.mark.unit
def test_cancel_requests_version_separately_and_never_move_the_order(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    request = CancelRequest(order.order_id, OWNER, NOW, "operator asked")
    with pytest.raises(order_states.WrongProcess):
        env.worker.request_cancel(request, correlation_id="c")
    env.core.request_cancel(request, correlation_id="c")
    assert env.worker.get(order.order_id)[1].aggregate_version == 3
    v = env.worker.cancel_progress(request.cancel_id, CancelProgress.SENDING, expected_version=1, at=NOW)
    v = env.worker.cancel_progress(request.cancel_id, CancelProgress.SENDING, expected_version=v, at=NOW)
    assert env.worker.cancel_attempts(request.cancel_id) == 2
    with pytest.raises(StaleWrite):
        env.worker.cancel_progress(request.cancel_id, CancelProgress.SENT, expected_version=1, at=NOW)
    v = env.worker.cancel_progress(request.cancel_id, CancelProgress.CLOSED, expected_version=v, at=NOW,
                                   outcome="CANCELLED")
    assert env.worker.open_cancels() == []
    assert env.core_outbox.of(request.cancel_id) == [(1, "cancel.requested")]
    assert env.worker_outbox.of(request.cancel_id) == [(2, "cancel.progressed"), (3, "cancel.progressed"),
                                                       (4, "cancel.progressed")]
    final = env.created()
    env.walk(final, S.GATE_REJECTED)
    with pytest.raises(ValueError, match="nothing to cancel"):
        env.core.request_cancel(CancelRequest(final.order_id, OWNER, NOW, "x"), correlation_id="c")


# ---------------------------------------------------------------- point in time and audit


@pytest.mark.postgres
@pytest.mark.unit
def test_as_of_sees_only_versions_recorded_by_then(env):
    order = env.created()  # recorded at NOW
    env.clock.advance_to(NOW + timedelta(hours=1))
    env.walk(order, S.SUBMITTING)  # recorded at NOW + 1h
    at = NOW + timedelta(hours=1)
    assert [(o.order_id, s) for o, s, _ in env.worker.as_of("R1", at)] == [(order.order_id, S.SUBMITTING)]
    assert [s for _, s, _ in env.worker.as_of("R1", at - timedelta(microseconds=1))] == [S.NEW]
    assert env.worker.as_of("R1", NOW - timedelta(microseconds=1)) == []


@pytest.mark.postgres
@pytest.mark.unit
def test_a_fresh_process_decodes_order_audit_events(env, pg_database):
    order = env.created()
    probe = (
        "import json, os, sys\n"
        "from investment_engine.audit.events import AuditStore\n"
        "from investment_engine.storage.database import PostgresDatabase\n"
        "from investment_engine.storage.postgres import open_operational_pg\n"
        "(e,) = AuditStore(PostgresDatabase(open_operational_pg(os.environ['IE_PROBE_DSN']))).for_target('order', sys.argv[1])\n"
        "print(json.dumps([type(e.after).__name__, e.after.order_id, str(e.after.quantity)]))\n"
    )
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-c", probe, order.order_id], capture_output=True, text=True, timeout=120,
                         cwd=root, env={**os.environ, "IE_PROBE_DSN": pg_database, "PYTHONPATH": str(root)})
    assert out.returncode == 0, out.stderr.splitlines()[-1:]
    assert json.loads(out.stdout) == ["Order", order.order_id, "10"]


@pytest.mark.postgres
@pytest.mark.unit
@pytest.mark.parametrize("hostile", HOSTILE, ids=["prec1-down", "prec3-ceiling", "prec6-inexact-trapped"])
def test_fill_totals_and_average_ignore_the_callers_decimal_context(env, hostile):
    """B2 (Codex M4 review): with precision 1, two 6-share fills stored filled_qty 10 and an average of 120."""
    order = env.created(quantity="20")
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    with localcontext() as context:
        hostile_context(context, hostile)
        assert env.fill(order, "6", "f1", "100.00") is FillOutcome.RECORDED
        assert env.fill(order, "6", "f2", "100.01") is FillOutcome.RECORDED
    status = env.worker.get(order.order_id)[1]
    assert (status.filled_qty, status.avg_price) == (Decimal(12), Decimal("100.0050000000"))
