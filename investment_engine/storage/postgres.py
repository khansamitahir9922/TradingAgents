"""The Operational Database on PostgreSQL from M3 (ADR-008; docs/tasks/M3-01.md).

Schema scripts live in storage/schema_pg/NNNN_*.sql, numbered like the SQLite
track: PostgreSQL version N has the tables, columns, keys and checks of
SQLite version N, with native types (DATE, TIMESTAMPTZ, BYTEA, NUMERIC). Each
script runs in one transaction together with its schema_version row, and a
database newer than the code is refused.

Connections are opened in autocommit mode, so a read never starts a hidden
transaction; transactions are owned by the database port (M3-02). The session
time zone is UTC.

Advisory-lock keys are the first 8 bytes of SHA-256 of a name, as a signed
64-bit integer. Callers take several in ascending order (advisory_keys), so
two transactions can never wait on each other in opposite orders. A hash
collision only adds serialization; it never lets a conflict through.

psycopg is imported only here and in the other storage modules (M3-00 rule 5),
and only inside the functions that connect: AppendOnlyViolation is shared with
the SQLite path, so importing this module must not need the driver (the
`engine` extra) or create an import cycle with storage.sqlite.
"""

import hashlib
import re
from importlib.resources import files
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

_SCRIPT_NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")


class AppendOnlyViolation(RuntimeError):
    """A write that would change or remove an append-only record was refused."""


def open_operational_pg(dsn: str) -> "psycopg.Connection":
    """Connect to the Operational Database at `dsn` (never logged), in autocommit mode with UTC session time."""
    import psycopg

    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute("SET TIME ZONE 'UTC'")
    return conn


def _pg_schema_scripts() -> list[tuple[int, str]]:
    scripts = []
    for entry in files("investment_engine.storage").joinpath("schema_pg").iterdir():
        match = _SCRIPT_NAME.fullmatch(entry.name)
        if match:
            scripts.append((int(match[1]), entry.read_text(encoding="utf-8")))
    return sorted(scripts)


def _current_version(conn: "psycopg.Connection") -> int:
    if conn.execute("SELECT to_regclass('public.schema_version')").fetchone()[0] is None:
        return 0
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]


def apply_pg_schema(conn: "psycopg.Connection") -> int:
    """Apply every pending schema script in order, each atomically; return the resulting version."""
    from investment_engine.storage.sqlite import SchemaVersionError

    scripts = _pg_schema_scripts()
    latest = scripts[-1][0] if scripts else 0
    current = _current_version(conn)
    if current > latest:
        raise SchemaVersionError(f"database schema is version {current}; this code knows up to {latest}")
    for number, sql in scripts:
        if number <= current:
            continue
        with conn.transaction():
            conn.execute(sql)
            conn.execute("INSERT INTO schema_version (version) VALUES (%s)", (number,))
    return max(current, latest)


def connection_lost_errors() -> tuple[type[BaseException], ...]:
    """The driver's errors for a lost or unusable connection: the role loops rebuild their connections on these and
    on nothing else (Codex M4 review B4). Only this package imports the driver."""
    import psycopg

    return (psycopg.OperationalError, psycopg.InterfaceError)


def advisory_key(name: str) -> int:
    """A transaction advisory-lock key for `name`: SHA-256's first 8 bytes as a signed 64-bit integer."""
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big", signed=True)


def advisory_keys(*names: str) -> list[int]:
    """The distinct keys for `names`, in the ascending order every caller must acquire them in."""
    return sorted({advisory_key(n) for n in names})
