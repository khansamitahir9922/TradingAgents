"""The Execution Worker's loop (architecture Part E, G1 steps 11–14, G4; docs/tasks/M4-03.md and later).

`step()` is one pass over durable work, and everything time-dependent in it
reads the injected clock: a LiveClock in the deployed process, a ReplayClock
in the offline harness and the tests (D24). The worker and the Core Engine
share no memory and never call each other; they communicate only through
database rows (ADR-005). Later tasks add the gate (M4-05), submission,
ingestion and cancels (M4-07) and recovery (M4-08) to the step, in the order
M4-07 rule 5 fixes.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from investment_engine.audit.events import AuditStore
from investment_engine.events.outbox import Outbox
from investment_engine.oms.order_states import ProcessRole
from investment_engine.oms.order_store import OrderStore


@dataclass(frozen=True)
class StepReport:
    published: int


class ExecutionWorker:
    def __init__(self, db, *, clock, broker) -> None:
        self.db, self.clock, self.broker = db, clock, broker
        self.outbox = Outbox(db, writer=ProcessRole.EXECUTION, clock=clock)
        self.orders = OrderStore(db, role=ProcessRole.EXECUTION, audit=AuditStore(db), outbox=self.outbox,
                                 clock=clock)

    def step(self) -> StepReport:
        return StepReport(published=self.outbox.publish_pending())

    def run(self, *, poll_seconds: Decimal, stop: Callable[[], bool]) -> None:
        """Live mode: publish what an earlier run left unpublished, then step until `stop()` is true."""
        self.outbox.publish_pending()
        while not stop():
            self.step()
            deadline = time.monotonic() + float(poll_seconds)
            while not stop() and time.monotonic() < deadline:
                time.sleep(0.05)


__all__ = ["ExecutionWorker", "StepReport"]
