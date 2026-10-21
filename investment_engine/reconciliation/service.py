"""Read-only, process-neutral readiness adapter; never captures or repairs a broker."""
from investment_engine.ledger.contracts import identity
from investment_engine.reconciliation.compare import InternalOrders, oms_fingerprint
from investment_engine.reconciliation.incidents import AccountingReadiness


def capture_prefix(snapshot, *, orders, at):
    """Bind a worker's capture proof to the OMS state it actually observed.

    NEW has no broker effect, so its creation cannot cause a capture loop. Any
    accepted fill or live-order change invalidates an earlier proof, even at the
    same replay instant. Its message-completeness bit is recorded separately.
    """
    rows = tuple((order, state, quantity, tuple(orders.fills(order.order_id)))
                  for order, state, quantity in orders.as_of(snapshot.account_id, at))
    evidence = InternalOrders(snapshot.account_id, at, at, snapshot.broker_account_id,
                               snapshot.snapshot_id, "capture-prefix", True, at, rows)
    return identity((snapshot.snapshot_id, oms_fingerprint(evidence)))


class ReadinessReader:
    def __init__(self, db, *, service=None):
        self.db, self.service = db, service

    def activated(self, account_id):
        return self.db.fetchone("SELECT 1 FROM ledger_activations WHERE account_id=:a", {"a": account_id}) is not None

    def at(self, account_id, at):
        if self.service is not None:
            return self.service.ready(account_id, at)
        # A worker without the injected verifier must fail closed after activation.
        return AccountingReadiness(False, "ledger readiness verifier not configured", at, None, None, None, None, ())
