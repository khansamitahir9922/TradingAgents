"""Carrying cancel requests to a durable close (Law 15; D31; docs/tasks/M4-07.md rule 3; Codex M4 review B2, R1).

For each request not CLOSED, once per step and whatever the kill switch says:

    order NEW                         the gate's `cancel` check rejects it; the request closes when it's final
    order SUBMITTED, PARTIALLY_FILLED -> CANCEL_PENDING and SENDING (attempt n), commit; broker.cancel outside
                                      any transaction; CANCELLED or PENDING -> SENT; a timeout leaves SENDING
    order CANCEL_PENDING, SENDING     after a crash or a timeout: send again (attempt n + 1); the broker
                                      de-duplicates by client order id
    order CANCEL_PENDING, SENT        wait: the CANCELLED or FILL message makes the order final
    order SUBMITTING or UNKNOWN       wait: there's no G3 edge to CANCEL_PENDING until it's resolved
    order final                       CLOSED: CANCELLED, TOO_LATE (filled or expired) or NOTHING_TO_CANCEL

Saving CANCEL_PENDING is never treated as cancelled, and a PENDING answer
never closes the request: only the order's final state does.
"""

from dataclasses import dataclass

from investment_engine.execution.broker_port import BrokerTimeout
from investment_engine.market.availability import check_utc
from investment_engine.oms.intent_store import StaleWrite
from investment_engine.oms.order_states import FINAL, OrderState
from investment_engine.oms.orders import CancelProgress

S = OrderState
P = CancelProgress
_OUTCOME = {S.CANCELLED: "CANCELLED", S.FILLED: "TOO_LATE", S.EXPIRED: "TOO_LATE",
            S.REJECTED: "NOTHING_TO_CANCEL", S.GATE_REJECTED: "NOTHING_TO_CANCEL"}


@dataclass(frozen=True)
class CancelReport:
    sent: int
    closed: int
    waiting: int


def _send(request, version, *, orders, broker, now) -> int:
    """SENDING is committed; the broker call happens outside any transaction; then SENT is recorded."""
    try:
        result = broker.cancel(request_client(orders, request), at=now)
    except BrokerTimeout:
        return 0  # stays SENDING: resent next step
    if result.outcome in ("CANCELLED", "PENDING"):
        orders.cancel_progress(request.cancel_id, P.SENT, expected_version=version, at=now,
                               received_at=result.received_at)
    elif result.outcome == "TOO_LATE":
        orders.cancel_progress(request.cancel_id, P.SENT, expected_version=version, at=now,
                               received_at=result.received_at)  # closes when the order's final state arrives
    else:  # UNKNOWN_ORDER: the broker has no record; recorded, and the request waits for the order's resolution
        orders.record_anomaly(request.order_id, kind="cancel_unknown_order", detail=result.reason, at=now,
                              broker_ref=f"{request.cancel_id}:{version}")
    return 1


def request_client(orders, request) -> str:
    return orders.get(request.order_id)[0].client_order_id


def process_cancels(*, orders, broker, clock, sendable=lambda: True) -> CancelReport:
    """`sendable()` is false while an earlier broker call is stalled (D26; Codex M4 review B5): requests whose order
    is final still close, and the others wait, with no attempt recorded that wasn't made. A concurrent change to
    one request or order (StaleWrite) leaves only that request for the next step (B4)."""
    now = check_utc(clock.now(), "now")
    counts = {"sent": 0, "closed": 0, "waiting": 0}
    for request, progress, version in orders.open_cancels():
        try:
            counts[_one(request, progress, version, orders=orders, broker=broker, now=now, sendable=sendable)] += 1
        except StaleWrite:
            counts["waiting"] += 1
    return CancelReport(counts["sent"], counts["closed"], counts["waiting"])


def _one(request, progress, version, *, orders, broker, now, sendable) -> str:
    order, status = orders.get(request.order_id)
    if status.state in FINAL:
        orders.cancel_progress(request.cancel_id, P.CLOSED, expected_version=version, at=now,
                               outcome=_OUTCOME[status.state])
        return "closed"
    if not sendable():
        return "waiting"
    if status.state in (S.SUBMITTED, S.PARTIALLY_FILLED):
        db = orders._db
        with db.transaction():
            db.lock(f"account-control|{order.account_id}")
            orders.transition(order.order_id, S.CANCEL_PENDING, expected_aggregate_version=status.aggregate_version,
                              at=now, reason=f"cancel requested ({request.cancel_id})")
            version = orders.cancel_progress(request.cancel_id, P.SENDING, expected_version=version, at=now)
        return "sent" if _send(request, version, orders=orders, broker=broker, now=now) else "waiting"
    if status.state is S.CANCEL_PENDING and progress is P.SENDING:
        version = orders.cancel_progress(request.cancel_id, P.SENDING, expected_version=version, at=now)
        return "sent" if _send(request, version, orders=orders, broker=broker, now=now) else "waiting"
    return "waiting"  # NEW (the gate rejects it), SUBMITTING, UNKNOWN, or CANCEL_PENDING already SENT


__all__ = ["CancelReport", "process_cancels"]
