"""Copy an M1-M2 SQLite Operational Database into PostgreSQL (docs/tasks/M3-03.md).

The source file is opened read-only and never changed. Instruments, symbol
mappings, lineage records and evaluation records are copied with identical
ids, and record content is copied byte for byte. Every copied record is then
read back through its store on PostgreSQL and must hash to its id, in both
evaluation formats (the M2 R1 rule). Evaluation records are read back with the
supplied calendars, so a record labelled with a calendar version that isn't
supplied aborts the copy; a current calendar is never bound to an old name.

Everything happens in one target transaction. A row already present with
identical content counts as present. A different row under the same key, an
overlapping mapping, a corrupted source record or an unknown calendar aborts
the whole copy, and nothing is written. Running it again is safe.

Source schemas 1-4 are accepted. Tables a schema doesn't have yet (no lineage
before 2, no evaluation records before 3) count as zero.
"""

import sqlite3
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from investment_engine.evaluation.run_store import EvaluationRunStore
from investment_engine.lineage.records import LineageStore
from investment_engine.market.symbols import SymbolMapping
from investment_engine.storage.database import SqliteDatabase
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    _current_version,
)

TABLES = ("instruments", "symbol_mappings", "lineage_records", "evaluation_records")
SUPPORTED_SOURCE = range(1, 5)


class CopyConflict(ValueError):
    """The target already holds a different row under a key being copied; nothing was copied."""


@dataclass(frozen=True)
class CopyReport:
    source_path: Path
    source_schema: int
    target_schema: int
    copied: Mapping[str, int]
    already_present: Mapping[str, int]
    verified_ids: int


def _source(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"no SQLite file at {path}")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None)


def copy_sqlite_to_postgres(sqlite_path: Path, target, *, calendars: Mapping[str, object]) -> CopyReport:
    from investment_engine.storage.postgres import apply_pg_schema

    if getattr(target, "backend", None) != "postgresql":
        raise TypeError("the copy's target is a PostgresDatabase")
    raw = _source(Path(sqlite_path))
    try:
        schema = _current_version(raw)
        if schema not in SUPPORTED_SOURCE:
            raise ValueError(f"source is at schema {schema}; this copy supports SQLite schemas 1-4")
        source = SqliteDatabase(raw)
        target_schema = apply_pg_schema(target.connection)
        copied = dict.fromkeys(TABLES, 0)
        present = dict.fromkeys(TABLES, 0)
        verified = 0
        with target.transaction():
            _instruments(source, target, copied, present)
            _mappings(source, target, copied, present)
            if schema >= 2:
                verified += _records(source, target, "lineage_records", "lineage_id", "generated_at", copied, present,
                                     LineageStore(target).get)
            if schema >= 3:
                store = EvaluationRunStore(target, calendars=calendars)
                verified += _records(source, target, "evaluation_records", "record_id", "as_of", copied, present,
                                     store.get)
        return CopyReport(Path(sqlite_path), schema, target_schema, MappingProxyType(copied),
                          MappingProxyType(present), verified)
    finally:
        raw.close()


def _instruments(source, target, copied, present) -> None:
    source_repo, target_repo = SqliteInstrumentRepository(source), SqliteInstrumentRepository(target)
    for instrument in source_repo.list():
        try:
            existing = target_repo.get(instrument.instrument_id)
        except KeyError:
            target_repo.add(instrument)
            copied["instruments"] += 1
            continue
        if existing != instrument:
            raise CopyConflict(f"instrument {instrument.instrument_id} differs in the target; nothing copied")
        present["instruments"] += 1


def _mappings(source, target, copied, present) -> None:
    columns = "instrument_id, provider, symbol, valid_from, valid_to"
    resolver = SqliteSymbolResolver(target)
    for row in source.fetchall(f"SELECT {columns} FROM symbol_mappings ORDER BY provider, symbol, valid_from"):
        mapping = SymbolMapping(row[0], row[1], row[2], source.as_date(row[3]), source.as_date(row[4]))
        existing = target.fetchone(
            f"SELECT {columns} FROM symbol_mappings WHERE provider = :provider AND symbol = :symbol "
            "AND valid_from = :valid_from",
            {"provider": mapping.provider, "symbol": mapping.symbol, "valid_from": mapping.valid_from})
        if existing is not None:
            stored = SymbolMapping(existing[0], existing[1], existing[2], target.as_date(existing[3]),
                                   target.as_date(existing[4]))
            if stored != mapping:
                raise CopyConflict(f"mapping {mapping} differs in the target; nothing copied")
            present["symbol_mappings"] += 1
            continue
        try:
            resolver.add(mapping)
        except ValueError as exc:
            raise CopyConflict(f"mapping {mapping} conflicts in the target ({exc}); nothing copied") from exc
        copied["symbol_mappings"] += 1


def _records(source, target, table, key, time_column, copied, present, read_back) -> int:
    rows = source.fetchall(f"SELECT {key}, instrument_id, {time_column}, content FROM {table} ORDER BY {key}")
    for record_id, instrument_id, at, blob in rows:
        blob = bytes(blob)
        existing = target.fetchone(f"SELECT content FROM {table} WHERE {key} = :id", {"id": record_id})
        if existing is not None:
            if zlib.decompress(bytes(existing[0])) != zlib.decompress(blob):
                raise CopyConflict(f"{record_id} is stored in the target with different content; nothing copied")
            present[table] += 1
            continue
        target.execute(f"INSERT INTO {table} ({key}, instrument_id, {time_column}, content) "
                       "VALUES (:id, :instrument_id, :at, :content)",
                       {"id": record_id, "instrument_id": instrument_id, "at": datetime.fromisoformat(at),
                        "content": blob})
        copied[table] += 1
    for record_id, *_ in rows:
        read_back(record_id)  # raises unless the stored content hashes to its id (and, for evaluations, its calendar)
    return len(rows)
