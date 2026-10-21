"""A simulated research run: stored views, through the full order path, to the simulated broker (architecture Part
K M4; Law 20; D23, D24; PRD UC-11 at M4; docs/tasks/M4-13.md).

The harness builds the unchanged Core Engine and Execution Worker role objects, each with its own database
connection, process role, stores and clock, and steps them on one replay timeline. They exchange work only through
database rows, and only worker code calls the broker port. The broker comes from the factory's allowlist as
`simulated`, for a RESEARCH account only; no secrets are loaded. A PAPER account is refused.

For each stored view, in time order (B5):
1. a worker step at the view's time: the broker materializes every session decided by then, and the worker ingests
   those fills and expiries, so the next proposal is sized on the post-fill portfolio;
2. the Core role proposes the view against the provisional projection (M4-09), Level 2 approves it, then the Core
   converts and publishes;
3. a worker step just after: gate and submission, before the target session's open.
After the last view, one more worker step at the last target session's cutoff ingests the final outcomes.

A range already run for the account is refused: use a fresh account. If the provisional projection becomes
unavailable (a corporate action without coverage, a fractional split, an unsupported action, or an unresolved order
crossing an action; M4-09 rule 3), proposing stops for the account from that view, with the reason, which the report
and the order log give (rule 4). The worker keeps stepping, so orders already placed still reach a final state; no
portfolio is ever invented.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from investment_engine.clock import ReplayClock
from investment_engine.core.engine import CoreEngine
from investment_engine.execution.factory import build_broker, build_gate_reads
from investment_engine.execution.worker import ExecutionWorker
from investment_engine.killswitch.flag import KillSwitchReader
from investment_engine.lineage.records import LineageStore
from investment_engine.oms.pipeline import ControlStores, propose
from investment_engine.policy.accounts import AccountKind
from investment_engine.portfolio.provisional import ProvisionalFingerprints

_TICK = timedelta(microseconds=1)


class SimulationRefused(ValueError):
    """The run was not started; nothing was written."""


@dataclass(frozen=True)
class SimulationReport:
    account_id: str
    views: int
    proposals: dict
    orders: int
    stops: tuple[str, ...]  # why proposing stopped (the projection became Unavailable), at most one


def stored_views(db, instrument_id: str, first: datetime, last: datetime) -> list:
    store = LineageStore(db)
    out = []
    for lineage_id in store.ids(instrument_id):
        record = store.get(lineage_id)
        if first <= record.generated_at <= last:
            out.append(replace(record.decision, evidence_refs=(lineage_id,)))
    return sorted(out, key=lambda v: (v.generated_at, v.evidence_refs))


def simulate(account_id: str, *, views, open_db, knowledge, calendar, coverage, flag_path, source: str,
             calendar_version: str, code_version: str, proposal_knowledge=None, accounting_factory=None,
             accounting_work_budget: int = 8) -> SimulationReport:
    """`open_db()` returns a fresh PostgresDatabase: one connection per role. `knowledge` is the broker's and the
    gate's, which may run ahead. `proposal_knowledge(view, stores)`, when given, is each proposal's: bounded at the
    sequence of that view's own decision bar, so an event delivered at exactly the view's time but after its bar is
    never seen by the proposal (Law 5; Codex M4 review B3), as in M3's replay path."""
    if not views:
        raise SimulationRefused("no stored views in that range; run 'views replay' first")
    if type(accounting_work_budget) is not int or accounting_work_budget < 1:
        raise SimulationRefused("accounting work budget must be a positive integer")
    start = views[0].generated_at
    core_clock, worker_clock = ReplayClock(start), ReplayClock(start)
    core_db, worker_db = open_db(), open_db()
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    core = ControlStores.open(core_db, core_clock, instruments=SqliteInstrumentRepository(core_db))
    account = core.accounts.account(account_id)
    if account.kind is not AccountKind.RESEARCH:
        raise SimulationRefused("only a RESEARCH account runs a simulation; a PAPER account never reaches the simulator "
                                "(D23)")
    accounting = None if accounting_factory is None else accounting_factory(core_db, core_clock)
    engine = CoreEngine(core, clock=core_clock, accounting=accounting)
    core_orders = engine.orders
    if core_orders.for_account(account_id):
        raise SimulationRefused(f"{account_id} already has orders from a run; use a fresh account")

    # The broker has its own connection, never the worker's: a call outliving the D26 deadline can't share it (B5).
    # Scoped to this account, the broker and the worker never touch another account's work (B9).
    broker = build_broker("simulated", account_kind=AccountKind.RESEARCH, db=open_db(), account_id=account_id,
                          knowledge=knowledge, calendar=calendar, source=source)
    worker_accounting = None if accounting_factory is None else accounting_factory(worker_db, worker_clock)
    worker = ExecutionWorker(worker_db, clock=worker_clock, broker=broker, kill_switch=KillSwitchReader(flag_path),
                             accounts=frozenset({account_id}), accounting=worker_accounting)
    worker_stores = ControlStores.open(worker_db, worker_clock, instruments=SqliteInstrumentRepository(worker_db))
    worker.reads = build_gate_reads(worker_stores, worker.orders, knowledge=knowledge, calendar=calendar,
                                    fingerprints=ProvisionalFingerprints(worker_stores.snapshots, worker.orders,
                                                                         knowledge=knowledge, calendar=calendar,
                                                                         coverage=coverage, source=source),
                                    accounting=worker_accounting)

    def at(t):
        for clock in (core_clock, worker_clock):
            if t > clock.now():
                clock.advance_to(t)

    def settle():
        if accounting is None or not accounting.activated(account_id):
            worker.step()
            return True
        previous = None
        for _ in range(accounting_work_budget):
            worker.step()
            engine.publish_and_consume()
            engine.sync_accounting(account_id, at=core_clock.now())
            ready = accounting.ready(account_id, core_clock.now())
            from investment_engine.oms.order_states import OrderState
            pending = worker.orders.in_states(OrderState.NEW, account_id=account_id)
            if ready.ready and not pending:
                return True
            marker = (ready, tuple((o.order_id, s.aggregate_version) for o, s in worker.orders.for_account(account_id)),
                      core_db.fetchone("SELECT count(*) FROM processed_events WHERE consumer='accounting-ledger'")[0])
            if marker == previous:
                break
            previous = marker
        return False

    outcomes, stops = {}, []
    for view in views:
        t = view.generated_at
        at(t)
        settled = settle()  # 1: finite pinned prefix before sizing
        if not settled and not stops:
            stops.append(f"{t.isoformat()}: INCOMPLETE accounting prefix/readiness (no progress or work budget)")
        if stops:
            outcomes["NOT_PROPOSED (stopped)"] = outcomes.get("NOT_PROPOSED (stopped)", 0) + 1
            continue
        seen = knowledge if proposal_knowledge is None else proposal_knowledge(view, core)
        record = propose(account_id, view, at=t, stores=core, knowledge=seen, calendar=calendar,
                         coverage=coverage, calendar_version=calendar_version, code_version=code_version,
                         correlation_id=f"sim:{account_id}:{t.isoformat()}", orders=core_orders, accounting=accounting)
        outcomes[record.outcome.value] = outcomes.get(record.outcome.value, 0) + 1
        if record.outcome.value == "PREREQUISITE_MISSING" and "snapshot" in record.missing:
            stops.append(f"{t.isoformat()}: {record.reason}")  # the projection is Unavailable: stop here (rule 4)
        engine.convert(account_id, at=t)  # 2: the Core role object's conversion, at replay time
        engine.publish_and_consume()
        at(t + _TICK)
        if not settle() and not stops:
            stops.append(f"{core_clock.now().isoformat()}: INCOMPLETE accounting after proposal (no progress or work budget)")
    last = max(o.target_session for o, _ in core_orders.for_account(account_id)) if core_orders.for_account(
        account_id) else None
    if last is not None:
        at(calendar.next_session(last).open + _TICK)
        settled = settle()
        settled = settle() and settled
        if not settled and not stops:
            stops.append(f"{core_clock.now().isoformat()}: INCOMPLETE final accounting prefix/readiness")
    engine.publish_and_consume()
    return SimulationReport(account_id, len(views), outcomes, len(core_orders.for_account(account_id)), tuple(stops))


__all__ = ["SimulationRefused", "SimulationReport", "simulate", "stored_views"]
