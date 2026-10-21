"""The Core Engine's loop: convert approved intents, publish the outbox, run Core consumers (architecture Part E,
G1 step 10, G4; docs/tasks/M4-03.md).

In live mode it converts PAPER accounts' approved intents at the live
clock's time; under D22 none can be approved in M4, so this does nothing yet.
RESEARCH accounts are converted at their replay times by the offline harness
(M4-13). Every write goes through the order and intent stores in one
transaction; the Core Engine never touches the Execution Worker's transitions.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

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
    def __init__(self, stores, *, clock, accounting=None) -> None:
        self.stores, self.clock = stores, clock
        self.accounting = accounting
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
                converted += len(self.convert(account.account_id, at=now).converted)
        published, consumed = self.publish_and_consume()
        return CoreStepReport(converted, published, consumed)

    def convert(self, account_id: str, *, at):
        """The Core role's conversion of one account's approved intents at a business time: the live step's for
        PAPER accounts, and the offline research harness's at replay time (D24; Codex M4 review B12)."""
        return convert_approved(account_id, at=at, stores=self.stores, orders=self.orders)

    def publish_and_consume(self) -> tuple[int, int]:
        """Publish the outbox, then run the order-log consumer; returns (published, consumed)."""
        published = self.outbox.publish_pending()
        report = self.consumer.run_once(limit=1000)
        accounted = 0
        if self.accounting is not None:
            result = self.accounting.consumer.run_once(limit=1000)
            accounted = result.applied + result.unhandled
        return published, report.applied + report.unhandled + accounted

    def sync_accounting(self, account_id, *, at):
        return None if self.accounting is None else self.accounting.synchronize(account_id, at=at)

    def run(self, *, poll_seconds: Decimal, stop: Callable[[], bool],
            reconnect: Callable[[], "CoreEngine"] | None = None) -> "CoreEngine":
        """Live mode: publish what an earlier run left unpublished (G4), then step until `stop()` is true. If the
        database connection is lost and `reconnect` is given, it builds an engine on new connections, which
        republishes and resumes (M4-08; Codex M4 review B4); without it the error is raised. Returns the engine in
        use when it stopped."""
        from investment_engine.storage.postgres import connection_lost_errors

        lost = connection_lost_errors()
        engine = self
        while not stop():
            try:
                if engine is None:
                    engine = reconnect()
                engine.outbox.publish_pending()
                while not stop():
                    engine.step()
                    _wait(poll_seconds, stop)
            except lost:
                if reconnect is None:
                    raise
                engine = None
                _wait(poll_seconds, stop)
        return engine or self


def _wait(seconds: Decimal, stop: Callable[[], bool]) -> None:
    deadline = time.monotonic() + float(seconds)
    while not stop() and time.monotonic() < deadline:
        time.sleep(0.05)


__all__ = ["CoreEngine", "CoreStepReport"]
