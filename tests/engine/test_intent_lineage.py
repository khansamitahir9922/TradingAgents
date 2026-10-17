"""Intent lineage and proposal records are append-only and content-addressed (docs/tasks/M3-12.md)."""

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from investment_engine.lineage.intent_lineage import IntentLineageRecord, IntentLineageStore
from investment_engine.oms.intents import IntentState
from investment_engine.oms.pipeline import ProposalOutcome, ProposalRecord, ProposalStore
from investment_engine.storage.database import AppendOnlyViolation, SqliteDatabase
from tests.engine.test_intent_pipeline import DAY, SESSIONS, Env, view_for, write_bars

pytestmark = pytest.mark.postgres


@pytest.fixture
def reduced(pg_database, tmp_path):
    """A proposal whose intent was reduced: two lineage records, v1 SUPERSEDED and v2 AWAITING_APPROVAL."""
    env = Env(pg_database, tmp_path / "market", reader=write_bars(tmp_path / "thin", SESSIONS, volume="1000"))
    env.account("R1")
    record = env.propose("R1", view_for(env.stores, env.reader, DAY))
    yield env, record
    env.close()


@pytest.mark.unit
def test_every_version_has_a_record_that_round_trips_and_verifies_its_id(reduced):
    env, record = reduced
    v1, v2 = env.stores.intent_lineage.for_intent(record.intent_id)
    assert (v1.version, v1.final_state, v2.version, v2.final_state) == (1, IntentState.SUPERSEDED, 2,
                                                                        IntentState.AWAITING_APPROVAL)
    for r in (v1, v2):
        assert r.lineage_id.startswith("ilin-") and env.stores.intent_lineage.get(r.lineage_id) == r
        assert IntentLineageRecord(**{f: getattr(r, f) for f in r.__dataclass_fields__ if f != "lineage_id"}) == r
    assert v1.snapshot_id == v2.snapshot_id and v1.reference_bar == v2.reference_bar
    assert v1.policy_version == v2.policy_version and v1.risk_version == v2.risk_version
    assert replace(v1, code_version="other").lineage_id != v1.lineage_id  # the id covers the content...
    moved = replace(v1.autonomy, recorded_at=v1.autonomy.recorded_at + timedelta(days=3), set_by="someone-else")
    assert replace(v1, autonomy=moved).lineage_id == v1.lineage_id  # ...but not the setting's provenance
    assert replace(v1, autonomy=replace(v1.autonomy, level=2)).lineage_id != v1.lineage_id
    with pytest.raises(KeyError):
        env.stores.intent_lineage.get("ilin-unknown")


@pytest.mark.unit
def test_an_identical_append_is_a_no_op(reduced):
    env, record = reduced
    v1, _ = env.stores.intent_lineage.for_intent(record.intent_id)
    before = env.count("intent_lineage_records")
    env.stores.intent_lineage.append(v1)
    stored = env.stores.proposals.for_view("R1", record.view_lineage_id)
    env.stores.proposals.append(stored)
    assert env.count("intent_lineage_records") == before and env.count("proposal_records") == 1


@pytest.mark.unit
def test_a_conflicting_proposal_for_the_same_account_and_view_is_refused(reduced):
    env, record = reduced
    other = ProposalRecord(record.account_id, record.view_lineage_id, record.at, ProposalOutcome.NO_INTENT,
                           "a different story", (), None, ())
    with pytest.raises(ValueError, match="different proposal"):
        env.stores.proposals.append(other)
    assert env.stores.proposals.for_view("R1", record.view_lineage_id) == record


@pytest.mark.unit
@pytest.mark.parametrize("table", ["intent_lineage_records", "proposal_records"])
@pytest.mark.parametrize("statement", ["UPDATE {t} SET content = content", "DELETE FROM {t}", "TRUNCATE {t}"])
def test_history_can_not_be_changed(reduced, table, statement):
    env, _ = reduced
    before = env.count(table)
    with pytest.raises(AppendOnlyViolation):
        env.stores.db.execute(statement.format(t=table))
    assert env.count(table) == before


@pytest.mark.unit
def test_the_stores_are_postgresql_only():
    db = SqliteDatabase(sqlite3.connect(":memory:", isolation_level=None))
    with pytest.raises(TypeError, match="PostgreSQL only"):
        IntentLineageStore(db)
    with pytest.raises(TypeError, match="PostgreSQL only"):
        ProposalStore(db)
