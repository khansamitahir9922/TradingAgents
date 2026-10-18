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
from investment_engine.events.consumer import Consumer
from investment_engine.events.outbox import Outbox
from investment_engine.execution.factory import build_broker, build_gate_reads
from investment_engine.execution.worker import ExecutionWorker
from investment_engine.killswitch.flag import KillSwitchReader
from investment_engine.lineage.records import LineageStore
from investment_engine.oms.conversion import convert_approved
from investment_engine.oms.order_states import ProcessRole
from investment_engine.oms.order_store import OrderStore
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
             calendar_version: str, code_version: str) -> SimulationReport:
    """`open_db()` returns a fresh PostgresDatabase: one connection per role."""
    if not views:
        raise SimulationRefused("no stored views in that range; run 'views replay' first")
    start = views[0].generated_at
    core_clock, worker_clock = ReplayClock(start), ReplayClock(start)
    core_db, worker_db = open_db(), open_db()
    from investment_engine.storage.sqlite import SqliteInstrumentRepository

    core = ControlStores.open(core_db, core_clock, instruments=SqliteInstrumentRepository(core_db))
    account = core.accounts.account(account_id)
    if account.kind is not AccountKind.RESEARCH:
        raise SimulationRefused("only a RESEARCH account runs a simulation; a PAPER account never reaches the simulator "
                                "(D23)")
    core_outbox = Outbox(core_db, writer=ProcessRole.CORE, clock=core_clock)
    core_orders = OrderStore(core_db, role=ProcessRole.CORE, audit=core.audit, outbox=core_outbox, clock=core_clock)
    if core_orders.for_account(account_id):
        raise SimulationRefused(f"{account_id} already has orders from a run; use a fresh account")
    consumer = Consumer(core_db, name="order-log", handles={}, clock=core_clock)  # marks what the Core has seen

    broker = build_broker("simulated", account_kind=AccountKind.RESEARCH, db=worker_db, knowledge=knowledge,
                          calendar=calendar, source=source)
    worker = ExecutionWorker(worker_db, clock=worker_clock, broker=broker, kill_switch=KillSwitchReader(flag_path))
    worker_stores = ControlStores.open(worker_db, worker_clock, instruments=SqliteInstrumentRepository(worker_db))
    worker.reads = build_gate_reads(worker_stores, worker.orders, knowledge=knowledge, calendar=calendar,
                                    fingerprints=ProvisionalFingerprints(worker_stores.snapshots, worker.orders,
                                                                         knowledge=knowledge, calendar=calendar,
                                                                         coverage=coverage, source=source))

    def at(t):
        for clock in (core_clock, worker_clock):
            if t > clock.now():
                clock.advance_to(t)

    outcomes, stops = {}, []
    for view in views:
        t = view.generated_at
        at(t)
        worker.step()  # 1: everything decided by now is ingested before sizing
        if stops:
            outcomes["NOT_PROPOSED (stopped)"] = outcomes.get("NOT_PROPOSED (stopped)", 0) + 1
            continue
        record = propose(account_id, view, at=t, stores=core, knowledge=knowledge, calendar=calendar,
                         coverage=coverage, calendar_version=calendar_version, code_version=code_version,
                         correlation_id=f"sim:{account_id}:{t.isoformat()}", orders=core_orders)
        outcomes[record.outcome.value] = outcomes.get(record.outcome.value, 0) + 1
        if record.outcome.value == "PREREQUISITE_MISSING" and "snapshot" in record.missing:
            stops.append(f"{t.isoformat()}: {record.reason}")  # the projection is Unavailable: stop here (rule 4)
        convert_approved(account_id, at=t, stores=core, orders=core_orders)  # 2
        core_outbox.publish_pending()
        consumer.run_once(limit=1000)
        at(t + _TICK)
        worker.step()  # 3: gate and submit before the target session's open
    last = max(o.target_session for o, _ in core_orders.for_account(account_id)) if core_orders.for_account(
        account_id) else None
    if last is not None:
        at(calendar.next_session(last).open + _TICK)
        worker.step()
        worker.step()
    core_outbox.publish_pending()
    consumer.run_once(limit=1000)
    return SimulationReport(account_id, len(views), outcomes, len(core_orders.for_account(account_id)), tuple(stops))


__all__ = ["SimulationRefused", "SimulationReport", "simulate", "stored_views"]
