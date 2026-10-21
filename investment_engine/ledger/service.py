"""Core accounting composition: delivered sources, per-event effects and pinned readiness.

The selector takes explicit public action deliveries. It never reads a replay
reader's private buffers, calls a broker, or treats availability as delivery.
"""
from dataclasses import replace

from investment_engine.audit.events import AuditStore
from investment_engine.events.consumer import Consumer
from investment_engine.events.outbox import Outbox
from investment_engine.ledger.balances import balances
from investment_engine.ledger.contracts import AccountingUnavailable, SourceBundle
from investment_engine.ledger.fingerprint import project
from investment_engine.ledger.restate import _validate_sources, sync_account
from investment_engine.ledger.sources import action_reference, fill_reference, opening_bundle
from investment_engine.ledger.store import LedgerStore
from investment_engine.oms.order_states import ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.policy.accounts import AccountRegistry
from investment_engine.portfolio.reference import Unavailable
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
from investment_engine.reconciliation.compare import InternalOrders, compare
from investment_engine.reconciliation.incidents import AccountingReadiness, IncidentStore
from investment_engine.reconciliation.service import capture_prefix
from investment_engine.reconciliation.snapshots import BrokerSnapshotStore


class SourceSelector:
    def __init__(self, db, *, clock, command_clock, calendar, provider, coverage, delivered_actions,
                 market_root=None):
        self.db, self.clock, self.calendar = db, clock, calendar
        self.provider, self.coverage = provider, coverage
        self.delivered_actions, self.market_root = delivered_actions, market_root
        audit = AuditStore(db)
        self.states = PortfolioSnapshotStore(db, audit, AccountRegistry(db, audit, command_clock), command_clock)
        self.orders = OrderStore(db, role=ProcessRole.CORE, audit=audit,
                                 outbox=Outbox(db, writer=ProcessRole.CORE, clock=clock), clock=clock)

    def __call__(self, account_id, at):
        opening = opening_bundle(self.states.starting_state(account_id), at=at)
        records, refs = list(opening.records), list(opening.references)
        held = {i for i, _ in opening.records[0].positions}
        for order, _ in self.orders.for_account(account_id):
            for fill in self.orders.fills(order.order_id):
                if max(fill.executed_at, fill.delivered_at, fill.recorded_at) <= at:
                    records.append((order, fill))
                    refs.append(fill_reference(order, fill))
                    held.add(order.instrument_id)
        coverage = self.coverage(account_id, at) if callable(self.coverage) else self.coverage
        if coverage is not None:
            records.extend(c for c in coverage if c.instrument_id in held)
        for action, delivered in self.delivered_actions(account_id, at):
            if (action.instrument_id in held and max(action.available_from, delivered) <= at and
                    self.calendar.session(action.ex_date).open > opening.records[0].effective_at):
                records.append(action)
                refs.append(action_reference(action, delivered_at=delivered, calendar=self.calendar))
        if self.market_root is not None:
            records.append({"market_root": str(self.market_root)})
        return SourceBundle(account_id, at, tuple(records), tuple(refs), self.provider,
                            "explicit-delivered-source-selector", (), "source-selector-v1")


class AccountingService:
    def __init__(self, db, *, clock, command_clock, sources):
        self.db, self.clock, self.sources = db, clock, sources
        self.audit = AuditStore(db)
        self.outbox = Outbox(db, writer=ProcessRole.CORE, clock=clock)
        self.ledger = LedgerStore(db, audit=self.audit, outbox=self.outbox, clock=clock, command_clock=command_clock)
        self.orders = OrderStore(db, role=ProcessRole.CORE, audit=self.audit, outbox=self.outbox, clock=clock)
        self.snapshots = BrokerSnapshotStore(db, role=ProcessRole.CORE, audit=self.audit,
                                              outbox=self.outbox, clock=clock)
        self.incidents = IncidentStore(db, audit=self.audit, outbox=self.outbox,
            accounts=AccountRegistry(db, self.audit, command_clock), clock=clock, command_clock=command_clock,
            current_evidence=self._current_or_none)
        self.consumer = Consumer(db, name="accounting-ledger", clock=clock, serialize=True,
                                  handles={"order.fill_recorded": self._fill_event})

    def activated(self, account_id):
        return self.ledger.activation(account_id) is not None

    def _fill_event(self, event):
        order = self.orders.get(event.aggregate_id)[0]
        if self.activated(order.account_id):
            sync_account(order.account_id, through=self.clock.now(),
                          sources=self.sources(order.account_id, self.clock.now()), ledger=self.ledger)

    def current(self, account_id, at):
        """Read-only recomputation, called with the account lock by readiness/resolution."""
        head = self.ledger.read_head(account_id, known_at=at)
        snapshot = self.snapshots.latest(account_id, known_at=at)
        if snapshot is None:
            raise AccountingUnavailable(account_id, at, ("worker snapshot not recorded",))
        prefix = self.snapshots.ingestion(snapshot.snapshot_id, known_at=at)
        value = balances(account_id, effective_at=at, known_at=at, book_id=head.book_id, ledger=self.ledger)
        if isinstance(value, AccountingUnavailable):
            raise value
        try:
            source_bundle = self.sources(account_id, at)
            if not source_bundle.complete:
                raise AccountingUnavailable(account_id, at, source_bundle.omissions)
            # Validate completeness/content against actual immutable source stores,
            # including a correction delivered after the last successful sync.
            _, _, _, refs = _validate_sources(account_id, at, source_bundle, self.ledger, head,
                                               self.sources.calendar)
            if not {r.source_id for r in refs} <= {r.source_id for r in head.sources}:
                raise AccountingUnavailable(account_id, at, ("ledger has not synchronized the current source prefix",))
        except AccountingUnavailable as exc:
            value = replace(value, complete=False, reasons=tuple(exc.reasons))
        rows = tuple((order, state, qty, tuple(self.orders.fills(order.order_id)))
                      for order, state, qty in self.orders.as_of(account_id, at))
        complete = bool(prefix and prefix.complete and
                        prefix.prefix_ref == capture_prefix(snapshot, orders=self.orders, at=at))
        evidence = InternalOrders(account_id, at, at, snapshot.broker_account_id, snapshot.snapshot_id,
            prefix.observation_id if prefix else "missing-worker-ingestion-proof", complete,
            at, rows, () if complete else ("worker has not proved the current pinned message/OMS prefix",))
        return compare(account_id, snapshot=snapshot, ledger_balances=value, internal_orders=evidence, known_at=at)

    def synchronize(self, account_id, *, at):
        if not self.activated(account_id):
            return None
        if self.db.in_transaction:
            raise RuntimeError("accounting synchronization must own its transaction; consumer dispatch is separate")
        try:
            with self.db.transaction():
                self.db.lock(f"account-control|{account_id}")
                sync_account(account_id, through=at, sources=self.sources(account_id, at), ledger=self.ledger)
        except AccountingUnavailable:
            # The failed sync transaction rolled back in full. Read and record
            # the gap in a new scope, never suppress a poisoned nested scope.
            return self._observe_current(account_id, at)
        return self._observe_current(account_id, at)

    def _observe_current(self, account_id, at):
        with self.db.transaction():
            self.db.lock(f"account-control|{account_id}")
            try:
                result = self.current(account_id, at)
            except AccountingUnavailable:
                return None
            self.incidents.observe(result, force_incident="negative cash from accepted facts" in result.reasons)
            return result

    def ready(self, account_id, at):
        try:
            return self.incidents.readiness(account_id, at=at)
        except AccountingUnavailable as exc:
            return AccountingReadiness(False, str(exc), at, None, None, None, None, ())

    def _current_or_none(self, account_id, at):
        try:
            return self.current(account_id, at)
        except AccountingUnavailable:
            # The incident verifier treats absent comparable evidence as false.
            # Catch before leaving its transaction scope, so an expected data
            # gap cannot poison a caller's account-locked gate transaction.
            return None

    def current_balances(self, account_id, at):
        with self.db.transaction():
            self.db.lock(f"account-control|{account_id}")
            ready = self.ready(account_id, at)
            if not ready.ready:
                return AccountingUnavailable(account_id, at, (ready.reason,))
            return balances(account_id, effective_at=at, known_at=at, book_id=ready.book_id, ledger=self.ledger)

    def projection(self, account_id, at):
        with self.db.transaction():
            self.db.lock(f"account-control|{account_id}")
            value = self.current_balances(account_id, at)
            if isinstance(value, AccountingUnavailable):
                return Unavailable(str(value))
            return project(value, orders=self.orders, account_id=account_id, at=at)
