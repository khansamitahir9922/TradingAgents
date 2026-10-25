"""The Research Worker loop (M6-07; ADR-001; architecture Part E).

One job per step: claim it (a lease covering the whole bounded run), reserve the
day's budget, run the adapter outside any transaction under a deadline, then save
the record, context, usage and final version atomically and publish. A run past
its deadline is recorded FAILED; its thread may still be talking to the provider,
so the worker starts nothing new until it returns (as M4 does for a stalled
broker call). A lost database connection keeps its type, for the reconnect.
Nothing here can reach a broker, the OMS, the ledger or the kill switch.
"""

from __future__ import annotations

import importlib.metadata
import threading
import time
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal

from investment_engine.audit.events import AuditStore
from investment_engine.events.outbox import Outbox
from investment_engine.market.availability import check_utc
from investment_engine.oms.order_states import ProcessRole
from investment_engine.research.budget import BudgetRefused, ResearchBudget, actual_usage
from investment_engine.research.context import NoResearchContext, build_context
from investment_engine.research.contracts import JobState, ResearchRecord, RunOutcome, UsageTotals
from investment_engine.research.store import ResearchStore, StaleJob

LEASE_MARGIN = timedelta(minutes=5)  # the lease outlives the deadline, so a live run is never re-claimed


@dataclass(frozen=True)
class StepReport:
    claimed: int = 0
    succeeded: int = 0
    failed: int = 0
    refused: int = 0
    published: int = 0


class ResearchWorker:
    def __init__(self, db, *, worker_id: str, clock, port, calendar, deadline: timedelta,
                 code_version: str = "unversioned") -> None:
        self.db, self.worker_id, self.clock = db, worker_id, clock
        self.port, self.calendar, self.deadline = port, calendar, deadline
        self.code_version = code_version
        self.outbox = Outbox(db, writer=ProcessRole.RESEARCH, clock=clock)
        self.store = ResearchStore(db, role=ProcessRole.RESEARCH, audit=AuditStore(db), outbox=self.outbox,
                                   clock=clock)
        self.budget = ResearchBudget(self.store, accounts=None, clock=clock, command_clock=clock)
        self._stalled: threading.Thread | None = None

    def stalled(self) -> bool:
        if self._stalled is not None and not self._stalled.is_alive():
            self._stalled = None
        return self._stalled is not None

    def wait_for_stalled(self, timeout: float) -> None:
        if self._stalled is not None:
            self._stalled.join(timeout)

    def _bounded_run(self, job, attempt):
        result: dict = {}

        def call():
            try:
                result["output"] = self.port.run(job, attempt=attempt, clock=self.clock)
            except BaseException as exc:  # handed to the caller below
                result["error"] = exc

        thread = threading.Thread(target=call, name=f"research-{job.job_id[:12]}", daemon=True)
        thread.start()
        thread.join(self.deadline.total_seconds())
        if thread.is_alive():
            self._stalled = thread
            return None
        if "error" in result:
            raise result["error"]
        return result["output"]

    def _failed_record(self, job, attempt, started, reason) -> ResearchRecord:
        try:
            upstream = importlib.metadata.version("tradingagents")
        except importlib.metadata.PackageNotFoundError:
            upstream = "unknown"
        return ResearchRecord(job.job_id, attempt, job.settings, upstream, self.code_version, (), (), (), (), "{}",
                              UsageTotals(0, None, None, 0), ("the run's calls were not captured",), started,
                              max(started, check_utc(self.clock.now(), "now")), RunOutcome.FAILED, reason)

    def step(self) -> StepReport:
        if self.stalled():
            return StepReport(published=self.outbox.publish_pending())
        now = check_utc(self.clock.now(), "now")
        for job_id in self.store.claimable(at=now):
            current = self.store.current(job_id)
            try:
                claim = self.store.claim(job_id, expected_version=current.version, worker_id=self.worker_id,
                                         lease=self.deadline + LEASE_MARGIN)
            except StaleJob:
                continue  # another worker took it first
            return self._run_claim(job_id, claim)
        return StepReport(published=self.outbox.publish_pending())

    def _run_claim(self, job_id, claim) -> StepReport:
        expected = claim.version.version
        try:
            reservation = self.budget.reserve(claim.run_id)
        except BudgetRefused as refused:
            self.store.refuse_budget(job_id, expected_version=expected, worker_id=self.worker_id, reason=str(refused))
            return StepReport(claimed=1, refused=1, published=self.outbox.publish_pending())
        job = self.store.job(job_id)
        started = check_utc(self.clock.now(), "start")
        output = self._bounded_run(job, claim.attempt)
        context, usage = None, None
        if output is None:
            record = self._failed_record(job, claim.attempt, started,
                                         f"deadline exceeded after {self.deadline.total_seconds():g}s; "
                                         "the run is abandoned and its reservation stays counted")
        else:
            record = output.record
            usage = actual_usage(reservation, record.usage, at=check_utc(self.clock.now(), "now"))
            try:
                context = build_context(output, instrument_id=job.instrument_id, calendar=self.calendar)
            except NoResearchContext as missing:
                if record.outcome is RunOutcome.SUCCEEDED:
                    record = replace(record, outcome=RunOutcome.FAILED, failure=str(missing))
        final = self.store.finish(job_id, expected_version=expected, worker_id=self.worker_id, record=record,
                                  context=context, usage=usage)
        ok = final.state is JobState.SUCCEEDED
        return StepReport(claimed=1, succeeded=int(ok), failed=int(not ok), published=self.outbox.publish_pending())

    def run(self, *, poll_seconds: Decimal, stop, reconnect=None) -> ResearchWorker:
        """Step until `stop()`; a lost connection rebuilds the worker through `reconnect` (keeping any stall)."""
        from investment_engine.storage.postgres import connection_lost_errors

        lost = connection_lost_errors()
        worker, stalled = self, None
        while not stop():
            try:
                if worker is None:
                    worker = reconnect()
                    worker._stalled = stalled
                while not stop():
                    worker.step()
                    _wait(poll_seconds, stop)
            except lost:
                if reconnect is None:
                    raise
                stalled, worker = (worker._stalled if worker is not None else stalled), None
                _wait(poll_seconds, stop)
        return worker or self


def _wait(seconds: Decimal, stop) -> None:
    deadline = time.monotonic() + float(seconds)
    while not stop() and time.monotonic() < deadline:
        time.sleep(0.05)


__all__ = ["LEASE_MARGIN", "ResearchWorker", "StepReport"]
