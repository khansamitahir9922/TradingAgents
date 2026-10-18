"""Start-up recovery for the Execution Worker (architecture G4; Laws 11, 14; PRD UC-13; ADR-004 section 5;
docs/tasks/M4-08.md).

In order, before the first normal step:
1. publish the outbox rows an earlier run left unpublished (with their original ids);
2. resolve SUBMITTING orders: saved before the broker call, so the call may or may not have happened. A
   lookup by client order id gives the broker's report (-> SUBMITTED, and its messages are then ingested) or no
   record (-> UNKNOWN, D20). **Never resent** (Law 14). A lookup error leaves it SUBMITTING for the next try;
3. resolve UNKNOWN orders the same way (the worker's `lookup_unknown`);
4. the normal step follows: orders still NEW go through the gate again, and unfinished cancel requests continue,
   CANCEL_PENDING ones being resent (M4-07 rule 3).
"""

from dataclasses import dataclass

from investment_engine.market.availability import check_utc
from investment_engine.oms.order_states import OrderState

S = OrderState


@dataclass(frozen=True)
class RecoveryReport:
    republished: int
    submitting_found: int
    submitting_unknown: int
    submitting_left: int
    unknown_looked_up: int


def recover(worker) -> RecoveryReport:
    republished = worker.outbox.publish_pending()
    now = check_utc(worker.clock.now(), "now")
    found = unknown = left = 0
    for order, _ in worker.orders.in_states(S.SUBMITTING):
        try:
            report = worker.port.lookup(order.client_order_id, at=now)  # under the D26 deadline
        except Exception:  # can't tell yet: leave it SUBMITTING and try again next time
            left += 1
            continue
        with worker.db.transaction():
            worker.db.lock(f"account-control|{order.account_id}")
            _, status = worker.orders.get(order.order_id)
            if status.state is not S.SUBMITTING:
                continue
            if report is None:
                worker.orders.transition(order.order_id, S.UNKNOWN, expected_aggregate_version=status.aggregate_version,
                                         at=now, reason="recovered: the broker has no record; never resent (D20)",
                                         broker_ref=f"recovery:{now.isoformat()}")
                unknown += 1
            else:
                worker.orders.transition(order.order_id, S.SUBMITTED,
                                         expected_aggregate_version=status.aggregate_version, at=now,
                                         reason="recovered: the broker has the order",
                                         broker_order_id=report.broker_order_id,
                                         broker_ref=f"recovery:{now.isoformat()}")
                found += 1
    looked_up = worker.lookup_unknown()
    return RecoveryReport(republished, found, unknown, left, looked_up)


__all__ = ["RecoveryReport", "recover"]
