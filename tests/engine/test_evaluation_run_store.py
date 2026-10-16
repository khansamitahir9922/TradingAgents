"""Immutable evaluation run records (docs/tasks/M2-11.md rule 5; M2-11b)."""

import sqlite3
import zlib
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files

import pytest

from investment_engine.evaluation.metrics import DirectionEvaluation, MetricValue
from investment_engine.evaluation.returns import LabelConfig, ReturnBasis
from investment_engine.evaluation.run_store import (
    EvaluationRecord,
    EvaluationRunConflict,
    EvaluationRunStore,
)
from investment_engine.evaluation.simulation import EvaluationConfig, EvaluationRun
from investment_engine.evaluation.walk_forward import (
    PROMOTION_STATUS,
    STITCHED_LABEL,
    Fold,
    FoldResult,
    WalkForwardConfig,
    WalkForwardResult,
)
from investment_engine.storage.sqlite import apply_schema, open_operational_db

NVDA = "EQ_US_NVDA"
LABELS = LabelConfig(5, ReturnBasis.SPLIT_ADJUSTED_PRICE_RETURN, "labels-0.1.0")
WF = WalkForwardConfig(24, 6, 6, LABELS, "wf-0.1.0")
EVAL = EvaluationConfig("eval-0.1.0", Decimal("10000"), "USD", Decimal("5"), "LONG_OR_CASH",
                        "CASH_ON_EX_DATE_RESEARCH_ASSUMPTION")
AT = datetime(2026, 10, 12, 20, tzinfo=UTC)


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def record(**changes):
    fold = Fold(utc(2019, 1, 2, 14, 30), utc(2020, 12, 31, 21), utc(2021, 1, 4, 14, 30), utc(2021, 7, 2, 13, 30),
                LABELS, WF.version)
    run = EvaluationRun(config=EVAL, label="SIMULATED / REPLAY · historical research", source="yfinance",
                        instrument_id=NVDA, first=date(2021, 1, 4), last=date(2021, 7, 1), as_of=AT, trades=(),
                        equity_curve=((date(2021, 1, 4), Decimal("10000")),),
                        cash_curve=((date(2021, 1, 4), Decimal("10000")),), ending_shares=Decimal(0), complete=True,
                        metrics=(MetricValue("net_return", 0.0, 1, ""),), benchmarks=(), lineage_refs=("lin-a",),
                        input_refs=(), limitations=("SIMULATED research.",))
    direction = DirectionEvaluation("labels-0.1.0", LABELS.basis, 5, 1, 0, 1, 0, 0,
                                    (MetricValue("direction_accuracy", None, 0, "no directional view"),), (),
                                    ("No statistical significance is claimed.",))
    result = WalkForwardResult((FoldResult(fold, 10, 5, 5, 1, 0, direction, run),),
                               ((fold.test_start, 0.0),), STITCHED_LABEL, PROMOTION_STATUS, ("limitation",))
    values = {"walk_forward_config": WF, "evaluation_config": EVAL, "result": result, "source": "yfinance",
              "instrument_id": NVDA, "as_of": AT, "code_version": "test-code", "calendar_version": "test-cal",
              "coverage_evidence_refs": ("verification:yfinance|EQ_US_NVDA|SPLIT|...",),
              "coverage_reason": "verified Yahoo actions; research assumption",
              "backfill_assumption": "BACKFILL_ASSUMED availability at each bar's close"}
    values.update(changes)
    return EvaluationRecord(**values)


@pytest.fixture
def db(tmp_path):
    conn = open_operational_db(tmp_path / "op.sqlite3")
    apply_schema(conn)
    yield conn
    conn.close()


@pytest.mark.unit
def test_a_record_reconstructs_its_config_and_references_exactly(db):
    store = EvaluationRunStore(db)
    r = record()
    store.append(r)
    back = store.get(r.record_id)
    assert back == r and back.record_id == r.record_id
    assert back.result.folds[0].run.equity_curve == ((date(2021, 1, 4), Decimal("10000")),)
    assert back.result.promotion == PROMOTION_STATUS
    assert back.walk_forward_config == WF and back.evaluation_config == EVAL


@pytest.mark.unit
def test_append_is_idempotent_and_a_conflicting_id_raises(db):
    store = EvaluationRunStore(db)
    store.append(record())
    store.append(record())
    assert db.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0] == 1
    r = record(code_version="other")
    db.execute("INSERT INTO evaluation_records VALUES (?, ?, ?, ?)",
               (r.record_id, NVDA, AT.isoformat(), zlib.compress(b"{}")))
    with pytest.raises(EvaluationRunConflict):
        store.append(r)


@pytest.mark.unit
def test_direct_sql_update_and_delete_are_refused(db):
    EvaluationRunStore(db).append(record())
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE evaluation_records SET instrument_id = 'EQ_US_MSFT'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM evaluation_records")


@pytest.mark.unit
def test_the_id_hashes_every_assumption():
    base = record().record_id
    for change in ({"code_version": "x"}, {"calendar_version": "x"}, {"coverage_reason": "x"},
                   {"backfill_assumption": "x"}):  # a cost change must be computed, not relabelled (B5)
        assert record(**change).record_id != base


@pytest.mark.unit
def test_a_record_requires_versions_and_a_utc_time():
    for change in ({"code_version": ""}, {"calendar_version": " "}, {"as_of": datetime(2026, 10, 12)}):
        with pytest.raises((TypeError, ValueError)):
            record(**change)


@pytest.mark.unit
def test_the_store_has_no_update_or_delete_path_and_lists_ids(db):
    store = EvaluationRunStore(db)
    assert not [n for n in dir(store) if n.startswith(("update", "delete", "remove", "replace"))]
    store.append(record())
    assert store.ids(NVDA) == [record().record_id]


@pytest.mark.unit
def test_the_migration_ships_with_the_package():
    names = {e.name for e in files("investment_engine.storage").joinpath("schema").iterdir()}
    assert "0003_evaluation.sql" in names


@pytest.mark.unit
@pytest.mark.parametrize("statement", [
    "INSERT OR REPLACE INTO evaluation_records VALUES (?, ?, ?, ?)",
    "REPLACE INTO evaluation_records VALUES (?, ?, ?, ?)",
    "INSERT INTO evaluation_records VALUES (?, ?, ?, ?) ON CONFLICT (record_id) DO UPDATE SET content = excluded.content",
    "INSERT OR IGNORE INTO evaluation_records VALUES (?, ?, ?, ?)",
])
def test_replacing_an_existing_evaluation_id_through_sql_is_refused_and_the_original_survives(db, statement):
    store = EvaluationRunStore(db)
    r = record()
    store.append(r)
    original = db.execute("SELECT content FROM evaluation_records WHERE record_id = ?", (r.record_id,)).fetchone()[0]
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute(statement, (r.record_id, NVDA, AT.isoformat(), zlib.compress(b"{}")))
    assert db.execute("SELECT content FROM evaluation_records WHERE record_id = ?", (r.record_id,)).fetchone()[0] == original
    assert store.get(r.record_id) == r
    store.append(r)


# ------------------------------------------------------------------ B5: the outer record must agree with its folds


@pytest.mark.unit
@pytest.mark.parametrize("change", ["cost", "source", "instrument", "cutoff", "label", "fold_version",
                                    "direction_basis", "stitched", "promotion"])
def test_a_record_contradicting_its_fold_results_is_refused(change):
    from dataclasses import replace
    base = record()
    fold = base.result.folds[0]
    kwargs = {}
    if change == "cost":
        kwargs["evaluation_config"] = replace(EVAL, costs_bps_per_side=Decimal("10"))
    elif change == "source":
        kwargs["source"] = "testvendor"
    elif change == "instrument":
        kwargs["instrument_id"] = "EQ_US_MSFT"
    elif change == "cutoff":
        kwargs["as_of"] = datetime(2026, 10, 13, tzinfo=UTC)
    elif change == "label":
        kwargs["walk_forward_config"] = replace(WF, label_config=LabelConfig(10, LABELS.basis, "labels-other"))
    elif change == "fold_version":
        kwargs["walk_forward_config"] = replace(WF, version="wf-other")
    elif change == "direction_basis":
        direction = replace(fold.direction, basis=ReturnBasis.TOTAL_RETURN_CLOSE_REINVESTED)
        kwargs["result"] = replace(base.result, folds=(replace(fold, direction=direction),))
    elif change == "stitched":
        kwargs["result"] = replace(base.result, stitched=((fold.fold.test_start, 0.5),))
    else:
        kwargs["result"] = replace(base.result, promotion="PROMOTED")
    with pytest.raises(ValueError):
        record(**kwargs)


@pytest.mark.unit
def test_a_consistent_record_still_serializes_and_appends_idempotently(db):
    store = EvaluationRunStore(db)
    store.append(record())
    store.append(record())
    assert store.get(record().record_id) == record()
