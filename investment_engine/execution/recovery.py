"""Start-up recovery for the Execution Worker (architecture G4; Laws 11, 14; PRD UC-13; ADR-004 section 5;
docs/tasks/M4-08.md).

In order, before the first normal step:
1. publish the outbox rows an earlier run left unpublished (with their original ids);
2. resolve SUBMITTING orders: saved before the broker call, so the call may or may not have happened. A
   lookup by client order id gives the broker's report (-> SUBMITTED, and its messages are then ingested) or no
   record (-> UNKNOWN, D20). **Never resent** (Law 14). A lookup error leaves it SUBMITTING, and every normal
   step tries it again (`ExecutionWorker.reconcile_submitting`; Codex M4 review B4);
3. resolve UNKNOWN orders the same way (the worker's `lookup_unknown`);
4. the normal step follows: orders still NEW go through the gate again, and unfinished cancel requests continue,
   CANCEL_PENDING ones being resent (M4-07 rule 3).
"""

from dataclasses import dataclass

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
    found, unknown, left, just_looked_up = worker.reconcile_submitting()  # the per-order retry every step runs (B4)
    looked_up = worker.lookup_unknown(skip=just_looked_up)
    return RecoveryReport(republished, found, unknown, left, looked_up)


__all__ = ["RecoveryReport", "recover"]
