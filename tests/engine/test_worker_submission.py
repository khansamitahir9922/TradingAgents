"""Submission in three phases (docs/tasks/M4-07.md rules 1, 5, 6; Laws 13, 14)."""

import pytest

from investment_engine.oms.order_states import OrderState as S
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import open_operational_pg
from tests.engine.test_intent_pipeline import DAY
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
