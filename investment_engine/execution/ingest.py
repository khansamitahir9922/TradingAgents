"""Applying broker messages to the order store exactly once (architecture G1 step 14, G3; Part J;
docs/tasks/M4-07.md rule 2; the M4-00 rule 4 fill matrix).

Each message is applied in its own transaction, after the account-control lock
(M4-05 rule 4: fills and terminal states change gate inputs). Idempotency
comes from what the store already records: an applied message's id is the
`broker_ref` of the version or anomaly it produced, and a fill is keyed by its
broker fill id. So reading the message stream again, after a crash or on
every step, applies nothing twice. (The spec's stored broker cursor would
need a schema change outside M4-07's allowed files, so the de-duplication
rides on these existing records; the effect is the same.)

    ACK        SUBMITTING, UNKNOWN -> SUBMITTED; later states: no change
    FILL       the M4-00 rule 4 matrix (accounting; G3 edges only)
    CANCELLED  CANCEL_PENDING -> CANCELLED; SUBMITTED, PARTIALLY_FILLED -> CANCEL_PENDING -> CANCELLED
               (unsolicited); UNKNOWN -> CANCELLED; final: no change
    EXPIRED    SUBMITTING, SUBMITTED, UNKNOWN -> EXPIRED; PARTIALLY_FILLED, CANCEL_PENDING: an anomaly, no edge
               (D19); final: no change
    REJECTED   SUBMITTING, SUBMITTED, UNKNOWN -> REJECTED; anything later: an anomaly
"""

from dataclasses import dataclass

from investment_engine.execution.broker_port import BrokerMessage
from investment_engine.market.availability import check_utc
from investment_engine.oms.order_states import FINAL, OrderState
from investment_engine.oms.orders import Fill, FillOutcome

S = OrderState


@dataclass(frozen=True)
class IngestReport:
    applied: int
    skipped: int  # already applied, or no effect
    anomalies: int


def _applied(db, order_id: str, message_id: str) -> bool:
    return db.fetchone(
        "SELECT 1 FROM order_versions WHERE order_id = :o AND broker_ref = :m "
        "UNION ALL SELECT 1 FROM broker_anomalies WHERE order_id = :o AND broker_ref = :m LIMIT 1",
        {"o": order_id, "m": message_id}) is not None


def apply_message(message: BrokerMessage, *, orders, clock) -> str:
    """Apply one message; returns "applied", "skipped" or "anomaly"."""
    db = orders._db
    now = check_utc(clock.now(), "now")
    try:
        order, _ = orders.by_client_id(message.client_order_id)
    except KeyError:
        return "skipped"  # not one of ours
    with db.transaction():
        db.lock(f"account-control|{order.account_id}")
        order, status = orders.get(order.order_id)
        if _applied(db, order.order_id, message.message_id):
            return "skipped"
        at, ref, state = message.delivered_at, message.message_id, status.state

        def move(to, reason):
            nonlocal status
            status = orders.transition(order.order_id, to, expected_aggregate_version=status.aggregate_version,
                                       at=at, reason=reason, broker_ref=ref)

        def anomaly(kind, detail):
            orders.record_anomaly(order.order_id, kind=kind, detail=detail, at=at, broker_ref=ref)
            return "anomaly"

        if message.kind == "ACK":
            if state in (S.SUBMITTING, S.UNKNOWN):
                move(S.SUBMITTED, "acknowledged by the broker")
                return "applied"
            return "skipped"
        if message.kind == "FILL":
            f = message.fill
            if db.fetchone("SELECT 1 FROM broker_anomalies WHERE order_id = :o AND broker_ref = :f",
                           {"o": order.order_id, "f": f.broker_fill_id}) is not None:
                return "skipped"  # a refused or conflicting fill already recorded; duplicates are the store's to spot
            fill = Fill(order.order_id, f.quantity, f.price, f.fee, f.currency, f.executed_at, message.delivered_at,
                        now, f.broker_fill_id, f.provenance)
            outcome = orders.record_fill(fill, expected_aggregate_version=status.aggregate_version)
            return {FillOutcome.RECORDED: "applied", FillOutcome.DUPLICATE: "skipped"}.get(outcome, "anomaly")
        if message.kind == "CANCELLED":
            if state is S.CANCEL_PENDING or state is S.UNKNOWN:
                move(S.CANCELLED, message.reason or "cancelled by the broker")
                return "applied"
            if state in (S.SUBMITTED, S.PARTIALLY_FILLED):  # unsolicited: two legal edges
                move(S.CANCEL_PENDING, "the broker cancelled it unsolicited")
                move(S.CANCELLED, message.reason or "cancelled by the broker")
                return "applied"
            if state in FINAL:
                return "skipped"
            return anomaly("cancelled_without_edge", f"CANCELLED for a {state} order")
        if message.kind == "EXPIRED":
            if state in (S.SUBMITTING, S.SUBMITTED, S.UNKNOWN):
                move(S.EXPIRED, message.reason or "expired by the broker")
                return "applied"
            if state in (S.PARTIALLY_FILLED, S.CANCEL_PENDING):
                return anomaly("expired_without_edge", f"EXPIRED for a {state} order has no G3 edge (D19)")
            return "skipped"
        if message.kind == "REJECTED":
            if state in (S.SUBMITTING, S.SUBMITTED, S.UNKNOWN):
                move(S.REJECTED, message.reason or "rejected by the broker")
                return "applied"
            if state is S.REJECTED:
                return "skipped"
            return anomaly("rejected_after_progress", f"REJECTED for a {state} order")
        return anomaly("unknown_message", f"unknown message kind {message.kind}")


def ingest(*, broker, orders, clock) -> IngestReport:
    """Read every message the broker has delivered by now and apply each once."""
    now = check_utc(clock.now(), "now")
    counts = {"applied": 0, "skipped": 0, "anomaly": 0}
    for message in broker.messages(after=None, at=now):
        counts[apply_message(message, orders=orders, clock=clock)] += 1
    return IngestReport(counts["applied"], counts["skipped"], counts["anomaly"])


__all__ = ["IngestReport", "apply_message", "ingest"]
