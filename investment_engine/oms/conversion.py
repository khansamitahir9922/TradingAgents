"""Converting approved intent versions into orders, and recording cancel requests (architecture G1 step 10, G2,
G3; Law 12; PRD UC-07; D31; docs/tasks/M4-02.md).

The Core Engine turns each APPROVED latest intent version into exactly one
NEW order. In one transaction, under the account-control lock, it re-reads
the intent, writes APPROVED -> CONVERTED by compare-and-set, creates the order
with its derived ids, and adds `order.created`. The order copies the approved
version exactly and pins two references the gate compares later: the
version's content id and the economic fingerprint of the snapshot the
proposal was decided on. Anything that isn't convertible is listed in the
report with its reason, never raised.

A cancel request is a command row from a named Admin or Trader (checked at the
live command time), accepted whatever the kill switch says; it changes no
order state, which only the Execution Worker does.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from investment_engine.audit.events import Actor, ActorKind
from investment_engine.lineage.records import canonical_json
from investment_engine.market.availability import check_utc
from investment_engine.oms.intent_store import StaleWrite
from investment_engine.oms.intents import IntentState, OrderIntent
from investment_engine.oms.order_states import ProcessRole
from investment_engine.oms.orders import CancelRequest, Order, order_ids
from investment_engine.policy.accounts import NotAuthorized, Role
from investment_engine.portfolio.fingerprint import fingerprint_of

CANCELLERS = (Role.ADMIN, Role.TRADER)  # D31
_CORE = Actor(ActorKind.PROCESS, ProcessRole.CORE.value, None, None)


def intent_content_id(intent: OrderIntent) -> str:
    """The approved version's content id, pinned on its order (Law 12; M4-05 check 2)."""
    return "int-" + hashlib.sha256(canonical_json(intent).encode()).hexdigest()


@dataclass(frozen=True)
class ConversionReport:
    converted: tuple[Order, ...]
    skipped: tuple[tuple[str, int, str], ...]  # (intent_id, version, reason)


def _order_for(stored, snapshot, kind, at: datetime) -> Order:
    intent = stored.intent
    order_id, client_id = order_ids(intent.intent_id, intent.version)
    return Order(order_id, client_id, intent.intent_id, intent.version, intent_content_id(intent),
                 fingerprint_of(snapshot), intent.account_id, kind, intent.instrument_id, intent.side,
                 intent.quantity, intent.order_type, intent.limit_price, intent.time_in_force,
                 intent.target_session, at)


def convert_approved(account_id: str, *, at: datetime, stores, orders) -> ConversionReport:
    """Convert every APPROVED latest version of the account's intents at business time `at`."""
    at = check_utc(at, "at")
    if orders.role is not ProcessRole.CORE:
        raise ValueError("conversion is the Core Engine's (G3)")
    if getattr(orders, "_db", None) is not stores.db:
        raise ValueError("the order store must share the control stores' database port (one transaction)")
    kind = stores.accounts.account(account_id).kind
    converted, skipped = [], []
    for seen in stores.intents.for_account(account_id):
        intent = seen.intent
        if seen.state is not IntentState.APPROVED:
            continue
        key = (intent.intent_id, intent.version)
        try:
            with stores.db.transaction():
                stores.db.lock(f"account-control|{account_id}")
                current = stores.intents.get(intent.intent_id)
                if current.intent.version != intent.version:
                    skipped.append((*key, f"not the latest version (v{current.intent.version} is)"))
                    continue
                if current.state is not IntentState.APPROVED:
                    skipped.append((*key, f"no longer APPROVED ({current.state})"))
                    continue
                if orders.for_intent(*key) is not None:
                    skipped.append((*key, "already converted"))
                    continue
                if current.approval_expires_at is None or at >= current.approval_expires_at:
                    skipped.append((*key, "approval expired"))
                    continue
                snapshot = stores.snapshots.get(intent.snapshot_id)
                order = _order_for(current, snapshot, kind, at)
                stores.intents.convert(intent.intent_id, intent.version,
                                       expected_aggregate_version=current.aggregate_version, at=at, by=_CORE,
                                       reason=f"converted into {order.order_id}",
                                       correlation_id=f"conversion:{intent.intent_id}:{intent.version}")
                orders.create(order, by=_CORE, correlation_id=f"conversion:{intent.intent_id}:{intent.version}")
                converted.append(order)
        except StaleWrite:
            skipped.append((*key, "intent changed meanwhile (stale write)"))
    return ConversionReport(tuple(converted), tuple(skipped))


def request_cancel(order_id: str, *, operator_id: str, reason: str, command_at: datetime, stores,
                   orders) -> CancelRequest:
    """Record a cancel request from a named Admin or Trader (D31). It changes no order state (G3)."""
    command_at = check_utc(command_at, "command_at")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("a cancel request needs a reason")
    try:
        operator = stores.accounts.operator(operator_id, command_at)
    except KeyError:
        raise NotAuthorized(f"{operator_id} is not a registered operator") from None
    if not operator.active:
        raise NotAuthorized(f"{operator_id} is not an active operator now")
    if operator.role not in CANCELLERS:
        raise NotAuthorized(f"{operator_id} ({operator.role}) may not cancel; an Admin or Trader may (D31)")
    actor = Actor(ActorKind.OPERATOR, operator.operator_id, operator.role.value, None)
    request = CancelRequest(order_id, actor, command_at, reason)
    return orders.request_cancel(request, correlation_id=f"cancel:{request.cancel_id}")


__all__ = ["CANCELLERS", "ConversionReport", "convert_approved", "intent_content_id", "request_cancel"]
