"""Part J's fault-injection list with real Core and Execution Worker processes (docs/tasks/M4-12.md).

Each scenario runs from a fresh database. The role objects are unchanged production code, started as OS
processes through tests/engine/process_harness.py, and they communicate only through the database. A process
that fails to start is a test error, never a pass. Each scenario asserts the end state from the stores.

Not applicable: "missing research" (research isn't on the M4 path; it arrives in M6).
Not run: an actual PostgreSQL server restart (the owner's shared server is never stopped); scenario 4 is a
dropped client connection instead (M4-08 rule 6).
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from investment_engine.oms.order_states import OrderState as S
from tests.engine import process_harness
from tests.engine.test_conversion import order_store
from tests.engine.test_intent_pipeline import CAL, DAY, SESSIONS, write_bars
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


def count(env, sql, **params):
    return env.stores.db.fetchone(sql, params)[0]


def fills(env, order):
    return order_store(env).fills(order.order_id)


def message(env, order, kind, delivered, *, message_id, quantity=None, fill_id=None, executed=None):
    """Play the broker: a message in the simulator's own table (the test acting as the market). A fill executes at
    `executed` (default: when it is delivered)."""
    fill = None
    if kind == "FILL":
        import json

        fill = json.dumps({"broker_fill_id": fill_id, "quantity": str(quantity), "price": "120.00", "fee": "0",
                           "currency": "USD", "executed_at": (executed or delivered).isoformat(), "provenance": "{}"},
                          sort_keys=True)
    env.stores.db.execute("INSERT INTO sim_broker.messages VALUES (:m, :c, :k, :d, :f, 'injected')",
                          {"m": message_id, "c": order.client_order_id, "k": kind, "d": delivered, "f": fill})


def submitted(env, day=DAY):
    order, view = env.convert(day)
    child(env, "worker", pre_open(order, view))
    assert env.state(order).state is S.SUBMITTED
    return order, view


@pytest.mark.unit
@pytest.mark.parametrize("fault", ["before_submit", "after_submit"])
def test_1_worker_killed_mid_submission(env, fault):
    order, view = env.convert(DAY)
    assert child(env, "worker", pre_open(order, view), fault) is None
    child(env, "worker", pre_open(order, view) + timedelta(minutes=1))
    child(env, "worker", after_close(order))
    broker_orders = count(env, "SELECT COUNT(*) FROM sim_broker.orders WHERE client_order_id = :c",
                          c=order.client_order_id)
    assert broker_orders == (0 if fault == "before_submit" else 1)
    assert env.state(order).state is (S.UNKNOWN if fault == "before_submit" else S.FILLED)


@pytest.mark.unit
def test_1b_worker_killed_mid_cancel(env):
    order, view = submitted(env)
    env.cancel(order)
    at = pre_open(order, view) + timedelta(minutes=2)
    assert child(env, "worker", at, "cancel_before_call") is None
    child(env, "worker", at + timedelta(minutes=1))
    child(env, "worker", at + timedelta(minutes=2))
    assert env.state(order).state is S.CANCELLED


@pytest.mark.unit
def test_2_core_killed_after_approval(env):
    view = env.approved_view(DAY)
    assert child(env, "core", view.generated_at, "core_before_conversion") is None
    assert env.count("orders") == 0
    child(env, "core", view.generated_at + timedelta(seconds=1))
    assert env.count("orders") == 1


@pytest.mark.unit
def test_3_broker_timeout_is_unknown_then_resolved_by_lookup_never_resent(env):
    order, view = env.convert(DAY)
    child(env, "worker", pre_open(order, view), "raise_timeout")
    assert env.state(order).state is S.UNKNOWN
    child(env, "worker", pre_open(order, view) + timedelta(minutes=1))
    assert env.state(order).state is S.SUBMITTED
    assert count(env, "SELECT COUNT(*) FROM sim_broker.orders WHERE client_order_id = :c", c=order.client_order_id) == 1


@pytest.mark.unit
def test_4_a_dropped_connection_fails_the_step_and_a_restart_is_consistent(env):
    order, view = env.convert(DAY)
    failed = process_harness.run({"role": "worker", "at": pre_open(order, view).isoformat(), "market": str(env.root),
                                  "flag": str(env.flag), "fault": "drop_connection", "expect_failure": True,
                                  "account": "R2"}, dsn=env.dsn, tmp=env.tmp)
    assert failed.returncode != 0 and env.state(order).state is S.NEW  # nothing half-done
    child(env, "worker", pre_open(order, view) + timedelta(minutes=1))
    assert env.state(order).state is S.SUBMITTED


@pytest.mark.unit
def test_5_and_7_duplicate_fills_and_repeated_delivery_apply_once(env):
    order, view = submitted(env)
    during = CAL.session(order.target_session).open + timedelta(minutes=10)  # before the simulator decides
    message(env, order, "FILL", during, message_id="dup-1", quantity=order.quantity, fill_id="f-dup")
    message(env, order, "FILL", during, message_id="dup-2", quantity=order.quantity, fill_id="f-dup")
    for k in range(3):  # the stream is read again on every step: repeated delivery
        child(env, "worker", during + timedelta(minutes=k + 1))
    assert len(fills(env, order)) == 1 and env.state(order).state is S.FILLED


@pytest.mark.unit
def test_6_cancelled_then_an_earlier_execution_delivered_late(env):
    """Part J: a fill that executed *before* the cancellation, but was delivered after it (Codex M4 review B12: the
    earlier version executed it after the cancel). The order stays CANCELLED; the fill counts, as accounting only,
    with its true execution time."""
    order, view = submitted(env)
    during = CAL.session(order.target_session).open + timedelta(minutes=10)
    message(env, order, "CANCELLED", during, message_id="c-1")
    child(env, "worker", during + timedelta(minutes=1))
    assert env.state(order).state is S.CANCELLED
    executed = during - timedelta(minutes=5)  # before the cancellation took effect
    message(env, order, "FILL", during + timedelta(minutes=2), message_id="late-fill", quantity=Decimal(3),
            fill_id="late", executed=executed)
    child(env, "worker", during + timedelta(minutes=3))
    status = env.state(order)
    assert (status.state, status.filled_qty) == (S.CANCELLED, Decimal(3))  # accounting only: no state edge
    (fill,) = fills(env, order)
    assert fill.executed_at == executed and fill.delivered_at == during + timedelta(minutes=2)


@pytest.mark.unit
def test_8_a_stale_feed_expires_without_inventing_a_fill(pg_database, tmp_path):
    target = SESSIONS[61]
    env = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control",
                    reader=write_bars(tmp_path / "market", [d for d in SESSIONS if d != target]))
    env.dsn, env.tmp = pg_database, tmp_path
    try:
        order, view = env.convert(SESSIONS[60])
        assert order.target_session == target
        child(env, "worker", pre_open(order, view))
        cutoff = CAL.next_session(target).open
        child(env, "worker", cutoff + timedelta(minutes=1))
        assert env.state(order).state is S.EXPIRED and fills(env, order) == []
    finally:
        env.close()


@pytest.mark.unit
def test_9_a_data_revision_before_submission_fails_the_gate(env):
    from investment_engine.market.store.writer import MarketDataWriter
    from tests.engine.test_raw_reference import observation

    order, view = env.convert(DAY)
    at = pre_open(order, view)
    # a correction of the decision bar, received (so available: the store never backdates one) before submission
    MarketDataWriter(env.root).write_candles([observation(DAY, close="119.0000", received=at - timedelta(seconds=30))],
                                             import_id="correction")
    child(env, "worker", at)
    assert env.state(order).state is S.GATE_REJECTED
    (gate,) = order_store(env).gate_decisions(order.order_id)
    assert [c.name for c in gate.checks if not c.passed] == ["view"]


@pytest.mark.unit
def test_10_an_approval_expiring_before_submission(env):
    order, view = env.convert(DAY)
    child(env, "worker", after_close(order))
    assert env.state(order).state is S.GATE_REJECTED
    (gate,) = order_store(env).gate_decisions(order.order_id)
    assert "approval" in [c.name for c in gate.checks if not c.passed]


@pytest.mark.unit
def test_11_a_concurrent_cancel_request_and_fill(env):
    order, view = submitted(env)
    during = CAL.session(order.target_session).open + timedelta(minutes=10)
    message(env, order, "FILL", during, message_id="race-fill", quantity=order.quantity, fill_id="race")
    cancel = process_harness.start({"role": "cancel", "at": during.isoformat(), "order_id": order.order_id,
                                    "command_at": env.clock.now().isoformat(), "market": str(env.root),
                                    "flag": str(env.flag), "account": "R2"}, dsn=env.dsn, tmp=env.tmp)
    worker = process_harness.start({"role": "worker", "at": (during + timedelta(minutes=1)).isoformat(),
                                    "market": str(env.root), "flag": str(env.flag), "account": "R2"},
                                   dsn=env.dsn, tmp=env.tmp)
    for p in (cancel, worker):
        p.communicate(timeout=120)
        assert p.returncode == 0
    for k in range(2):
        child(env, "worker", during + timedelta(minutes=k + 2))
    assert env.state(order).state in (S.FILLED, S.CANCELLED) and len(fills(env, order)) <= 1
    assert count(env, "SELECT COUNT(*) FROM cancel_progress WHERE progress <> 'CLOSED' AND cancel_id NOT IN "
                      "(SELECT cancel_id FROM cancel_progress WHERE progress = 'CLOSED')") == 0


@pytest.mark.unit
def test_12_the_kill_switch_flipped_between_approval_and_submission(env):
    order, view = env.convert(DAY)
    env.enable(False, 2)
    child(env, "worker", pre_open(order, view))
    assert env.state(order).state is S.GATE_REJECTED
    assert count(env, "SELECT COUNT(*) FROM sim_broker.orders") == 0
