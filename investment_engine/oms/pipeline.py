"""The intent pipeline: one view becomes a recorded proposal (architecture G1 steps 6-9; docs/tasks/M3-12.md).

For one account and one view: expire that account's due intents, gather the
prerequisites (account, autonomy setting, limits, rules, the view's lineage,
the instrument, the raw reference, the starting state and the snapshot), size,
create version 1, run policy, run risk (a reduction supersedes v1 with v2,
which is checked again), then route by autonomy: Level 1 waits for approval
until the target session's open; Level 2 is approved by rule until that
session's close (never past the view's validity). A proposal already late
expires through legal G2 edges (EXPIRED_ON_ARRIVAL; no new transition).

Exactly what ran is recorded (Codex B3): a ProposalRecord per (account, view);
an IntentLineageRecord per intent version, superseded ones included, with
NotRun for a check that never ran; nothing is invented. An unknown account
returns a diagnostic record that is not stored and changes nothing (Codex
acceptance note 3). Everything for one (account, view) commits in one managed
transaction, audit events included, or nothing does.

Serialization (S4, B5): the account-control lock is held for the whole
proposal, so settings can't change underneath it; a BUY also takes the
account's buy-admission lock for its target session before risk reads the
admitted count, and keeps it until the admission commits.

Timelines never mix (R3): RESEARCH proposals act at an explicit replay time
and PAPER proposals only at the live clock's time; expiry touches only the
proposing account. Replays read point-in-time knowledge through the Knowledge
port (S2). M3 has no fills: holdings stay at the declared start. No orders,
broker, kill switch or outbox here.
"""

import dataclasses
import hashlib
import json
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.decision.market_view import MarketView
from investment_engine.lineage.intent_lineage import IntentLineageRecord, IntentLineageStore
from investment_engine.lineage.records import LineageStore, canonical_json, decode, register
from investment_engine.market.availability import check_utc
from investment_engine.oms.intent_store import IntentStore, StoredIntent
from investment_engine.oms.intents import IntentState, Side
from investment_engine.policy.accounts import AccountKind, AccountRegistry
from investment_engine.policy.checks import check_policy
from investment_engine.portfolio.reference import Unavailable, decision_reference
from investment_engine.portfolio.sizer import SIZER_VERSION, size
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore, build_snapshot
from investment_engine.risk.checks import (
    RiskInputs,
    average_daily_value,
    check_risk,
    reduced_version,
)
from investment_engine.risk.decisions import NotRun, RiskOutcome
from investment_engine.risk.limits import LimitStore, NoLimits
from investment_engine.storage.sqlite import port

CORE = Actor(ActorKind.PROCESS, "core-engine", None, None)
POLICY_NOT_RUN_REASON = "policy rejected: risk not evaluated"


class ProposalOutcome(StrEnum):
    PREREQUISITE_MISSING = "PREREQUISITE_MISSING"
    NO_INTENT = "NO_INTENT"
    POLICY_REJECTED = "POLICY_REJECTED"
    RISK_REJECTED = "RISK_REJECTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXPIRED_ON_ARRIVAL = "EXPIRED_ON_ARRIVAL"


@dataclass(frozen=True)
class ProposalRecord:
    account_id: str
    view_lineage_id: str
    at: datetime
    outcome: ProposalOutcome
    reason: str
    missing: tuple[str, ...]
    intent_id: str | None
    versions: tuple[int, ...]
    record_id: str = field(init=False)  # "prp-" + SHA-256

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", ProposalOutcome(self.outcome))
        object.__setattr__(self, "missing", tuple(self.missing))
        object.__setattr__(self, "versions", tuple(self.versions))
        content = canonical_json({f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init})
        object.__setattr__(self, "record_id", "prp-" + hashlib.sha256(content.encode()).hexdigest())


register(ProposalOutcome)
register(ProposalRecord)


class ProposalStore:
    def __init__(self, db) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("proposal records are PostgreSQL only (docs/tasks/M3-12.md)")

    def append(self, record: ProposalRecord) -> None:
        blob = canonical_json(record)
        existing = self.for_view(record.account_id, record.view_lineage_id)
        if existing is not None:
            if existing != record:
                raise ValueError(f"{record.account_id} already has a different proposal for this view")
            return
        self._db.execute("INSERT INTO proposal_records VALUES (:id, :account, :view, :at, :outcome, :content)",
                         {"id": record.record_id, "account": record.account_id, "view": record.view_lineage_id,
                          "at": record.at, "outcome": record.outcome.value, "content": zlib.compress(blob.encode(), 6)})

    def for_view(self, account_id: str, view_lineage_id: str) -> ProposalRecord | None:
        row = self._db.fetchone("SELECT content FROM proposal_records WHERE account_id = :a AND view_lineage_id = :v",
                                {"a": account_id, "v": view_lineage_id})
        return None if row is None else decode(json.loads(zlib.decompress(bytes(row[0])).decode()))

    def for_account(self, account_id: str) -> list[ProposalRecord]:
        rows = self._db.fetchall("SELECT content FROM proposal_records WHERE account_id = :a ORDER BY at, record_id",
                                 {"a": account_id})
        return [decode(json.loads(zlib.decompress(bytes(r[0])).decode())) for r in rows]


@dataclass(frozen=True)
class ControlStores:
    """One Database port shared by every store, so they join one managed transaction."""

    db: object
    audit: AuditStore
    accounts: AccountRegistry
    limits: LimitStore
    snapshots: PortfolioSnapshotStore
    intents: IntentStore
    lineage: LineageStore
    intent_lineage: IntentLineageStore
    proposals: ProposalStore
    instruments: object
    clock: object  # the live command clock

    @classmethod
    def open(cls, db, clock, *, instruments) -> "ControlStores":
        audit = AuditStore(db)
        accounts = AccountRegistry(db, audit, clock)
        return cls(db, audit, accounts, LimitStore(db, audit, accounts, clock),
                   PortfolioSnapshotStore(db, audit, accounts, clock), IntentStore(db, audit, accounts, clock),
                   LineageStore(db), IntentLineageStore(db), ProposalStore(db), instruments, clock)


def _business_time(kind: AccountKind, at: datetime | None, clock) -> datetime:
    """The time an account's command acts at: an explicit replay time for RESEARCH, the live clock for PAPER."""
    if kind is AccountKind.PAPER:
        if at is not None:
            raise ValueError("a PAPER account acts only at the live clock's time; a supplied time is refused "
                             "(Codex re-review R3)")
        return check_utc(clock.now(), "now")
    if at is None:
        raise ValueError("a RESEARCH account acts at an explicit replay time; none was supplied (R3)")
    return check_utc(at, "at")


def expire_due(account_id: str, *, at: datetime | None, stores: ControlStores) -> list[StoredIntent]:
    """Expire one account's waiting intents past their deadline and approved ones past their expiry.

    RESEARCH accounts expire at the replay time given; PAPER accounts take no time (`at=None`) and expire at the
    live clock's time."""
    at = _business_time(stores.accounts.account(account_id).kind, at, stores.clock)
    return _expire(account_id, at, stores)


def _expire(account_id: str, at: datetime, stores: ControlStores) -> list[StoredIntent]:
    expired = []
    with stores.db.transaction():
        stores.db.lock(f"account-control|{account_id}")
        for due in stores.intents.due_for_expiry(account_id, at):
            deadline = due.approval_deadline if due.state is IntentState.AWAITING_APPROVAL else due.approval_expires_at
            expired.append(stores.intents.transition(
                due.intent.intent_id, due.intent.version, IntentState.EXPIRED,
                expected_aggregate_version=due.aggregate_version, at=at, by=CORE,
                reason=f"{due.state} past {deadline.isoformat()}"))
    return expired


def expire_paper_due(*, clock, stores: ControlStores) -> list[StoredIntent]:
    """Expire every PAPER account's due intents at the live clock's time; never touches RESEARCH accounts."""
    now = check_utc(clock.now(), "now")
    expired = []
    for account in stores.accounts.accounts():
        if account.kind is AccountKind.PAPER:
            expired.extend(_expire(account.account_id, now, stores))
    return expired


@dataclass
class _Run:
    """The facts of one proposal, gathered as they're established."""

    account_id: str
    view: MarketView
    at: datetime
    view_lineage_id: str
    calendar_version: str
    code_version: str
    correlation_id: str


def _session_bounds(calendar, session):
    s = calendar.session(session)
    return s.open, s.close


def propose(account_id: str, view: MarketView, *, at: datetime | None, stores: ControlStores, knowledge, calendar,
            coverage, calendar_version: str, code_version: str, correlation_id: str) -> ProposalRecord:
    """Propose one view for one account. RESEARCH: `at` is the replay time. PAPER: `at=None`, the live time."""
    view_lineage_id = view.evidence_refs[0] if view.evidence_refs else ""
    try:
        account = stores.accounts.account(account_id)
    except KeyError:
        # A returned diagnostic only: nothing is stored or expired for an unknown account (acceptance note 3).
        when = check_utc(at if at is not None else stores.clock.now(), "at")
        return ProposalRecord(account_id, view_lineage_id, when, ProposalOutcome.PREREQUISITE_MISSING,
                              f"unknown account {account_id}", ("account",), None, ())
    at = _business_time(account.kind, at, stores.clock)
    if not view_lineage_id:
        # Records are keyed by (account, view lineage id); a view naming no lineage can't be keyed, so, like an
        # unknown account, it gets a returned diagnostic and nothing is stored or expired.
        return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.PREREQUISITE_MISSING,
                              "view lineage: the view names no lineage record", ("view lineage",), None, ())
    # The lineage record is read once, here, and this same object is both checked against the view and used by
    # the proposal. A record missing now stays missing for this proposal even if it is published meanwhile: no
    # later read can bring in a record the view was never compared with (Codex M3 re-review R2).
    try:
        view_lineage = stores.lineage.get(view_lineage_id)
    except KeyError:
        view_lineage = None
    mismatch = _view_mismatch(view, view_lineage_id, view_lineage)
    if mismatch:
        # The view isn't the decision its lineage recorded, so nothing it would produce could be reconstructed
        # (Law 18). Like an unknown account, it gets a returned diagnostic; nothing is stored or expired, and the
        # genuine view can still be proposed (Codex M3 review B2).
        return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.PREREQUISITE_MISSING,
                              f"view lineage: {mismatch}", ("view lineage",), None, ())
    with stores.db.transaction():
        stores.db.lock(f"account-control|{account_id}")
        existing = stores.proposals.for_view(account_id, view_lineage_id)
        if existing is not None:
            return existing  # idempotent: the same account and view were already proposed
        _expire(account_id, at, stores)
        record = _propose(account_id, view, at, stores, knowledge, calendar, coverage, calendar_version, code_version,
                          correlation_id, view_lineage_id, view_lineage)
        stores.proposals.append(record)
    return record


def _view_mismatch(view: MarketView, view_lineage_id: str, stored) -> str:
    """Why `view` isn't the decision in `stored` (the LineageRecord read for this proposal), or "" if it is. M2's
    pipeline hands out the stored decision with exactly its lineage id as evidence (decision/pipeline.py); no other
    difference is allowed, and nothing is replaced or repaired here. No record (`stored` is None) is not a match:
    the proposal records the missing view lineage as a prerequisite."""
    if stored is None:
        return ""
    expected = dataclasses.replace(stored.decision, evidence_refs=(view_lineage_id,))
    if view == expected:
        return ""
    differ = [f.name for f in dataclasses.fields(view) if getattr(view, f.name) != getattr(expected, f.name)]
    return f"the view differs from the decision stored in {view_lineage_id}: {', '.join(differ) or 'its type'}"


def _missing(account_id, view_lineage_id, at, missing: list[tuple[str, str]]) -> ProposalRecord:
    return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.PREREQUISITE_MISSING,
                          "; ".join(f"{name}: {why}" for name, why in missing), tuple(n for n, _ in missing), None, ())


def _propose(account_id, view, at, stores: ControlStores, knowledge, calendar, coverage, calendar_version,
             code_version, correlation_id, view_lineage_id, view_lineage) -> ProposalRecord:
    missing: list[tuple[str, str]] = []
    try:
        autonomy = stores.accounts.autonomy_at(account_id, at)
    except LookupError as exc:
        autonomy, _ = None, missing.append(("autonomy", str(exc)))
    try:
        limits = stores.limits.risk_at(account_id, at)
    except NoLimits as exc:
        limits, _ = None, missing.append(("limits", str(exc)))
    try:
        rules = stores.limits.policy_at(account_id, at)
    except NoLimits as exc:
        rules, _ = None, missing.append(("rules", str(exc)))
    if view_lineage is None:  # as read, and checked, by propose(); never read again here
        missing.append(("view lineage", f"{view_lineage_id or 'none'} is not stored"))
    instrument = reference = snapshot = starting = None
    try:
        instrument = stores.instruments.get(view.instrument_id)
    except KeyError as exc:
        missing.append(("instrument", str(exc)))
    if view_lineage is not None and instrument is not None:
        found = decision_reference(view_lineage, knowledge=knowledge, instruments=stores.instruments, at=at)
        if isinstance(found, Unavailable):
            missing.append(("reference", found.reason))
        else:
            reference = found
    try:
        starting = stores.snapshots.starting_state(account_id)
    except KeyError as exc:
        missing.append(("starting state", str(exc)))
    if starting is not None and view_lineage is not None:
        clear = stores.limits.last_clear_at(account_id, at)  # the drawdown epoch, whatever happened since (D3)
        baseline = clear.at if clear is not None and clear.at >= starting.effective_at else starting.effective_at
        peak = stores.snapshots.peak(account_id, since=baseline, at=at) if at >= baseline else None
        history = [] if peak is None else [peak]  # the highest stored equity since the baseline is all it needs
        built = build_snapshot(account_id, at=at, starting=starting, knowledge=knowledge, calendar=calendar,
                               coverage=coverage, last_clear=clear, history=history,
                               source=view_lineage.snapshot.source)
        if isinstance(built, Unavailable):
            missing.append(("snapshot", built.reason))
        else:
            snapshot = built
            stores.snapshots.append(snapshot)
    if reference is not None and snapshot is not None:
        held = next((h for h in snapshot.positions if h.instrument_id == reference.instrument_id), None)
        if held is not None and held.price_ref != reference.bar:
            # A correction arrived after the view: the holding is valued from the newer revision while the view
            # decided on the older one. Sizing from both would mix revisions, so this is a missing prerequisite,
            # recorded like any other (M3-08 rule 4; Codex M3 review B7). Other sizing errors still raise.
            missing.append(("reference", f"the snapshot values {reference.instrument_id} from revision "
                                         f"{held.price_ref.revision} of {held.price_ref.start_time.date()}, but the "
                                         f"view decided on revision {reference.bar.revision} of "
                                         f"{reference.bar.start_time.date()}; size from one revision only"))
    if missing:
        return _missing(account_id, view_lineage_id, at, missing)

    sizing = size(view, view_lineage=view_lineage, reference=reference, snapshot=snapshot, limits=limits, rules=rules,
                  calendar=calendar, at=at, sizer_version=SIZER_VERSION)
    if sizing.intent is None:
        return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.NO_INTENT, sizing.reason, (), None, ())

    intents = stores.intents
    stored = intents.create(sizing.intent, by=CORE, correlation_id=correlation_id)
    intent = stored.intent
    versions = [intent.version]
    account = stores.accounts.account(account_id)
    adv = adv_refs = admitted = already = None
    adv_missing = ""
    while True:
        policy = check_policy(intent, account=account, autonomy=autonomy, rules=rules, instrument=instrument,
                              snapshot=snapshot, view_lineage=view_lineage, calendar=calendar, at=at)

        def lineage(final_state, risk_decision, *, read=None, used=(), _intent=intent, _policy=policy):
            """This version's record: only what ran for it (a policy rejection read no count and no volumes)."""
            record = IntentLineageRecord(
                _intent.intent_id, _intent.version, final_state, view_lineage_id, snapshot.snapshot_id,
                reference.bar, used, autonomy, rules.version, limits.version, SIZER_VERSION, _policy,
                risk_decision, read, calendar_version, code_version)
            stores.intent_lineage.append(record)
            return record.lineage_id

        if not policy.passed:
            not_run = NotRun("risk", POLICY_NOT_RUN_REASON)
            intents.transition(intent.intent_id, intent.version, IntentState.POLICY_REJECTED,
                               expected_aggregate_version=stored.aggregate_version, at=at, by=CORE,
                               reason=_failures(policy.checks), correlation_id=correlation_id,
                               policy_decision=policy, risk_decision=not_run,
                               lineage_id=lineage(IntentState.POLICY_REJECTED, not_run))
            return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.POLICY_REJECTED,
                                  _failures(policy.checks), (), intent.intent_id, tuple(versions))

        if intent.side is Side.BUY:
            stores.db.lock(f"buy-admission|{account_id}|{intent.target_session.isoformat()}")
            admitted = intents.admitted_buys(account_id, intent.target_session, excluding=intent.intent_id)
            already = intents.was_admitted(intent.intent_id)
        else:
            admitted, already = None, False  # no admission count for a SELL
        if adv is None and not adv_missing:
            adv, adv_refs, adv_missing = average_daily_value(
                knowledge, calendar, reference.source, reference.instrument_id, reference.session,
                limits.adv_sessions, at=at)
        risk, halt_request = check_risk(intent, RiskInputs(
            snapshot=snapshot, limits=limits, halt=stores.limits.halt_at(account_id, at), reference=reference,
            adv=adv, adv_refs=adv_refs or (), admitted_buys_excluding_self=admitted or 0,
            already_admitted=bool(already), view=view, view_lineage=view_lineage, adv_missing=adv_missing), at=at)
        if halt_request is not None:
            stores.limits.set_halt(account_id, at=at, limits_version=halt_request.limits_version,
                                   reason=halt_request.reason)

        def checked(final_state, _risk=risk, _read=admitted, _used=adv_refs or (), _lineage=lineage):
            return _lineage(final_state, _risk, read=_read, used=_used)
        if risk.outcome is RiskOutcome.REJECT:
            intents.transition(intent.intent_id, intent.version, IntentState.RISK_REJECTED,
                               expected_aggregate_version=stored.aggregate_version, at=at, by=CORE,
                               reason=_failures(risk.checks), correlation_id=correlation_id, policy_decision=policy,
                               risk_decision=risk, lineage_id=checked(IntentState.RISK_REJECTED))
            return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.RISK_REJECTED,
                                  _failures(risk.checks), (), intent.intent_id, tuple(versions))
        if risk.outcome is RiskOutcome.REDUCE:
            smaller = reduced_version(intent, risk, at=at)
            stored = intents.supersede(intent.intent_id, intent.version, smaller,
                                       expected_aggregate_version=stored.aggregate_version, at=at, by=CORE,
                                       reason=_failures(risk.checks), correlation_id=correlation_id,
                                       policy_decision=policy, risk_decision=risk,
                                       lineage_id=checked(IntentState.SUPERSEDED))
            intent = stored.intent
            versions.append(intent.version)
            continue  # the new version runs policy and risk again (M3-11 rule 3)
        return _route(account_id, view, at, stores, calendar, autonomy, intent, stored, policy, risk, checked,
                      versions, view_lineage_id, correlation_id)


def _failures(checks) -> str:
    failed = [f"{c.name}: {c.reason}" for c in checks if not c.passed]
    return "; ".join(failed) or "all checks passed"


def _route(account_id, view, at, stores, calendar, autonomy, intent, stored, policy, risk, lineage, versions,
           view_lineage_id, correlation_id) -> ProposalRecord:
    intents = stores.intents
    opening, closing = _session_bounds(calendar, intent.target_session)
    if autonomy.level == 1:
        waiting = intents.transition(intent.intent_id, intent.version, IntentState.AWAITING_APPROVAL,
                                     expected_aggregate_version=stored.aggregate_version, at=at, by=CORE,
                                     reason="Level 1: awaiting a named approver (D11 deadline: the target open)",
                                     correlation_id=correlation_id, policy_decision=policy, risk_decision=risk,
                                     approval_deadline=opening,
                                     lineage_id=lineage(IntentState.AWAITING_APPROVAL))
        if at >= opening:
            intents.transition(intent.intent_id, intent.version, IntentState.EXPIRED,
                               expected_aggregate_version=waiting.aggregate_version, at=at, by=CORE,
                               reason=f"proposed at or after the approval deadline {opening.isoformat()}",
                               correlation_id=correlation_id)
            return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.EXPIRED_ON_ARRIVAL,
                                  f"Level 1 deadline {opening.isoformat()} had passed", (), intent.intent_id,
                                  tuple(versions))
        return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.AWAITING_APPROVAL,
                              f"awaiting approval until {opening.isoformat()}", (), intent.intent_id, tuple(versions))
    expires = min(closing, view.valid_until)
    approved = intents.transition(intent.intent_id, intent.version, IntentState.APPROVED,
                                  expected_aggregate_version=stored.aggregate_version, at=at, by=CORE,
                                  reason="Level 2 rule: policy and risk passed", correlation_id=correlation_id,
                                  policy_decision=policy, risk_decision=risk, approved_by="core-engine (Level 2 rule)",
                                  approved_at=at, approval_expires_at=expires,
                                  approval_recorded_at=check_utc(stores.clock.now(), "now"),
                                  lineage_id=lineage(IntentState.APPROVED))
    if at >= expires:
        intents.transition(intent.intent_id, intent.version, IntentState.EXPIRED,
                           expected_aggregate_version=approved.aggregate_version, at=at, by=CORE,
                           reason=f"approved at or after its expiry {expires.isoformat()}",
                           correlation_id=correlation_id)
        return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.EXPIRED_ON_ARRIVAL,
                              f"Level 2 expiry {expires.isoformat()} had passed", (), intent.intent_id,
                              tuple(versions))
    return ProposalRecord(account_id, view_lineage_id, at, ProposalOutcome.APPROVED,
                          f"approved by the Level 2 rule until {expires.isoformat()}", (), intent.intent_id,
                          tuple(versions))


def propose_over_replay(account_id: str, views: Sequence[MarketView], *, events, stores: ControlStores,
                        knowledge_reader, calendar, coverage, calendar_version: str, code_version: str,
                        proposal_delay: timedelta = timedelta(0),
                        make_knowledge: Callable | None = None) -> list[ProposalRecord]:
    """Propose each view in time order against one RESEARCH account, as the replay delivers its knowledge.

    `events` is the ReplayFeed the views were made from; `knowledge_reader` is an empty M2 ReplayKnowledgeReader
    that accepts them. A view is proposed at `generated_at + proposal_delay` (feed latency is already in
    `generated_at`), once every event delivered by then is accepted. With no extra delay, equal-time events after
    the view's own decision bar are excluded (`through_sequence`), exactly as the view saw them.
    """
    from investment_engine.portfolio.reference import ReplayKnowledge

    if stores.accounts.account(account_id).kind is not AccountKind.RESEARCH:
        raise ValueError("only RESEARCH accounts are replayed; PAPER accounts act at live time")
    if proposal_delay < timedelta(0):
        raise ValueError("proposal_delay can't be negative")
    pending = sorted(views, key=lambda v: (v.generated_at, v.evidence_refs))
    records, sequences = [], {}

    def flush(before: datetime | None):
        while pending and (before is None or pending[0].generated_at + proposal_delay < before):
            v = pending.pop(0)
            at = v.generated_at + proposal_delay
            through = None
            if proposal_delay == timedelta(0):
                bar = _decision_bar(stores, v)
                through = sequences.get(bar) if bar is not None else None
            # Every event delivered by `at` has been accepted, so the knowledge is complete through `at`.
            knowledge = (make_knowledge or ReplayKnowledge)(knowledge_reader, through_sequence=through,
                                                            calendar=calendar, complete_through=at)
            records.append(propose(account_id, v, at=at, stores=stores, knowledge=knowledge, calendar=calendar,
                                   coverage=coverage, calendar_version=calendar_version, code_version=code_version,
                                   correlation_id=f"replay:{account_id}:{at.isoformat()}"))

    for event in events:
        flush(event.received_at)
        knowledge_reader.accept(event)
        p = event.payload
        sequences[(p.source, p.instrument_id, getattr(p, "start_time", None), p.revision)] = event.sequence
    flush(None)
    return records


def _decision_bar(stores: ControlStores, view: MarketView):
    try:
        lineage = stores.lineage.get(view.evidence_refs[0])
    except (KeyError, IndexError):
        return None
    snap = lineage.snapshot
    zone = ZoneInfo(stores.instruments.get(view.instrument_id).timezone)
    for ref in lineage.bar_refs:
        if (ref.source, ref.instrument_id) == (snap.source, snap.instrument_id) \
                and ref.start_time.astimezone(zone).date() == snap.session_date:
            return (ref.source, ref.instrument_id, ref.start_time, ref.revision)
    return None
