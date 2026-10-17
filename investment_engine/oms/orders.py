"""Order contracts (architecture Part H `Order`, `Fill`, `CancelRequest`, `GateDecision`; docs/tasks/M4-00.md).

An Order is immutable once created: it copies the approved intent version
exactly and pins the references the Pre-Execution Gate later compares against
(the intent version's content id and the proposal's economic fingerprint,
M4-02, M4-05). Its changing part is OrderStatus, written only by
compare-and-set (order_store). Money and quantities are Decimal (Law 16).

Ids are derived, never random, so a replay gives the same orders (Part J):
the order and client order ids come from the intent id and version; fill ids
from the broker's fill id.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from investment_engine.audit.events import Actor
from investment_engine.lineage.records import register
from investment_engine.market.availability import check_utc
from investment_engine.oms.intents import Side
from investment_engine.oms.order_states import OrderState
from investment_engine.policy.accounts import AccountKind
from investment_engine.policy.decisions import CheckResult


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def order_ids(intent_id: str, intent_version: int) -> tuple[str, str]:
    """(order_id, client_order_id) for one intent version; at most one order per version (M4-00 rule 5)."""
    digest = _hash(f"order|{intent_id}|{intent_version}")
    return "ord-" + digest, "ie-" + digest[:32]


def _decimal(value, name: str, *, positive: bool = False, whole: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal (Law 16)")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if not positive and value < 0:
        raise ValueError(f"{name} can't be negative")
    if whole and value != value.to_integral_value():
        raise ValueError(f"{name} is whole shares, not {value}")
    return value


@dataclass(frozen=True)
class Order:
    order_id: str
    client_order_id: str
    intent_id: str
    intent_version: int
    intent_content_id: str  # the approved version's content id (Law 12; M4-05 check 2)
    position_fingerprint: str  # the proposal's economic fingerprint (M4-02 rule 1.3; M4-05 check 6)
    account_id: str
    account_kind: AccountKind
    instrument_id: str
    side: Side
    quantity: Decimal
    order_type: str
    limit_price: Decimal
    time_in_force: str
    target_session: date
    created_at: datetime  # business time of the conversion

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", Side(self.side))
        object.__setattr__(self, "account_kind", AccountKind(self.account_kind))
        if (self.order_id, self.client_order_id) != order_ids(self.intent_id, self.intent_version):
            raise ValueError("order ids are derived from the intent id and version (M4-00 rule 5)")
        for name in ("intent_content_id", "position_fingerprint", "account_id", "instrument_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"an order needs {name}")
        _decimal(self.quantity, "quantity", positive=True, whole=True)
        _decimal(self.limit_price, "limit_price", positive=True)
        if (self.order_type, self.time_in_force) != ("LIMIT", "DAY"):
            raise ValueError("M4 orders are LIMIT / DAY (D7)")
        check_utc(self.created_at, "created_at")


@dataclass(frozen=True)
class OrderStatus:
    order_id: str
    state: OrderState
    aggregate_version: int
    filled_qty: Decimal
    avg_price: Decimal | None
    broker_order_id: str | None
    anomalies: int


@dataclass(frozen=True)
class Fill:
    order_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    currency: str
    executed_at: datetime  # when the modelled or reported execution happened
    delivered_at: datetime  # when the broker made it available
    recorded_at: datetime  # when the worker ingested it
    broker_fill_id: str  # unique: de-duplication (Part J)
    provenance: str  # canonical JSON explaining the fill (M4-06 rule 4)
    fill_id: str = field(init=False)

    def __post_init__(self) -> None:
        _decimal(self.quantity, "quantity", positive=True, whole=True)
        _decimal(self.price, "price", positive=True)
        _decimal(self.fee, "fee")
        if self.currency != "USD":
            raise ValueError("v1 fills are in USD")
        for name in ("executed_at", "delivered_at", "recorded_at"):
            check_utc(getattr(self, name), name)
        if not isinstance(self.broker_fill_id, str) or not self.broker_fill_id.strip():
            raise ValueError("a fill needs the broker's fill id")
        object.__setattr__(self, "fill_id", "fil-" + _hash(f"fill|{self.order_id}|{self.broker_fill_id}"))

    def same_execution(self, other: "Fill") -> bool:
        """The same broker fill reported again (identical content apart from when it was ingested)."""
        keys = ("order_id", "quantity", "price", "fee", "currency", "executed_at", "broker_fill_id", "provenance")
        return all(getattr(self, k) == getattr(other, k) for k in keys)


class FillOutcome(StrEnum):
    RECORDED = "RECORDED"
    DUPLICATE = "DUPLICATE"  # the same broker fill again: nothing changes
    CONFLICT = "CONFLICT"  # the same broker fill id with different content: refused, stored as an anomaly
    REFUSED = "REFUSED"  # not allowed in the order's state, or an overfill: stored as an anomaly


@dataclass(frozen=True)
class CancelRequest:
    order_id: str
    requested_by: Actor
    requested_at: datetime
    reason: str
    cancel_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.requested_by, Actor):
            raise TypeError("requested_by must be an Actor")
        check_utc(self.requested_at, "requested_at")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("a cancel request needs a reason")
        object.__setattr__(self, "cancel_id", "cxl-" + _hash(
            f"cancel|{self.order_id}|{self.requested_by.actor_id}|{self.requested_at.isoformat()}"))


class CancelProgress(StrEnum):
    REQUESTED = "REQUESTED"
    SENDING = "SENDING"
    SENT = "SENT"
    CLOSED = "CLOSED"


CANCEL_EDGES: dict[CancelProgress, frozenset[CancelProgress]] = {
    CancelProgress.REQUESTED: frozenset({CancelProgress.SENDING, CancelProgress.CLOSED}),
    CancelProgress.SENDING: frozenset({CancelProgress.SENDING, CancelProgress.SENT, CancelProgress.CLOSED}),
    CancelProgress.SENT: frozenset({CancelProgress.SENDING, CancelProgress.CLOSED}),
}
CANCEL_OUTCOMES = ("CANCELLED", "TOO_LATE", "NOTHING_TO_CANCEL")


@dataclass(frozen=True)
class GateDecision:
    order_id: str
    attempt: int
    passed: bool
    checks: tuple[CheckResult, ...]
    checked_at: datetime
    inputs: str  # canonical JSON of what was checked (Law 18)

    def __post_init__(self) -> None:
        check_utc(self.checked_at, "checked_at")
        if self.passed != all(c.passed for c in self.checks) or not self.checks:
            raise ValueError("a gate decision passes exactly when every recorded check passed")


@dataclass(frozen=True)
class OrderTransition:
    order_id: str
    aggregate_version: int
    from_state: OrderState | None
    to_state: OrderState
    at: datetime
    recorded_at: datetime
    by: str
    reason: str
    broker_ref: str | None


@dataclass(frozen=True)
class Anomaly:
    order_id: str
    kind: str
    detail: str
    at: datetime
    recorded_at: datetime
    broker_ref: str
    at_version: int


for _cls in (Order, OrderStatus, Fill, CancelRequest, GateDecision, OrderTransition, Anomaly):
    register(_cls)
for _enum in (FillOutcome, CancelProgress):
    register(_enum)

__all__ = ["CANCEL_EDGES", "CANCEL_OUTCOMES", "Anomaly", "CancelProgress", "CancelRequest", "Fill", "FillOutcome",
           "GateDecision", "Order", "OrderStatus", "OrderTransition", "order_ids"]
