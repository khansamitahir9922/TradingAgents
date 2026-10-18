"""Applying broker messages once, under the matrix (docs/tasks/M4-07.md rule 2; M4-00 rule 4)."""

from datetime import timedelta

import pytest

from investment_engine.oms.order_states import OrderState as S
from tests.engine.test_intent_pipeline import DAY
from tests.engine.worker_env import WorkerEnv, after_close, pre_open

pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database, tmp_path):
    e = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    yield e
    e.close()


def submitted(env):
    order, view = env.convert(DAY)
    env.worker(pre_open(order, view)).step()
    assert env.state(order).state is S.SUBMITTED
    return order


def steps(env, order, n=1, at=None):
    for _ in range(n):
        env.worker(at or after_close(order)).step()
    return env.state(order)


@pytest.mark.unit
def test_partial_fills_then_a_completing_one(env):
    order = submitted(env)
    t = after_close(order)
    first = order.quantity // 3
    env.broker.send("FILL", order.client_order_id, t, quantity=str(first), fill_id="a")
    env.broker.send("FILL", order.client_order_id, t, quantity=str(first), fill_id="b")
    assert steps(env, order).state is S.PARTIALLY_FILLED
    env.broker.send("FILL", order.client_order_id, t, quantity=str(order.quantity - 2 * first), fill_id="c")
    status = steps(env, order, 2)
    assert (status.state, status.filled_qty) == (S.FILLED, order.quantity)


@pytest.mark.unit
def test_cancelled_delivered_before_a_delayed_fill(env):
    order = submitted(env)
    t = after_close(order)
    env.broker.send("CANCELLED", order.client_order_id, t)
    assert steps(env, order).state is S.CANCELLED  # unsolicited: SUBMITTED -> CANCEL_PENDING -> CANCELLED
    env.broker.send("FILL", order.client_order_id, t + timedelta(minutes=1), quantity="1", fill_id="late")
    status = steps(env, order, 1, t + timedelta(minutes=2))
    assert (status.state, status.filled_qty) == (S.CANCELLED, 1)  # accounting only; the state stays final


@pytest.mark.unit
def test_duplicate_and_reordered_messages_apply_once(env):
    order, view = env.convert(DAY)
    env.broker.timeout_next_submit = True  # UNKNOWN; then a fill arrives before any ack
    env.worker(pre_open(order, view)).step()
    t = after_close(order)
    env.broker.send("FILL", order.client_order_id, t, quantity=str(order.quantity), fill_id="f", message_id="m1")
    env.broker.send("ACK", order.client_order_id, t, message_id="m0-late-ack")
    env.broker.queue.append(env.broker.queue[-2])  # the fill delivered twice
    status = steps(env, order, 3)
    assert (status.state, status.filled_qty) == (S.FILLED, order.quantity)
    assert len(env.worker(t).orders.fills(order.order_id)) == 1


@pytest.mark.unit
def test_expired_on_a_partially_filled_order_is_an_anomaly_once(env):
    order = submitted(env)
    t = after_close(order)
    env.broker.send("FILL", order.client_order_id, t, quantity="1", fill_id="p")
    env.broker.send("EXPIRED", order.client_order_id, t + timedelta(minutes=1))
    status = steps(env, order, 3, t + timedelta(minutes=2))
    assert status.state is S.PARTIALLY_FILLED  # D19: no G3 edge
    kinds = [a.kind for a in env.worker(t).orders.anomalies(order.order_id)]
    assert kinds == ["expired_without_edge"]


@pytest.mark.unit
def test_a_conflicting_fill_is_one_anomaly_however_many_steps(env):
    order = submitted(env)
    t = after_close(order)
    env.broker.send("FILL", order.client_order_id, t, quantity="1", fill_id="x", message_id="a")
    env.broker.send("FILL", order.client_order_id, t, quantity="2", fill_id="x", message_id="b")
    steps(env, order, 3)
    kinds = [a.kind for a in env.worker(t).orders.anomalies(order.order_id)]
    assert kinds == ["conflicting_duplicate_fill"] and env.state(order).filled_qty == 1
