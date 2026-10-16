"""LineageRecord and its append-only store (Part H; ADR-008; docs/tasks/M2-07.md).

A LineageRecord holds everything needed to explain one view: every feature
and health input revision, action references and coverage evidence, feature,
strategy and policy versions, the full DataHealth and its thresholds, the
snapshot, the strategy signals, the decision (before its evidence references
are added), configuration, and the calendar and code versions. Fields for
later milestones are present and None.

Its id is the SHA-256 of canonical JSON of that content: UTC ISO times,
Decimal strings, sorted mappings and explicit type tags, so a record can be
rebuilt exactly and any change gives a different id. The id and the returned
view's evidence references are excluded, so there's no hash recursion.

The store is append-only over the Operational Database (SQLite through M2):
an identical append is a no-op, a different record under the same id raises,
there is no update or delete path, and schema triggers refuse UPDATE and
DELETE. The canonical JSON is stored zlib-compressed.
"""

import dataclasses
import hashlib
import json
import sqlite3
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.market.availability import AvailabilityBasis, check_utc
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
from investment_engine.quant.adjusted import ActionCoverage, ActionRef, AdjustedBasis, BarRef
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import Direction, StrategySignal

# ---------------------------------------------------------------- canonical codec

_DATACLASSES = {cls.__name__: cls for cls in (
    BarRef, ActionRef, ActionCoverage, SourceKey, SourceHealth, Applicability, DataHealth, HealthThresholds,
    FeatureSnapshot, StrategySignal, MarketView)}
_ENUMS = {cls.__name__: cls for cls in (
    Timeframe, AvailabilityBasis, ActionType, HealthStatus, AdjustedBasis, Direction, ViewDirection)}


def register(cls) -> None:
    """Make another frozen dataclass or enum encodable (used by evaluation records)."""
    (_ENUMS if issubclass(cls, Enum) else _DATACLASSES)[cls.__name__] = cls


def encode(value: object) -> object:
    """A JSON-compatible, type-tagged form of `value`, deterministic for equal values."""
    if isinstance(value, Enum):  # before str: StrEnum members are strings too
        name = type(value).__name__
        if _ENUMS.get(name) is not type(value):
            raise TypeError(f"enum {name} is not registered for lineage")
        return {"$enum": name, "v": value.value}
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("lineage refuses non-finite floats")
        return {"$float": repr(value)}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": check_utc(value, "datetime").isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, timedelta):
        return {"$timedelta": [value.days, value.seconds, value.microseconds]}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        name = type(value).__name__
        if _DATACLASSES.get(name) is not type(value):
            raise TypeError(f"{name} is not registered for lineage")
        # Fields added to a class after records were stored are omitted while None ("not recorded"), so a
        # historical record re-encodes to its original canonical payload and id (Codex M2 re-review R1).
        later = getattr(type(value), "LINEAGE_LATER_FIELDS", ())
        return {"$type": name, "fields": {f.name: encode(getattr(value, f.name))
                                          for f in dataclasses.fields(value)
                                          if f.init and not (f.name in later and getattr(value, f.name) is None)}}
    if isinstance(value, Mapping):
        items = [[encode(k), encode(v)] for k, v in value.items()]
        return {"$map": sorted(items, key=lambda kv: json.dumps(kv[0], sort_keys=True))}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    raise TypeError(f"cannot encode {type(value).__name__} in lineage")


def decode(value: object) -> object:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, list):
        return tuple(decode(v) for v in value)
    tag = next(iter(value))
    if tag == "$enum":
        return _ENUMS[value["$enum"]](value["v"])
    if tag == "$float":
        return float(value["$float"])
    if tag == "$decimal":
        return Decimal(value["$decimal"])
    if tag == "$datetime":
        return datetime.fromisoformat(value["$datetime"])
    if tag == "$date":
        return date.fromisoformat(value["$date"])
    if tag == "$timedelta":
        days, seconds, micros = value["$timedelta"]
        return timedelta(days=days, seconds=seconds, microseconds=micros)
    if tag == "$map":
        return MappingProxyType({decode(k): decode(v) for k, v in value["$map"]})
    if tag == "$type":
        cls = _DATACLASSES[value["$type"]]
        return cls(**{k: decode(v) for k, v in value["fields"].items()})
    raise ValueError(f"unknown lineage tag {tag}")


def canonical_json(value: object) -> str:
    return json.dumps(encode(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ---------------------------------------------------------------- the record


@dataclass(frozen=True)
class LineageRecord:
    instrument_id: str
    generated_at: datetime
    bar_refs: tuple[BarRef, ...]  # complete feature and health input identities
    action_refs: tuple[ActionRef, ...]
    action_coverage: ActionCoverage  # including verified-empty coverage evidence
    feature_versions: Mapping[str, str]
    strategy_versions: Mapping[str, str]
    policy_version: str
    data_health: DataHealth  # full immutable result, reasons, age, gaps, T
    health_thresholds: HealthThresholds
    snapshot: FeatureSnapshot  # values and unavailable/warm-up reasons
    signals: tuple[StrategySignal | None, ...]
    decision: MarketView  # before adding evidence_refs; includes ABSTAIN
    config: Mapping[str, object]  # validated immutable policy/feature parameters
    calendar_version: str
    code_version: str  # investment_engine.__version__ plus the git commit if known, supplied by the caller
    research_run: None = None
    model_version: None = None
    portfolio_snapshot: None = None
    risk_versions: None = None
    lineage_id: str = field(init=False)

    def __post_init__(self) -> None:
        check_utc(self.generated_at, "generated_at")
        for name in ("policy_version", "calendar_version", "code_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if self.decision.evidence_refs:
            raise ValueError("the recorded decision is the view before its evidence references are added")
        if (self.decision.generated_at, self.snapshot.as_of, self.data_health.as_of) != (self.generated_at,) * 3:
            raise ValueError("decision, snapshot and DataHealth must share the record's T")
        if self.decision.instrument_id != self.instrument_id or self.snapshot.instrument_id != self.instrument_id:
            raise ValueError("decision and snapshot must be for the record's instrument")
        if any(getattr(self, n) is not None for n in ("research_run", "model_version", "portfolio_snapshot",
                                                      "risk_versions")):
            raise ValueError("research, model, portfolio and risk lineage belong to later milestones")
        for name in ("feature_versions", "strategy_versions"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        # Normalized through the codec, so a rebuilt record compares equal (lists become tuples).
        object.__setattr__(self, "config", decode(encode(dict(self.config))))
        object.__setattr__(self, "lineage_id", "lin-" + hashlib.sha256(self.content().encode()).hexdigest())

    def content(self) -> str:
        """The canonical JSON the id hashes: every field except the id itself."""
        return canonical_json({f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init})

    @classmethod
    def from_content(cls, content: str) -> "LineageRecord":
        fields_ = decode(json.loads(content))
        return cls(**dict(fields_))


# ---------------------------------------------------------------- the store


class LineageConflict(ValueError):
    """A different record already exists under this lineage id."""


class LineageStore:
    """Append-only lineage over the Operational Database (schema 0002)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, record: LineageRecord) -> None:
        if not isinstance(record, LineageRecord):
            raise TypeError(f"expected a LineageRecord, not {type(record).__name__}")
        content = record.content()
        blob = zlib.compress(content.encode(), 6)
        existing = self._conn.execute("SELECT content FROM lineage_records WHERE lineage_id = ?",
                                      (record.lineage_id,)).fetchone()
        if existing is not None:
            if zlib.decompress(existing[0]).decode() != content:
                raise LineageConflict(f"{record.lineage_id} is already recorded with different content")
            return
        self._conn.execute(
            "INSERT INTO lineage_records (lineage_id, instrument_id, generated_at, content) VALUES (?, ?, ?, ?)",
            (record.lineage_id, record.instrument_id, record.generated_at.isoformat(), blob))

    def get(self, lineage_id: str) -> LineageRecord:
        row = self._conn.execute("SELECT content FROM lineage_records WHERE lineage_id = ?",
                                 (lineage_id,)).fetchone()
        if row is None:
            raise KeyError(lineage_id)
        record = LineageRecord.from_content(zlib.decompress(row[0]).decode())
        if record.lineage_id != lineage_id:
            raise ValueError(f"stored content for {lineage_id} hashes to {record.lineage_id}")
        return record

    def ids(self, instrument_id: str) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT lineage_id FROM lineage_records WHERE instrument_id = ? ORDER BY generated_at, lineage_id",
            (instrument_id,))]
