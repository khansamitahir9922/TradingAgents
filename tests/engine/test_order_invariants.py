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
from investment_engine.risk.decisions import RiskOutcome
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
    rejecting_accounts(env)
    yield env
    env.close()


def rejecting_accounts(env):
    """RP's policy restricts NVDA (POLICY_REJECTED); RR has a latched halt (RISK_REJECTED). Both Level 2, so only
    the checks stand between their intents and an order (Codex M4 review B12)."""
    from tests.engine.test_intent_pipeline import NVDA, OWNER, START

    for account in ("RP", "RR"):
        env.account(account, level=2)
    env.stores.limits.restrict("RP", NVDA, by=OWNER, reason="invariant test", effective_at=START)
    env.stores.limits.set_halt("RR", at=START, limits_version="risk-1", reason="invariant test")


def run_flow(env, seed, day):
    from investment_engine.oms.conversion import convert_approved
    from tests.engine.test_conversion import order_store
    from tests.engine.worker_env import after_close, pre_open

    plan = order_sequences.flow_plan(seed)
    order, view = env.convert(day, tag=f"seed-{seed}")
    if plan["unreadable"]:
        env.flag.write_text("not a flag", encoding="utf-8")  # unreadable: disabled, fail closed (ADR-006)
    if plan["rejected_on"]:  # the same decision for an account whose checks reject it: never an order
        env.propose(plan["rejected_on"], view)
        assert convert_approved(plan["rejected_on"], at=view.generated_at, stores=env.stores,
                                orders=order_store(env)).converted == ()
    if not plan["unreadable"]:
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
        # Part J: no path reaches the broker without Policy and Risk having *passed*, and the Gate
        if sent:
            assert intent.state is IntentState.CONVERTED and intent.policy_decision.passed is True, seed
            assert intent.risk_decision.outcome in (RiskOutcome.APPROVE, RiskOutcome.REDUCE), seed
            assert (True,) in gates, seed
        # nothing new is submitted while the kill switch is off (cancels still pass, see M4-07)
        if not plan["enabled"]:
            assert sent == 0 and status.state in (S.GATE_REJECTED,), (seed, status.state)
        # UNKNOWN orders are never resubmitted
        assert sent <= 1, seed
        # every order's intent is CONVERTED
        assert intent.state is IntentState.CONVERTED, seed
    # Part J: rejected intents never become orders, however the flows went
    for account, outcome in (("RP", "POLICY_REJECTED"), ("RR", "RISK_REJECTED")):
        records = env.stores.proposals.for_account(account)
        assert records and {r.outcome.value for r in records} == {outcome}, account  # non-vacuous
        assert env.stores.db.fetchone("SELECT COUNT(*) FROM orders WHERE account_id = :a", {"a": account})[0] == 0
    # an approved intent version never changes: its content id still matches the order's pin
    from investment_engine.oms.conversion import intent_content_id

    for o, _ in env.worker(env.clock.now() + timedelta(days=3650)).orders.for_account("R2"):
        assert intent_content_id(env.stores.intents.get(o.intent_id, o.intent_version).intent) == o.intent_content_id


def complete_record(env, order):
    """Everything a run leaves for one order: its view and intent, every version, fill, gate check and anomaly."""
    orders = env.worker(env.clock.now()).orders
    intent = env.stores.intents.get(order.intent_id, order.intent_version)
    return (order, intent.intent.view_lineage_id, intent.intent, intent.state,
            [(t.aggregate_version, t.from_state, t.to_state, t.at, t.by, t.reason, t.broker_ref)
             for t in orders.history(order.order_id)],
            [(f.fill_id, f.quantity, f.price, f.fee, f.executed_at, f.delivered_at, f.recorded_at, f.provenance)
             for f in orders.fills(order.order_id)],
            [(g.attempt, g.passed, g.checks, g.checked_at) for g in orders.gate_decisions(order.order_id)],
            [(a.kind, a.detail, a.at) for a in orders.anomalies(order.order_id)])


@pytest.mark.postgres
@pytest.mark.unit
def test_replay_determinism_two_runs_give_the_same_views_intents_and_complete_histories(tmp_path):
    """Two fresh databases, the same seeded flows (submission, kill switch, rejections and post-submission
    cancels): identical views, intents, every order version, fill, gate check and anomaly (Codex M4 review B12)."""
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
            rejecting_accounts(env)
            try:
                rows = [complete_record(env, run_flow(env, seed, SESSIONS[60 + seed])[0]) for seed in range(6)]
                rows += [complete_record(env, run_cancel_flow(env, seed, SESSIONS[80 + seed])[0]) for seed in range(4)]
                rows.append(sorted((r.record_id, r.outcome.value) for a in ("R2", "RP", "RR")
                                   for r in env.stores.proposals.for_account(a)))
                outcomes.append(rows)
            finally:
                env.close()
    assert outcomes[0] == outcomes[1]


# ---------------------------------------------------------------- cancels after submission (B12)


def run_cancel_flow(env, seed, day):
    from tests.engine.worker_env import after_close, pre_open

    plan = order_sequences.cancel_plan(seed)
    order, view = env.convert(day, tag=f"cancel-{seed}")
    env.enable(True, sequence=10_000 + seed)
    env.worker(pre_open(order, view)).step()
    assert env.state(order).state is S.SUBMITTED, seed
    if plan["trading_off"]:
        env.enable(False, sequence=20_000 + seed)
    t = after_close(order)
    half = max(order.quantity // 2, 1)
    if plan["partial"]:
        env.broker.send("FILL", order.client_order_id, t - timedelta(minutes=5), quantity=str(half),
                        fill_id=f"cancel-{seed}-part", message_id=f"cancel-{seed}-part")
    if plan["answer"] == "EXPIRED_FIRST":  # the session expired it before the cancel was processed
        env.broker.send("EXPIRED", order.client_order_id, t - timedelta(minutes=1), message_id=f"cancel-{seed}-exp")
    env.cancel(order)
    env.broker.timeout_next_cancel = plan["timeout_first"]
    worker = env.worker(t)
    steps = []
    if plan["crash_before_send"]:
        real = env.broker.cancel

        def crash(client, *, at):
            env.broker.cancel = real
            raise KeyboardInterrupt("the worker dies with SENDING saved, before the broker call")

        env.broker.cancel = crash
        with pytest.raises(KeyboardInterrupt):
            worker.step()
        worker = env.worker(t + timedelta(seconds=30))  # a restarted worker recovers, then steps
        from investment_engine.execution.recovery import recover

        recover(worker)
    steps.append(observe(env, order, worker.step()))
    steps.append(observe(env, order, env.worker(t + timedelta(minutes=1)).step()))
    remaining = order.quantity - (half if plan["partial"] else 0)
    answer_at = t + timedelta(minutes=2)
    if plan["answer"] == "FILL":
        env.broker.send("FILL", order.client_order_id, answer_at, quantity=str(remaining),
                        fill_id=f"cancel-{seed}-rest", message_id=f"cancel-{seed}-rest")
    elif plan["answer"] == "CANCELLED":
        env.broker.send("CANCELLED", order.client_order_id, answer_at, message_id=f"cancel-{seed}-answer")
    for k in range(3, 6):
        steps.append(observe(env, order, env.worker(t + timedelta(minutes=k)).step()))
    return order, plan, steps


def observe(env, order, _report):
    from investment_engine.oms.order_states import FINAL

    state = env.state(order).state
    requests = env.stores.db.fetchall("SELECT p.progress, p.outcome FROM cancel_progress p JOIN cancel_requests r "
                                      "ON r.cancel_id = p.cancel_id WHERE r.order_id = :o ORDER BY p.version",
                                      {"o": order.order_id})
    closed = [outcome for progress, outcome in requests if progress == "CLOSED"]
    return state, state in FINAL, closed


@pytest.mark.postgres
@pytest.mark.unit
def test_cancels_after_submission_close_durably_and_only_once_the_order_is_final(flow):
    """Part J and M4-07 rule 3, over seeded post-submission sequences: a cancel request is never CLOSED while its
    order isn't final, and once the order is final the request is CLOSED with the matching outcome, whatever timed
    out or crashed on the way. The kill switch never blocks it."""
    from tests.engine.test_intent_pipeline import SESSIONS

    env = flow
    expected = {S.CANCELLED: "CANCELLED", S.FILLED: "TOO_LATE", S.EXPIRED: "TOO_LATE"}
    finals = set()
    for seed in range(max(FLOW_SEEDS // 2, 20)):  # at least 20, so every final outcome occurs
        order, plan, steps = run_cancel_flow(env, seed, SESSIONS[60 + seed % 120])
        for state, final, closed in steps:
            assert final or not closed, (seed, plan, state)  # never closed early
        state, final, closed = steps[-1]
        assert final, (seed, plan, state)  # the broker's answer settled it
        assert closed == [expected[state]], (seed, plan, state, closed)  # closed once, with the right outcome
        assert env.broker.submitted(order.client_order_id) == 1, seed  # a cancel never resubmits
        finals.add(state)
    assert finals == set(expected), finals  # non-vacuous: every way an order ends was exercised
