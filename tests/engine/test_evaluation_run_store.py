"""Immutable evaluation run records (docs/tasks/M2-11.md rule 5; M2-11b)."""

import base64
import json
import sqlite3
import zlib
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

import pytest

from investment_engine.evaluation.metrics import DirectionEvaluation, MetricValue
from investment_engine.evaluation.returns import LabelConfig, ReturnBasis
from investment_engine.evaluation.run_store import (
    EvaluationRecord,
    EvaluationRunConflict,
    EvaluationRunStore,
    check_fold_periods,
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
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.storage.sqlite import apply_schema, open_operational_db
from tests.engine.test_sqlite_store import SCHEMA_SCRIPTS

NVDA = "EQ_US_NVDA"
LABELS = LabelConfig(5, ReturnBasis.SPLIT_ADJUSTED_PRICE_RETURN, "labels-0.1.0")
WF = WalkForwardConfig(24, 6, 6, LABELS, "wf-0.1.0")
EVAL = EvaluationConfig("eval-0.1.0", Decimal("10000"), "USD", Decimal("5"), "LONG_OR_CASH",
                        "CASH_ON_EX_DATE_RESEARCH_ASSUMPTION")
AT = datetime(2026, 10, 12, 20, tzinfo=UTC)
CAL = load_us_equities_calendar()
CALENDARS = {"test-cal": CAL}  # the record fixture's declared calendar version
OLD_FORMAT = Path(__file__).parent / "fixtures" / "evaluation" / "record-57d4316.json"


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
    store = EvaluationRunStore(db, calendars=CALENDARS)
    r = record()
    store.append(r)
    back = store.get(r.record_id)
    assert back == r and back.record_id == r.record_id
    assert back.result.folds[0].run.equity_curve == ((date(2021, 1, 4), Decimal("10000")),)
    assert back.result.promotion == PROMOTION_STATUS
    assert back.walk_forward_config == WF and back.evaluation_config == EVAL


@pytest.mark.unit
def test_append_is_idempotent_and_a_conflicting_id_raises(db):
    store = EvaluationRunStore(db, calendars=CALENDARS)
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
    EvaluationRunStore(db, calendars=CALENDARS).append(record())
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
    store = EvaluationRunStore(db, calendars=CALENDARS)
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
    store = EvaluationRunStore(db, calendars=CALENDARS)
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
    store = EvaluationRunStore(db, calendars=CALENDARS)
    store.append(record())
    store.append(record())
    assert store.get(record().record_id) == record()


# ------------------------------------------------------------------ R1: historical serialized formats stay readable


def schema_3_db(tmp_path):
    conn = open_operational_db(tmp_path / "old.sqlite3")
    for number, script in enumerate(SCHEMA_SCRIPTS[:3], start=1):
        sql = script.read_text(encoding="utf-8")
        conn.executescript(f"BEGIN;\n{sql}\nINSERT INTO schema_version (version) VALUES ({number});\nCOMMIT;")
    return conn


def old_format():
    fixture = json.loads(OLD_FORMAT.read_text(encoding="utf-8"))
    return fixture, base64.b64decode(fixture["content_zlib_b64"])


def with_audit(r, sample=(date(2021, 1, 4),), excluded=(date(2021, 1, 5),)):
    fold = r.result.folds[0]
    direction = replace(fold.direction, trailing_refs=(), last_period_sample=sample, last_period_excluded=excluded)
    return record(result=replace(r.result, folds=(replace(fold, direction=direction),)))


@pytest.mark.unit
def test_a_genuine_57d4316_record_reads_back_with_its_original_id_after_the_upgrade(tmp_path):
    fixture, blob = old_format()
    conn = schema_3_db(tmp_path)
    conn.execute("INSERT INTO evaluation_records VALUES (?, ?, ?, ?)",
                 (fixture["record_id"], fixture["instrument_id"], fixture["as_of"], blob))
    assert apply_schema(conn) == len(SCHEMA_SCRIPTS) >= 4
    store = EvaluationRunStore(conn, calendars=CALENDARS)
    back = store.get(fixture["record_id"])
    assert back.record_id == fixture["record_id"]
    assert back.content() == zlib.decompress(blob).decode()  # the same canonical payload, not a rewrite
    direction = back.result.folds[0].direction
    assert direction.trailing_refs is None and direction.last_period_sample is None  # honestly not recorded
    assert direction.last_period_excluded is None and not direction.last_period_audit_recorded
    store.append(back)  # idempotent; the stored bytes are untouched
    assert conn.execute("SELECT content FROM evaluation_records").fetchall() == [(blob,)]
    conn.close()


@pytest.mark.unit
def test_corrupt_content_is_detected_in_both_formats(tmp_path):
    fixture, blob = old_format()
    new = with_audit(record())
    conn = schema_3_db(tmp_path)
    apply_schema(conn)
    old_text = zlib.decompress(blob).decode().replace("test-code", "edited-code")
    new_text = new.content().replace("2021-01-05", "2021-01-06")
    for record_id, text in ((fixture["record_id"], old_text), (new.record_id, new_text)):
        conn.execute("INSERT INTO evaluation_records VALUES (?, ?, ?, ?)",
                     (record_id, NVDA, AT.isoformat(), zlib.compress(text.encode())))
        with pytest.raises(ValueError, match="hashes to"):
            EvaluationRunStore(conn, calendars=CALENDARS).get(record_id)
    conn.close()


@pytest.mark.unit
def test_a_current_record_keeps_its_audit_sample_and_round_trips(db):
    store = EvaluationRunStore(db, calendars=CALENDARS)
    new = with_audit(record())
    assert new.record_id != record().record_id  # recorded audit details are part of the identity
    store.append(new)
    store.append(new)
    back = store.get(new.record_id)
    assert back == new and back.result.folds[0].direction.last_period_sample == (date(2021, 1, 4),)
    assert back.result.folds[0].direction.last_period_audit_recorded
    empty = with_audit(record(), sample=(), excluded=())  # recorded as empty is not "not recorded"
    assert empty.record_id not in (new.record_id, record().record_id)


@pytest.mark.unit
def test_audit_fields_are_recorded_together_or_not_at_all():
    direction = record().result.folds[0].direction
    with pytest.raises(ValueError, match="together"):
        replace(direction, last_period_sample=())


# ------------------------------------------------------------------ R2: a run must cover exactly its fold's sessions


def with_run_dates(first, last, complete=True):
    r = record()
    fold = r.result.folds[0]
    run = replace(fold.run, first=first, last=last, complete=complete)
    return record(result=replace(r.result, folds=(replace(fold, run=run),)))


@pytest.mark.unit
@pytest.mark.parametrize("first, last", [
    (date(2021, 1, 5), date(2021, 7, 1)),     # truncated start
    (date(2021, 1, 4), date(2021, 1, 15)),    # truncated end: ten sessions labelled as six months
    (date(2020, 12, 31), date(2021, 7, 1)),   # starts before the fold
    (date(2021, 1, 4), date(2021, 7, 2)),     # ends after the half-open fold
])
def test_a_run_not_covering_its_fold_is_refused(db, first, last):
    r = with_run_dates(first, last)
    with pytest.raises(ValueError, match="fold 1"):
        EvaluationRunStore(db, calendars=CALENDARS).append(r)
    with pytest.raises(ValueError, match="fold 1"):
        check_fold_periods(r, CALENDARS)
    assert db.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0] == 0


@pytest.mark.unit
def test_complete_and_unfinished_folds_with_matching_sessions_are_accepted(db):
    store = EvaluationRunStore(db, calendars=CALENDARS)
    store.append(record())  # 2021-01-04 .. 2021-07-01: the sessions of [Jan 4 open, Jul 2 open)
    unfinished = with_run_dates(date(2021, 1, 4), date(2021, 7, 1), complete=False)  # B3: incomplete, same period
    store.append(unfinished)
    assert not store.get(unfinished.record_id).result.folds[0].run.complete


@pytest.mark.unit
def test_the_declared_calendar_version_must_be_supplied(db):
    with pytest.raises(ValueError, match="calendar"):
        EvaluationRunStore(db, calendars={"other-cal": CAL}).append(record())


@pytest.mark.unit
def test_a_genuine_historical_record_passes_the_period_check(tmp_path):
    fixture, blob = old_format()
    conn = schema_3_db(tmp_path)
    conn.execute("INSERT INTO evaluation_records VALUES (?, ?, ?, ?)",
                 (fixture["record_id"], fixture["instrument_id"], fixture["as_of"], blob))
    apply_schema(conn)
    check_fold_periods(EvaluationRunStore(conn, calendars=CALENDARS).get(fixture["record_id"]), CALENDARS)
    conn.close()
