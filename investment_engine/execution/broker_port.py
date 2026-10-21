"""The broker port: the only way to a broker (Law 1; Law 20; architecture Part F; docs/tasks/M4-03.md).

The simulated broker (M4-06) implements it, and M7's paper adapter will; each
must pass the same contract suite (Part J). `submit` and `cancel` may raise
BrokerTimeout when the outcome is unknown: the worker then records UNKNOWN or
keeps the cancel in SENDING, and never resends a submission (Law 14).
`messages` returns only what the broker has delivered by `at`.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from investment_engine.oms.orders import Order
from investment_engine.reconciliation.contracts import BrokerSnapshot

BROKER_DEADLINE_SECONDS = 10  # D26: a broker call that hasn't answered by then has an unknown outcome


class BrokerTimeout(Exception):
    """The broker didn't answer in time; the outcome is unknown."""


class BrokerCallFailed(BrokerTimeout):
    """The broker call raised: its outcome is unknown, as after a timeout (Codex M4 re-review N1). The worker's own
    database errors never take this form; they happen outside the broker call."""


class BrokerBusy(BrokerTimeout):
    """An earlier call to this broker hasn't returned; nothing else is sent until it does (Codex M4 review B5)."""


@dataclass(frozen=True)
class SubmitResult:
    accepted: bool
    broker_order_id: str | None
    reason: str


@dataclass(frozen=True)
class CancelResult:
    outcome: str  # CANCELLED (conclusive now) | PENDING (decided later, as messages) | TOO_LATE | UNKNOWN_ORDER
    received_at: datetime | None
    reason: str


@dataclass(frozen=True)
class BrokerOrderReport:
    client_order_id: str
    broker_order_id: str
    status: str  # the broker's view: OPEN, CANCEL_RECEIVED, FILLED, CANCELLED, EXPIRED, REJECTED
    filled_qty: Decimal
    message_ids: tuple[str, ...]


@dataclass(frozen=True)
class BrokerFill:
    broker_fill_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    currency: str
    executed_at: datetime
    provenance: str  # canonical JSON (M4-06 rule 4)


@dataclass(frozen=True)
class BrokerMessage:
    message_id: str
    client_order_id: str
    kind: str  # ACK | FILL | EXPIRED | CANCELLED | REJECTED
    delivered_at: datetime
    fill: BrokerFill | None
    reason: str


class BrokerPort(Protocol):
    def snapshot(self, account_id: str, *, at: datetime) -> BrokerSnapshot: ...

    def submit(self, order: Order, *, at: datetime) -> SubmitResult: ...

    def cancel(self, client_order_id: str, *, at: datetime) -> CancelResult: ...

    def lookup(self, client_order_id: str, *, at: datetime) -> BrokerOrderReport | None: ...

    def messages(self, *, after: str | None, at: datetime) -> list[BrokerMessage]: ...


__all__ = ["BrokerFill", "BrokerMessage", "BrokerOrderReport", "BrokerPort", "BrokerTimeout", "BrokerBusy", "BrokerCallFailed", "BROKER_DEADLINE_SECONDS", "CancelResult",
           "SubmitResult"]
