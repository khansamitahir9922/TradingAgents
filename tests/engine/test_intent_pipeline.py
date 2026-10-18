"""The intent pipeline: outcomes, atomicity, idempotency and expiry (docs/tasks/M3-12.md).

Helpers here are shared by test_buy_admission.py and test_intent_replay.py.
"""

import itertools
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

import pytest

from investment_engine.audit.events import Actor, ActorKind
from investment_engine.clock import ReplayClock
from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import Timeframe
from investment_engine.market.data_health import Applicability, DataHealth
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.oms.intents import IntentState
from investment_engine.oms.pipeline import (
    ControlStores,
    ProposalOutcome,
    expire_due,
    expire_paper_due,
    propose,
)
from investment_engine.policy.accounts import AccountKind
from investment_engine.portfolio.reference import StoreKnowledge
from investment_engine.quant.adjusted import BarRef
from investment_engine.risk.limits import load_limits_file
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from investment_engine.storage.sqlite import SqliteInstrumentRepository
from tests.engine.test_lineage import record as lineage_record
from tests.engine.test_portfolio_snapshot import coverage as action_coverage
from tests.engine.test_raw_reference import observation
from tests.engine.test_sqlite_store import instrument

pytestmark = pytest.mark.postgres
CAL = load_us_equities_calendar()
NVDA = "EQ_US_NVDA"
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)  # the real command time
OWNER = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "LOQ")
SESSIONS = [s.date for s in CAL.sessions_between(date(2024, 1, 2), date(2024, 9, 30))]
START = datetime(2019, 1, 2, 21, tzinfo=UTC)
PROPOSED = files("investment_engine.risk").joinpath("proposed_limits.json").read_text(encoding="utf-8")
TABLES = ("intents", "intent_versions", "intent_transitions", "intent_lineage_records", "proposal_records",
          "portfolio_snapshots", "audit_events", "halts")
LIVE = object()  # Env.propose: act at the live clock's time (PAPER), supplying no time


def covered():
    """Established action coverage for NVDA over the whole test period: holdings can be carried."""
    return action_coverage(first=date(2019, 1, 1), last=date(2024, 12, 31))


def t_of(day):
    return CAL.session(day).close + timedelta(minutes=5)


def write_bars(root, days, *, volume="1000000", close="120.0000"):
    writer = MarketDataWriter(root)
    obs = [replace(observation(d, close=close), volume=Decimal(volume)) for d in days]
    writer.write_candles(obs, import_id="bars")
    return MarketDataReader(root)


def bar_ref(reader, day, revision=1):
    s = CAL.session(day)
    (c,) = [c for c in reader.candle_revision_history("yfinance", NVDA, Timeframe.D1, s.open,
                                                       s.open + timedelta(microseconds=1)) if c.revision == revision]
    return BarRef(c.source, c.instrument_id, c.timeframe, c.start_time, c.revision, c.import_id, c.available_from,
                  c.availability_basis)


def view_for(stores, reader, day, direction="BULLISH", *, valid_days=1, tag="", bar=None, generated_at=None,
             valid_until=None):
    """A stored LineageRecord and its MarketView for `day`'s close, built on M2's own lineage fixture."""
    t = generated_at or t_of(day)
    health = DataHealth(NVDA, t, Applicability(True, ""), (), True)
    ref = bar or bar_ref(reader, day)
    base = lineage_record()
    snap = replace(base.snapshot, as_of=t, session_date=day, input_refs=(ref,), data_health=health)
    until, valid_until = valid_until, CAL.session(CAL.next_session(day).date).close
    for _ in range(valid_days - 1):
        valid_until = CAL.session(CAL.next_session(valid_until.date()).date).close
    valid_until = until or valid_until
    strength = 0.5 if direction in ("BULLISH", "BEARISH") else 0.0
    reason = "required data not OK" if direction == "ABSTAIN" else ""
    decision = MarketView(NVDA, ViewDirection(direction), strength, None, "5 sessions", t, valid_until, None, health,
                          (), "0.1.0", reason, ())
    record = replace(base, generated_at=t, bar_refs=(ref,), data_health=health, snapshot=snap, decision=decision,
                     code_version=f"test-{tag}")
    stores.lineage.append(record)
    return replace(decision, evidence_refs=(record.lineage_id,))


class Env:
    def __init__(self, dsn, root, *, now=NOW, reader=None):
        self.dsn, self.root, self.opened = dsn, root, []
        self.clock = ReplayClock(now)
        self.stores = self.connect()
        apply_pg_schema(self.stores.db.connection)
        self.stores.instruments.add(instrument(active_from=date(2019, 1, 1)))
        self.stores.accounts.bootstrap_admin("owner", os_user="LOQ")
        self.reader = reader or write_bars(root, SESSIONS)
        self.knowledge = StoreKnowledge(self.reader, CAL)

    def connect(self, clock=None):
        conn = open_operational_pg(self.dsn)
        self.opened.append(conn)
        db = PostgresDatabase(conn)
        return ControlStores.open(db, clock or self.clock, instruments=SqliteInstrumentRepository(db))

    def account(self, account_id, *, level=1, kind=AccountKind.RESEARCH, limits=True, start=True, effective=START):
        s = self.stores
        when = effective if kind is AccountKind.RESEARCH else None
        s.accounts.create_account(account_id, kind, "USD", by=OWNER, reason="test", effective_at=when)
        if level:
            s.accounts.set_autonomy(account_id, level, by=OWNER, reason="test", effective_at=when)
        if limits:
            risk, policy = load_limits_file(PROPOSED)
            s.limits.publish_risk(account_id, risk, by=OWNER, reason="D1-D9", effective_at=when)
            s.limits.publish_policy(account_id, policy, by=OWNER, reason="D7", effective_at=when)
        if start:
            s.snapshots.declare_start(account_id, by=OWNER, reason="D14", effective_at=when)

    def propose(self, account_id, view, *, at=None, stores=None, knowledge=None, coverage=None, declared_only=False):
        when = None if at is LIVE else (at or view.generated_at)
        return propose(account_id, view, at=when, stores=stores or self.stores,
                       knowledge=knowledge or self.knowledge, calendar=CAL, coverage=coverage,
                       calendar_version="cal-1", code_version="test", correlation_id="test",
                       declared_only=declared_only)

    def count(self, table, where="", params=None):
        return self.stores.db.fetchone(f"SELECT COUNT(*) FROM {table} {where}", params or {})[0]

    def counts(self):
        return {t: self.count(t) for t in TABLES}

    def close(self):
        for c in self.opened:
            c.close()


@pytest.fixture
def env(pg_database, tmp_path):
    e = Env(pg_database, tmp_path / "market")
    yield e
    e.close()


DAY = SESSIONS[60]
TARGET = CAL.next_session(DAY).date


# ---------------------------------------------------------------- the outcome matrix (B3)


@pytest.mark.unit
def test_an_unknown_account_gets_a_returned_diagnostic_and_nothing_changes(env):
    env.account("R1")
    waiting = env.propose("R1", view_for(env.stores, env.reader, DAY))
    view = view_for(env.stores, env.reader, SESSIONS[80], tag="late")
    before = env.counts()
    record = env.propose("NOPE", view)  # long after R1's deadline: it must expire nothing either
    assert record.outcome is ProposalOutcome.PREREQUISITE_MISSING and record.missing == ("account",)
    assert env.counts() == before and env.stores.proposals.for_view("NOPE", record.view_lineage_id) is None
    assert env.stores.intents.get(waiting.intent_id).state is IntentState.AWAITING_APPROVAL


@pytest.mark.unit
def test_views_without_lineage_get_a_returned_diagnostic_and_never_share_a_record(env):
    env.account("R1")
    waiting = env.propose("R1", view_for(env.stores, env.reader, DAY))
    before = env.counts()
    late = t_of(SESSIONS[80])  # long after R1's deadline: nothing may expire either
    bare = [replace(view_for(env.stores, env.reader, d, tag="b"), evidence_refs=()) for d in SESSIONS[70:72]]
    records = [env.propose("R1", v, at=late) for v in bare]
    assert [r.missing for r in records] == [("view lineage",), ("view lineage",)]
    assert env.counts() == before and env.stores.proposals.for_view("R1", "") is None
    assert env.stores.intents.get(waiting.intent_id).state is IntentState.AWAITING_APPROVAL
    unstored = replace(view_for(env.stores, env.reader, SESSIONS[72], tag="u"), evidence_refs=("lin-unknown",))
    named = env.propose("R1", unstored)  # a named but unknown lineage is an ordinary stored record
    assert named.missing == ("view lineage",) and env.stores.proposals.for_view("R1", "lin-unknown") == named


@pytest.mark.unit
def test_a_view_must_be_exactly_the_decision_stored_in_its_lineage(env):
    """Codex B2: a stored NEUTRAL decision, re-presented as BULLISH under the same lineage id, made a BUY."""
    env.account("R1")
    waiting = env.propose("R1", view_for(env.stores, env.reader, DAY))
    neutral = view_for(env.stores, env.reader, SESSIONS[70], "NEUTRAL", tag="n")
    other = view_for(env.stores, env.reader, SESSIONS[71], tag="o")
    t = neutral.generated_at
    forged = {
        "direction": replace(neutral, direction=ViewDirection.BULLISH, strength=0.5),
        "data_health": replace(neutral, data_health=DataHealth(NVDA, t, Applicability(True, ""), (), False)),
        "valid_until": replace(neutral, valid_until=neutral.valid_until + timedelta(days=1)),
        "generated_at": replace(neutral, generated_at=t - timedelta(minutes=1)),
        "instrument_id": replace(neutral, instrument_id="EQ_US_AMD"),
        "evidence_refs": replace(neutral, evidence_refs=(*neutral.evidence_refs, "lin-extra")),
    }
    before = env.counts()
    late = t_of(SESSIONS[80])  # long after R1's deadline: a refused view must expire nothing
    for field, view in forged.items():
        record = env.propose("R1", view, at=late)
        assert record.outcome is ProposalOutcome.PREREQUISITE_MISSING and record.missing == ("view lineage",), field
        assert f"differs from the decision stored in {neutral.evidence_refs[0]}: {field}" in record.reason, field
    stronger = env.propose("R1", replace(other, strength=0.9), at=late)  # a BULLISH view, re-presented stronger
    assert stronger.missing == ("view lineage",) and stronger.reason.endswith(": strength")
    swapped = env.propose("R1", replace(other, evidence_refs=neutral.evidence_refs), at=late)  # another decision
    assert swapped.missing == ("view lineage",) and "direction" in swapped.reason
    assert env.counts() == before and env.stores.proposals.for_view("R1", neutral.evidence_refs[0]) is None
    assert env.stores.intents.get(waiting.intent_id).state is IntentState.AWAITING_APPROVAL
    genuine = env.propose("R1", neutral)  # the real view is unaffected by the refused ones
    assert genuine.outcome is ProposalOutcome.NO_INTENT and "NEUTRAL" in genuine.reason


@pytest.mark.unit
def test_a_lineage_published_between_check_and_use_never_binds_an_unchecked_view(env, monkeypatch):
    """Codex re-review R2: the check saw no lineage; a producer then committed the genuine NEUTRAL record on another
    connection, and a later read let a BULLISH forgery become a BUY against it. The proposal now uses the one record
    it read and checked."""
    env.account("R1")
    pending = []
    with monkeypatch.context() as patch:  # a producer that has made its view but not yet committed its lineage
        patch.setattr(env.stores.lineage, "append", pending.append)
        neutral = view_for(env.stores, env.reader, SESSIONS[40], "NEUTRAL")
    (record,) = pending
    producer = env.connect()
    real, missed = env.stores.lineage.get, []

    def get(lineage_id):
        try:
            return real(lineage_id)
        except KeyError:
            if not missed:  # the first read really misses; the producer commits right after it
                missed.append(lineage_id)
                producer.lineage.append(record)
            raise

    monkeypatch.setattr(env.stores.lineage, "get", get)
    forged = replace(neutral, direction=ViewDirection.BULLISH, strength=0.5)
    outcome = env.propose("R1", forged)
    assert missed == [record.lineage_id] and real(record.lineage_id) == record  # the record exists now
    assert outcome.outcome is ProposalOutcome.PREREQUISITE_MISSING and outcome.missing == ("view lineage",)
    assert env.count("intents") == 0 and env.count("intent_lineage_records") == 0
    monkeypatch.undo()
    again = env.propose("R1", forged)  # now refused against the published record itself
    assert again.missing == ("view lineage",) and "differs from the decision stored" in again.reason
    assert env.count("intents") == 0


@pytest.mark.unit
def test_missing_prerequisites_are_named_and_nothing_is_invented(env):
    env.account("NL", limits=False)
    env.account("NS", start=False)
    env.account("EARLY", effective=datetime(2025, 1, 2, tzinfo=UTC))  # its settings start after the view
    env.account("NR")
    view = view_for(env.stores, env.reader, DAY)
    expected = {"NL": ("limits", "rules"), "NS": ("starting state",)}
    for account_id, missing in expected.items():
        record = env.propose(account_id, view)
        assert record.outcome is ProposalOutcome.PREREQUISITE_MISSING and record.missing == missing, account_id
    early = env.propose("EARLY", view)  # nothing is effective yet: not even the account's Level 0 setting
    assert early.missing == ("autonomy", "limits", "rules", "snapshot")
    unknown_revision = view_for(env.stores, env.reader, SESSIONS[61], tag="rev",
                                bar=replace(bar_ref(env.reader, SESSIONS[61]), revision=7))
    assert env.propose("NR", unknown_revision).missing == ("reference",)
    assert env.count("intents") == 0 and env.count("intent_lineage_records") == 0
    assert env.count("proposal_records") == 4  # existing accounts get their record stored
    # Snapshots exist only where one was built: NL's (limits aren't needed for it) and NR's; none for NS or EARLY.
    assert env.count("portfolio_snapshots") == 2


@pytest.mark.unit
def test_a_missing_session_is_named_and_no_older_bar_is_used(pg_database, tmp_path):
    full = write_bars(tmp_path / "full", SESSIONS)
    gap = write_bars(tmp_path / "gap", [d for d in SESSIONS if d != DAY])  # DAY's bar never arrived
    env = Env(pg_database, tmp_path / "market", reader=gap)
    try:
        env.account("H1", start=False)
        env.stores.snapshots.declare_start("H1", by=OWNER, reason="D14", positions=((NVDA, Decimal("100")),),
                                           effective_at=START)
        record = env.propose("H1", view_for(env.stores, gap, DAY, bar=bar_ref(full, DAY)), coverage=covered())
        assert record.outcome is ProposalOutcome.PREREQUISITE_MISSING  # never valued at the older close
        assert record.missing == ("reference", "snapshot") and f"{DAY}" in record.reason
        assert "coverage" not in record.reason
        assert env.count("intents") == 0 and env.count("portfolio_snapshots") == 0
        env.account("R1")
        later = SESSIONS[70]  # DAY lies inside this view's 20-session volume window
        adv = env.propose("R1", view_for(env.stores, gap, later, tag="adv"))
        assert adv.outcome is ProposalOutcome.RISK_REJECTED and f"{DAY} not known" in adv.reason
    finally:
        env.close()


@pytest.mark.unit
@pytest.mark.parametrize("direction, reason", [("ABSTAIN", "ABSTAIN"), ("NEUTRAL", "NEUTRAL")])
def test_no_intent_views_store_a_record_and_a_snapshot_only(env, direction, reason):
    env.account("R1")
    record = env.propose("R1", view_for(env.stores, env.reader, DAY, direction))
    assert record.outcome is ProposalOutcome.NO_INTENT and reason in record.reason
    assert record.intent_id is None and record.versions == ()
    assert env.count("intents") == 0 and env.count("portfolio_snapshots") == 1
    assert env.count("intent_lineage_records") == 0 and env.count("proposal_records") == 1


def _assert_policy_rejected(env, record):
    assert record.outcome is ProposalOutcome.POLICY_REJECTED and record.versions == (1,)
    stored = env.stores.intents.get(record.intent_id)
    assert stored.state is IntentState.POLICY_REJECTED and not stored.policy_decision.passed
    assert stored.risk_decision.stage == "risk" and stored.risk_decision.reason == "policy rejected: risk not evaluated"
    (lineage,) = env.stores.intent_lineage.for_intent(record.intent_id)
    assert lineage.risk_decision == stored.risk_decision and stored.lineage_id == lineage.lineage_id
    assert lineage.policy_decision == stored.policy_decision and lineage.admitted_buys_read is None
    assert env.count("portfolio_snapshots") == 1 and env.count("halts") == 0


@pytest.mark.unit
def test_policy_rejection_records_policy_and_a_not_run_risk_decision(env):
    env.account("R0", level=0)  # the account's default Level 0 setting
    record = env.propose("R0", view_for(env.stores, env.reader, DAY))
    _assert_policy_rejected(env, record)
    assert "advisory" in record.reason


@pytest.mark.unit
def test_a_paper_account_proposes_only_at_live_time_and_is_rejected_for_promotion(pg_database, tmp_path):
    live = t_of(DAY)
    env = Env(pg_database, tmp_path / "market", now=live)  # the live clock reads the view's time here
    try:
        env.account("P1", kind=AccountKind.PAPER)
        view = view_for(env.stores, env.reader, DAY)
        before = env.counts()
        with pytest.raises(ValueError, match="live clock"):  # a supplied time is refused, even the live one
            env.propose("P1", view, at=live)
        with pytest.raises(ValueError, match="live clock"):
            expire_due("P1", at=live, stores=env.stores)
        assert env.counts() == before
        record = env.propose("P1", view, at=LIVE)
        _assert_policy_rejected(env, record)
        assert record.at == live and "PROMOTION NOT ASSESSED" in record.reason
    finally:
        env.close()


@pytest.mark.unit
def test_a_research_proposal_needs_an_explicit_replay_time(env):
    env.account("R1")
    with pytest.raises(ValueError, match="replay time"):
        env.propose("R1", view_for(env.stores, env.reader, DAY), at=LIVE)
    with pytest.raises(ValueError, match="replay time"):
        expire_due("R1", at=None, stores=env.stores)


@pytest.mark.unit
def test_risk_rejection_runs_both_checks(pg_database, tmp_path):
    env = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "short", SESSIONS[55:61]))
    try:
        env.account("R1")
        record = env.propose("R1", view_for(env.stores, env.reader, DAY))
        assert record.outcome is ProposalOutcome.RISK_REJECTED and "volume history unavailable" in record.reason
        stored = env.stores.intents.get(record.intent_id)
        assert stored.policy_decision.passed and stored.risk_decision.outcome.value == "REJECT"
        (lineage,) = env.stores.intent_lineage.for_intent(record.intent_id)
        assert lineage.risk_decision == stored.risk_decision and lineage.admitted_buys_read == 0
    finally:
        env.close()


@pytest.mark.unit
def test_a_reduction_supersedes_v1_and_v2_waits_for_approval(pg_database, tmp_path):
    env = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "thin", SESSIONS, volume="1000"))
    try:  # ADV 120,000: 1% = 1,200 = 10 shares
        env.account("R1")
        record = env.propose("R1", view_for(env.stores, env.reader, DAY))
        assert record.outcome is ProposalOutcome.AWAITING_APPROVAL and record.versions == (1, 2)
        v1, v2 = env.stores.intents.versions(record.intent_id)
        assert v1.state is IntentState.SUPERSEDED and v1.risk_decision.outcome.value == "REDUCE"
        assert v1.policy_decision.passed and v2.policy_decision.passed
        assert v2.state is IntentState.AWAITING_APPROVAL and v2.intent.quantity == Decimal(10)
        assert v2.risk_decision.outcome.value == "APPROVE"
        assert v2.approval_deadline == CAL.session(TARGET).open  # D11
        lineages = env.stores.intent_lineage.for_intent(record.intent_id)
        assert [(r.version, r.final_state) for r in lineages] == [(1, IntentState.SUPERSEDED),
                                                                  (2, IntentState.AWAITING_APPROVAL)]
        assert lineages[0].risk_decision == v1.risk_decision  # the pre-reduction decision stays in history
        assert env.stores.intents.get(record.intent_id).lineage_id == lineages[1].lineage_id
    finally:
        env.close()


@pytest.mark.unit
def test_level_2_is_approved_by_rule_until_the_target_close(env):
    env.account("R2", level=2)
    view = view_for(env.stores, env.reader, DAY)
    record = env.propose("R2", view)
    assert record.outcome is ProposalOutcome.APPROVED
    stored = env.stores.intents.get(record.intent_id)
    assert stored.state is IntentState.APPROVED and stored.approved_by == "core-engine (Level 2 rule)"
    assert stored.approved_at == view.generated_at and stored.approval_expires_at == CAL.session(TARGET).close
    assert stored.approval_recorded_at == NOW
    path = [t.to_state for t in env.stores.intents.history(record.intent_id)]
    assert path == [IntentState.PROPOSED, IntentState.APPROVED]


@pytest.mark.unit
def test_level_2_approval_never_outlives_the_view(env):
    env.account("R2", level=2)
    shorter = CAL.session(TARGET).open + timedelta(hours=1)
    record = env.propose("R2", view_for(env.stores, env.reader, DAY, valid_until=shorter))  # stored as such
    assert env.stores.intents.get(record.intent_id).approval_expires_at == shorter  # D10


@pytest.mark.unit
def test_late_proposals_expire_on_arrival_through_legal_edges(env):
    env.account("R1")
    env.account("R2", level=2)
    view = view_for(env.stores, env.reader, DAY)
    opening = CAL.session(TARGET).open
    one = env.propose("R1", view, at=opening)  # exactly at the deadline: too late (>=)
    assert one.outcome is ProposalOutcome.EXPIRED_ON_ARRIVAL
    path = [t.to_state for t in env.stores.intents.history(one.intent_id)]
    assert path == [IntentState.PROPOSED, IntentState.AWAITING_APPROVAL, IntentState.EXPIRED]
    just_before = env.propose("R1", view_for(env.stores, env.reader, DAY, tag="b"),
                              at=opening - timedelta(microseconds=1))
    assert just_before.outcome is ProposalOutcome.AWAITING_APPROVAL
    long_view = view_for(env.stores, env.reader, SESSIONS[61], valid_days=3, tag="long")
    closing = CAL.session(CAL.next_session(SESSIONS[61]).date).close
    two = env.propose("R2", long_view, at=closing)
    assert two.outcome is ProposalOutcome.EXPIRED_ON_ARRIVAL
    assert [t.to_state for t in env.stores.intents.history(two.intent_id)] == [
        IntentState.PROPOSED, IntentState.APPROVED, IntentState.EXPIRED]
    lineage = env.stores.intent_lineage.for_intent(two.intent_id)
    assert [r.final_state for r in lineage] == [IntentState.APPROVED]  # the routed state; expiry is in history


@pytest.mark.unit
def test_the_first_buy_of_the_cash_only_account_uses_the_raw_reference(env):
    env.account("R1")
    record = env.propose("R1", view_for(env.stores, env.reader, DAY))
    assert record.outcome is ProposalOutcome.AWAITING_APPROVAL
    stored = env.stores.intents.get(record.intent_id)
    assert stored.intent.reference_price == Decimal("120.0000") and stored.intent.quantity == Decimal(82)
    assert stored.intent.reference_bar == bar_ref(env.reader, DAY)
    (lineage,) = env.stores.intent_lineage.for_intent(record.intent_id)
    assert lineage.reference_bar == bar_ref(env.reader, DAY) and lineage.admitted_buys_read == 0
    assert len(lineage.adv_refs) == 20 and lineage.view_lineage_id == record.view_lineage_id
    view_lineage = env.stores.lineage.get(record.view_lineage_id)
    assert view_lineage.portfolio_snapshot is None and view_lineage.risk_versions is None  # rule 8


# ---------------------------------------------------------------- atomicity, idempotency, expiry


def failing_writes(monkeypatch):
    """Make the n-th INSERT, UPDATE or DELETE fail, whether sent through execute or, like the intent store's
    compare-and-set UPDATE ... RETURNING, through fetchone or fetchall; returns the control dict."""
    control = {"n": 0, "fail_at": 0, "returning": 0}

    def failing(real):
        def run(self, sql, params=None):
            if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                control["n"] += 1
                control["returning"] += real.__name__ != "execute"
                if control["n"] == control["fail_at"]:
                    raise RuntimeError(f"injected failure at write {control['n']}")
            return real(self, sql, params)
        return run

    for name in ("execute", "fetchone", "fetchall"):
        monkeypatch.setattr(PostgresDatabase, name, failing(getattr(PostgresDatabase, name)))
    return control


@pytest.mark.unit
def test_a_failure_at_each_write_in_turn_leaves_nothing_behind(env, monkeypatch):
    env.account("R1")
    view = view_for(env.stores, env.reader, DAY)
    before = env.counts()
    control = failing_writes(monkeypatch)
    failures = 0
    for k in itertools.count(1):
        control.update(n=0, fail_at=k)
        try:
            record = env.propose("R1", view)
        except RuntimeError as exc:
            assert f"write {k}" in str(exc)
            failures += 1
            assert env.counts() == before, k
            assert env.stores.intents.admitted_buys("R1", TARGET) == 0, k
            continue
        break
    assert record.outcome is ProposalOutcome.AWAITING_APPROVAL
    assert failures == control["n"] >= 8  # every write of the successful run was tried as the failing one
    assert control["returning"] >= 1  # compare-and-set writes (UPDATE ... RETURNING) were among them


@pytest.mark.unit
def test_proposing_the_same_view_again_returns_the_stored_record_and_changes_nothing(env):
    env.account("R1")
    view = view_for(env.stores, env.reader, DAY)
    first = env.propose("R1", view)
    counts = env.counts()
    assert env.propose("R1", view) == first
    assert env.propose("R1", view, at=t_of(DAY) + timedelta(minutes=1)) == first  # the record answers, not `at`
    assert env.counts() == counts
    assert env.stores.proposals.for_view("R1", first.view_lineage_id) == first


@pytest.mark.unit
def test_expiry_moves_waiting_and_approved_intents_with_audit_events(env):
    env.account("R1")
    env.account("R2", level=2)
    waiting = env.propose("R1", view_for(env.stores, env.reader, DAY))
    approved = env.propose("R2", view_for(env.stores, env.reader, DAY, tag="2"))
    opening, closing = CAL.session(TARGET).open, CAL.session(TARGET).close
    assert expire_due("R1", at=opening - timedelta(microseconds=1), stores=env.stores) == []
    (moved,) = expire_due("R1", at=opening, stores=env.stores)
    assert moved.state is IntentState.EXPIRED and moved.intent.intent_id == waiting.intent_id
    assert expire_due("R2", at=opening, stores=env.stores) == []  # approved until the close
    (moved,) = expire_due("R2", at=closing, stores=env.stores)
    assert moved.intent.intent_id == approved.intent_id
    for intent_id, at in ((waiting.intent_id, opening), (approved.intent_id, closing)):
        (expiry,) = [e for e in env.stores.audit.for_target("intent", intent_id) if e.action == "intent.expired"]
        assert expiry.business_at == at and expiry.at == NOW and expiry.actor.kind.value == "PROCESS"


@pytest.mark.unit
def test_expiry_stays_within_each_research_accounts_timeline(env):
    env.account("A")  # replay 2024-03 here, B replays 2024-08
    env.account("B")
    a = env.propose("A", view_for(env.stores, env.reader, SESSIONS[40], tag="a"))
    a_events = env.stores.audit.for_target("intent", a.intent_id)
    env.propose("B", view_for(env.stores, env.reader, SESSIONS[150], tag="b"))  # B is far later
    expire_due("B", at=t_of(SESSIONS[170]), stores=env.stores)
    assert env.stores.intents.get(a.intent_id).state is IntentState.AWAITING_APPROVAL
    assert env.stores.audit.for_target("intent", a.intent_id) == a_events
    b_states = {i.intent.intent_id: i.state for i in env.stores.intents.for_account("B")}
    expire_due("A", at=CAL.session(CAL.next_session(SESSIONS[40]).date).open, stores=env.stores)
    assert env.stores.intents.get(a.intent_id).state is IntentState.EXPIRED
    assert {i.intent.intent_id: i.state for i in env.stores.intents.for_account("B")} == b_states
    with pytest.raises(KeyError):
        expire_due("NOPE", at=NOW, stores=env.stores)


@pytest.mark.unit
def test_paper_expiry_runs_on_live_time_and_never_touches_research_accounts(pg_database, tmp_path):
    live = t_of(DAY)
    env = Env(pg_database, tmp_path / "market", now=live)
    try:
        env.account("R1", effective=START)
        research = env.propose("R1", view_for(env.stores, env.reader, DAY, tag="r"))
        env.clock.advance_to(CAL.session(TARGET).open + timedelta(hours=1))  # live time passes R1's deadline
        assert expire_paper_due(clock=env.clock, stores=env.stores) == []
        assert env.stores.intents.get(research.intent_id).state is IntentState.AWAITING_APPROVAL
    finally:
        env.close()


# ---------------------------------------------------------------- the boundary


@pytest.mark.unit
def test_the_pipeline_imports_no_broker_kill_switch_or_outbox_code():
    import ast

    import investment_engine.lineage.intent_lineage as lineage
    import investment_engine.oms.pipeline as pipeline

    names = set()
    for module in (pipeline, lineage):
        for node in ast.walk(ast.parse(Path(module.__file__).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
            elif isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
    assert names and not [n for n in names if any(w in n for w in ("broker", "kill", "outbox", "execution"))]


# ---------------------------------------------------------------- the drawdown epoch is the latest clear (B4)


@pytest.mark.unit
def test_the_drawdown_epoch_is_the_latest_clear_even_after_a_later_halt(pg_database, tmp_path):
    """Codex B4: 100,000; 85,000 (halt); cleared at 85,000; 60,000 (29.4% below the clear: halted again); then
    80,000. Every snapshot after the clear measures from 85,000, never from the old 100,000 peak."""
    a, b, c, d = SESSIONS[60:64]
    closes = dict.fromkeys(SESSIONS[:64], "100.0000")
    closes.update({b: "85.0000", c: "60.0000", d: "80.0000"})
    root = tmp_path / "fall"
    MarketDataWriter(root).write_candles([replace(observation(day, close=close), volume=Decimal("100000000"))
                                          for day, close in closes.items()], import_id="fall")
    env = Env(pg_database, tmp_path / "market", reader=MarketDataReader(root))
    try:
        env.account("H1", start=False)
        env.stores.snapshots.declare_start("H1", by=OWNER, reason="D14", cash=Decimal("0"),
                                           positions=((NVDA, Decimal("1000")),), effective_at=START)

        def snapshot_after(day):  # a SELL view: proposals run (and store a snapshot) whatever the halt state
            record = env.propose("H1", view_for(env.stores, env.reader, day, "BEARISH", tag=str(day)),
                                 coverage=covered())
            assert record.intent_id is not None, record
            s = env.stores.snapshots.latest("H1", t_of(day))
            return s.equity, s.peak_equity, s.baseline_at

        assert snapshot_after(a) == (Decimal("100000"), Decimal("100000"), START)
        assert snapshot_after(b)[:2] == (Decimal("85000"), Decimal("100000"))  # 15.0%: the risk check halts BUYs
        env.stores.limits.set_halt("H1", at=t_of(b), limits_version="risk-1", reason="drawdown 15.0%")
        clear_at = t_of(b) + timedelta(minutes=30)
        env.stores.limits.clear_halt("H1", by=OWNER, reason="reviewed", equity_now=Decimal("85000"),
                                     effective_at=clear_at)
        assert snapshot_after(c) == (Decimal("60000"), Decimal("85000"), clear_at)  # 29.4% below the clear
        env.stores.limits.set_halt("H1", at=t_of(c), limits_version="risk-1", reason="drawdown 29.4%")
        assert snapshot_after(d) == (Decimal("80000"), Decimal("85000"), clear_at)  # still the clear's epoch
    finally:
        env.close()


@pytest.mark.unit
def test_a_correction_between_view_and_proposal_is_a_missing_reference_not_an_error(env):
    """Codex B7: a holding valued from a later revision than the view's bar raised instead of being recorded."""
    env.account("H1", start=False)
    env.stores.snapshots.declare_start("H1", by=OWNER, reason="D14", cash=Decimal("98800"),
                                       positions=((NVDA, Decimal("10")),), effective_at=START)
    view = view_for(env.stores, env.reader, DAY)
    MarketDataWriter(env.root).write_candles([observation(DAY, close="121.0000",
                                                          received=view.generated_at + timedelta(minutes=1))],
                                             import_id="correction")
    knowledge = StoreKnowledge(MarketDataReader(env.root), CAL)
    record = env.propose("H1", view, at=view.generated_at + timedelta(minutes=2), knowledge=knowledge,
                         coverage=covered())
    assert record.outcome is ProposalOutcome.PREREQUISITE_MISSING and record.missing == ("reference",)
    assert "revision 2" in record.reason and "revision 1" in record.reason
    assert env.count("intents") == 0 and env.count("intent_lineage_records") == 0
    assert env.stores.proposals.for_view("H1", record.view_lineage_id) == record  # stored, like any prerequisite
