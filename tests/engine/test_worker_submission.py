"""Submission in three phases (docs/tasks/M4-07.md rules 1, 5, 6; Laws 13, 14)."""

from datetime import timedelta

import pytest

from investment_engine.execution import worker as worker_module
from investment_engine.oms.order_states import OrderState as S
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import open_operational_pg
from tests.engine.test_intent_pipeline import CAL, DAY, OWNER
from tests.engine.worker_env import WorkerEnv, after_close, pre_open

pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database, tmp_path):
    e = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    yield e
    e.close()


@pytest.mark.unit
def test_new_then_submitting_then_submitted_then_filled(env):
    order, view = env.convert(DAY)
    report = env.worker(pre_open(order, view)).step()
    assert (report.submitted, env.broker.submitted(order.client_order_id)) == (1, 1)
    assert env.state(order).state is S.SUBMITTED
    env.broker.send("FILL", order.client_order_id, after_close(order), quantity=str(order.quantity))
    env.worker(after_close(order)).step()
    status = env.state(order)
    assert (status.state, status.filled_qty) == (S.FILLED, order.quantity)
    versions = [(t.aggregate_version, t.to_state) for t in env.worker(after_close(order)).orders.history(order.order_id)]
    assert versions == [(1, S.NEW), (2, S.SUBMITTING), (3, S.SUBMITTED), (4, S.FILLED)]


@pytest.mark.unit
def test_submitting_is_committed_before_the_broker_is_called(env, pg_database):
    order, view = env.convert(DAY)
    seen = []

    def check(o):  # read on another connection, at the moment of the call
        conn = open_operational_pg(pg_database)
        try:
            seen.append(PostgresDatabase(conn).fetchone("SELECT state FROM orders WHERE order_id = :id",
                                                        {"id": o.order_id})[0])
        finally:
            conn.close()

    env.broker.on_submit = check
    env.worker(pre_open(order, view)).step()
    assert seen == ["SUBMITTING"]


@pytest.mark.unit
def test_a_gate_failure_sends_nothing(env):
    order, view = env.convert(DAY)
    env.enable(False, 2)
    report = env.worker(pre_open(order, view)).step()
    assert report.gate_rejected == 1 and env.broker.submits == []
    assert env.state(order).state is S.GATE_REJECTED


@pytest.mark.unit
def test_a_timeout_gives_unknown_and_the_order_is_never_resubmitted(env):
    order, view = env.convert(DAY)
    env.broker.timeout_next_submit = True
    env.worker(pre_open(order, view)).step()
    assert env.state(order).state is S.UNKNOWN
    env.broker.known.pop(order.client_order_id)  # the broker never got it (D20)
    for _ in range(3):
        env.worker(after_close(order)).step()
    assert env.broker.submitted(order.client_order_id) == 1 and env.state(order).state is S.UNKNOWN
    worker = env.worker(after_close(order))
    assert {a.kind for a in worker.orders.anomalies(order.order_id)} == {"lookup_no_record"}


@pytest.mark.unit
def test_a_definite_broker_rejection(env):
    order, view = env.convert(DAY)
    env.broker.reject_next_submit = "not allowed"
    env.worker(pre_open(order, view)).step()
    assert env.state(order).state is S.REJECTED and env.broker.submitted(order.client_order_id) == 1


def wait_for_the_account_lock(worker, monkeypatch, until):
    """The account-control lock is held elsewhere: the gate gets it only once the clock has reached `until`."""
    original = worker.db.lock

    def lock(key):
        original(key)
        if key.startswith("account-control|") and worker.clock.now() < until:
            worker.clock.advance_to(until)

    monkeypatch.setattr(worker.db, "lock", lock)


@pytest.mark.unit
@pytest.mark.parametrize("after, failing", [("open", {"session"}), ("approval", {"session", "approval"})])
def test_the_gate_decides_at_the_time_it_holds_its_locks_not_before(env, monkeypatch, after, failing):
    """B1 (Codex M4 review): the time was read before the lock wait, so an order could pass the pre-open check
    after the open and reach the broker stamped before it."""
    order, _ = env.convert(DAY)
    session = CAL.session(order.target_session)
    worker = env.worker(session.open - timedelta(microseconds=1))
    later = session.open + timedelta(seconds=1) if after == "open" else session.close + timedelta(minutes=1)
    wait_for_the_account_lock(worker, monkeypatch, later)
    assert worker.submit(order.order_id) == "GATE_REJECTED"
    assert env.broker.submits == []
    (gate,) = worker.orders.gate_decisions(order.order_id)
    assert gate.checked_at == later and failing <= {c.name for c in gate.checks if not c.passed}


@pytest.mark.unit
def test_a_control_that_takes_effect_during_the_lock_wait_is_seen(env, monkeypatch):
    order, view = env.convert(DAY)
    start = pre_open(order, view)
    env.stores.accounts.set_autonomy("R2", 1, by=OWNER, reason="lowered while the gate waited",
                                     effective_at=start + timedelta(minutes=1))
    worker = env.worker(start)
    wait_for_the_account_lock(worker, monkeypatch, start + timedelta(minutes=2))
    assert worker.submit(order.order_id) == "GATE_REJECTED" and env.broker.submits == []
    (gate,) = worker.orders.gate_decisions(order.order_id)
    assert [c.name for c in gate.checks if not c.passed] == ["controls"]


@pytest.mark.unit
def test_the_broker_call_carries_its_own_time_never_the_gates(env, monkeypatch):
    order, view = env.convert(DAY)
    start = pre_open(order, view)
    worker = env.worker(start)
    real = worker_module.gate_order

    def gate_then_time_passes(*args, **kwargs):
        decision = real(*args, **kwargs)
        worker.clock.advance_to(start + timedelta(minutes=2))
        return decision

    monkeypatch.setattr(worker_module, "gate_order", gate_then_time_passes)
    assert worker.submit(order.order_id) == "SUBMITTED"
    assert env.broker.submits == [(order.client_order_id, start + timedelta(minutes=2))]
    (gate,) = worker.orders.gate_decisions(order.order_id)
    assert gate.checked_at == start
