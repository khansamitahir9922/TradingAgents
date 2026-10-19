"""The gate's lock-then-read protocol against concurrent writers, on PostgreSQL (docs/tasks/M4-05.md rule 4).

Each writer that can change a gate input takes the account-control lock first.
Two deterministic interleavings per writer:
- the writer holds the lock while the gate starts: the gate waits, then reads the change and rejects;
- the gate holds the lock (paused after its reads) while the writer starts: the writer waits; the gate passes,
  and the change commits after the decision.
Never a pass on a superseded read.
"""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.execution.gate import gate_order
from investment_engine.execution.reads import StoreGateReads
from investment_engine.killswitch.flag import FlagState, KillSwitchReader, encode_flag
from investment_engine.oms.conversion import convert_approved
from investment_engine.oms.order_states import OPEN, OrderState, ProcessRole
from investment_engine.oms.orders import Fill, GateDecision
from investment_engine.policy.decisions import CheckResult
from investment_engine.portfolio.fingerprint import (
    DeclaredFingerprints,
    Reservation,
    economic_fingerprint,
)
from investment_engine.risk.limits import load_limits_file
from tests.engine.test_conversion import order_store
from tests.engine.test_intent_pipeline import CAL, DAY, OWNER, PROPOSED, SESSIONS, Env, view_for

pytestmark = pytest.mark.postgres


class StandInFingerprints:
    """A stand-in for M4-09's provider: the declared start, plus fills and/or open-order reservations."""

    def __init__(self, stores, orders, *, fills=False, reservations=False):
        self.stores, self.orders, self.fills, self.reservations = stores, orders, fills, reservations

    def at(self, account_id, at, *, excluding_order):
        start = self.stores.snapshots.starting_state(account_id)
        cash, held, reserved = start.cash, dict(start.positions), []
        for order, status in self.orders.for_account(account_id):
            if order.order_id == excluding_order:
                continue
            if self.fills and status.filled_qty:
                held[order.instrument_id] = held.get(order.instrument_id, Decimal(0)) + status.filled_qty
                cash -= status.filled_qty * status.avg_price
            if self.reservations and status.state in OPEN:
                remaining = order.quantity - status.filled_qty
                reserved.append(Reservation(order.order_id, order.instrument_id, order.side, remaining,
                                            remaining * order.limit_price))
        return economic_fingerprint(cash=cash, positions=list(held.items()), reservations=reserved)


@pytest.fixture
def env(pg_database, tmp_path):
    e = Env(pg_database, tmp_path / "market")
    e.account("R2", level=2)
    flag = tmp_path / "control" / "trading_enabled.json"
    flag.parent.mkdir(parents=True)
    flag.write_text(encode_flag(FlagState(True, 1, e.clock.now(), "owner", True, "go")), encoding="utf-8")
    e.kill_switch = KillSwitchReader(flag)
    yield e
    e.close()


def convert(env, day):
    view = view_for(env.stores, env.reader, day, tag=str(day))
    record = env.propose("R2", view, declared_only=True)  # independent orders on one account (B6; worker_env.py)
    report = convert_approved("R2", at=view.generated_at, stores=env.stores, orders=order_store(env))
    (order,) = report.converted
    return order, view, record


def gate_at(order, view):
    at = view.generated_at + timedelta(minutes=1)
    assert at < CAL.session(order.target_session).open
    return at


def worker_reads(env, stores, *, fills=False, reservations=False):
    orders = order_store(env, stores, role=ProcessRole.EXECUTION)
    if fills or reservations:
        provider = StandInFingerprints(stores, orders, fills=fills, reservations=reservations)
    else:
        provider = DeclaredFingerprints(stores.snapshots)
    return orders, StoreGateReads(stores, orders, knowledge=env.knowledge, calendar=CAL, fingerprints=provider)


@pytest.mark.unit
def test_a_real_order_passes_the_gate_and_moves_to_submitting(env):
    order, view, _ = convert(env, DAY)
    orders, reads = worker_reads(env, env.connect())
    decision = gate_order(order.order_id, clock=ReplayClock(gate_at(order, view)), orders=orders, reads=reads,
                          kill_switch=env.kill_switch)
    assert decision.passed, [(c.name, c.reason) for c in decision.checks if not c.passed]
    assert orders.get(order.order_id)[1].state is OrderState.SUBMITTING
    (stored,) = orders.gate_decisions(order.order_id)
    assert [c.name for c in stored.checks][0] == "kill_switch" and len(stored.checks) == 8


def _interleave(env, order, view, *, writer, reads_kw, writer_first: bool):
    """Run the gate and `writer(stores)` on two connections in a forced order. Returns the decision."""
    gate_stores, writer_stores = env.connect(), env.connect()
    orders, reads = worker_reads(env, gate_stores, **reads_kw)
    at = gate_at(order, view)
    hold, go, result = threading.Event(), threading.Event(), {}

    if writer_first:
        def run_writer():
            with writer_stores.db.transaction():
                writer_stores.db.lock("account-control|R2")
                hold.set()
                go.wait(timeout=30)
                writer(writer_stores)

        t = threading.Thread(target=run_writer)
        t.start()
        hold.wait(timeout=30)
        g = threading.Thread(target=lambda: result.setdefault("decision", gate_order(
            order.order_id, clock=ReplayClock(at), orders=orders, reads=reads, kill_switch=env.kill_switch)))
        g.start()
        g.join(timeout=1)
        assert g.is_alive(), "the gate must wait for the writer's lock"
        go.set()
        t.join(timeout=60)
        g.join(timeout=60)
    else:
        real_read = reads.read

        def paused_read(o, *, at):
            value = real_read(o, at=at)
            hold.set()
            go.wait(timeout=30)
            return value

        reads.read = paused_read
        g = threading.Thread(target=lambda: result.setdefault("decision", gate_order(
            order.order_id, clock=ReplayClock(at), orders=orders, reads=reads, kill_switch=env.kill_switch)))
        g.start()
        hold.wait(timeout=30)

        def run_writer():
            with writer_stores.db.transaction():
                writer_stores.db.lock("account-control|R2")
                writer(writer_stores)
            result["writer_done"] = True

        t = threading.Thread(target=run_writer)
        t.start()
        t.join(timeout=1)
        assert t.is_alive(), "the writer must wait for the gate's lock"
        go.set()
        g.join(timeout=60)
        t.join(timeout=60)
    return result["decision"]


@pytest.mark.unit
@pytest.mark.parametrize("writer_first", [True, False], ids=["writer-first", "gate-first"])
def test_a_limits_publish_and_the_gate(env, writer_first):
    order, view, _ = convert(env, DAY)

    def writer(stores):
        risk, _ = load_limits_file(PROPOSED)
        stores.limits.publish_risk("R2", {**risk, "max_new_buys_per_session": 4}, by=OWNER, reason="tighter",
                                   effective_at=view.generated_at - timedelta(days=30))

    decision = _interleave(env, order, view, writer=writer, reads_kw={}, writer_first=writer_first)
    if writer_first:
        assert not decision.passed and [c.name for c in decision.checks if not c.passed] == ["controls"]
    else:
        assert decision.passed


@pytest.mark.unit
@pytest.mark.parametrize("writer_first", [True, False], ids=["writer-first", "gate-first"])
def test_a_fill_on_another_order_and_the_gate(env, writer_first):
    other, other_view, _ = convert(env, SESSIONS[50])
    worker = order_store(env, role=ProcessRole.EXECUTION)
    gate = GateDecision(other.order_id, 1, True, (CheckResult("kill_switch", True, "test"),), other_view.generated_at, "{}")
    status = worker.transition(other.order_id, OrderState.SUBMITTING, expected_aggregate_version=1,
                               at=other_view.generated_at, reason="test", gate=gate)
    worker.transition(other.order_id, OrderState.SUBMITTED, expected_aggregate_version=status.aggregate_version,
                      at=other_view.generated_at, reason="test")
    order, view, _ = convert(env, DAY)

    def writer(stores):
        fills = order_store(env, stores, role=ProcessRole.EXECUTION)
        _, current = fills.get(other.order_id)
        fills.record_fill(Fill(other.order_id, Decimal(1), Decimal("100.00"), Decimal(0), "USD", view.generated_at,
                               view.generated_at, view.generated_at, "fill-x", "{}"),
                          expected_aggregate_version=current.aggregate_version)

    decision = _interleave(env, order, view, writer=writer, reads_kw={"fills": True}, writer_first=writer_first)
    if writer_first:
        assert [c.name for c in decision.checks if not c.passed] == ["positions"]
    else:
        assert decision.passed


@pytest.mark.unit
@pytest.mark.parametrize("writer_first", [True, False], ids=["writer-first", "gate-first"])
def test_a_new_conversion_and_the_gate(env, writer_first):
    order, view, _ = convert(env, DAY)
    later = view_for(env.stores, env.reader, SESSIONS[70], tag="later")
    env.propose("R2", later, declared_only=True)

    def writer(stores):
        report = convert_approved("R2", at=later.generated_at, stores=stores, orders=order_store(env, stores))
        assert len(report.converted) == 1

    decision = _interleave(env, order, view, writer=writer, reads_kw={"reservations": True},
                           writer_first=writer_first)
    if writer_first:
        assert [c.name for c in decision.checks if not c.passed] == ["positions"]
    else:
        assert decision.passed


@pytest.mark.unit
def test_free_races_with_a_limits_publish_never_pass_a_superseded_read(env):
    """20 unforced races: whichever commits first, the decision is consistent with it (pass, or controls only)."""
    outcomes = []
    for n in range(20):
        order, view, _ = convert(env, SESSIONS[100 + n])
        gate_stores, writer_stores = env.connect(), env.connect()
        orders, reads = worker_reads(env, gate_stores)
        barrier, out = threading.Barrier(2), {}

        def gate(barrier=barrier, out=out, order=order, view=view, orders=orders, reads=reads):
            barrier.wait()
            out["d"] = gate_order(order.order_id, clock=ReplayClock(gate_at(order, view)), orders=orders, reads=reads,
                                  kill_switch=env.kill_switch)

        def publish(barrier=barrier, writer_stores=writer_stores, n=n, view=view):
            barrier.wait()
            risk, _ = load_limits_file(PROPOSED)
            writer_stores.limits.publish_risk("R2", {**risk, "max_new_buys_per_session": 5 + n % 3}, by=OWNER,
                                              reason="race", effective_at=view.generated_at - timedelta(days=30))

        threads = [threading.Thread(target=gate), threading.Thread(target=publish)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        decision = out["d"]
        assert decision.passed or [c.name for c in decision.checks if not c.passed] == ["controls"]
        outcomes.append(decision.passed)
    assert len(outcomes) == 20  # either order can win; both are consistent


def free_race(env, gate_view_day, writer, *, reads_kw, before_race=None):
    """One unforced race: the gate and `writer(stores, view)` start together on their own connections.
    `before_race()` runs once the gate's order exists."""
    order, view, _ = convert(env, gate_view_day)
    if before_race is not None:
        before_race()
    gate_stores, writer_stores = env.connect(), env.connect()
    orders, reads = worker_reads(env, gate_stores, **reads_kw)
    barrier, out = threading.Barrier(2), {}

    def gate():
        barrier.wait()
        out["d"] = gate_order(order.order_id, clock=ReplayClock(gate_at(order, view)), orders=orders, reads=reads,
                              kill_switch=env.kill_switch)

    def write():
        barrier.wait()
        writer(writer_stores, view)

    threads = [threading.Thread(target=gate), threading.Thread(target=write)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return out["d"]


@pytest.mark.unit
def test_free_races_with_a_fill_on_another_order_are_consistent(env):
    """M4-05: twenty interleavings for the fill writer too (Codex M4 review B12), not one forced pair."""
    outcomes = []
    for n in range(20):
        other, other_view, _ = convert(env, SESSIONS[40 + n])
        worker = order_store(env, role=ProcessRole.EXECUTION)
        gate = GateDecision(other.order_id, 1, True, (CheckResult("kill_switch", True, "test"),),
                            other_view.generated_at, "{}")
        status = worker.transition(other.order_id, OrderState.SUBMITTING, expected_aggregate_version=1,
                                   at=other_view.generated_at, reason="test", gate=gate)
        worker.transition(other.order_id, OrderState.SUBMITTED, expected_aggregate_version=status.aggregate_version,
                          at=other_view.generated_at, reason="test")

        def fill(stores, view, other=other, n=n):
            fills = order_store(env, stores, role=ProcessRole.EXECUTION)
            _, current = fills.get(other.order_id)
            fills.record_fill(Fill(other.order_id, Decimal(1), Decimal("100.00"), Decimal(0), "USD", view.generated_at,
                                   view.generated_at, view.generated_at, f"race-fill-{n}", "{}"),
                              expected_aggregate_version=current.aggregate_version)

        decision = free_race(env, SESSIONS[100 + n], fill, reads_kw={"fills": True})
        assert decision.passed or [c.name for c in decision.checks if not c.passed] == ["positions"], n
        outcomes.append(decision.passed)
    assert len(outcomes) == 20


@pytest.mark.unit
def test_free_races_with_a_new_conversion_are_consistent(env):
    """M4-05: twenty interleavings for the conversion writer (Codex M4 review B12)."""
    outcomes = []
    for n in range(20):
        later = view_for(env.stores, env.reader, SESSIONS[140 + n % 20], tag=f"race-later-{n}")

        def conversion(stores, view, later=later):
            convert_approved("R2", at=later.generated_at, stores=stores, orders=order_store(env, stores))

        decision = free_race(env, SESSIONS[100 + n], conversion, reads_kw={"reservations": True},
                             before_race=lambda later=later: env.propose("R2", later, declared_only=True))
        assert decision.passed or [c.name for c in decision.checks if not c.passed] == ["positions"], n
        outcomes.append(decision.passed)
    assert len(outcomes) == 20
