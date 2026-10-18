"""The Core Engine's loop: convert approved intents, publish the outbox, run Core consumers (architecture Part E,
G1 step 10, G4; docs/tasks/M4-03.md).

In live mode it converts PAPER accounts' approved intents at the live
clock's time; under D22 none can be approved in M4, so this does nothing yet.
RESEARCH accounts are converted at their replay times by the offline harness
(M4-13). Every write goes through the order and intent stores in one
transaction; the Core Engine never touches the Execution Worker's transitions.
"""

from dataclasses import dataclass

from investment_engine.events.consumer import Consumer
from investment_engine.events.outbox import Outbox
from investment_engine.oms.conversion import convert_approved
from investment_engine.oms.order_states import ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.policy.accounts import AccountKind


@dataclass(frozen=True)
class CoreStepReport:
    converted: int
    published: int
    consumed: int = 0


class CoreEngine:
    def __init__(self, stores, *, clock) -> None:
        self.stores, self.clock = stores, clock
        self.outbox = Outbox(stores.db, writer=ProcessRole.CORE, clock=clock)
        self.orders = OrderStore(stores.db, role=ProcessRole.CORE, audit=stores.audit, outbox=self.outbox,
                                 clock=clock)
        # The Core's order-log projection consumer (M4-01 rule 6, M4-13): it applies every event once, in order per
        # aggregate, and records what it has seen; the order log itself reads the order store directly.
        self.consumer = Consumer(stores.db, name="order-log", handles={}, clock=clock)

    def step(self) -> CoreStepReport:
        converted = 0
        now = self.clock.now()
        for account in self.stores.accounts.accounts():
            if account.kind is AccountKind.PAPER:
                converted += len(convert_approved(account.account_id, at=now, stores=self.stores,
                                                  orders=self.orders).converted)
        published = self.outbox.publish_pending()
        report = self.consumer.run_once(limit=1000)
        return CoreStepReport(converted, published, report.applied + report.unhandled)


__all__ = ["CoreEngine", "CoreStepReport"]
