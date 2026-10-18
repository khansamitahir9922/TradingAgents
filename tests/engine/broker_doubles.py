"""A scriptable, in-memory BrokerPort for tests only (docs/tasks/M4-03.md; extended by M4-07, M4-08, M4-11).

It records every call, so tests can assert that nothing was submitted, or
that an UNKNOWN order was never resubmitted (Part J). Behaviour is scripted:
a timeout on the next submit or cancel, queued messages (fills, partial
fills, duplicates, reordering), and lookups with or without a record.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from investment_engine.execution.broker_port import (
    BrokerFill,
    BrokerMessage,
    BrokerOrderReport,
    BrokerTimeout,
    CancelResult,
    SubmitResult,
)


@dataclass
class ScriptedBroker:
    submits: list = field(default_factory=list)  # (client_order_id, at)
    cancels: list = field(default_factory=list)
    lookups: list = field(default_factory=list)
    known: dict = field(default_factory=dict)  # client_order_id -> BrokerOrderReport
    queue: list = field(default_factory=list)  # BrokerMessage, in delivery order
    timeout_next_submit: bool = False
    timeout_next_cancel: bool = False
    reject_next_submit: str | None = None
    cancel_outcome: str = "PENDING"
    on_submit: object = None  # a callable(order) run at the moment submit is called (phase-boundary checks)

    def submit(self, order, *, at: datetime) -> SubmitResult:
        self.submits.append((order.client_order_id, at))
        if self.on_submit is not None:
            self.on_submit(order)
        if self.timeout_next_submit:
            self.timeout_next_submit = False
            self.known[order.client_order_id] = BrokerOrderReport(order.client_order_id, "b-" + order.client_order_id,
                                                                  "OPEN", Decimal(0), ())
            raise BrokerTimeout("scripted timeout")
        if self.reject_next_submit is not None:
            reason, self.reject_next_submit = self.reject_next_submit, None
            return SubmitResult(False, None, reason)
        self.known[order.client_order_id] = BrokerOrderReport(order.client_order_id, "b-" + order.client_order_id,
                                                              "OPEN", Decimal(0), ())
        return SubmitResult(True, "b-" + order.client_order_id, "accepted")

    def cancel(self, client_order_id: str, *, at: datetime) -> CancelResult:
        self.cancels.append((client_order_id, at))
        if self.timeout_next_cancel:
            self.timeout_next_cancel = False
            raise BrokerTimeout("scripted cancel timeout")
        return CancelResult(self.cancel_outcome, at, "scripted")

    def lookup(self, client_order_id: str, *, at: datetime) -> BrokerOrderReport | None:
        self.lookups.append((client_order_id, at))
        return self.known.get(client_order_id)

    def messages(self, *, after: str | None, at: datetime) -> list[BrokerMessage]:
        ids = [m.message_id for m in self.queue]
        start = ids.index(after) + 1 if after in ids else 0
        return [m for m in self.queue[start:] if m.delivered_at <= at]

    # ---------------------------------------------------------------- scripting helpers

    def send(self, kind: str, client_order_id: str, at: datetime, *, quantity: str | None = None,
             price: str = "100.00", fill_id: str | None = None, message_id: str | None = None,
             reason: str = "") -> BrokerMessage:
        fill = None
        if kind == "FILL":
            fill = BrokerFill(fill_id or f"fill-{len(self.queue)}", Decimal(quantity), Decimal(price), Decimal("0"),
                              "USD", at, '{"source":"scripted"}')
        message = BrokerMessage(message_id or f"msg-{len(self.queue)}", client_order_id, kind, at, fill, reason)
        self.queue.append(message)
        return message

    def submitted(self, client_order_id: str) -> int:
        return sum(1 for c, _ in self.submits if c == client_order_id)
