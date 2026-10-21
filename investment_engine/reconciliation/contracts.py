"""Immutable evidence records shared by Core and Execution Worker (M5-00)."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investment_engine.ledger.contracts import amount, content, digest, identity
from investment_engine.lineage.records import register
from investment_engine.market.availability import (
    check_instrument_id,
    check_name,
    check_revision,
    check_utc,
)


@dataclass(frozen=True)
class BrokerPosition:
    instrument_id: str
    quantity: Decimal
    unit: str

    def __post_init__(self):
        check_instrument_id(self.instrument_id)
        amount(self.quantity, whole=True)
        if self.unit != "SHARES":
            raise ValueError("position unit must be SHARES")


@dataclass(frozen=True)
class BrokerOpenOrder:
    order_id: str
    client_order_id: str
    instrument_id: str
    side: str
    status: str
    remaining: Decimal

    def __post_init__(self):
        check_name(self.order_id, "order_id")
        check_name(self.client_order_id, "client_order_id")
        check_instrument_id(self.instrument_id)
        amount(self.remaining, whole=True)
        if self.side not in ("BUY", "SELL") or self.status not in ("OPEN", "CANCEL_RECEIVED") or self.remaining <= 0:
            raise ValueError("invalid resting broker order")


@dataclass(frozen=True)
class BrokerSnapshot:
    account_id: str
    broker: str
    broker_account_id: str
    source: str
    effective_at: datetime
    taken_at: datetime
    received_at: datetime
    currency: str
    cash: Decimal | None
    positions: tuple[BrokerPosition, ...] | None
    open_orders: tuple[BrokerOpenOrder, ...] | None
    cash_basis: str
    coverage_ref: str
    raw_hash: str
    execution_refs: tuple[str, ...]
    complete: bool
    reasons: tuple[str, ...]

    def __post_init__(self):
        for name in ("account_id", "broker", "broker_account_id", "source", "cash_basis", "coverage_ref"):
            check_name(getattr(self, name), name)
        for name in ("effective_at", "taken_at", "received_at"):
            check_utc(getattr(self, name), name)
        if not self.effective_at <= self.taken_at <= self.received_at:
            raise ValueError("snapshot times must be ordered")
        if self.currency != "USD":
            raise ValueError("only USD supported")
        if self.cash is not None:
            amount(self.cash, signed=True)
        for name, cls, key in (("positions", BrokerPosition, lambda v: v.instrument_id),
                               ("open_orders", BrokerOpenOrder, lambda v: v.order_id)):
            values = getattr(self, name)
            if values is not None:
                values = tuple(sorted(values, key=key))
                if not all(isinstance(v, cls) for v in values) or len({key(v) for v in values}) != len(values):
                    raise ValueError("invalid/duplicate snapshot items")
                object.__setattr__(self, name, values)
        object.__setattr__(self, "execution_refs", tuple(sorted(self.execution_refs)))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        digest(self.raw_hash, "raw_hash")
        if self.complete and (self.reasons or self.cash is None or self.positions is None or self.open_orders is None):
            raise ValueError("complete snapshot requires all fields, no missing reasons")

    @property
    def snapshot_id(self):
        return identity(content(self))


@dataclass(frozen=True)
class Difference:
    field: str
    unit: str
    internal: object
    broker: object
    reason: str

    def __post_init__(self):
        for name in ("field", "unit", "reason"):
            check_name(getattr(self, name), name)
        for value in (self.internal, self.broker):
            if isinstance(value, float):
                raise TypeError("difference values cannot be floats")


@dataclass(frozen=True)
class ReconciliationResult:
    account_id: str
    at: datetime
    book_id: str
    snapshot_id: str
    oms_hash: str
    status: str
    differences: tuple[Difference, ...]
    reasons: tuple[str, ...]

    def __post_init__(self):
        for name in ("account_id", "book_id", "snapshot_id", "oms_hash"):
            check_name(getattr(self, name), name)
        check_utc(self.at, "at")
        object.__setattr__(self, "differences", tuple(self.differences))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.status not in ("MATCH", "MISMATCH", "INCOMPLETE"):
            raise ValueError("invalid reconciliation status")
        if self.status == "MATCH" and (self.differences or self.reasons):
            raise ValueError("MATCH requires complete agreeing evidence")
        if self.status == "MISMATCH" and not self.differences:
            raise ValueError("MISMATCH requires differences")
        if self.status == "INCOMPLETE" and not self.reasons:
            raise ValueError("INCOMPLETE requires reasons")

    @property
    def result_id(self):
        return identity(content(self))


@dataclass(frozen=True)
class IncidentTransition:
    incident_id: str
    account_id: str
    sequence: int
    state: str
    result_id: str
    actor_id: str
    reason: str
    command_at: datetime
    business_at: datetime

    def __post_init__(self):
        for name in ("incident_id", "account_id", "result_id", "actor_id", "reason"):
            check_name(getattr(self, name), name)
        check_revision(self.sequence)
        check_utc(self.command_at, "command_at")
        check_utc(self.business_at, "business_at")
        if self.state not in ("OPEN", "ACKNOWLEDGED", "RESOLVED"):
            raise ValueError("invalid incident state")


for _type in (BrokerPosition, BrokerOpenOrder, BrokerSnapshot, Difference,
              ReconciliationResult, IncidentTransition):
    register(_type)
