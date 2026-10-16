"""Immutable evaluation run records (docs/tasks/M2-11.md rule 5; M2-11b).

An EvaluationRecord is one complete walk-forward evaluation: its walk-forward
and evaluation configurations (costs included), every fold's boundaries,
direction metrics with their baseline samples and outcome references, and
each fold's SIMULATED run with its decision lineage ids and realised input
references; plus the code and calendar versions, the coverage evidence and
the backfill assumption it rests on. Its id hashes that canonical content, so
every reported number can be traced to exactly what produced it.

Stored in the Operational Database's evaluation domain through the database
port (PostgreSQL from M3, or a legacy SQLite file; M3-02), append-only (schema
0003): an identical append is a no-op, a different record under the same id
raises, there's no update or delete path, and SQL triggers refuse UPDATE and
DELETE. The canonical JSON is stored zlib-compressed.
"""

import dataclasses
import hashlib
import json
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from investment_engine.evaluation.metrics import DirectionEvaluation
from investment_engine.evaluation.returns import ReturnBasis, ReturnObservation
from investment_engine.evaluation.simulation import EvaluationConfig
from investment_engine.evaluation.walk_forward import (
    PROMOTION_STATUS,
    WalkForwardConfig,
    WalkForwardResult,
)
from investment_engine.lineage.records import canonical_json, decode, register
from investment_engine.market.availability import check_utc
from investment_engine.market.calendar.base import CalendarRangeError
from investment_engine.storage.sqlite import port


@dataclass(frozen=True)
class EvaluationRecord:
    walk_forward_config: WalkForwardConfig
    evaluation_config: EvaluationConfig
    result: WalkForwardResult
    source: str
    instrument_id: str
    as_of: datetime  # when realised outcomes were read
    code_version: str
    calendar_version: str
    coverage_evidence_refs: tuple[str, ...]
    coverage_reason: str
    backfill_assumption: str
    record_id: str = field(init=False)

    def __post_init__(self) -> None:
        check_utc(self.as_of, "as_of")
        for name in ("source", "instrument_id", "code_version", "calendar_version", "coverage_reason",
                     "backfill_assumption"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        object.__setattr__(self, "coverage_evidence_refs", tuple(self.coverage_evidence_refs))
        self._check_consistency()
        object.__setattr__(self, "record_id", "eval-" + hashlib.sha256(self.content().encode()).hexdigest())

    def _check_consistency(self) -> None:
        """The outer configuration and labels must describe exactly what the folds computed (Codex B5)."""
        wf, labels = self.walk_forward_config, self.walk_forward_config.label_config
        problems = []
        if self.result.promotion != PROMOTION_STATUS:
            problems.append(f"promotion status {self.result.promotion!r}; thresholds are not accepted")
        if len(self.result.stitched) != len(self.result.folds):
            problems.append("stitched summary and folds differ in length")
        for i, (fr, (start, value)) in enumerate(zip(self.result.folds, self.result.stitched, strict=False), 1):
            run, d, fold = fr.run, fr.direction, fr.fold
            if run.config != self.evaluation_config:
                problems.append(f"fold {i} ran with {run.config.version} ({run.config.costs_bps_per_side} bps), not "
                                f"{self.evaluation_config.version} ({self.evaluation_config.costs_bps_per_side} bps)")
            if (run.source, run.instrument_id) != (self.source, self.instrument_id):
                problems.append(f"fold {i} is for {run.source} {run.instrument_id}")
            if run.as_of != self.as_of:
                problems.append(f"fold {i} was evaluated at {run.as_of}, not {self.as_of}")
            if (fold.config_version, fold.label_config) != (wf.version, labels):
                problems.append(f"fold {i} has walk-forward/label configuration {fold.config_version}")
            if (d.config_version, d.basis, d.horizon_sessions) != (labels.version, labels.basis,
                                                                   labels.horizon_sessions):
                problems.append(f"fold {i} direction metrics use {d.config_version} {d.basis} h={d.horizon_sessions}")
            net = next((m.value for m in run.metrics if m.key == "net_return"), None)
            if start != fold.test_start or value != net:
                problems.append(f"stitched entry {i} doesn't match its fold's net return")
        if problems:
            raise ValueError("inconsistent evaluation record: " + "; ".join(problems))

    def content(self) -> str:
        return canonical_json({f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init})

    @classmethod
    def from_content(cls, content: str) -> "EvaluationRecord":
        return cls(**dict(decode(json.loads(content))))


for _cls in (DirectionEvaluation, ReturnObservation, ReturnBasis, EvaluationRecord):
    register(_cls)


class EvaluationRunConflict(ValueError):
    """A different evaluation record already exists under this id."""


def check_fold_periods(record: EvaluationRecord, calendars: Mapping[str, object]) -> None:
    """Each fold's run must cover exactly the sessions of its half-open test window (Codex M2 re-review R2).

    The sessions come from the calendar the record declares (`calendars[record.calendar_version]`): the run's
    first session opens at the fold's test start, and the session after its last opens at the test end. A
    shorter, longer or shifted run is refused, never labelled as the fold. An unfinished fold still requests
    its whole window and is reported incomplete (B3); partial-window evaluations are not supported.
    """
    calendar = calendars.get(record.calendar_version)
    if calendar is None:
        raise ValueError(f"the record's calendar {record.calendar_version!r} was not supplied")
    problems = []
    for i, fr in enumerate(record.result.folds, 1):
        fold, run = fr.fold, fr.run
        try:
            starts = calendar.is_session(run.first) and calendar.session(run.first).open == fold.test_start
            ends = run.first <= run.last and calendar.next_session(run.last).open == fold.test_end
        except CalendarRangeError:
            starts = ends = False
        if not (starts and ends):
            problems.append(f"fold {i} run covers sessions {run.first}..{run.last}, not the fold's test window "
                            f"{fold.test_start.isoformat()}..{fold.test_end.isoformat()} (half-open) on "
                            f"{record.calendar_version}")
    if problems:
        raise ValueError("evaluation periods don't match their folds: " + "; ".join(problems))


class EvaluationRunStore:
    """Append-only evaluation records over the Operational Database (schema 0003).

    `calendars` maps calendar versions to calendars; a record's fold periods are checked against the one it
    declares when it is appended and when it is read back.
    """

    def __init__(self, db, *, calendars: Mapping[str, object]) -> None:
        self._db = port(db)
        self._calendars = dict(calendars)

    def append(self, record: EvaluationRecord) -> None:
        if not isinstance(record, EvaluationRecord):
            raise TypeError(f"expected an EvaluationRecord, not {type(record).__name__}")
        check_fold_periods(record, self._calendars)
        content = record.content()
        with self._db.transaction():
            existing = self._db.fetchone("SELECT content FROM evaluation_records WHERE record_id = :id",
                                         {"id": record.record_id})
            if existing is not None:
                if zlib.decompress(bytes(existing[0])).decode() != content:
                    raise EvaluationRunConflict(f"{record.record_id} is already recorded with different content")
                return
            self._db.execute(
                "INSERT INTO evaluation_records (record_id, instrument_id, as_of, content) "
                "VALUES (:id, :instrument_id, :as_of, :content)",
                {"id": record.record_id, "instrument_id": record.instrument_id, "as_of": record.as_of,
                 "content": zlib.compress(content.encode(), 6)})

    def get(self, record_id: str) -> EvaluationRecord:
        row = self._db.fetchone("SELECT content FROM evaluation_records WHERE record_id = :id", {"id": record_id})
        if row is None:
            raise KeyError(record_id)
        record = EvaluationRecord.from_content(zlib.decompress(bytes(row[0])).decode())
        if record.record_id != record_id:
            raise ValueError(f"stored content for {record_id} hashes to {record.record_id}")
        check_fold_periods(record, self._calendars)
        return record

    def ids(self, instrument_id: str) -> list[str]:
        return [r[0] for r in self._db.fetchall(
            "SELECT record_id FROM evaluation_records WHERE instrument_id = :id ORDER BY as_of, record_id",
            {"id": instrument_id})]
