"""LineageRecord and its append-only store (Part H; docs/tasks/M2-07.md)."""

import sqlite3
import zlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType

import pytest

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.lineage.records import (
    LineageConflict,
    LineageRecord,
    LineageStore,
    canonical_json,
    decode,
    encode,
)
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.candles import Timeframe
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import (
    Applicability,
    DataHealth,
    HealthStatus,
    HealthThresholds,
    SourceHealth,
    SourceKey,
)
from investment_engine.quant.adjusted import (
    AdjustedBasis,
    BarRef,
    VerificationEvidence,
    establish_coverage,
)
from investment_engine.quant.indicators import DEFINITIONS
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import Direction, StrategySignal
from investment_engine.storage.sqlite import apply_schema, open_operational_db

NVDA = "EQ_US_NVDA"
AT = datetime(2024, 6, 21, 21, tzinfo=UTC)
YF_D1 = SourceKey("yfinance", Timeframe.D1)


def record(**changes):
    ev = VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                              date(2019, 1, 1), date(2026, 10, 12), "v", "COMPLETE")
    cov = establish_coverage([ev], source="yfinance", instrument_id=NVDA, types=[ActionType.SPLIT],
                             first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=AT, reason="t")
    entry = SourceHealth(YF_D1, HealthStatus.DEGRADED, AT, AT - timedelta(hours=1), timedelta(hours=1), 0,
                         (AT - timedelta(days=3),), "1 expected bar missing")
    health = DataHealth(NVDA, AT, Applicability(True, ""), (entry,), False)
    ref = BarRef("yfinance", NVDA, Timeframe.D1, AT - timedelta(hours=7), 2, "imp", AT - timedelta(hours=1),
                 AvailabilityBasis.OBSERVED)
    snap = FeatureSnapshot(NVDA, "yfinance", AT, date(2024, 6, 21), MappingProxyType({d.key: None for d in DEFINITIONS}),
                           MappingProxyType({d.key: d.version for d in DEFINITIONS}), (ref,), (), cov, "",
                           AdjustedBasis.SPLIT_ADJUSTED_AS_OF, health, (), 101.25)
    signal = StrategySignal("daily-trend", "0.1.0", Direction.BULLISH, 0.3, ("r",), ("k",))
    view = MarketView(NVDA, ViewDirection.ABSTAIN, 0.0, None, "5 sessions", AT, AT + timedelta(days=3), "BULLISH",
                      health, (), "0.1.0", "required data not OK: yfinance D1: DEGRADED", ("r",))
    values = {"instrument_id": NVDA, "generated_at": AT, "bar_refs": (ref,), "action_refs": (),
              "action_coverage": cov, "feature_versions": snap.feature_versions,
              "strategy_versions": {"daily-trend": "0.1.0"}, "policy_version": "0.1.0", "data_health": health,
              "health_thresholds": HealthThresholds(), "snapshot": snap, "signals": (signal, None), "decision": view,
              "config": {"policy_version": "0.1.0", "features": ("a", "b")}, "calendar_version": "cal-1",
              "code_version": "test-0.0.0"}
    values.update(changes)
    return LineageRecord(**values)


@pytest.fixture
def db(tmp_path):
    conn = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(conn)
    yield conn
    conn.close()


@pytest.mark.unit
def test_a_record_round_trips_exactly_through_the_store(db):
    store = LineageStore(db)
    r = record()
    store.append(r)
    back = store.get(r.lineage_id)
    assert back == r and back.lineage_id == r.lineage_id
    assert back.data_health.sources[0].status is HealthStatus.DEGRADED
    assert back.decision.abstain_reason.endswith("DEGRADED")


@pytest.mark.unit
def test_an_identical_append_is_a_no_op(db):
    store = LineageStore(db)
    store.append(record())
    store.append(record())
    assert db.execute("SELECT COUNT(*) FROM lineage_records").fetchone()[0] == 1


@pytest.mark.unit
def test_a_different_record_under_an_existing_id_raises(db):
    r = record()
    db.execute("INSERT INTO lineage_records VALUES (?, ?, ?, ?)",
               (r.lineage_id, NVDA, AT.isoformat(), zlib.compress(b"{}")))
    with pytest.raises(LineageConflict):
        LineageStore(db).append(r)


@pytest.mark.unit
def test_direct_sql_update_and_delete_are_refused(db):
    LineageStore(db).append(record())
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE lineage_records SET instrument_id = 'EQ_US_MSFT'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM lineage_records")
    assert db.execute("SELECT COUNT(*) FROM lineage_records").fetchone()[0] == 1


@pytest.mark.unit
def test_the_store_has_no_update_or_delete_path():
    assert not [n for n in dir(LineageStore) if n.startswith(("update", "delete", "remove", "replace"))]


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"calendar_version": "cal-2"},
    {"health_thresholds": HealthThresholds(lookback_sessions=30)},
    {"config": {"policy_version": "0.1.0", "features": ("a", "c")}},
    {"code_version": "test-0.0.1"},
    {"strategy_versions": {"daily-trend": "0.2.0"}},
])
def test_any_content_change_changes_the_id(change):
    assert record(**change).lineage_id != record().lineage_id


@pytest.mark.unit
def test_a_change_in_decision_content_changes_the_id():
    r = record()
    other = replace(r.decision, reasons=("other",))
    assert record(decision=other).lineage_id != r.lineage_id


@pytest.mark.unit
def test_the_id_is_a_hash_of_content_without_the_id_or_evidence_refs():
    r = record()
    assert r.lineage_id.startswith("lin-") and r.lineage_id not in r.content()
    with pytest.raises(ValueError, match="evidence"):
        record(decision=replace(r.decision, evidence_refs=("lin-x",)))


@pytest.mark.unit
def test_record_fields_must_share_t_and_instrument_and_name_their_versions():
    r = record()
    with pytest.raises(ValueError):
        record(generated_at=AT + timedelta(seconds=1))
    with pytest.raises(ValueError):
        record(code_version="")
    with pytest.raises(ValueError):
        record(instrument_id="EQ_US_MSFT")
    with pytest.raises(ValueError):
        record(model_version="m1")
    assert r.research_run is None and r.portfolio_snapshot is None and r.risk_versions is None


@pytest.mark.unit
def test_canonical_json_is_independent_of_mapping_order_and_refuses_unknown_types():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert decode(encode({"x": (1.5, None)})) == {"x": (1.5, None)}
    with pytest.raises(TypeError):
        encode(object())
    with pytest.raises(ValueError):
        encode(float("nan"))
    with pytest.raises(ValueError):
        encode(datetime(2024, 1, 1))  # naive times are refused, not guessed


@pytest.mark.unit
@pytest.mark.parametrize("statement", [
    "INSERT OR REPLACE INTO lineage_records VALUES (?, ?, ?, ?)",
    "REPLACE INTO lineage_records VALUES (?, ?, ?, ?)",
    "INSERT INTO lineage_records VALUES (?, ?, ?, ?) ON CONFLICT (lineage_id) DO UPDATE SET content = excluded.content",
    "INSERT OR IGNORE INTO lineage_records VALUES (?, ?, ?, ?)",
])
def test_replacing_an_existing_lineage_id_through_sql_is_refused_and_the_original_survives(db, statement):
    store = LineageStore(db)
    r = record()
    store.append(r)
    original = db.execute("SELECT content FROM lineage_records WHERE lineage_id = ?", (r.lineage_id,)).fetchone()[0]
    assert db.execute("PRAGMA recursive_triggers").fetchone()[0] == 0  # the ordinary connection setting
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute(statement, (r.lineage_id, NVDA, AT.isoformat(), zlib.compress(b"{}")))
    assert db.execute("SELECT content FROM lineage_records WHERE lineage_id = ?", (r.lineage_id,)).fetchone()[0] == original
    assert store.get(r.lineage_id) == r
    store.append(r)  # the API's identical append is still a no-op
