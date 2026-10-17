"""Proposals over a replay read only what the feed delivered (docs/tasks/M3-12.md rule 9; Codex S2)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.decision.pipeline import ReplayKnowledgeReader
from investment_engine.market.candles import Timeframe
from investment_engine.market.replay import ReplayFeed
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import MarketDataWriter
from investment_engine.oms.pipeline import ProposalOutcome, propose_over_replay
from investment_engine.policy.accounts import AccountKind
from tests.engine.conftest import maintenance_dsn, temporary_database
from tests.engine.test_intent_pipeline import (
    CAL,
    DAY,
    NOW,
    NVDA,
    SESSIONS,
    Env,
    t_of,
    view_for,
    write_bars,
)
from tests.engine.test_raw_reference import event, observation, stored

pytestmark = pytest.mark.postgres
FED = SESSIONS[30:63]  # enough volume history before DAY (SESSIONS[60])
BEFORE, TWO_BEFORE = SESSIONS[59], SESSIONS[58]


@pytest.fixture
def env(pg_database, tmp_path):
    e = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "market", FED))
    yield e
    e.close()


def correct(env, day, *, received, close="130.0000"):
    """Store revision 2 of `day`'s bar, available at `received`."""
    MarketDataWriter(env.root).write_candles([replace(observation(day, close=close, received=received),
                                                      volume=Decimal("2000000"))], import_id=f"fix-{day}")
    env.reader = MarketDataReader(env.root)
    (_, fixed) = stored(env.reader, day)
    assert fixed.revision == 2 and fixed.available_from <= received
    return fixed


def bar_events(reader, *, delivered=None, rank=None):
    """One BAR_CLOSED event per stored revision of the FED days, in delivery order.

    `delivered` maps (day, revision) to a delivery time (default: a minute after availability); `rank` orders
    events delivered at the same time (lower first), which fixes their feed sequence."""
    delivered, rank = delivered or {}, rank or {}
    items = []
    for d in FED:
        for c in stored(reader, d):
            when = delivered.get((d, c.revision), c.available_from + timedelta(minutes=1))
            items.append((when, rank.get((d, c.revision), 0), c.start_time, c.revision, c))
    items.sort(key=lambda x: x[:4])
    return [event(c, k + 1, received=when) for k, (when, _, _, _, c) in enumerate(items)]


def run(env, views, events, account_id="R1", **kwargs):
    return propose_over_replay(account_id, views, events=events, stores=env.stores,
                               knowledge_reader=ReplayKnowledgeReader(), calendar=CAL, coverage=None,
                               calendar_version="cal-1", code_version="test", **kwargs)


def adv_revisions(env, record):
    (lineage,) = env.stores.intent_lineage.for_intent(record.intent_id)
    return {r.start_time.astimezone(ZONE).date(): r.revision for r in lineage.adv_refs}


T = t_of(DAY)
ZONE = ZoneInfo("America/New_York")


@pytest.mark.unit
def test_a_correction_available_before_but_delivered_after_t_is_not_used(env):
    env.account("R1")
    env.account("R2")
    correct(env, BEFORE, received=T - timedelta(minutes=30))
    view = view_for(env.stores, env.reader, DAY)
    late = run(env, [view], bar_events(env.reader, delivered={(BEFORE, 2): T + timedelta(hours=1)}))
    assert late[0].outcome is ProposalOutcome.AWAITING_APPROVAL
    assert adv_revisions(env, late[0])[BEFORE] == 1  # available at T, but not yet delivered
    on_time = run(env, [view], bar_events(env.reader), account_id="R2")
    assert adv_revisions(env, on_time[0])[BEFORE] == 2  # control: delivered before T, so it's known


@pytest.mark.unit
def test_equal_time_events_follow_the_feed_sequence(env):
    env.account("R1")
    correct(env, BEFORE, received=T - timedelta(minutes=30))
    correct(env, TWO_BEFORE, received=T - timedelta(minutes=30))
    view = view_for(env.stores, env.reader, DAY, generated_at=T)
    at_t = {(BEFORE, 2): T, (DAY, 1): T, (TWO_BEFORE, 2): T}  # three events delivered at exactly T...
    order = {(BEFORE, 2): 1, (DAY, 1): 2, (TWO_BEFORE, 2): 3}  # ...in this sequence
    (record,) = run(env, [view], bar_events(env.reader, delivered=at_t, rank=order))
    revisions = adv_revisions(env, record)
    assert revisions[BEFORE] == 2 and revisions[TWO_BEFORE] == 1  # only those up to the decision bar's sequence
    (with_delay,) = run(env, [view_for(env.stores, env.reader, DAY, generated_at=T, tag="d")],
                        bar_events(env.reader, delivered=at_t, rank=order), proposal_delay=timedelta(seconds=1))
    assert adv_revisions(env, with_delay)[TWO_BEFORE] == 2  # a second later, everything delivered at T is known


@pytest.mark.unit
def test_a_decision_bar_not_yet_delivered_is_missing_and_no_older_bar_is_used(env):
    env.account("R1")
    view = view_for(env.stores, env.reader, DAY)
    (record,) = run(env, [view], bar_events(env.reader, delivered={(DAY, 1): T + timedelta(hours=1)}))
    assert record.outcome is ProposalOutcome.PREREQUISITE_MISSING and record.missing == ("reference",)
    assert env.count("intents") == 0


@pytest.mark.unit
def test_settings_effective_after_the_replay_time_are_not_used(env):
    env.account("R1", effective=t_of(SESSIONS[61]))  # set up for replay times from SESSIONS[61] on
    views = [view_for(env.stores, env.reader, d, tag=str(d)) for d in SESSIONS[60:63]]
    records = run(env, views, bar_events(env.reader))
    assert [r.outcome for r in records] == [ProposalOutcome.PREREQUISITE_MISSING,
                                            ProposalOutcome.AWAITING_APPROVAL, ProposalOutcome.AWAITING_APPROVAL]
    assert "autonomy" in records[0].missing and [r.at for r in records] == [v.generated_at for v in views]


def replay(dsn, root, *, now):
    """A replay through M2's ReplayFeed into a fresh database, with its setup recorded at real time `now`."""
    env = Env(dsn, root, now=now, reader=write_bars(root, FED))
    try:
        env.account("R1")
        views = [view_for(env.stores, env.reader, d, tag=str(d)) for d in SESSIONS[60:63]]
        start = CAL.session(FED[0]).open - timedelta(days=1)
        feed = ReplayFeed(env.reader, ReplayClock(start), sources=["yfinance"], instrument_ids=[NVDA],
                          timeframes=[Timeframe.D1], start=start, end=t_of(FED[-1]) + timedelta(minutes=1))
        records = run(env, views, feed)
        intents = [env.stores.intents.get(r.intent_id) for r in records]
        lineage = [r.lineage_id for rec in records for r in env.stores.intent_lineage.for_intent(rec.intent_id)]
        return records, [(i.intent, i.policy_decision, i.risk_decision) for i in intents], lineage
    finally:
        env.close()


@pytest.mark.unit
def test_replay_is_deterministic_across_fresh_databases_and_setup_days(tmp_path):
    runs = []
    for k, now in enumerate((NOW, NOW + timedelta(days=3, hours=5))):  # setups recreated on different days
        with temporary_database(maintenance_dsn()) as dsn:
            runs.append(replay(dsn, tmp_path / f"m{k}", now=now))
    (r1, i1, l1), (r2, i2, l2) = runs
    assert len(r1) == 3 and all(r.outcome is ProposalOutcome.AWAITING_APPROVAL for r in r1)
    assert [r.record_id for r in r1] == [r.record_id for r in r2] and r1 == r2
    assert i1 == i2 and l1 == l2


@pytest.mark.unit
def test_replay_refuses_paper_accounts_and_negative_delays(env):
    env.clock.advance_to(datetime(2026, 10, 17, tzinfo=UTC))
    env.account("P1", kind=AccountKind.PAPER)
    with pytest.raises(ValueError, match="RESEARCH"):
        run(env, [], [], account_id="P1")
    env.account("R1")
    with pytest.raises(ValueError, match="negative"):
        run(env, [], [], proposal_delay=timedelta(seconds=-1))
