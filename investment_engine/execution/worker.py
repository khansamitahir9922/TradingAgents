"""The Execution Worker's loop (architecture Part E, G1 steps 11–14, G4; docs/tasks/M4-03.md, M4-07.md).

`step()` is one pass over durable work, and everything time-dependent reads
the injected clock: a LiveClock in the deployed process, a ReplayClock in the
offline harness and the tests (D24). The worker and the Core Engine share no
memory and never call each other; they communicate only through database rows
(ADR-005). The order within a step (M4-07 rule 5) puts fills and cancels ahead
of new risk:

    1 publish pending events   2 ingest broker messages   3 cancels
    4 SUBMITTING and UNKNOWN lookups                       5 new submissions

Uncertain orders are reconciled on every step, not only at start-up (Codex M4
review B4): a SUBMITTING order (its broker call may or may not have happened)
and an UNKNOWN one are looked up again each step until the broker's answer
settles them, keeping their reservations meanwhile, and are never resent. A
broker error or a concurrent change (StaleWrite) on one order, message or cancel
request skips only that item for the step. A lost database connection ends the
step; `run(..., reconnect=)` then rebuilds the connections and stores, recovers
again and resumes. A broker call that raises anything is, at the port, an unknown
outcome (`BrokerCallFailed`, like a timeout): a submit becomes UNKNOWN, a cancel stays
SENDING and records an anomaly, a lookup or message read waits for the next step. The
worker's own database errors are not broker-call failures and still end the step.

Submission has three phases (Law 14): the gate transaction commits SUBMITTING;
the broker call happens outside every transaction; an outcome transaction
records SUBMITTED, REJECTED, or UNKNOWN on a timeout or any unknown outcome.
A submission is never repeated.

**The broker deadline (D26; Codex M4 review B5).** Every broker call goes
through `worker.port`, which runs it on its own thread and waits at most
`deadline_seconds` (BROKER_DEADLINE_SECONDS, 10 s). A call that hasn't answered
by then counts as timed out: a submit becomes UNKNOWN and its late answer is
discarded (a lookup reconciles it), a cancel stays SENDING, and a lookup or a
message read is skipped for the step. Until the stalled call returns, no other
broker call is made and no new submission is gated (`broker_stalled()`), so a
broker connection is never used by two calls at once and no order is made
UNKNOWN for nothing. A broker that needs a database connection gets its own,
never the worker's.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from investment_engine.audit.events import AuditStore
from investment_engine.events.outbox import Outbox
from investment_engine.execution.broker_port import (
    BROKER_DEADLINE_SECONDS,
    BrokerBusy,
    BrokerCallFailed,
    BrokerTimeout,
)
from investment_engine.execution.cancels import process_cancels
from investment_engine.execution.gate import gate_order
from investment_engine.execution.ingest import IngestReport, ingest
from investment_engine.market.availability import check_utc
from investment_engine.oms.intent_store import StaleWrite
from investment_engine.oms.order_states import OrderState, ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.policy.accounts import AccountKind

S = OrderState


@dataclass(frozen=True)
class StepReport:
    published: int
    ingested: int = 0
    cancels_sent: int = 0
    cancels_closed: int = 0
    lookups: int = 0
    submitted: int = 0
    gate_rejected: int = 0
    unknown: int = 0


class _BoundedPort:
    """The broker port as the worker calls it: each call under the deadline. The method is looked up when it is
    called, so a substituted method is bounded too."""

    _CALLS = frozenset({"submit", "cancel", "lookup", "messages"})

    def __init__(self, worker) -> None:
        self._worker = worker

    def __getattr__(self, name):
        target = getattr(self._worker.broker, name)
        if name not in self._CALLS:
            return target
        return lambda *args, **kwargs: self._worker._bounded(name, target, *args, **kwargs)


class ExecutionWorker:
    def __init__(self, db, *, clock, broker, kill_switch=None, reads=None,
                 serves: frozenset[AccountKind] = frozenset({AccountKind.RESEARCH}),
                 deadline_seconds: float = BROKER_DEADLINE_SECONDS, accounts: frozenset[str] | None = None) -> None:
        """`accounts` limits every kind of work to those accounts (None: all): submissions, ingestion, SUBMITTING
        and UNKNOWN reconciliation, and cancels (Codex M4 review B9)."""
        self.db, self.clock, self.broker = db, clock, broker
        self.kill_switch, self.reads, self.serves = kill_switch, reads, serves
        self.accounts = None if accounts is None else frozenset(accounts)
        self.deadline_seconds = deadline_seconds
        self._stalled: threading.Thread | None = None
        self.port = _BoundedPort(self)
        self.outbox = Outbox(db, writer=ProcessRole.EXECUTION, clock=clock)
        self.orders = OrderStore(db, role=ProcessRole.EXECUTION, audit=AuditStore(db), outbox=self.outbox,
                                 clock=clock)

    def in_scope(self, order) -> bool:
        return self.accounts is None or order.account_id in self.accounts

    def broker_stalled(self) -> bool:
        """True while a timed-out broker call is still running."""
        if self._stalled is not None and not self._stalled.is_alive():
            self._stalled = None
        return self._stalled is not None

    def _bounded(self, name: str, call, *args, **kwargs):
        if self.broker_stalled():
            raise BrokerBusy(f"an earlier broker call hasn't returned; no {name} is sent until it does")
        box = {}

        def run():
            try:
                box["result"] = call(*args, **kwargs)
            except BaseException as exc:  # handed to the caller below
                box["error"] = exc

        thread = threading.Thread(target=run, name=f"broker-{name}", daemon=True)
        thread.start()
        thread.join(self.deadline_seconds)
        if thread.is_alive():
            self._stalled = thread  # its answer, when it comes, is discarded
            raise BrokerTimeout(f"no answer to {name} within {self.deadline_seconds} s (D26)")
        error = box.get("error")
        if isinstance(error, BrokerTimeout):
            raise error
        if isinstance(error, Exception):  # any other failure of the call: its outcome is unknown (N1)
            raise BrokerCallFailed(f"{name} failed: {type(error).__name__}: {error}"[:500]) from error
        if error is not None:  # KeyboardInterrupt, SystemExit: never swallowed
            raise error
        return box["result"]

    def step(self) -> StepReport:
        published = self.outbox.publish_pending()
        try:
            ingested = ingest(broker=self.port, orders=self.orders, clock=self.clock, in_scope=self.in_scope)
        except BrokerTimeout:  # no messages read this step; the next one reads them
            ingested = IngestReport(0, 0, 0)
        cancels = process_cancels(orders=self.orders, broker=self.port, clock=self.clock,
                                  sendable=lambda: not self.broker_stalled(), in_scope=self.in_scope)
        *_, looked_up = self.reconcile_submitting()
        lookups = self.lookup_unknown(skip=looked_up)
        submitted = rejected = unknown = 0
        if self.reads is not None and self.kill_switch is not None and not self.broker_stalled():
            for order, _ in self.orders.in_states(S.NEW):
                if order.account_kind not in self.serves or not self.in_scope(order):
                    continue  # not this worker's (D23; B9): the order waits, unsent
                if self.broker_stalled():
                    break  # a submit just timed out: the rest wait, NEW, for the next step
                outcome = self.submit(order.order_id)
                submitted += outcome == "SUBMITTED"
                rejected += outcome == "GATE_REJECTED"
                unknown += outcome == "UNKNOWN"
        published += self.outbox.publish_pending()
        return StepReport(published, ingested.applied, cancels.sent, cancels.closed, lookups, submitted, rejected,
                          unknown)

    def submit(self, order_id: str) -> str:
        """Gate, then the broker call outside any transaction, then the outcome. Returns the resulting state.

        Each phase reads the clock for itself (B1): the gate once it holds its locks, the broker call when it is
        made, and the outcome when it is recorded. The order's terms never change, and nothing is resubmitted.
        While an earlier broker call is stalled, nothing is gated: the order stays NEW (B5)."""
        if self.broker_stalled():
            return "BROKER_BUSY"
        try:
            decision = gate_order(order_id, clock=self.clock, orders=self.orders, reads=self.reads,
                                  kill_switch=self.kill_switch)
        except StaleWrite:
            return "STALE"
        if decision is None:
            return "NOT_NEW"
        if not decision.passed:
            return "GATE_REJECTED"
        order, status = self.orders.get(order_id)  # SUBMITTING is committed before the call (Law 14)
        try:
            result = self.port.submit(order, at=check_utc(self.clock.now(), "now"))
        except BrokerTimeout:
            result = None
        except Exception:  # any error leaves the outcome unknown: never resend
            result = None
        with self.db.transaction():
            self.db.lock(f"account-control|{order.account_id}")
            now = check_utc(self.clock.now(), "now")
            _, status = self.orders.get(order_id)
            if status.state is not S.SUBMITTING:
                return status.state.value  # a message already moved it (an ACK ingested meanwhile)
            if result is None:
                to, reason, broker_id = S.UNKNOWN, "the broker's answer is unknown; never resent", None
            elif result.accepted:
                to, reason, broker_id = S.SUBMITTED, "accepted by the broker", result.broker_order_id
            else:
                to, reason, broker_id = S.REJECTED, f"rejected by the broker: {result.reason}", None
            self.orders.transition(order_id, to, expected_aggregate_version=status.aggregate_version, at=now,
                                   reason=reason, broker_order_id=broker_id)
        return to.value

    def lookup_unknown(self, *, skip=frozenset()) -> int:
        """Look up each UNKNOWN order once (D20): a report resolves it; no record leaves it UNKNOWN, recorded. A
        lookup that times out leaves the order UNKNOWN for the next step. Orders in `skip` were looked up a moment
        ago, in the same pass. Returns the lookups answered."""
        now = check_utc(self.clock.now(), "now")
        count = 0
        for order, status in self.orders.in_states(S.UNKNOWN):
            if order.order_id in skip or not self.in_scope(order):
                continue
            try:
                report = self.port.lookup(order.client_order_id, at=now)
            except Exception:  # unanswered, stalled or a broker error: still UNKNOWN, tried again next step (B4)
                continue
            count += 1
            if report is None:
                self.orders.record_anomaly(order.order_id, kind="lookup_no_record",
                                           detail="UNRESOLVED: broker has no record (D20); never resent", at=now,
                                           broker_ref=f"lookup:{now.isoformat()}")
                continue
            if report.status in ("OPEN", "CANCEL_RECEIVED"):
                try:
                    with self.db.transaction():
                        self.db.lock(f"account-control|{order.account_id}")
                        _, status = self.orders.get(order.order_id)
                        if status.state is S.UNKNOWN:
                            self.orders.transition(order.order_id, S.SUBMITTED,
                                                   expected_aggregate_version=status.aggregate_version, at=now,
                                                   reason="the broker reports it open",
                                                   broker_order_id=report.broker_order_id,
                                                   broker_ref=f"lookup:{now.isoformat()}")
                except StaleWrite:
                    continue  # changed meanwhile (a message moved it): looked at again next step
            # FILLED, CANCELLED, EXPIRED, REJECTED: their messages resolve it at the next ingestion
        return count

    def reconcile_submitting(self) -> tuple[int, int, int, frozenset]:
        """Look up each SUBMITTING order: saved before its broker call, so the call may or may not have happened.
        A report gives SUBMITTED (its messages are then ingested); no record gives UNKNOWN (D20). An error leaves it
        SUBMITTING, reserved, for the next step. **Never resent** (Law 14). Returns (found, unknown, left, the
        order ids looked up)."""
        now = check_utc(self.clock.now(), "now")
        found = unknown = left = 0
        looked_up = set()
        for order, _ in self.orders.in_states(S.SUBMITTING):
            if not self.in_scope(order):
                continue
            looked_up.add(order.order_id)
            try:
                report = self.port.lookup(order.client_order_id, at=now)
            except Exception:  # can't tell yet: tried again next step (B4)
                left += 1
                continue
            try:
                with self.db.transaction():
                    self.db.lock(f"account-control|{order.account_id}")
                    _, status = self.orders.get(order.order_id)
                    if status.state is not S.SUBMITTING:
                        continue
                    if report is None:
                        self.orders.transition(order.order_id, S.UNKNOWN,
                                               expected_aggregate_version=status.aggregate_version, at=now,
                                               reason="recovered: the broker has no record; never resent (D20)",
                                               broker_ref=f"recovery:{now.isoformat()}")
                        unknown += 1
                    else:
                        self.orders.transition(order.order_id, S.SUBMITTED,
                                               expected_aggregate_version=status.aggregate_version, at=now,
                                               reason="recovered: the broker has the order",
                                               broker_order_id=report.broker_order_id,
                                               broker_ref=f"recovery:{now.isoformat()}")
                        found += 1
            except StaleWrite:
                left += 1
        return found, unknown, left, frozenset(looked_up)

    def run(self, *, poll_seconds: Decimal, stop: Callable[[], bool],
            reconnect: Callable[[], "ExecutionWorker"] | None = None) -> "ExecutionWorker":
        """Live mode: recover first (G4: republish, resolve SUBMITTING and UNKNOWN; M4-08), then step until
        `stop()` is true. If the database connection is lost and `reconnect` is given, it builds a new worker on
        new connections; that worker recovers again, then the loop resumes (M4-08 acceptance; Codex M4 review B4).
        Without `reconnect` the error is raised. Returns the worker in use when it stopped."""
        from investment_engine.execution.recovery import recover
        from investment_engine.storage.postgres import connection_lost_errors

        lost = connection_lost_errors()
        worker, stalled = self, None
        while not stop():
            try:
                if worker is None:
                    worker = reconnect()
                    worker._stalled = stalled  # a call still running on the old broker blocks the new one too
                recover(worker)
                while not stop():
                    worker.step()
                    _wait(poll_seconds, stop)
            except lost:
                if reconnect is None:
                    raise
                stalled, worker = (worker._stalled if worker is not None else stalled), None
                _wait(poll_seconds, stop)  # then rebuild and recover
        return worker or self


def _wait(seconds: Decimal, stop: Callable[[], bool]) -> None:
    deadline = time.monotonic() + float(seconds)
    while not stop() and time.monotonic() < deadline:
        time.sleep(0.05)


__all__ = ["ExecutionWorker", "StepReport"]
