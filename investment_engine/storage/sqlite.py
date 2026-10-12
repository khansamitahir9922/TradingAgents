"""The Operational Database on SQLite (ADR-008): schema scripts and reference-data stores.

Schema changes are forward-only numbered scripts (storage/schema/NNNN_*.sql),
each applied atomically together with its schema_version row. The stores have
no delete path: instruments change only through update_lifecycle, so an ID
is never freed for reuse (ADR-003). Symbol mappings obey exactly M1-04's
rules (investment_engine.market.symbols), checked inside the inserting
transaction.
"""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path

from investment_engine.market.instruments import Instrument, InstrumentStatus
from investment_engine.market.symbols import SymbolMapping, UnknownSymbol, conflict, covers

_SCRIPT_NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")


class SchemaVersionError(RuntimeError):
    """The database was written by a newer version of the code."""


def open_operational_db(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the database at `path`, with foreign keys enforced.

    The connection is in autocommit mode; writes that must be atomic run in
    an explicit transaction.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _transaction(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _schema_scripts() -> list[tuple[int, str]]:
    scripts = []
    for entry in files("investment_engine.storage").joinpath("schema").iterdir():
        match = _SCRIPT_NAME.fullmatch(entry.name)
        if match:
            scripts.append((int(match[1]), entry.read_text(encoding="utf-8")))
    return sorted(scripts)


def _current_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if not exists:
        return 0
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]


def apply_schema(conn: sqlite3.Connection) -> int:
    """Apply every pending schema script in order; return the resulting version."""
    scripts = _schema_scripts()
    latest = scripts[-1][0] if scripts else 0
    current = _current_version(conn)
    if current > latest:
        raise SchemaVersionError(f"database schema is version {current}; this code knows up to {latest}")
    for number, sql in scripts:
        if number <= current:
            continue
        try:
            conn.executescript(f"BEGIN;\n{sql}\nINSERT INTO schema_version (version) VALUES ({number});\nCOMMIT;")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return max(current, latest)


def _plain_date(value: object, what: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return value


def _iso(d: date | None) -> str | None:
    return None if d is None else d.isoformat()


def _from_iso(text: str | None) -> date | None:
    return None if text is None else date.fromisoformat(text)


_INSTRUMENT_COLUMNS = (
    "instrument_id, asset_class, currency, exchange, timezone, status, active_from, active_to"
)


def _instrument(row: tuple) -> Instrument:
    instrument_id, asset_class, currency, exchange, timezone, status, active_from, active_to = row
    return Instrument(
        instrument_id=instrument_id,
        asset_class=asset_class,
        currency=currency,
        exchange=exchange,
        timezone=timezone,
        status=status,
        active_from=_from_iso(active_from),
        active_to=_from_iso(active_to),
    )


class SqliteInstrumentRepository:
    """The instrument master. There is deliberately no way to delete an instrument."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, instrument: Instrument) -> None:
        try:
            with _transaction(self._conn):
                self._conn.execute(
                    f"INSERT INTO instruments ({_INSTRUMENT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        instrument.instrument_id,
                        instrument.asset_class.value,
                        instrument.currency,
                        instrument.exchange,
                        instrument.timezone,
                        instrument.status.value,
                        _iso(instrument.active_from),
                        _iso(instrument.active_to),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise ValueError(
                    f"{instrument.instrument_id} is already registered; IDs are never reused"
                ) from exc
            raise ValueError(f"cannot add {instrument.instrument_id}: {exc}") from exc

    def get(self, instrument_id: str) -> Instrument:
        row = self._conn.execute(
            f"SELECT {_INSTRUMENT_COLUMNS} FROM instruments WHERE instrument_id = ?", (instrument_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown instrument {instrument_id!r}")
        return _instrument(row)

    def list(self) -> list[Instrument]:
        rows = self._conn.execute(f"SELECT {_INSTRUMENT_COLUMNS} FROM instruments ORDER BY instrument_id")
        return [_instrument(row) for row in rows]

    def update_lifecycle(self, instrument_id: str, status: InstrumentStatus, active_to: date | None) -> None:
        """Change only the lifecycle (status and end date), under M1-03's rules."""
        with _transaction(self._conn):
            updated = replace(self.get(instrument_id), status=status, active_to=active_to)  # validates
            self._conn.execute(
                "UPDATE instruments SET status = ?, active_to = ? WHERE instrument_id = ?",
                (updated.status.value, _iso(updated.active_to), instrument_id),
            )


_MAPPING_COLUMNS = "instrument_id, provider, symbol, valid_from, valid_to"


def _mapping(row: tuple) -> SymbolMapping:
    instrument_id, provider, symbol, valid_from, valid_to = row
    return SymbolMapping(instrument_id, provider, symbol, _from_iso(valid_from), _from_iso(valid_to))


class SqliteSymbolResolver:
    """Symbol mappings in SQLite, with the same interface and rules as M1-04's SymbolResolver."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, mapping: SymbolMapping) -> None:
        with _transaction(self._conn):
            candidates = [
                _mapping(row)
                for row in self._conn.execute(
                    f"SELECT {_MAPPING_COLUMNS} FROM symbol_mappings"
                    " WHERE provider = ? AND (symbol = ? OR instrument_id = ?)",
                    (mapping.provider, mapping.symbol, mapping.instrument_id),
                )
            ]
            clash = conflict(mapping, candidates)
            if clash is not None:
                raise ValueError(f"{mapping} overlaps {clash}")
            try:
                self._conn.execute(
                    f"INSERT INTO symbol_mappings ({_MAPPING_COLUMNS}) VALUES (?, ?, ?, ?, ?)",
                    (
                        mapping.instrument_id,
                        mapping.provider,
                        mapping.symbol,
                        _iso(mapping.valid_from),
                        _iso(mapping.valid_to),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"cannot add {mapping}: unknown instrument {mapping.instrument_id}") from exc

    def resolve(self, provider: str, symbol: str, on: date) -> str:
        """The instrument ID `provider` meant by `symbol` on `on`."""
        _plain_date(on, "on")
        rows = self._conn.execute(
            f"SELECT {_MAPPING_COLUMNS} FROM symbol_mappings WHERE provider = ? AND symbol = ?",
            (provider, symbol),
        )
        for mapping in map(_mapping, rows):
            if covers(mapping, on):
                return mapping.instrument_id
        raise UnknownSymbol(f"no {provider} mapping for {symbol!r} on {on}")

    def symbol_for(self, instrument_id: str, provider: str, on: date) -> str:
        """The symbol `provider` used for `instrument_id` on `on`."""
        _plain_date(on, "on")
        rows = self._conn.execute(
            f"SELECT {_MAPPING_COLUMNS} FROM symbol_mappings WHERE instrument_id = ? AND provider = ?",
            (instrument_id, provider),
        )
        for mapping in map(_mapping, rows):
            if covers(mapping, on):
                return mapping.symbol
        raise UnknownSymbol(f"no {provider} symbol for {instrument_id} on {on}")
