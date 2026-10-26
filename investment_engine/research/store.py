"""Append-only research evidence on PostgreSQL (M6-02; C2).

Core (and the CLI acting for it) requests jobs and sets budgets; only the Research
Worker claims, finishes and saves runs. Each job version is a compare-and-set
successor of the previous one. A run's record, context, actual usage, final job
version and its event commit in one transaction (Law 11: save, then publish).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from investment_engine.audit.events import Actor, AuditEvent
from investment_engine.events.envelope import EventEnvelope
from investment_engine.ledger.contracts import identity
from investment_engine.lineage.records import canonical_json, decode
from investment_engine.market.availability import check_name, check_utc
from investment_engine.oms.order_states import ProcessRole
from investment_engine.research.contracts import (
    BudgetPolicy,
    BudgetUsage,
    JobState,
    JobVersion,
    ResearchContext,
    ResearchJob,
    ResearchRecord,
    RunOutcome,
    check_job_edge,
)
from investment_engine.storage.sqlite import port

MAX_ATTEMPTS = 2  # one run and, after a crash, one re-claim


class StaleJob(ValueError):
    """The job moved on since the caller read it; nothing was written."""


@dataclass(frozen=True)
class Claim:
    version: JobVersion
    attempt: int
    run_id: str


def run_id_for(job_id: str, attempt: int) -> str:
    """The run ID ResearchRecord derives for (job, attempt): fixed when the run is claimed."""
    return "rrn-" + identity((job_id, attempt))


class ResearchStore:
    def __init__(self, db, *, role, audit, outbox, clock) -> None:
        self.db = port(db)
        if self.db.backend != "postgresql":
            raise TypeError("research evidence requires PostgreSQL")
        self.role = ProcessRole(role)
        if self.role not in (ProcessRole.CORE, ProcessRole.RESEARCH):
            raise PermissionError("research evidence is written by the Core or the Research Worker only")
        if getattr(audit, "_db", None) is not self.db or getattr(outbox, "_db", None) is not self.db:
            raise ValueError("research, audit and outbox stores must share one database port")
        if outbox.writer is not self.role:
            raise ValueError("the outbox must write as this store's role")
        self.audit, self.outbox, self.clock = audit, outbox, clock

    # ------------------------------------------------------------------ helpers
    def _require(self, role: ProcessRole, what: str) -> None:
        if self.role is not role:
            raise PermissionError(f"{what} is written only by the {role.value}, not the {self.role.value}")

    def _claim_role(self) -> None:
        self.db.execute("SELECT set_config('investment_engine.process_role', :role, true)", {"role": self.role.value})

    def _now(self) -> datetime:
        return check_utc(self.clock.now(), "now")

    @staticmethod
    def _decode(row, kind):
        if row is None:
            raise KeyError("no such research record")
        value = decode(json.loads(row[0]))
        if not isinstance(value, kind):
            raise ValueError(f"stored research content is not a {kind.__name__}")
        return value

    def _append_version(self, value: JobVersion) -> JobVersion:
        self.db.execute("INSERT INTO research_job_versions (job_id,version,state,at,actor,lease_until,run_id,content) "
                        "VALUES(:j,:v,:s,:at,:actor,:lease,:run,:c)",
                        {"j": value.job_id, "v": value.version, "s": value.state.value, "at": value.at,
                         "actor": value.actor, "lease": value.lease_until, "run": value.run_id,
                         "c": canonical_json(value)})
        return value

    def _locked_current(self, job_id: str, expected_version: int) -> JobVersion:
        self.db.lock(f"research-job|{job_id}")
        current = self.current(job_id)
        if current.version != expected_version:
            raise StaleJob(f"{job_id} is at version {current.version}, not {expected_version}; nothing was written")
        return current

    def _event(self, event_type: str, value: JobVersion, now: datetime, payload) -> None:
        self.outbox.add(EventEnvelope(event_type, 1, "research-job", value.job_id, value.version, value.at, now,
                                      value.job_id, None, canonical_json(payload)))

    # -------------------------------------------------------------------- reads
    def job(self, job_id: str) -> ResearchJob:
        value = self._decode(self.db.fetchone("SELECT content FROM research_jobs WHERE job_id=:j", {"j": job_id}),
                             ResearchJob)
        if value.job_id != job_id:
            raise ValueError("stored research job content/identity mismatch")
        return value

    def versions(self, job_id: str) -> tuple[JobVersion, ...]:
        rows = self.db.fetchall("SELECT content FROM research_job_versions WHERE job_id=:j ORDER BY version",
                                {"j": job_id})
        return tuple(self._decode(row, JobVersion) for row in rows)

    def current(self, job_id: str) -> JobVersion:
        versions = self.versions(job_id)
        if not versions:
            raise KeyError(job_id)
        return versions[-1]

    def record(self, run_id: str) -> ResearchRecord:
        value = self._decode(self.db.fetchone("SELECT content FROM research_records WHERE run_id=:r",
                                              {"r": run_id}), ResearchRecord)
        if value.run_id != run_id:
            raise ValueError("stored research record content/identity mismatch")
        return value

    def context(self, run_id: str) -> ResearchContext:
        """Only a context whose job succeeded with this run, for the job's instrument (checked on read too)."""
        value = self._decode(self.db.fetchone("SELECT content FROM research_contexts WHERE run_id=:r",
                                              {"r": run_id}), ResearchContext)
        if value.run_id != run_id:
            raise ValueError("stored research context identity mismatch")
        record = self.record(run_id)
        succeeded = self.db.fetchone("SELECT 1 FROM research_job_versions WHERE job_id=:j AND run_id=:r "
                                     "AND state='SUCCEEDED'", {"j": record.job_id, "r": run_id})
        if succeeded is None or record.outcome is not RunOutcome.SUCCEEDED:
            raise ValueError("a research context is shown only for a run its job recorded as succeeded")
        self._check_bundle(self.job(record.job_id), record, value)
        return value

    def latest_context(self, instrument_id: str, *, at: datetime) -> ResearchContext | None:
        """The newest context generated at or before `at` (valid or expired: the caller labels it)."""
        row = self.db.fetchone("SELECT c.run_id FROM research_contexts c JOIN research_job_versions v ON "
                               "v.run_id = c.run_id AND v.state = 'SUCCEEDED' WHERE c.instrument_id=:i AND "
                               "c.generated_at<=:t ORDER BY c.generated_at DESC, c.run_id DESC LIMIT 1",
                               {"i": instrument_id, "t": check_utc(at, "at")})
        return None if row is None else self.context(row[0])

    def claimable(self, *, at: datetime) -> tuple[str, ...]:
        """Jobs a worker may claim now: REQUESTED, or CLAIMED with an expired lease and a re-claim left."""
        at = check_utc(at, "at")
        rows = self.db.fetchall(
            "SELECT v.job_id FROM research_job_versions v WHERE v.version = (SELECT max(w.version) FROM "
            "research_job_versions w WHERE w.job_id = v.job_id) AND (v.state = 'REQUESTED' OR (v.state = 'CLAIMED' "
            "AND v.lease_until <= :t AND (SELECT count(*) FROM research_job_versions c WHERE c.job_id = v.job_id "
            "AND c.state = 'CLAIMED') < :max)) ORDER BY v.at, v.job_id", {"t": at, "max": MAX_ATTEMPTS})
        return tuple(r[0] for r in rows)

    def latest_policy(self) -> BudgetPolicy | None:
        row = self.db.fetchone("SELECT content FROM research_budget_policies ORDER BY version DESC LIMIT 1")
        return None if row is None else self._decode(row, BudgetPolicy)

    def usage_on(self, day) -> tuple[BudgetUsage, ...]:
        rows = self.db.fetchall("SELECT content FROM research_budget_usage WHERE day=:d ORDER BY at, run_id, kind",
                                {"d": day})
        return tuple(self._decode(row, BudgetUsage) for row in rows)

    # ------------------------------------------------------------- Core writes
    def request(self, job: ResearchJob, *, by: Actor) -> JobVersion:
        """Record a request (idempotent per job). The caller has authorized `by` (M6-08)."""
        self._require(ProcessRole.CORE, "a research request")
        if not isinstance(job, ResearchJob):
            raise TypeError("ResearchJob required")
        if not isinstance(by, Actor) or by.actor_id != job.requested_by:
            raise ValueError("the request is attributed to the operator who made it")
        now = self._now()
        with self.db.transaction():
            self.db.lock(f"research-job|{job.job_id}")
            self._claim_role()
            row = self.db.fetchone("SELECT content FROM research_jobs WHERE job_id=:j", {"j": job.job_id})
            if row is not None:
                if self._decode(row, ResearchJob) != job:
                    raise ValueError("research job identity conflict")
                return self.versions(job.job_id)[0]
            self.db.execute("INSERT INTO research_jobs (job_id,instrument_id,research_date,requested_by,requested_at,"
                            "content) VALUES(:j,:i,:d,:by,:at,:c)",
                            {"j": job.job_id, "i": job.instrument_id, "d": job.research_date, "by": job.requested_by,
                             "at": job.requested_at, "c": canonical_json(job)})
            check_job_edge(None, JobState.REQUESTED)
            value = self._append_version(JobVersion(job.job_id, 1, JobState.REQUESTED, job.requested_at,
                                                    job.requested_by, None, None, job.reason))
            self.audit.append(AuditEvent(by, "research.request", "research-job", job.job_id, None, job, now,
                                         job.requested_at, job.reason, job.job_id, job.job_id))
            self._event("research.requested", value, now, job)
            return value

    def expire_unclaimed(self, job_id: str, *, expected_version: int, actor: str, reason: str) -> JobVersion:
        self._require(ProcessRole.CORE, "expiring an unclaimed request")
        with self.db.transaction():
            self._claim_role()
            current = self._locked_current(job_id, expected_version)
            check_job_edge(current.state, JobState.EXPIRED_UNCLAIMED)
            now = self._now()
            value = self._append_version(JobVersion(job_id, current.version + 1, JobState.EXPIRED_UNCLAIMED, now,
                                                    check_name(actor, "actor"), None, None, reason))
            self._event("research.expired", value, now, value)
            return value

    def set_policy(self, policy: BudgetPolicy) -> BudgetPolicy:
        """Append a budget policy; Admin authorization is the budget module's (M6-06)."""
        self._require(ProcessRole.CORE, "a budget policy")
        with self.db.transaction():
            self.db.lock("research-budget-policy")
            self._claim_role()
            latest = self.latest_policy()
            if policy.version != (1 if latest is None else latest.version + 1):
                raise StaleJob("budget policy version is stale")
            self.db.execute("INSERT INTO research_budget_policies (version,set_by,set_at,content) VALUES(:v,:by,:at,:c)",
                            {"v": policy.version, "by": policy.set_by, "at": policy.set_at, "c": canonical_json(policy)})
            return policy

    @staticmethod
    def _check_bundle(job, record, context) -> None:
        """A saved run belongs to exactly its job: frozen settings, instrument and its own timing."""
        if record.settings != job.settings:
            raise ValueError("the run record's settings differ from its job's frozen settings")
        if context is not None and (context.instrument_id != job.instrument_id
                                    or context.generated_at != record.finished_at):
            raise ValueError("the context must be its job's instrument, generated when its run finished")

    # ----------------------------------------------------- Research Worker writes
    def claim(self, job_id: str, *, expected_version: int, worker_id: str, lease: timedelta) -> Claim:
        self._require(ProcessRole.RESEARCH, "a research claim")
        if not isinstance(lease, timedelta) or lease <= timedelta(0):
            raise ValueError("a lease must be a positive duration")
        with self.db.transaction():
            self._claim_role()
            current = self._locked_current(job_id, expected_version)
            now = self._now()
            check_job_edge(current.state, JobState.CLAIMED)
            attempt = sum(v.state is JobState.CLAIMED for v in self.versions(job_id)) + 1
            if current.state is JobState.CLAIMED and now < current.lease_until:
                raise StaleJob(f"{job_id} is leased to {current.actor} until {current.lease_until.isoformat()}")
            if attempt > MAX_ATTEMPTS:
                raise StaleJob(f"{job_id} has used its {MAX_ATTEMPTS} attempts")
            run_id = run_id_for(job_id, attempt)
            value = self._append_version(JobVersion(job_id, current.version + 1, JobState.CLAIMED, now,
                                                    check_name(worker_id, "worker_id"), now + lease, run_id,
                                                    f"attempt {attempt}"))
            # Every job version is an event: consumers read each aggregate's versions contiguously.
            self._event("research.claimed", value, now, value)
            return Claim(value, attempt, run_id)

    def add_usage(self, usage: BudgetUsage) -> BudgetUsage:
        """Insert budget evidence in the caller's transaction (the budget module holds its day lock)."""
        self._require(ProcessRole.RESEARCH, "budget usage")
        if not isinstance(usage, BudgetUsage):
            raise TypeError("BudgetUsage required")
        if not self.db.in_transaction:
            raise RuntimeError("budget usage is written inside its reservation or run transaction")
        self._claim_role()
        self.db.execute("INSERT INTO research_budget_usage (day,run_id,kind,requests,tokens,at,content) "
                        "VALUES(:d,:r,:k,:n,:t,:at,:c)",
                        {"d": usage.day, "r": usage.run_id, "k": usage.kind, "n": usage.requests, "t": usage.tokens,
                         "at": usage.at, "c": canonical_json(usage)})
        return usage

    def refuse_budget(self, job_id: str, *, expected_version: int, worker_id: str, reason: str) -> JobVersion:
        self._require(ProcessRole.RESEARCH, "a budget refusal")
        with self.db.transaction():
            self._claim_role()
            current = self._locked_current(job_id, expected_version)
            check_job_edge(current.state, JobState.BUDGET_REFUSED)
            now = self._now()
            value = self._append_version(JobVersion(job_id, current.version + 1, JobState.BUDGET_REFUSED, now,
                                                    worker_id, None, current.run_id, reason))
            self._event("research.budget_refused", value, now, value)
            return value

    def finish(self, job_id: str, *, expected_version: int, worker_id: str, record: ResearchRecord,
               context: ResearchContext | None, usage: BudgetUsage | None) -> JobVersion:
        """Save a finished run and its event atomically; only the current claim holder may."""
        self._require(ProcessRole.RESEARCH, "a finished run")
        if not isinstance(record, ResearchRecord) or record.job_id != job_id:
            raise ValueError("the record must be this job's ResearchRecord")
        succeeded = record.outcome is RunOutcome.SUCCEEDED
        if succeeded != (context is not None) or (context is not None and (
                not isinstance(context, ResearchContext) or context.run_id != record.run_id)):
            raise ValueError("a succeeded run saves exactly its own context; a failed run saves none")
        if usage is not None and (usage.run_id != record.run_id or usage.kind != "ACTUAL"):
            raise ValueError("finished-run usage must be this run's ACTUAL usage")
        with self.db.transaction():
            self._claim_role()
            current = self._locked_current(job_id, expected_version)
            self._check_bundle(self.job(job_id), record, context)
            if current.state is not JobState.CLAIMED or current.actor != worker_id or current.run_id != record.run_id:
                raise StaleJob("only the current claim holder finishes its own run")
            state = JobState.SUCCEEDED if succeeded else JobState.FAILED
            check_job_edge(current.state, state)
            now = self._now()
            self.db.execute("INSERT INTO research_records (run_id,job_id,attempt,outcome,started_at,finished_at,content) "
                            "VALUES(:r,:j,:a,:o,:s,:f,:c)",
                            {"r": record.run_id, "j": job_id, "a": record.attempt, "o": record.outcome.value,
                             "s": record.started_at, "f": record.finished_at, "c": canonical_json(record)})
            if context is not None:
                self.db.execute("INSERT INTO research_contexts (run_id,instrument_id,generated_at,valid_until,content) "
                                "VALUES(:r,:i,:g,:v,:c)",
                                {"r": context.run_id, "i": context.instrument_id, "g": context.generated_at,
                                 "v": context.valid_until, "c": canonical_json(context)})
            if usage is not None:
                self.add_usage(usage)
            value = self._append_version(JobVersion(job_id, current.version + 1, state, now, worker_id, None,
                                                    record.run_id, record.failure or "run finished"))
            self._event("research.completed", value, now, {"run_id": record.run_id, "outcome": record.outcome,
                                                           "context": context})
            return value


__all__ = ["Claim", "MAX_ATTEMPTS", "ResearchStore", "StaleJob", "run_id_for"]
