"""Copying an M1-M2 SQLite Operational Database into PostgreSQL, and the CLI on PostgreSQL (docs/tasks/M3-03.md)."""

import base64
import hashlib
import json
import subprocess
import sys
import zlib
from datetime import date, datetime

import pytest
from typer.testing import CliRunner

from investment_engine.config import ENV_PG_DSN, operational_db_dsn
from investment_engine.evaluation.run_store import EvaluationRunStore
from investment_engine.lineage.records import LineageStore
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.symbols import SymbolMapping
from investment_engine.storage.copy_sqlite import CopyConflict, copy_sqlite_to_postgres
from investment_engine.storage.database import PostgresDatabase, SqliteDatabase
from investment_engine.storage.postgres import (
    _pg_schema_scripts,
    apply_pg_schema,
    open_operational_pg,
)
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)
from tests.engine.test_evaluation_run_store import (
    OLD_FORMAT,
    record as evaluation_record,
    with_audit,
)
from tests.engine.test_lineage import record as lineage_record
from tests.engine.test_sqlite_store import SCHEMA_SCRIPTS, instrument

pytestmark = pytest.mark.postgres
CAL = load_us_equities_calendar()
CALENDARS = {"test-cal": CAL}
RUNNER = CliRunner()
LATEST_PG = _pg_schema_scripts()[-1][0]  # later M3 scripts add PostgreSQL-only tables


def source_at(path, schema: int):
    """An SQLite file at `schema`, filled the way M1-M2 code filled it."""
    conn = open_operational_db(path)
    for number, script in enumerate(SCHEMA_SCRIPTS[:schema], start=1):
        conn.executescript(f"BEGIN;\n{script.read_text(encoding='utf-8')}\nINSERT INTO schema_version (version) "
                           f"VALUES ({number});\nCOMMIT;")
    db = SqliteDatabase(conn)
    SqliteInstrumentRepository(db).add(instrument())
    SqliteSymbolResolver(db).add(SymbolMapping("EQ_US_NVDA", "yfinance", "NVDA", date(2019, 1, 1), None))
    ids = {}
    if schema >= 2:
        lin = lineage_record()
        LineageStore(db).append(lin)
        ids["lineage"] = lin.lineage_id
    if schema >= 3:
        fixture = json.loads(OLD_FORMAT.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO evaluation_records VALUES (?, ?, ?, ?)", (
            fixture["record_id"], fixture["instrument_id"], fixture["as_of"],
            base64.b64decode(fixture["content_zlib_b64"])))  # the genuine 57d4316 format
        current = with_audit(evaluation_record())
        EvaluationRunStore(db, calendars=CALENDARS).append(current)  # the current format
        ids["evaluation"] = (fixture["record_id"], current.record_id)
    conn.close()
    return ids


@pytest.fixture
def target(pg_database):
    conn = open_operational_pg(pg_database)
    yield PostgresDatabase(conn)
    conn.close()


def digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(db) -> dict[str, int]:
    return {t: db.fetchone(f"SELECT COUNT(*) FROM {t}")[0]
            for t in ("instruments", "symbol_mappings", "lineage_records", "evaluation_records")}


@pytest.mark.unit
def test_a_full_m2_database_copies_exactly_and_a_rerun_finds_everything_present(tmp_path, target):
    path = tmp_path / "op.sqlite3"
    ids = source_at(path, 4)
    before = digest(path)
    report = copy_sqlite_to_postgres(path, target, calendars=CALENDARS)
    assert (report.source_schema, report.target_schema) == (4, LATEST_PG)
    assert dict(report.copied) == {"instruments": 1, "symbol_mappings": 1, "lineage_records": 1,
                                   "evaluation_records": 2}
    assert report.verified_ids == 3
    lite = open_operational_db(path)
    for table, key in (("lineage_records", "lineage_id"), ("evaluation_records", "record_id")):
        for record_id, blob in lite.execute(f"SELECT {key}, content FROM {table}"):
            assert bytes(target.fetchone(f"SELECT content FROM {table} WHERE {key} = :id", {"id": record_id})[0]) == blob
    lite.close()
    assert LineageStore(target).get(ids["lineage"]).lineage_id == ids["lineage"]
    old, current = ids["evaluation"]
    store = EvaluationRunStore(target, calendars=CALENDARS)
    assert store.get(old).record_id == old and store.get(current).record_id == current  # both formats (R1)
    again = copy_sqlite_to_postgres(path, target, calendars=CALENDARS)
    assert sum(again.copied.values()) == 0 and dict(again.already_present) == dict(report.copied)
    assert digest(path) == before  # the source is never changed


@pytest.mark.unit
@pytest.mark.parametrize("schema, expected", [
    (1, {"instruments": 1, "symbol_mappings": 1, "lineage_records": 0, "evaluation_records": 0}),
    (2, {"instruments": 1, "symbol_mappings": 1, "lineage_records": 1, "evaluation_records": 0}),
    (3, {"instruments": 1, "symbol_mappings": 1, "lineage_records": 1, "evaluation_records": 2}),
])
def test_older_source_schemas_copy_with_missing_tables_counted_as_zero(tmp_path, target, schema, expected):
    path = tmp_path / "op.sqlite3"
    source_at(path, schema)
    before = digest(path)
    report = copy_sqlite_to_postgres(path, target, calendars=CALENDARS)
    assert report.source_schema == schema and dict(report.copied) == expected
    assert counts(target) == expected and digest(path) == before


@pytest.mark.unit
def test_a_newer_source_schema_is_refused(tmp_path, target):
    path = tmp_path / "op.sqlite3"
    source_at(path, 4)
    conn = open_operational_db(path)
    conn.execute("INSERT INTO schema_version (version) VALUES (5)")
    conn.close()
    with pytest.raises(ValueError, match="schema 5"):
        copy_sqlite_to_postgres(path, target, calendars=CALENDARS)


@pytest.mark.unit
def test_a_conflicting_target_row_aborts_with_nothing_copied(tmp_path, target):
    path = tmp_path / "op.sqlite3"
    ids = source_at(path, 4)
    apply_pg_schema(target.connection)
    target.execute("INSERT INTO lineage_records VALUES (:id, 'EQ_US_NVDA', :at, :c)",
                   {"id": ids["lineage"], "at": datetime(2024, 1, 1).astimezone(), "c": zlib.compress(b"{}")})
    with pytest.raises(CopyConflict, match=ids["lineage"]):
        copy_sqlite_to_postgres(path, target, calendars=CALENDARS)
    assert counts(target) == {"instruments": 0, "symbol_mappings": 0, "lineage_records": 1, "evaluation_records": 0}


@pytest.mark.unit
def test_a_corrupted_source_record_aborts_with_nothing_copied(tmp_path, target):
    path = tmp_path / "op.sqlite3"
    ids = source_at(path, 4)
    conn = open_operational_db(path)
    text = zlib.decompress(conn.execute("SELECT content FROM lineage_records").fetchone()[0]).decode()
    conn.execute("DROP TRIGGER lineage_records_no_update")  # simulate damage written outside the store
    conn.execute("UPDATE lineage_records SET content = ?", (zlib.compress(text.replace("EQ_US_NVDA", "EQ_US_NVDB", 1).encode()),))
    conn.close()
    with pytest.raises(ValueError, match="hashes to"):
        copy_sqlite_to_postgres(path, target, calendars=CALENDARS)
    assert sum(counts(target).values()) == 0
    assert ids


@pytest.mark.unit
def test_an_unsupported_calendar_version_aborts_and_is_named(tmp_path, target):
    path = tmp_path / "op.sqlite3"
    source_at(path, 4)
    with pytest.raises(ValueError, match="test-cal"):
        copy_sqlite_to_postgres(path, target, calendars={"us-equities-other": CAL})
    assert sum(counts(target).values()) == 0


# ---------------------------------------------------------------- the CLI on PostgreSQL


@pytest.fixture
def cli_env(pg_database, tmp_path, monkeypatch):
    from investment_engine import cli

    monkeypatch.setenv(ENV_PG_DSN, pg_database)
    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path / "data"))
    return cli, pg_database


@pytest.mark.unit
def test_an_unset_dsn_explains_without_echoing_anything(monkeypatch):
    from investment_engine import cli

    monkeypatch.delenv(ENV_PG_DSN, raising=False)
    with pytest.raises(RuntimeError, match="docs/dev/postgresql.md"):
        operational_db_dsn()
    result = RUNNER.invoke(cli.app, ["db", "status"])
    assert result.exit_code != 0 and ENV_PG_DSN in result.output and "docs/dev/postgresql.md" in result.output


@pytest.mark.unit
def test_init_status_and_copy_work_on_postgresql_and_never_print_the_dsn(cli_env, tmp_path):
    cli, dsn = cli_env
    from psycopg.conninfo import conninfo_to_dict

    password = conninfo_to_dict(dsn).get("password")
    init = RUNNER.invoke(cli.app, ["init"])
    assert init.exit_code == 0, init.output
    status = RUNNER.invoke(cli.app, ["db", "status"])
    assert status.exit_code == 0 and f"schema={LATEST_PG}" in status.output and "instruments=1" in status.output
    path = tmp_path / "old.sqlite3"
    conn = open_operational_db(path)
    apply_schema(conn)
    LineageStore(SqliteDatabase(conn)).append(lineage_record())
    conn.close()
    copied = RUNNER.invoke(cli.app, ["db", "copy-from-sqlite", str(path)])
    assert copied.exit_code == 0, copied.output
    assert "lineage_records=1" in copied.output
    for output in (init.output, status.output, copied.output):
        assert (password is None or password not in output) and "dbname=" not in output


@pytest.mark.unit
def test_the_base_install_imports_the_cli_and_asks_for_the_engine_extra(tmp_path):
    """Without psycopg, `--help` works and a PostgreSQL command names the extra (M3-03 rule 8)."""
    probe = (
        "import builtins, sys\n"
        "real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name.split('.')[0] == 'psycopg':\n"
        "        raise ModuleNotFoundError(\"No module named 'psycopg'\", name='psycopg')\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        "from typer.testing import CliRunner\n"
        "from investment_engine import cli\n"
        "r = CliRunner()\n"
        "h = r.invoke(cli.app, ['--help'])\n"
        "s = r.invoke(cli.app, ['db', 'status'], env={'INVESTMENT_ENGINE_PG_DSN': 'host=localhost dbname=x'})\n"
        "print(h.exit_code, s.exit_code)\n"
        "print(s.output)\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120,
                         cwd=str(tmp_path), env={"PYTHONPATH": str(__import__("pathlib").Path(__file__).parents[2]),
                                                 "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert out.returncode == 0, out.stderr
    codes, message = out.stdout.split("\n", 1)
    assert codes.split() == ["0", "1"]
    assert '.[engine]' in message
