"""Crash recovery with real OS processes (docs/tasks/M4-08.md; G4; Laws 11, 14; Part J fault injection).

Each crash is a hard kill (Popen.kill / TerminateProcess) at a fault point inside an unchanged role object; the
restart runs recovery and a normal step. Market data is the test store: a constant 120.00 bar, so a BUY limited at
121.20 fills at the target session's open once that session's bar is known.
"""

from datetime import timedelta

import pytest

from investment_engine.oms.order_states import OrderState as S
from tests.engine import process_harness
from tests.engine.test_conversion import order_store
from tests.engine.test_intent_pipeline import DAY
from tests.engine.worker_env import WorkerEnv, after_close, pre_open

pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database, tmp_path):
    e = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    e.dsn, e.tmp = pg_database, tmp_path
    yield e
    e.close()


def child(env, role, at, fault=None, **extra):
    spec = {"role": role, "at": at.isoformat(), "market": str(env.root), "flag": str(env.flag), "fault": fault,
            "account": "R2", **extra}
    return process_harness.run(spec, dsn=env.dsn, tmp=env.tmp)


def broker_orders(env, order):
    return env.stores.db.fetchone("SELECT COUNT(*) FROM sim_broker.orders WHERE client_order_id = :c",
                                  {"c": order.client_order_id})[0]


@pytest.mark.unit
def test_killed_after_submitting_is_saved_before_the_call_becomes_unknown_never_resent(env):
    order, view = env.convert(DAY)
    at = pre_open(order, view)
    assert child(env, "worker", at, "before_submit") is None
    assert env.state(order).state is S.SUBMITTING and broker_orders(env, order) == 0
    child(env, "worker", at + timedelta(minutes=1))
    assert env.state(order).state is S.UNKNOWN and broker_orders(env, order) == 0
    child(env, "worker", after_close(order))
    assert env.state(order).state is S.UNKNOWN and broker_orders(env, order) == 0  # never resent (Law 14)


@pytest.mark.unit
def test_killed_after_the_broker_accepted_resolves_to_one_order_and_fills(env):
    order, view = env.convert(DAY)
    at = pre_open(order, view)
    assert child(env, "worker", at, "after_submit") is None
    assert env.state(order).state is S.SUBMITTING and broker_orders(env, order) == 1
    child(env, "worker", at + timedelta(minutes=1))
    assert env.state(order).state is S.SUBMITTED and broker_orders(env, order) == 1
    child(env, "worker", after_close(order))
    status = env.state(order)
    assert (status.state, status.filled_qty) == (S.FILLED, order.quantity) and broker_orders(env, order) == 1


@pytest.mark.unit
def test_killed_mid_ingest_records_the_fill_once(env):
    order, view = env.convert(DAY)
    child(env, "worker", pre_open(order, view))
    assert child(env, "worker", after_close(order), "mid_ingest") is None
    assert env.state(order).state is S.SUBMITTED  # the fill's transaction never committed
    child(env, "worker", after_close(order) + timedelta(minutes=1))
    assert env.state(order).state is S.FILLED
    assert len(order_store(env).fills(order.order_id)) == 1


@pytest.mark.unit
@pytest.mark.parametrize("trading", [True, False], ids=["enabled", "disabled"])
@pytest.mark.parametrize("fault", ["cancel_before_call", "cancel_after_accept"])
def test_a_cancel_survives_a_crash_on_either_side_of_the_broker_call(env, fault, trading):
    order, view = env.convert(DAY)
    child(env, "worker", pre_open(order, view))
    assert env.state(order).state is S.SUBMITTED
    if not trading:
        env.enable(False, 2)  # cancels are never blocked (Law 15)
    env.cancel(order)
    at = pre_open(order, view) + timedelta(minutes=2)
    assert child(env, "worker", at, fault) is None
    assert env.state(order).state is S.CANCEL_PENDING
    child(env, "worker", at + timedelta(minutes=1))  # resent (idempotent at the broker), then the message closes it
    child(env, "worker", at + timedelta(minutes=2))
    assert env.state(order).state is S.CANCELLED
    cancels = env.stores.db.fetchall("SELECT progress, outcome FROM cancel_progress WHERE progress = 'CLOSED'")
    assert cancels == [("CLOSED", "CANCELLED")]


@pytest.mark.unit
@pytest.mark.parametrize("fault", ["core_before_conversion", "core_after_conversion"])
def test_the_core_engine_killed_around_conversion_converts_and_publishes_once(env, fault):
    view = env.approved_view(DAY)
    at = view.generated_at
    assert child(env, "core", at, fault) is None
    converted = env.count("orders")
    assert converted == (0 if fault == "core_before_conversion" else 1)
    child(env, "core", at + timedelta(seconds=1))
    assert env.count("orders") == 1
    published = env.stores.db.fetchall("SELECT event_type FROM event_log WHERE event_type = 'order.created'")
    assert len(published) == 1
    (order, _), = order_store(env).for_account("R2")
    child(env, "worker", pre_open(order, view))
    assert env.state(order).state is S.SUBMITTED and broker_orders(env, order) == 1


@pytest.mark.unit
def test_a_dropped_connection_mid_run_reconnects_consistently(env):
    order, view = env.convert(DAY)
    worker = env.worker(pre_open(order, view))
    worker.db.connection.close()  # the client-side drop (M4-08 rule 6); the server is never stopped
    import psycopg

    with pytest.raises(psycopg.OperationalError):
        worker.step()
    env._worker_stores = None  # a fresh connection, as a restarted worker would open
    env.worker(pre_open(order, view) + timedelta(minutes=1)).step()
    assert env.state(order).state is S.SUBMITTED and broker_orders(env, order) == 0  # the test double's broker
