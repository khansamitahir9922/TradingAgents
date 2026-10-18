"""Cancels carried to a durable close, even with trading disabled (docs/tasks/M4-07.md rule 3; Law 15)."""

import contextlib
import threading
from datetime import timedelta

import pytest

from investment_engine.oms.order_states import OrderState as S
from investment_engine.oms.orders import CancelProgress
from tests.engine.test_intent_pipeline import DAY, SESSIONS
from tests.engine.worker_env import WorkerEnv, after_close, pre_open

pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database, tmp_path):
    e = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    yield e
    e.close()


def submitted(env, day=DAY):
    order, view = env.convert(day)
    env.worker(pre_open(order, view)).step()
    return order, view


def request(env, order):
    worker = env.worker(after_close(order))
    return [(r.cancel_id, p) for r, p, _ in worker.orders.open_cancels() if r.order_id == order.order_id]


@pytest.mark.unit
def test_a_cancel_goes_through_with_trading_disabled_and_closes_when_final(env):
    order, view = submitted(env)
    env.enable(False, 2)
    t = after_close(order)
    env.cancel(order, t)
    env.worker(t).step()
    assert env.state(order).state is S.CANCEL_PENDING and [c for c, _ in env.broker.cancels] == [order.client_order_id]
    assert request(env, order)[0][1] is CancelProgress.SENT  # PENDING never closes it
    env.broker.send("CANCELLED", order.client_order_id, t + timedelta(minutes=1))
    env.worker(t + timedelta(minutes=2)).step()
    assert env.state(order).state is S.CANCELLED
    env.worker(t + timedelta(minutes=3)).step()
    assert request(env, order) == []
    (closed,) = env.stores.db.fetchall("SELECT progress, outcome FROM cancel_progress WHERE progress = 'CLOSED'")
    assert closed == ("CLOSED", "CANCELLED")


@pytest.mark.unit
def test_a_timeout_leaves_sending_and_the_next_step_resends(env):
    order, _ = submitted(env)
    t = after_close(order)
    env.cancel(order, t)
    env.broker.timeout_next_cancel = True
    env.worker(t).step()
    assert request(env, order)[0][1] is CancelProgress.SENDING
    env.worker(t + timedelta(minutes=1)).step()
    assert len(env.broker.cancels) == 2 and request(env, order)[0][1] is CancelProgress.SENT
    attempts = env.stores.db.fetchone("SELECT MAX(attempt) FROM cancel_progress")[0]
    assert attempts == 2


@pytest.mark.unit
def test_too_late_after_a_fill_closes_the_request(env):
    order, _ = submitted(env)
    t = after_close(order)
    env.cancel(order, t)
    env.broker.cancel_outcome = "TOO_LATE"
    env.worker(t).step()
    env.broker.send("FILL", order.client_order_id, t + timedelta(minutes=1), quantity=str(order.quantity))
    env.worker(t + timedelta(minutes=2)).step()
    env.worker(t + timedelta(minutes=3)).step()
    assert env.state(order).state is S.FILLED and request(env, order) == []
    assert env.stores.db.fetchone("SELECT outcome FROM cancel_progress WHERE progress = 'CLOSED'")[0] == "TOO_LATE"


@pytest.mark.unit
def test_a_cancel_request_racing_a_fill_ends_filled_or_cancelled_once(env):
    for n in range(20):
        order, _ = submitted(env, SESSIONS[100 + n])
        t = after_close(order)
        env.broker.send("FILL", order.client_order_id, t, quantity=str(order.quantity), fill_id=f"race-{n}")
        barrier = threading.Barrier(2)

        def core(order=order, t=t, barrier=barrier):
            barrier.wait()
            with contextlib.suppress(ValueError):  # the fill made it final first: nothing to cancel
                env.cancel(order, t)

        def worker(t=t, barrier=barrier):
            barrier.wait()
            env.worker(t).step()

        threads = [threading.Thread(target=core), threading.Thread(target=worker)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=60)
        for k in range(3):
            if env.state(order).state is S.CANCEL_PENDING:
                env.broker.send("CANCELLED", order.client_order_id, t + timedelta(minutes=k + 1),
                                message_id=f"c-{n}-{k}")
            env.worker(t + timedelta(minutes=k + 2)).step()
        status = env.state(order)
        assert status.state in (S.FILLED, S.CANCELLED)
        assert len(env.worker(t).orders.fills(order.order_id)) <= 1
        assert request(env, order) == []
