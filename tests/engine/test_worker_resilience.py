"""Uncertain orders reconciled on every step, per-item isolation, and reconnection inside the running role loops
(docs/tasks/M4-08.md; G4; Laws 11, 14; Codex M4 review B4)."""

import threading
import time
from datetime import timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.core.engine import CoreEngine
from investment_engine.execution.broker_port import BrokerTimeout
from investment_engine.execution.reads import StoreGateReads
from investment_engine.execution.recovery import recover
from investment_engine.execution.worker import ExecutionWorker
from investment_engine.killswitch.flag import KillSwitchReader
from investment_engine.oms.intent_store import StaleWrite
from investment_engine.oms.order_states import OrderState as S
from investment_engine.oms.orders import GateDecision
from investment_engine.policy.decisions import CheckResult
from investment_engine.portfolio.fingerprint import DeclaredFingerprints
from tests.engine.test_intent_pipeline import CAL, DAY, SESSIONS, t_of
from tests.engine.worker_env import WorkerEnv, after_close, pre_open

pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database, tmp_path):
    e = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    yield e
    e.close()


def submitting(env, worker, order, at):
    """The order saved as SUBMITTING, as if the worker died before or during its broker call."""
    _, state = worker.orders.get(order.order_id)
    gate = GateDecision(order.order_id, 1, True, (CheckResult("test", True, "pass"),), at, "{}")
    worker.orders.transition(order.order_id, S.SUBMITTING, expected_aggregate_version=state.aggregate_version,
                             at=at, reason="crashed mid-submission", gate=gate)


def until(condition, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


@pytest.mark.unit
def test_a_submitting_lookup_error_at_start_up_is_retried_by_the_next_normal_step(env):
    """B4: recovery ran only at start-up, so one failed lookup left the order SUBMITTING, reserved, indefinitely."""
    order, view = env.convert(DAY)
    worker = env.worker(pre_open(order, view))
    submitting(env, worker, order, pre_open(order, view))
    real, attempts = env.broker.lookup, []

    def flaky(client, *, at):
        attempts.append(client)
        if len(attempts) == 1:
            raise BrokerTimeout("temporary")
        return real(client, at=at)

    env.broker.lookup = flaky
    assert recover(worker).submitting_left == 1 and env.state(order).state is S.SUBMITTING
    worker.step()
    assert len(attempts) >= 2 and env.state(order).state is S.UNKNOWN  # the broker never had it (D20)
    assert env.broker.submits == []  # never resent (Law 14)


@pytest.mark.unit
def test_a_lookup_error_on_one_unknown_order_never_stops_another(env):
    real, failing = env.broker.lookup, set()

    def lookup(client, *, at):
        if client in failing:
            raise RuntimeError("the broker failed on this one")
        return real(client, at=at)

    env.broker.lookup = lookup
    orders = []
    for day, tag in ((DAY, "first"), (SESSIONS[SESSIONS.index(DAY) + 1], "second")):
        order, v = env.convert(day, tag=tag)  # each converted when its turn comes: a step gates every NEW order
        env.broker.timeout_next_submit = True  # the broker got it, but the answer was lost
        if not orders:
            failing.add(order.client_order_id)
        env.worker(pre_open(order, v)).step()  # the second's step looks up the first, and fails on it
        assert env.state(order).state is S.UNKNOWN
        orders.append(order)
    first, second = orders
    worker = env.worker(after_close(second))
    worker.step()
    assert env.state(first).state is S.UNKNOWN and env.state(second).state is S.SUBMITTED
    failing.clear()
    worker.step()
    assert env.state(first).state is S.SUBMITTED


@pytest.mark.unit
def test_a_concurrent_change_on_one_message_skips_only_that_message(env, monkeypatch):
    first, view = env.convert(DAY)
    env.worker(pre_open(first, view)).step()
    second, second_view = env.convert(SESSIONS[SESSIONS.index(DAY) + 1], tag="second")
    env.worker(pre_open(second, second_view)).step()
    t = after_close(second)
    for order in (first, second):
        env.broker.send("FILL", order.client_order_id, t, quantity=str(order.quantity))
    worker = env.worker(t + timedelta(minutes=1))
    real, raised = worker.orders.record_fill, []

    def stale_once(fill, **kwargs):
        if not raised and fill.order_id == first.order_id:
            raised.append(fill.broker_fill_id)
            raise StaleWrite("changed meanwhile")
        return real(fill, **kwargs)

    monkeypatch.setattr(worker.orders, "record_fill", stale_once)
    worker.step()
    assert raised and env.state(first).state is S.SUBMITTED and env.state(second).state is S.FILLED
    worker.step()
    assert env.state(first).state is S.FILLED


def terminate(env, db):
    """Kill the backend of `db`'s connection from the server side; the server itself keeps running."""
    env.stores.db.execute("SELECT pg_terminate_backend(:pid)", {"pid": db.connection.info.backend_pid})


@pytest.mark.unit
def test_the_running_worker_loop_reconnects_recovers_and_carries_on(env):
    start = t_of(DAY) + timedelta(minutes=1)
    assert start < CAL.session(CAL.next_session(DAY).date).open
    clock, built = ReplayClock(start), []

    def build():
        stores = env.connect(clock)
        worker = ExecutionWorker(stores.db, clock=clock, broker=env.broker, kill_switch=KillSwitchReader(env.flag))
        worker.reads = StoreGateReads(stores, worker.orders, knowledge=env.knowledge, calendar=CAL,
                                      fingerprints=DeclaredFingerprints(stores.snapshots))
        built.append(worker)
        return worker

    first, done = build(), threading.Event()
    loop = threading.Thread(target=lambda: first.run(poll_seconds=Decimal("0.05"), stop=done.is_set,
                                                     reconnect=build), daemon=True)
    loop.start()
    try:
        time.sleep(0.3)  # a few normal steps
        terminate(env, first.db)
        order, _ = env.convert(DAY)  # work arriving while the worker's connection is gone
        assert until(lambda: env.state(order).state is S.SUBMITTED), "the loop never recovered"
    finally:
        done.set()
        loop.join(30)
    assert not loop.is_alive() and len(built) >= 2  # rebuilt on new connections, inside the running loop
    assert env.broker.submitted(order.client_order_id) == 1


@pytest.mark.unit
def test_the_running_core_loop_reconnects_and_publishes_what_was_saved_meanwhile(env):
    clock, built = ReplayClock(t_of(DAY)), []

    def build():
        engine = CoreEngine(env.connect(clock), clock=clock)
        built.append(engine)
        return engine

    first, done = build(), threading.Event()
    loop = threading.Thread(target=lambda: first.run(poll_seconds=Decimal("0.05"), stop=done.is_set,
                                                     reconnect=build), daemon=True)
    loop.start()
    try:
        time.sleep(0.3)
        terminate(env, first.stores.db)
        order, _ = env.convert(DAY)  # its order.created event waits in the outbox

        def published():
            return env.stores.db.fetchone("SELECT COUNT(*) FROM event_log WHERE event_type = 'order.created' "
                                          "AND aggregate_id = :id", {"id": order.order_id})[0] == 1
        assert until(published), "the Core loop never recovered"
    finally:
        done.set()
        loop.join(30)
    assert not loop.is_alive() and len(built) >= 2


@pytest.mark.unit
def test_a_lost_broker_connection_reaches_the_running_loops_reconnect(env):
    """R5 (Codex M4 review of fd73684): N1 turned every broker-call exception into an ordinary unknown outcome,
    including the simulator's own lost database connection. The loop never rebuilt it, and a new order became
    UNKNOWN. A lost connection must reach the reconnect, whichever connection it was; ordinary broker errors stay
    isolated (N1). After the rebuild, the order is submitted exactly once, and messages, cancels and lookups work."""
    from investment_engine.execution.simulated_broker import SimulatedBroker, load_fee_schedule

    order, view = env.convert(DAY)
    clock = ReplayClock(pre_open(order, view))
    built, steps = [], []

    def build():
        stores, broker_stores = env.connect(clock), env.connect(clock)  # separate connections, as deployed
        broker = SimulatedBroker(broker_stores.db, knowledge=env.knowledge, calendar=CAL, source="yfinance",
                                 fees=load_fee_schedule())
        worker = ExecutionWorker(stores.db, clock=clock, broker=broker, kill_switch=KillSwitchReader(env.flag))
        worker.reads = StoreGateReads(stores, worker.orders, knowledge=env.knowledge, calendar=CAL,
                                      fingerprints=DeclaredFingerprints(stores.snapshots))
        real = worker.step

        def step():
            steps.append(len(steps))
            return real()

        worker.step = step
        built.append(worker)
        return worker

    first = build()
    first.broker._db.connection.close()  # only the broker's connection: the worker's and the server stay healthy
    last = first.run(poll_seconds=Decimal("0"), stop=lambda: len(steps) >= 4, reconnect=build)
    assert len(built) >= 2, "the reconnect was never called"
    assert env.state(order).state is S.SUBMITTED
    assert env.stores.db.fetchone("SELECT COUNT(*) FROM sim_broker.orders WHERE client_order_id = :c",
                                  {"c": order.client_order_id})[0] == 1  # exactly once
    # The rebuilt broker serves every call again: a lookup, a cancel and a message read.
    later = after_close(order) + timedelta(minutes=1)
    clock.advance_to(later)
    assert last.port.lookup(order.client_order_id, at=later) is not None
    env.cancel(order)
    last.step()
    assert {p.value for _, p, _ in last.orders.open_cancels()} <= {"SENT"}
    assert isinstance(last.port.messages(after=None, at=later), list)
