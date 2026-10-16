"""The Operational Database port (docs/tasks/M3-02.md).

One store code base runs on PostgreSQL, the operational database from M3
(ADR-008), and on SQLite, which stays for existing local files and the M1-M2
historical-format tests. Statements are constants in the stores and use named
`:name` parameters; PostgreSQL's adapter translates them to `%(name)s`,
leaving `::` casts and quoted literals alone.

The port owns transactions. Both connections run in autocommit mode, so a read
outside `transaction()` never opens a hidden driver transaction. The outermost
`transaction()` begins and then commits or rolls back. A nested one joins it
without a savepoint, and if a nested scope fails, the whole outermost
transaction rolls back, even when the caller caught the error (it then raises
TransactionAborted). `in_transaction` reports this managed scope only.

Driver errors become the port's own: AppendOnlyViolation for refused changes
to append-only records, IntegrityViolation (kind unique, check, foreign_key or
not_null) for constraint failures. `lock(*names)` serializes on application
keys: transaction advisory locks in ascending key order on PostgreSQL, and a
no-op on SQLite, where BEGIN IMMEDIATE already serializes writers.

Values: SQLite receives dates and datetimes as ISO-8601 text, exactly as M1-M2
stored them, and Decimals as text. PostgreSQL receives native values.
`as_date` and `as_datetime` read either form back.
"""

import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from investment_engine.storage.postgres import (
    AppendOnlyViolation,  # M3-01 contract; driver-free import
)

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class IntegrityViolation(ValueError):
    """A constraint refused the write; `kind` is unique, check, foreign_key, not_null or other."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class TransactionAborted(RuntimeError):
    """A nested scope failed, so the whole outermost transaction was rolled back."""


def _scan(sql: str) -> tuple[str, list[str]]:
    """`sql` with :name placeholders as %(name)s and literal % doubled, and the names found."""
    out, names, i, quote = [], [], 0, None
    while i < len(sql):
        ch = sql[i]
        if quote:
            out.append("%%" if ch == "%" else ch)
            if ch == quote:
                quote = None
            i += 1
        elif ch in "'\"":
            quote = ch
            out.append(ch)
            i += 1
        elif ch == ":" and sql.startswith("::", i):
            out.append("::")
            i += 2
        elif ch == ":" and (m := _NAME.match(sql, i + 1)):
            names.append(m.group())
            out.append(f"%({m.group()})s")
            i = m.end()
        else:
            out.append("%%" if ch == "%" else ch)
            i += 1
    return "".join(out), names


def translate_named(sql: str) -> str:
    """The PostgreSQL (psycopg) form of a statement written with :name parameters."""
    return _scan(sql)[0]


def _check_params(sql: str, params: Mapping[str, object]) -> list[str]:
    names = _scan(sql)[1]
    missing = sorted(set(names) - set(params))
    if missing:
        raise KeyError(f"no value for parameter(s): {', '.join(missing)}")
    return names


class _Base:
    backend: str

    def __init__(self) -> None:
        self._depth = 0
        self._poisoned = False

    @property
    def in_transaction(self) -> bool:
        return self._depth > 0

    @staticmethod
    def as_date(value: object) -> date | None:
        if value is None or (isinstance(value, date) and not isinstance(value, datetime)):
            return value
        return date.fromisoformat(value)

    @staticmethod
    def as_datetime(value: object) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._depth:
            self._depth += 1
            try:
                yield
            except BaseException:
                self._poisoned = True
                raise
            finally:
                self._depth -= 1
            return
        self._depth, self._poisoned = 1, False
        try:
            with self._begin():
                yield
                if self._poisoned:
                    raise TransactionAborted("a nested transaction scope failed; the whole transaction was rolled back")
        finally:
            self._depth, self._poisoned = 0, False

    def fetchone(self, sql: str, params: Mapping[str, object] | None = None) -> tuple | None:
        return self._run(sql, params or {}).fetchone()

    def fetchall(self, sql: str, params: Mapping[str, object] | None = None) -> list[tuple]:
        return list(self._run(sql, params or {}).fetchall())

    def execute(self, sql: str, params: Mapping[str, object] | None = None) -> None:
        self._run(sql, params or {})


class SqliteDatabase(_Base):
    backend: Literal["sqlite"] = "sqlite"

    def __init__(self, conn: sqlite3.Connection) -> None:
        if not isinstance(conn, sqlite3.Connection):
            raise TypeError(f"SqliteDatabase wraps a sqlite3.Connection, not {type(conn).__name__}")
        if conn.isolation_level is not None:
            raise ValueError("the SQLite connection must be in autocommit mode (isolation_level=None)")
        super().__init__()
        self.connection = conn

    @contextmanager
    def _begin(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        self.connection.execute("COMMIT")

    def lock(self, *names: str) -> None:
        if not self.in_transaction:
            raise RuntimeError("locks are taken inside a transaction")

    @staticmethod
    def _value(v: object) -> object:
        if isinstance(v, datetime | date):
            return v.isoformat()
        if isinstance(v, Decimal):
            return str(v)
        return v

    def _run(self, sql: str, params: Mapping[str, object]):
        _check_params(sql, params)
        try:
            return self.connection.execute(sql, {k: self._value(v) for k, v in params.items()})
        except sqlite3.DatabaseError as exc:
            message = str(exc)
            if "append-only" in message:
                raise AppendOnlyViolation(message) from None
            if isinstance(exc, sqlite3.IntegrityError):
                kind = next((k for marker, k in (("UNIQUE", "unique"), ("CHECK", "check"),
                                                 ("FOREIGN KEY", "foreign_key"), ("NOT NULL", "not_null"))
                             if marker in message), "other")
                raise IntegrityViolation(kind, message) from None
            raise


class PostgresDatabase(_Base):
    backend: Literal["postgresql"] = "postgresql"

    def __init__(self, conn) -> None:
        import psycopg

        if not isinstance(conn, psycopg.Connection):
            raise TypeError(f"PostgresDatabase wraps a psycopg.Connection, not {type(conn).__name__}")
        if not conn.autocommit:
            raise ValueError("the PostgreSQL connection must be in autocommit mode (open_operational_pg)")
        super().__init__()
        self.connection = conn

    @contextmanager
    def _begin(self) -> Iterator[None]:
        with self.connection.transaction():
            yield

    def lock(self, *names: str) -> None:
        from investment_engine.storage.postgres import advisory_keys

        if not self.in_transaction:
            raise RuntimeError("locks are taken inside a transaction")
        for key in advisory_keys(*names):
            self.connection.execute("SELECT pg_advisory_xact_lock(%s)", (key,))

    def _run(self, sql: str, params: Mapping[str, object]):
        from psycopg import errors

        names = _check_params(sql, params)
        query, args = (translate_named(sql), dict(params)) if names else (sql, None)
        try:
            return self.connection.execute(query, args)
        except errors.RaiseException as exc:
            if "append-only" in str(exc):
                raise AppendOnlyViolation(str(exc).splitlines()[0]) from None
            raise
        except errors.IntegrityError as exc:
            kind = {errors.UniqueViolation: "unique", errors.CheckViolation: "check",
                    errors.ForeignKeyViolation: "foreign_key", errors.NotNullViolation: "not_null"}.get(type(exc),
                                                                                                   "other")
            raise IntegrityViolation(kind, str(exc).splitlines()[0]) from None
