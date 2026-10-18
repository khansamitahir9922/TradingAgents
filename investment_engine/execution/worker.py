"""The Execution Worker's loop (architecture Part E, G1 steps 11–14, G4; docs/tasks/M4-03.md, M4-07.md).

`step()` is one pass over durable work, and everything time-dependent reads
the injected clock: a LiveClock in the deployed process, a ReplayClock in the
offline harness and the tests (D24). The worker and the Core Engine share no
memory and never call each other; they communicate only through database rows
(ADR-005). The order within a step (M4-07 rule 5) puts fills and cancels ahead
of new risk:

    1 publish pending events   2 ingest broker messages   3 cancels
    4 UNKNOWN lookups          5 new submissions

Submission has three phases (Law 14): the gate transaction commits SUBMITTING;
the broker call happens outside every transaction; an outcome transaction
records SUBMITTED, REJECTED, or UNKNOWN on a timeout or any unknown outcome.
A submission is never repeated.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from investment_engine.audit.events import AuditStore
from investment_engine.events.outbox import Outbox
from investment_engine.execution.broker_port import BrokerTimeout
from investment_engine.execution.cancels import process_cancels
from investment_engine.execution.gate import gate_order
from investment_engine.execution.ingest import ingest
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


class ExecutionWorker:
    def __init__(self, db, *, clock, broker, kill_switch=None, reads=None,
                 serves: frozenset[AccountKind] = frozenset({AccountKind.RESEARCH})) -> None:
        self.db, self.clock, self.broker = db, clock, broker
        self.kill_switch, self.reads, self.serves = kill_switch, reads, serves
        self.outbox = Outbox(db, writer=ProcessRole.EXECUTION, clock=clock)
        self.orders = OrderStore(db, role=ProcessRole.EXECUTION, audit=AuditStore(db), outbox=self.outbox,
                                 clock=clock)

    def step(self) -> StepReport:
        published = self.outbox.publish_pending()
        ingested = ingest(broker=self.broker, orders=self.orders, clock=self.clock)
        cancels = process_cancels(orders=self.orders, broker=self.broker, clock=self.clock)
        lookups = self.lookup_unknown()
        submitted = rejected = unknown = 0
        if self.reads is not None and self.kill_switch is not None:
            for order, _ in self.orders.in_states(S.NEW):
                if order.account_kind not in self.serves:
                    continue  # this broker never serves that account kind (D23); the order waits, unsent
                outcome = self.submit(order.order_id)
                submitted += outcome == "SUBMITTED"
                rejected += outcome == "GATE_REJECTED"
                unknown += outcome == "UNKNOWN"
        published += self.outbox.publish_pending()
        return StepReport(published, ingested.applied, cancels.sent, cancels.closed, lookups, submitted, rejected,
                          unknown)

    def submit(self, order_id: str) -> str:
        """Gate, then the broker call outside any transaction, then the outcome. Returns the resulting state."""
        now = check_utc(self.clock.now(), "now")
        try:
            decision = gate_order(order_id, at=now, orders=self.orders, reads=self.reads,
                                  kill_switch=self.kill_switch)
        except StaleWrite:
            return "STALE"
        if decision is None:
            return "NOT_NEW"
        if not decision.passed:
            return "GATE_REJECTED"
        order, status = self.orders.get(order_id)  # SUBMITTING is committed before the call (Law 14)
        try:
            result = self.broker.submit(order, at=now)
        except BrokerTimeout:
            result = None
        except Exception:  # any error leaves the outcome unknown: never resend
            result = None
        with self.db.transaction():
            self.db.lock(f"account-control|{order.account_id}")
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

    def lookup_unknown(self) -> int:
        """Look up each UNKNOWN order once (D20): a report resolves it; no record leaves it UNKNOWN, recorded."""
        now = check_utc(self.clock.now(), "now")
        count = 0
        for order, status in self.orders.in_states(S.UNKNOWN):
            count += 1
            report = self.broker.lookup(order.client_order_id, at=now)
            if report is None:
                self.orders.record_anomaly(order.order_id, kind="lookup_no_record",
                                           detail="UNRESOLVED: broker has no record (D20); never resent", at=now,
                                           broker_ref=f"lookup:{now.isoformat()}")
                continue
            if report.status in ("OPEN", "CANCEL_RECEIVED"):
                with self.db.transaction():
                    self.db.lock(f"account-control|{order.account_id}")
                    _, status = self.orders.get(order.order_id)
                    if status.state is S.UNKNOWN:
                        self.orders.transition(order.order_id, S.SUBMITTED,
                                               expected_aggregate_version=status.aggregate_version, at=now,
                                               reason="the broker reports it open", broker_order_id=report.broker_order_id,
                                               broker_ref=f"lookup:{now.isoformat()}")
            # FILLED, CANCELLED, EXPIRED, REJECTED: their messages resolve it at the next ingestion
        return count

    def run(self, *, poll_seconds: Decimal, stop: Callable[[], bool]) -> None:
        """Live mode: publish what an earlier run left unpublished, then step until `stop()` is true."""
        self.outbox.publish_pending()
        while not stop():
            self.step()
            deadline = time.monotonic() + float(poll_seconds)
            while not stop() and time.monotonic() < deadline:
                time.sleep(0.05)


__all__ = ["ExecutionWorker", "StepReport"]
