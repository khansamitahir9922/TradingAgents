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
    calendar: object = None  # given one, a cancel before the target session's open is conclusive, as at a broker
    orders: dict = field(default_factory=dict)  # client_order_id -> [order, status, filled]

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
        self.orders.setdefault(order.client_order_id, [order, "OPEN", Decimal(0)])
        return SubmitResult(True, "b-" + order.client_order_id, "accepted")

    def cancel(self, client_order_id: str, *, at: datetime) -> CancelResult:
        """Like a broker where the contract speaks (Codex M4 review B12): no such order, a final order, and (with a
        calendar) a cancel before the open; otherwise the scripted outcome."""
        self.cancels.append((client_order_id, at))
        if self.timeout_next_cancel:
            self.timeout_next_cancel = False
            raise BrokerTimeout("scripted cancel timeout")
        held = self.orders.get(client_order_id)
        if held is None and client_order_id not in self.known:
            return CancelResult("UNKNOWN_ORDER", None, "no such order")
        if held is not None and held[1] in ("FILLED", "EXPIRED", "REJECTED"):
            return CancelResult("TOO_LATE", at, f"the order is already {held[1]}")
        if held is not None and held[1] == "CANCELLED":
            return CancelResult("CANCELLED", at, "already cancelled")
        if held is not None and self.calendar is not None and at < self.calendar.session(held[0].target_session).open:
            held[1] = "CANCELLED"
            self.send("CANCELLED", client_order_id, at, reason="cancelled before the open")
            return CancelResult("CANCELLED", at, "cancelled before the open")
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
        held = self.orders.get(client_order_id)
        if held is not None and held[1] == "OPEN":
            if fill is not None:
                held[2] += fill.quantity
                if held[2] >= held[0].quantity:
                    held[1] = "FILLED"
            elif kind in ("CANCELLED", "EXPIRED", "REJECTED"):
                held[1] = kind
        return message

    def submitted(self, client_order_id: str) -> int:
        return sum(1 for c, _ in self.submits if c == client_order_id)
