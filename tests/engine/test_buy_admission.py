"""BUY admission is serialized per account and session (docs/tasks/M3-12.md rule 4; Codex B5)."""

import threading
from decimal import Decimal

import pytest

from investment_engine.oms.intents import IntentState
from investment_engine.oms.pipeline import ProposalOutcome, ProposalStore, expire_due
from tests.engine.test_intent_pipeline import (
    CAL,
    DAY,
    NOW,
    NVDA,
    OWNER,
    SESSIONS,
    START,
    TARGET,
    Env,
    covered,
    t_of,
    view_for,
    write_bars,
)

pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database, tmp_path):
    e = Env(pg_database, tmp_path / "market")
    yield e
    e.close()


@pytest.mark.unit
def test_concurrent_proposals_admit_exactly_one_new_buy_at_the_cap(env):
    env.account("R1")
    for rep in range(50):
        day = SESSIONS[100 + rep]
        for k in range(4):  # four of five slots taken for this target session
            assert env.propose("R1", view_for(env.stores, env.reader, day, tag=f"{rep}-{k}")).outcome is \
                ProposalOutcome.AWAITING_APPROVAL
        racers = [view_for(env.stores, env.reader, day, tag=f"{rep}-race-{k}") for k in range(2)]
        barrier, outcomes, errors = threading.Barrier(2), [], []

        def run(view, barrier=barrier, outcomes=outcomes, errors=errors):
            stores = env.connect()
            try:
                barrier.wait()
                outcomes.append(env.propose("R1", view, stores=stores))
            except Exception as exc:  # surfaced below, with the repetition
                errors.append(exc)
            finally:
                stores.db.connection.close()

        threads = [threading.Thread(target=run, args=(v,)) for v in racers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        assert not errors, (rep, errors)
        assert sorted(r.outcome for r in outcomes) == [ProposalOutcome.AWAITING_APPROVAL,
                                                       ProposalOutcome.RISK_REJECTED], rep
        (rejected,) = [r for r in outcomes if r.outcome is ProposalOutcome.RISK_REJECTED]
        assert "daily_buys" in rejected.reason, rep
        assert env.stores.intents.admitted_buys("R1", CAL.next_session(day).date) == 5


@pytest.mark.unit
def test_reductions_approvals_reruns_expiry_decline_and_rollbacks_take_no_new_slot(pg_database, tmp_path,
                                                                                   monkeypatch):
    env = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "thin", SESSIONS, volume="1000"))
    try:
        env.account("R1")

        def slots():
            return env.stores.intents.admitted_buys("R1", TARGET)

        view = view_for(env.stores, env.reader, DAY)
        reduced = env.propose("R1", view)
        assert reduced.versions == (1, 2) and slots() == 1  # v2 of a reduced intent takes no extra slot
        (lineage_v1, lineage_v2) = env.stores.intent_lineage.for_intent(reduced.intent_id)
        assert lineage_v1.admitted_buys_read == lineage_v2.admitted_buys_read == 0
        assert env.propose("R1", view) == reduced and slots() == 1  # an idempotent re-run

        second = env.propose("R1", view_for(env.stores, env.reader, DAY, tag="2"))
        third = env.propose("R1", view_for(env.stores, env.reader, DAY, tag="3"))
        assert slots() == 3
        stored = env.stores.intents.get(second.intent_id)
        env.stores.intents.transition(  # AWAITING_APPROVAL -> APPROVED
            second.intent_id, stored.intent.version, IntentState.APPROVED,
            expected_aggregate_version=stored.aggregate_version, at=t_of(DAY), by=OWNER, reason="test approval",
            approved_by="owner", approved_at=t_of(DAY), approval_expires_at=CAL.session(TARGET).close,
            approval_recorded_at=NOW)
        assert slots() == 3
        stored = env.stores.intents.get(third.intent_id)
        env.stores.intents.transition(third.intent_id, stored.intent.version, IntentState.DECLINED,
                                      expected_aggregate_version=stored.aggregate_version, at=t_of(DAY),
                                      by=OWNER, reason="test decline")
        assert slots() == 3  # a decline doesn't free the slot

        def fail(*args, **kwargs):  # the last write: the admission itself was already written in the transaction
            raise RuntimeError("injected failure at the proposal record")

        monkeypatch.setattr(ProposalStore, "append", fail)
        with pytest.raises(RuntimeError, match="injected"):
            env.propose("R1", view_for(env.stores, env.reader, DAY, tag="rolled-back"))
        assert slots() == 3
        monkeypatch.undo()

        expire_due("R1", at=CAL.session(TARGET).close, stores=env.stores)
        assert env.stores.intents.get(reduced.intent_id).state is IntentState.EXPIRED
        assert slots() == 3  # expiry doesn't free it either
    finally:
        env.close()


@pytest.mark.unit
def test_a_sell_takes_no_admission_lock_count(env):
    env.account("H1", start=False)
    env.stores.snapshots.declare_start("H1", by=OWNER, reason="D14", positions=((NVDA, Decimal("100")),),
                                       effective_at=START)
    record = env.propose("H1", view_for(env.stores, env.reader, DAY, "BEARISH"), coverage=covered())
    stored = env.stores.intents.get(record.intent_id)
    assert stored.intent.side.value == "SELL" and record.outcome is ProposalOutcome.AWAITING_APPROVAL
    (lineage,) = env.stores.intent_lineage.for_intent(record.intent_id)
    assert lineage.admitted_buys_read is None and len(lineage.adv_refs) == 20
    assert env.stores.intents.admitted_buys("H1", TARGET) == 0
