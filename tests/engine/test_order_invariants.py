"""Part J order invariants over seeded random sequences (docs/tasks/M4-11.md; architecture Part J; D33).

Each invariant is checked against the stores' final state and history, never against what the code believes it did.
Store-level properties run SEEDS (200) sequences; flow-level properties (real proposals, gate and worker) run FLOW_SEEDS
(200 by default, about 3 minutes; IE_INVARIANT_FLOW_SEEDS changes it). A failure names its seed.
"""

import os
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.execution.ingest import apply_message
from investment_engine.oms import order_states
from investment_engine.oms.intent_store import StaleWrite
from investment_engine.oms.intents import IntentState
from investment_engine.oms.order_states import EDGES, OWNER, OrderState as S, ProcessRole
from tests.engine import order_sequences
from tests.engine.test_order_store import PASS, Env as StoreEnv

SEEDS = 200
FLOW_SEEDS = int(os.environ.get("IE_INVARIANT_FLOW_SEEDS", "200"))
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


class Clock:
    def now(self):
        return NOW


@pytest.fixture(scope="module")
def store_env(request, tmp_path_factory):
    from tests.engine.conftest import maintenance_dsn, temporary_database

    dsn = maintenance_dsn()
    if dsn is None:
        pytest.skip("PostgreSQL test DSN not set (see docs/dev/postgresql.md)")
    with temporary_database(dsn) as database:
        env = StoreEnv(database)
        yield env
        env.close()


def submitted(env, n):
    order = env.created()
    status = env.worker.transition(order.order_id, S.SUBMITTING, expected_aggregate_version=1, at=NOW, reason="t",
                                   gate=PASS.__class__(order.order_id, 1, True, PASS.checks, NOW, "{}"))
    if n % 3:
        env.worker.transition(order.order_id, S.SUBMITTED, expected_aggregate_version=status.aggregate_version,
                              at=NOW, reason="t")
    return order


# ---------------------------------------------------------------- store-level properties (200 seeds)


@pytest.mark.postgres
@pytest.mark.unit
def test_random_broker_streams_keep_every_order_invariant(store_env):
    """No duplicate fills; a REJECTED or GATE_REJECTED order never fills; versions are contiguous with one event
    each; every state change is a G3 edge by its owner; filled never exceeds quantity."""
    env = store_env
    for seed in range(SEEDS):
        order = submitted(env, seed)
        stream = order_sequences.messages(seed, order.client_order_id, order.quantity, NOW)
        for message in stream:
            apply_message(message, orders=env.worker, clock=Clock())
        sent_ids = {m.fill.broker_fill_id for m in stream if m.fill is not None}
        _, status = env.worker.get(order.order_id)
        history = env.worker.history(order.order_id)
        fills = env.worker.fills(order.order_id)
        assert [t.aggregate_version for t in history] == list(range(1, len(history) + 1)), seed
        events = [v for v, _ in env.worker_outbox.of(order.order_id) + env.core_outbox.of(order.order_id)]
        assert sorted(events) == list(range(1, status.aggregate_version + 1)), seed  # one event per version
        assert len({f.broker_fill_id for f in fills}) == len(fills), seed  # Part J: no duplicate fills
        assert {f.broker_fill_id for f in fills} <= sent_ids, seed  # and each is a fill the broker really sent
        assert sum((f.quantity for f in fills), Decimal(0)) == status.filled_qty <= order.quantity, seed
        rejected_at = next((t.aggregate_version for t in history if t.to_state in (S.REJECTED, S.GATE_REJECTED)), None)
        if rejected_at is not None:  # Part J: a rejected order never becomes FILLED
            assert status.state is not S.FILLED and status.filled_qty == 0, seed
        for t in history[1:]:
            if t.from_state != t.to_state:
                assert t.to_state in EDGES[t.from_state], (seed, t.from_state, t.to_state)
                assert OWNER[(t.from_state, t.to_state)].value == t.by, seed


@pytest.mark.postgres
@pytest.mark.unit
def test_a_stale_compare_and_set_write_always_fails(store_env):
    env, rng = store_env, random.Random(7)
    for seed in range(SEEDS):
        order = submitted(env, 1)  # left SUBMITTED
        _, status = env.worker.get(order.order_id)
        first = S.CANCEL_PENDING  # then a write legal from the new state, but with the stale version
        second = rng.choice([S.CANCELLED])
        env.worker.transition(order.order_id, first, expected_aggregate_version=status.aggregate_version, at=NOW,
                              reason="first")
        with pytest.raises(StaleWrite):
            env.worker.transition(order.order_id, second, expected_aggregate_version=status.aggregate_version,
                                  at=NOW, reason="stale")
        after = env.worker.get(order.order_id)[1]
        assert (after.state, after.aggregate_version) == (first, status.aggregate_version + 1), seed
        stale = rng.choice([S.EXPIRED, S.REJECTED])  # not legal from the new state: refused as well, nothing written
        with pytest.raises((StaleWrite, order_states.IllegalTransition)):
            env.worker.transition(order.order_id, stale, expected_aggregate_version=status.aggregate_version,
                                  at=NOW, reason="stale")
        assert env.worker.get(order.order_id)[1] == after, seed


@pytest.mark.unit
def test_each_transition_is_written_only_by_its_owning_process():
    rng = random.Random(11)
    states = [None, *S]
    for _ in range(SEEDS):
        a, b, role = rng.choice(states), rng.choice(list(S)), rng.choice(list(ProcessRole))
        owner = OWNER.get((a, b))
        if owner is None:
            with pytest.raises(order_states.IllegalTransition):
                order_states.check(a, b, role)
        elif owner is role:
            order_states.check(a, b, role)
        else:
            with pytest.raises(order_states.WrongProcess):
                order_states.check(a, b, role)


@pytest.mark.unit
def test_no_process_other_than_the_execution_worker_can_load_broker_credentials():
    """Part J; the M4-03 layering rule and canary test, linked here."""
    from tests.engine.test_layering import PACKAGE, execution_boundary_offenders

    assert execution_boundary_offenders(PACKAGE) == []


# ---------------------------------------------------------------- flow-level properties (real gate and worker)


@pytest.fixture
def flow(pg_database, tmp_path):
    from tests.engine.worker_env import WorkerEnv

    env = WorkerEnv(pg_database, tmp_path / "market", tmp_path / "control")
    yield env
    env.close()


def run_flow(env, seed, day):
    from tests.engine.worker_env import after_close, pre_open

    plan = order_sequences.flow_plan(seed)
    order, view = env.convert(day, tag=f"seed-{seed}")
    env.enable(plan["enabled"], sequence=2 * seed + 2)
    env.broker.timeout_next_submit = plan["timeout"]
    at = pre_open(order, view)
    if plan["cancel"]:
        env.cancel(order)
    env.worker(at).step()
    if plan["flip_after"]:
        env.enable(not plan["enabled"], sequence=2 * seed + 3)
    t = after_close(order)
    if env.state(order).state is S.SUBMITTED and plan["answer"] != "none":
        quantity = str(order.quantity) if plan["answer"] == "FILL" else None
        env.broker.send(plan["answer"], order.client_order_id, t, quantity=quantity, fill_id=f"seed-{seed}",
                        message_id=f"seed-{seed}-answer")
    for k in range(3):
        env.worker(t + timedelta(minutes=k)).step()
    return order, plan


@pytest.mark.postgres
@pytest.mark.unit
def test_flows_never_bypass_controls_never_resubmit_unknown_and_respect_the_kill_switch(flow):
    from tests.engine.test_intent_pipeline import SESSIONS

    env = flow
    for seed in range(FLOW_SEEDS):
        order, plan = run_flow(env, seed, SESSIONS[60 + seed % 120])  # tagged views: distinct intents on reused days
        sent = env.broker.submitted(order.client_order_id)
        status = env.state(order)
        intent = env.stores.intents.get(order.intent_id, order.intent_version)
        gates = env.stores.db.fetchall("SELECT passed FROM gate_decisions WHERE order_id = :o", {"o": order.order_id})
        # Part J: no path reaches the broker without Policy, Risk and the Gate
        if sent:
            assert intent.state is IntentState.CONVERTED and intent.policy_decision is not None, seed
            assert intent.risk_decision is not None and (True,) in gates, seed
        # nothing new is submitted while the kill switch is off (cancels still pass, see M4-07)
        if not plan["enabled"]:
            assert sent == 0 and status.state in (S.GATE_REJECTED,), (seed, status.state)
        # UNKNOWN orders are never resubmitted
        assert sent <= 1, seed
        # rejected intents never become orders: every order's intent is CONVERTED
        assert intent.state is IntentState.CONVERTED, seed
    # an approved intent version never changes: its content id still matches the order's pin
    from investment_engine.oms.conversion import intent_content_id

    for o, _ in env.worker(env.clock.now() + timedelta(days=3650)).orders.for_account("R2"):
        assert intent_content_id(env.stores.intents.get(o.intent_id, o.intent_version).intent) == o.intent_content_id


@pytest.mark.postgres
@pytest.mark.unit
def test_replay_determinism_two_runs_give_the_same_orders_states_fills_and_ids(tmp_path):
    from tests.engine.conftest import maintenance_dsn, temporary_database
    from tests.engine.test_intent_pipeline import SESSIONS
    from tests.engine.worker_env import WorkerEnv

    dsn = maintenance_dsn()
    if dsn is None:
        pytest.skip("PostgreSQL test DSN not set (see docs/dev/postgresql.md)")
    outcomes = []
    for run in ("a", "b"):
        with temporary_database(dsn) as database:
            env = WorkerEnv(database, tmp_path / run / "market", tmp_path / run / "control")
            try:
                rows = []
                for seed in range(5):
                    order, _ = run_flow(env, seed, SESSIONS[60 + seed])
                    status = env.state(order)
                    fills = [(f.fill_id, f.quantity, f.price) for f in env.worker(env.clock.now()).orders.fills(order.order_id)]
                    rows.append((order.order_id, order.client_order_id, status.state, status.aggregate_version, fills))
                outcomes.append(rows)
            finally:
                env.close()
    assert outcomes[0] == outcomes[1]
