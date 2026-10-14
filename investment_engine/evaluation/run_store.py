"""Immutable evaluation run records (docs/tasks/M2-11.md rule 5; M2-11b).

An EvaluationRecord is one complete walk-forward evaluation: its walk-forward
and evaluation configurations (costs included), every fold's boundaries,
direction metrics with their baseline samples and outcome references, and
each fold's SIMULATED run with its decision lineage ids and realised input
references; plus the code and calendar versions, the coverage evidence and
the backfill assumption it rests on. Its id hashes that canonical content, so
every reported number can be traced to exactly what produced it.

Stored in the Operational Database's evaluation domain, append-only (schema
0003): an identical append is a no-op, a different record under the same id
raises, there's no update or delete path, and SQL triggers refuse UPDATE and
DELETE. The canonical JSON is stored zlib-compressed.
"""

import dataclasses
import hashlib
import json
import sqlite3
import zlib
from dataclasses import dataclass, field
from datetime import datetime

from investment_engine.evaluation.metrics import DirectionEvaluation
from investment_engine.evaluation.returns import ReturnBasis, ReturnObservation
from investment_engine.evaluation.simulation import EvaluationConfig
from investment_engine.evaluation.walk_forward import WalkForwardConfig, WalkForwardResult
from investment_engine.lineage.records import canonical_json, decode, register
from investment_engine.market.availability import check_utc


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
        object.__setattr__(self, "record_id", "eval-" + hashlib.sha256(self.content().encode()).hexdigest())

    def content(self) -> str:
        return canonical_json({f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init})

    @classmethod
    def from_content(cls, content: str) -> "EvaluationRecord":
        return cls(**dict(decode(json.loads(content))))


for _cls in (DirectionEvaluation, ReturnObservation, ReturnBasis, EvaluationRecord):
    register(_cls)


class EvaluationRunConflict(ValueError):
    """A different evaluation record already exists under this id."""


class EvaluationRunStore:
    """Append-only evaluation records over the Operational Database (schema 0003)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, record: EvaluationRecord) -> None:
        if not isinstance(record, EvaluationRecord):
            raise TypeError(f"expected an EvaluationRecord, not {type(record).__name__}")
        content = record.content()
        existing = self._conn.execute("SELECT content FROM evaluation_records WHERE record_id = ?",
                                      (record.record_id,)).fetchone()
        if existing is not None:
            if zlib.decompress(existing[0]).decode() != content:
                raise EvaluationRunConflict(f"{record.record_id} is already recorded with different content")
            return
        self._conn.execute(
            "INSERT INTO evaluation_records (record_id, instrument_id, as_of, content) VALUES (?, ?, ?, ?)",
            (record.record_id, record.instrument_id, record.as_of.isoformat(), zlib.compress(content.encode(), 6)))

    def get(self, record_id: str) -> EvaluationRecord:
        row = self._conn.execute("SELECT content FROM evaluation_records WHERE record_id = ?",
                                 (record_id,)).fetchone()
        if row is None:
            raise KeyError(record_id)
        record = EvaluationRecord.from_content(zlib.decompress(row[0]).decode())
        if record.record_id != record_id:
            raise ValueError(f"stored content for {record_id} hashes to {record.record_id}")
        return record

    def ids(self, instrument_id: str) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT record_id FROM evaluation_records WHERE instrument_id = ? ORDER BY as_of, record_id",
            (instrument_id,))]
