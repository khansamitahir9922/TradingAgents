"""The SQLite Operational Database (M1-M2; ADR-008) and the reference-data stores.

Schema changes are forward-only numbered scripts (storage/schema/NNNN_*.sql),
each applied atomically together with its schema_version row. From M3 the
operational database is PostgreSQL (storage/postgres.py); SQLite stays for
existing local files and the historical-format tests (docs/tasks/M3-02.md).

The reference-data stores run on either backend through the database port
(storage/database.py); their M1 names are kept. They have no delete path:
instruments change only through update_lifecycle, so an ID is never freed for
reuse (ADR-003). Symbol mappings obey exactly M1-04's rules
(investment_engine.market.symbols), checked inside the inserting transaction,
which first locks both conflict dimensions, so concurrent inserts on
PostgreSQL can't both pass (M3-01 rule 4).
"""

import re
import sqlite3
from dataclasses import replace
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path

from investment_engine.market.instruments import Instrument, InstrumentStatus
from investment_engine.market.symbols import SymbolMapping, UnknownSymbol, conflict, covers
from investment_engine.storage.database import IntegrityViolation

_SCRIPT_NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")


class SchemaVersionError(RuntimeError):
    """The database was written by a newer version of the code."""


def open_operational_db(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the database at `path`, with foreign keys enforced.

    The connection is in autocommit mode; wrap it in storage.database.SqliteDatabase
    for the stores, which own transactions.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


def port(db: object) -> object:
    """A store's database port; a raw driver connection is refused (no compatibility shim, M3-02 rule 5)."""
    if isinstance(db, sqlite3.Connection):
        raise TypeError("pass a database port, not a raw sqlite3.Connection: wrap it in SqliteDatabase(conn)")
    if not all(hasattr(db, name) for name in ("execute", "fetchone", "fetchall", "transaction", "backend")):
        raise TypeError(f"expected a database port (SqliteDatabase or PostgresDatabase), not {type(db).__name__}")
    return db


_INSTRUMENT_COLUMNS = (
    "instrument_id, asset_class, currency, exchange, timezone, status, active_from, active_to"
)


def _instrument(db, row: tuple) -> Instrument:
    instrument_id, asset_class, currency, exchange, timezone, status, active_from, active_to = row
    return Instrument(
        instrument_id=instrument_id,
        asset_class=asset_class,
        currency=currency,
        exchange=exchange,
        timezone=timezone,
        status=status,
        active_from=db.as_date(active_from),
        active_to=db.as_date(active_to),
    )


class SqliteInstrumentRepository:
    """The instrument master. There is deliberately no way to delete an instrument."""

    def __init__(self, db) -> None:
        self._db = port(db)

    def add(self, instrument: Instrument) -> None:
        try:
            with self._db.transaction():
                self._db.execute(
                    f"INSERT INTO instruments ({_INSTRUMENT_COLUMNS}) VALUES (:instrument_id, :asset_class, "
                    ":currency, :exchange, :timezone, :status, :active_from, :active_to)",
                    {
                        "instrument_id": instrument.instrument_id,
                        "asset_class": instrument.asset_class.value,
                        "currency": instrument.currency,
                        "exchange": instrument.exchange,
                        "timezone": instrument.timezone,
                        "status": instrument.status.value,
                        "active_from": instrument.active_from,
                        "active_to": instrument.active_to,
                    },
                )
        except IntegrityViolation as exc:
            if exc.kind == "unique":
                raise ValueError(
                    f"{instrument.instrument_id} is already registered; IDs are never reused"
                ) from exc
            raise ValueError(f"cannot add {instrument.instrument_id}: {exc}") from exc

    def get(self, instrument_id: str) -> Instrument:
        row = self._db.fetchone(
            f"SELECT {_INSTRUMENT_COLUMNS} FROM instruments WHERE instrument_id = :id", {"id": instrument_id}
        )
        if row is None:
            raise KeyError(f"unknown instrument {instrument_id!r}")
        return _instrument(self._db, row)

    def list(self) -> list[Instrument]:
        rows = self._db.fetchall(f"SELECT {_INSTRUMENT_COLUMNS} FROM instruments ORDER BY instrument_id")
        return [_instrument(self._db, row) for row in rows]

    def update_lifecycle(self, instrument_id: str, status: InstrumentStatus, active_to: date | None) -> None:
        """Change only the lifecycle (status and end date), under M1-03's rules."""
        with self._db.transaction():
            updated = replace(self.get(instrument_id), status=status, active_to=active_to)  # validates
            self._db.execute(
                "UPDATE instruments SET status = :status, active_to = :active_to WHERE instrument_id = :id",
                {"status": updated.status.value, "active_to": updated.active_to, "id": instrument_id},
            )


_MAPPING_COLUMNS = "instrument_id, provider, symbol, valid_from, valid_to"


def _mapping(db, row: tuple) -> SymbolMapping:
    instrument_id, provider, symbol, valid_from, valid_to = row
    return SymbolMapping(instrument_id, provider, symbol, db.as_date(valid_from), db.as_date(valid_to))


class SqliteSymbolResolver:
    """Symbol mappings, with the same interface and rules as M1-04's SymbolResolver."""

    def __init__(self, db) -> None:
        self._db = port(db)

    def add(self, mapping: SymbolMapping) -> None:
        with self._db.transaction():
            # Both conflict dimensions, locked in key order before anything is read (Codex M3 review B4).
            self._db.lock(f"map-instrument|{mapping.provider}|{mapping.instrument_id}",
                          f"map-symbol|{mapping.provider}|{mapping.symbol}")
            candidates = [
                _mapping(self._db, row)
                for row in self._db.fetchall(
                    f"SELECT {_MAPPING_COLUMNS} FROM symbol_mappings"
                    " WHERE provider = :provider AND (symbol = :symbol OR instrument_id = :instrument_id)",
                    {"provider": mapping.provider, "symbol": mapping.symbol, "instrument_id": mapping.instrument_id},
                )
            ]
            clash = conflict(mapping, candidates)
            if clash is not None:
                raise ValueError(f"{mapping} overlaps {clash}")
            try:
                self._db.execute(
                    f"INSERT INTO symbol_mappings ({_MAPPING_COLUMNS}) VALUES "
                    "(:instrument_id, :provider, :symbol, :valid_from, :valid_to)",
                    {
                        "instrument_id": mapping.instrument_id,
                        "provider": mapping.provider,
                        "symbol": mapping.symbol,
                        "valid_from": mapping.valid_from,
                        "valid_to": mapping.valid_to,
                    },
                )
            except IntegrityViolation as exc:
                raise ValueError(f"cannot add {mapping}: unknown instrument {mapping.instrument_id}") from exc

    def resolve(self, provider: str, symbol: str, on: date) -> str:
        """The instrument ID `provider` meant by `symbol` on `on`."""
        _plain_date(on, "on")
        rows = self._db.fetchall(
            f"SELECT {_MAPPING_COLUMNS} FROM symbol_mappings WHERE provider = :provider AND symbol = :symbol",
            {"provider": provider, "symbol": symbol},
        )
        for mapping in (_mapping(self._db, row) for row in rows):
            if covers(mapping, on):
                return mapping.instrument_id
        raise UnknownSymbol(f"no {provider} mapping for {symbol!r} on {on}")

    def symbol_for(self, instrument_id: str, provider: str, on: date) -> str:
        """The symbol `provider` used for `instrument_id` on `on`."""
        _plain_date(on, "on")
        rows = self._db.fetchall(
            f"SELECT {_MAPPING_COLUMNS} FROM symbol_mappings WHERE instrument_id = :id AND provider = :provider",
            {"id": instrument_id, "provider": provider},
        )
        for mapping in (_mapping(self._db, row) for row in rows):
            if covers(mapping, on):
                return mapping.symbol
        raise UnknownSymbol(f"no {provider} symbol for {instrument_id} on {on}")
