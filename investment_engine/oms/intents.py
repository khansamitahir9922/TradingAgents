"""The OrderIntent contract (architecture Part H, G2; ADR-004; docs/tasks/M3-08.md).

An OrderIntent is one immutable version of a proposed trade: the Part H fields
plus what M4's Pre-Execution Gate needs to check that everything is still
current (the reference bar, the view's validity, the snapshot and the policy
and limit versions). After creation none of it changes (Law 12); a risk
reduction is a new version with `supersedes` set. State, decisions, approval
fields and the compare-and-set counter live in the intent store (M3-09).

The intent id hashes the account, the view's lineage, the instrument and the
sizer version, so proposing again for the same view finds the same intent
instead of a duplicate. Quantities are whole shares and prices Decimal
(Law 16); floats and naive times are refused.
"""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from investment_engine.lineage.records import canonical_json, register
from investment_engine.market.availability import check_utc
from investment_engine.quant.adjusted import BarRef


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class IntentState(StrEnum):
    PROPOSED = "PROPOSED"
    POLICY_REJECTED = "POLICY_REJECTED"
    RISK_REJECTED = "RISK_REJECTED"
    SUPERSEDED = "SUPERSEDED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"  # an Order was created: M4 only; M3 refuses it (M3-09 rule 4)


def intent_id_for(account_id: str, view_lineage_id: str, instrument_id: str, sizer_version: str) -> str:
    return "int-" + hashlib.sha256(canonical_json([account_id, view_lineage_id, instrument_id,
                                                   sizer_version]).encode()).hexdigest()


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be positive, not {value}")
    return value


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    version: int
    account_id: str
    instrument_id: str
    side: Side
    quantity: Decimal  # whole shares, > 0
    order_type: str  # "LIMIT" (D7, D13)
    limit_price: Decimal
    time_in_force: str  # "DAY" (D7)
    reference_price: Decimal  # the decision bar's raw close (RawReference, M3-07)
    reference_bar: BarRef
    target_session: date  # the next regular session after the view's T
    view_lineage_id: str
    view_valid_until: datetime
    snapshot_id: str
    sizer_version: str
    policy_version: str
    risk_version: str
    created_at: datetime
    supersedes: int | None  # the version this one replaces (a risk reduction), else None

    MATERIAL: ClassVar[tuple[str, ...]] = ("account_id", "instrument_id", "side", "quantity", "order_type",
                                           "limit_price", "time_in_force")

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", Side(self.side))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("an intent version is a positive integer")
        _decimal(self.quantity, "quantity")
        if self.quantity != self.quantity.to_integral_value():
            raise ValueError(f"quantity is whole shares, not {self.quantity}")
        _decimal(self.limit_price, "limit_price")
        _decimal(self.reference_price, "reference_price")
        if self.order_type != "LIMIT" or self.time_in_force != "DAY":
            raise ValueError("v1 intents are DAY limit orders (D7, D13)")
        check_utc(self.view_valid_until, "view_valid_until")
        check_utc(self.created_at, "created_at")
        if self.supersedes is not None and not 1 <= self.supersedes < self.version:
            raise ValueError("a version supersedes an earlier version")
        for name in ("intent_id", "account_id", "instrument_id", "view_lineage_id", "snapshot_id", "sizer_version",
                     "policy_version", "risk_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")


for _cls in (Side, IntentState, OrderIntent):
    register(_cls)
