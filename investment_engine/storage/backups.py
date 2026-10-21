"""Verified local PostgreSQL dumps and later immutable market-file supersets.

No scheduler is installed. Restore targets must be explicitly disposable,
empty local test databases. Credentials travel only in private libpq environment
variables, never argv, manifests, error text or copied files.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path

from investment_engine.storage.postgres import open_operational_pg


class BackupError(RuntimeError):
    """A sanitized failure; partial jobs remain on disk and never claim success."""


def _sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _closed(path):
    if path.stat().st_size < 12:
        raise BackupError("market artifact is not a closed supported Parquet file")
    with path.open("rb") as stream:
        first = stream.read(4)
        stream.seek(-4, 2)
        last = stream.read(4)
    if first != b"PAR1" or last != b"PAR1":
        raise BackupError("market artifact is not a closed supported Parquet file")


def _safe(root, relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in ("..", ".") for p in path.parts):
        raise BackupError("unsafe backup relative path")
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise BackupError("backup path escapes its root")
    return target


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)


def _params(dsn, *, disposable=False):
    from psycopg.conninfo import conninfo_to_dict
    # Same explicit-key/single-loopback policy as the repository PostgreSQL
    # test guard. Native tools get a separately pinned environment as well.
    allowed = {"host", "port", "dbname", "user", "password", "connect_timeout", "application_name", "sslmode"}
    loopback = {"localhost":"127.0.0.1", "127.0.0.1":"127.0.0.1", "::1":"::1"}
    try:
        params = conninfo_to_dict(dsn)
    except Exception:
        raise BackupError("connection settings could not be parsed") from None
    if set(params)-allowed or params.get("host") not in loopback or not params.get("port", "5432").isdigit():
        raise BackupError("only explicit single-loopback connection settings are accepted")
    if any(k.upper().startswith("PG") for k in os.environ):
        raise BackupError("clear ambient libpq PG variables before backup/restore verification")
    if not params.get("dbname") or not params.get("user"):
        raise BackupError("explicit database and user are required")
    if disposable and re.fullmatch(r"ie_test_[0-9a-f]{16}", params["dbname"]) is None:
        raise BackupError("restore target must be a generated disposable test database")
    params["host"] = loopback[params["host"]]
    return params


def _env(params, directory):
    runtime = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "TZ"}
    env = {k:v for k,v in os.environ.items() if k.upper() in runtime}
    names = {"host":"PGHOST", "port":"PGPORT", "dbname":"PGDATABASE", "user":"PGUSER", "password":"PGPASSWORD",
             "connect_timeout":"PGCONNECT_TIMEOUT", "application_name":"PGAPPNAME", "sslmode":"PGSSLMODE"}
    env.update({names[k]:str(v) for k,v in params.items()})
    env.update(PGHOSTADDR=params["host"], PGCONNECT_TIMEOUT=params.get("connect_timeout", "5"),
               PGPASSFILE=str(directory/"no-password-file"), PGCLIENTENCODING="UTF8")
    return env


def _run(command, *, env):
    try:
        value = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=120, check=False)
    except Exception:
        raise BackupError("PostgreSQL tool could not complete") from None
    if value.returncode:
        raise BackupError("PostgreSQL tool failed; no successful result established")
    return value.stdout


def _tools(pg_bin, env):
    paths = [Path(pg_bin)/name for name in ("pg_dump.exe", "pg_restore.exe")]
    versions = []
    for path in paths:
        if not path.is_file():
            raise BackupError("required PostgreSQL tools unavailable")
        text = _run([str(path), "--version"], env=env).strip()
        match = re.fullmatch(r"pg_(?:dump|restore) \(PostgreSQL\) (17\.\d+)(?:.*)", text)
        if match is None:
            raise BackupError("verified PostgreSQL 17 tools required")
        versions.append(match[1])
    return (*paths, versions)


def _untag(value):
    if isinstance(value, dict):
        if "$type" in value:
            return {"record_type":value["$type"], **{k:_untag(v) for k,v in value["fields"].items()}}
        if "$map" in value:
            return {str(_untag(k)):_untag(v) for k,v in value["$map"]}
        if "$enum" in value:
            return value["v"]
        for tag in ("$datetime", "$date", "$decimal", "$float"):
            if tag in value:
                return value[tag]
        return {k:_untag(v) for k,v in value.items()}
    if isinstance(value, list):
        return [_untag(v) for v in value]
    return value


def _references(value, found, depth=0):
    if depth > 80:
        raise BackupError("source reference nesting is unsupported")
    if isinstance(value, bytes | memoryview):
        raw = bytes(value)
        try:
            value = zlib.decompress(raw).decode("utf-8")
        except (zlib.error, UnicodeError):
            try:
                value = raw.decode("utf-8")
            except UnicodeError:
                return
    if isinstance(value, str):
        if value.startswith(("{", "[")):
            try:
                _references(_untag(json.loads(value)), found, depth+1)
            except json.JSONDecodeError:
                return
        return
    if isinstance(value, dict):
        source = value.get("source", value.get("provider"))
        instrument = value.get("instrument_id", value.get("instrument"))
        ref = None
        if {"import_id", "revision"} <= value.keys() and source and instrument:
            if "timeframe" in value and ("start_time" in value or "start" in value):
                ref = {"kind":"candle", "source":source, "instrument_id":instrument, "timeframe":value["timeframe"],
                       "start_time":value.get("start_time",value.get("start")), "revision":value["revision"], "import_id":value["import_id"]}
            elif "ex_date" in value and "action_type" in value:
                ref = {"kind":"action", "source":source, "instrument_id":instrument, "action_type":value["action_type"],
                       "ex_date":value["ex_date"], "revision":value["revision"], "import_id":value["import_id"]}
        if value.get("record_type") == "SourceRef" and value.get("kind") in ("action", "mark"):
            parts = value["identity"].split("/")
            if value["kind"] == "action":
                ref = {"kind":"action", "source":parts[0], "instrument_id":parts[1], "action_type":parts[2],
                       "ex_date":parts[3], "revision":value["revision"], "import_id":value["stored_record_id"].split("/")[-1]}
            else:
                ref = {"kind":"candle", "source":parts[0], "instrument_id":parts[1], "timeframe":parts[2],
                       "start_time":parts[3], "revision":value["revision"], "import_id":value["stored_record_id"].split("/")[0]}
        if ref is not None:
            found[json.dumps(ref,sort_keys=True)] = ref
        for part in value.values():
            _references(part, found, depth+1)
    elif isinstance(value, tuple | list):
        for part in value:
            _references(part, found, depth+1)


def _database_state(conn, *, collect=False):
    from psycopg import sql
    state, refs = {}, {}
    tables = conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT LIKE 'pg_%' AND schemaname<>'information_schema' ORDER BY schemaname,tablename").fetchall()
    for schema, table in tables:
        name = sql.Identifier(schema, table)
        rows = conn.execute(sql.SQL("SELECT row_to_json(t)::text FROM {} t").format(name)).fetchall()
        values = sorted(row[0] for row in rows)
        state[f"{schema}.{table}"] = {"count":len(values), "sha256":hashlib.sha256("\n".join(values).encode()).hexdigest()}
        if collect:
            for row in conn.execute(sql.SQL("SELECT * FROM {}").format(name)):
                _references(row, refs)
    return state, [refs[k] for k in sorted(refs)]


def _check_references(root, references):
    if not references:
        return
    from investment_engine.market.candles import Timeframe
    from investment_engine.market.corporate_actions import ActionType
    from investment_engine.market.store.reader import MarketDataReader
    reader = MarketDataReader(root)
    for ref in references:
        if ref["kind"] == "candle":
            start = datetime.fromisoformat(ref["start_time"])
            rows = reader.candle_revision_history(ref["source"], ref["instrument_id"], Timeframe(ref["timeframe"]), start, start+timedelta(microseconds=1))
            rows = [r for r in rows if r.start_time == start and r.timeframe is Timeframe(ref["timeframe"])]
        else:
            day = date.fromisoformat(ref["ex_date"])
            rows = reader.action_revision_history(ref["source"], ref["instrument_id"], day, day+timedelta(days=1), types=(ActionType(ref["action_type"]),))
            rows = [r for r in rows if r.ex_date == day and r.action_type is ActionType(ref["action_type"])]
        if not any((r.source,r.instrument_id,r.revision,r.import_id) ==
                   (ref["source"],ref["instrument_id"],ref["revision"],ref["import_id"]) for r in rows):
            raise BackupError("a database market reference has no copied source revision")


def create_backup(dsn, *, destination, market_root, clock, pg_bin):
    from psycopg.conninfo import make_conninfo
    destination, market_root = Path(destination), Path(market_root)
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except OSError:
        raise BackupError("backup destination must be new; existing evidence was not overwritten") from None
    started = clock.now().isoformat()
    _write(destination/"started.json", {"status":"INCOMPLETE", "started_at":started})
    try:
        params = _params(dsn)
        env = _env(params, destination)
        dump, restore, versions = _tools(pg_bin, env)
        with open_operational_pg(make_conninfo("", **params)) as conn, conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if int(conn.execute("SHOW server_version_num").fetchone()[0])//10000 != 17:
                raise BackupError("PostgreSQL server/tool major versions differ")
            snapshot = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
            _run([str(dump), "--format=custom", "--no-password", "--snapshot="+snapshot,
                  "--file="+str(destination/"database.dump")], env=env)
            tables, references = _database_state(conn, collect=True)
        dumped = clock.now().isoformat()
        _run([str(restore), "--list", str(destination/"database.dump")], env=env)
        files = []
        if market_root.exists():
            for source in sorted(market_root.rglob("*.parquet")):
                if not source.resolve().is_relative_to(market_root.resolve()):
                    raise BackupError("market source path escapes its root")
                _closed(source)
                relative = source.relative_to(market_root)
                target = _safe(destination/"market", relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                before = _sha(source)
                shutil.copyfile(source, target)
                if _sha(target) != before or _sha(source) != before:
                    raise BackupError("immutable market source changed or copy integrity failed")
                files.append({"path":relative.as_posix(), "sha256":before, "size":target.stat().st_size})
        _check_references(destination/"market", references)
        manifest = {"version":1, "status":"SUCCESS", "started_at":started, "dump_finished_at":dumped,
            "finished_at":clock.now().isoformat(), "tools":versions,
            "consistency":"POSTGRES_EXPORTED_SNAPSHOT_WITH_LATER_IMMUTABLE_MARKET_SUPERSET",
            "dump":{"path":"database.dump", "sha256":_sha(destination/"database.dump")},
            "tables":tables, "market_references":references, "market_files":files,
            "excluded":"credentials, environment/secrets files, kill-switch flag/journal, application logs",
            "retention":"retain all jobs; no automatic deletion; same-disk copy does not protect against disk loss"}
        _write(destination/"manifest.json", manifest)
        return verify_backup(destination)
    except Exception as exc:
        _write(destination/"failed.json", {"status":"FAILED", "started_at":started, "finished_at":clock.now().isoformat(),
                                           "reason":"backup verification failed", "error_type":type(exc).__name__})
        raise BackupError("backup failed; partial evidence retained, no verified result") from None


def verify_backup(destination):
    destination = Path(destination)
    try:
        manifest = json.loads((destination/"manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "SUCCESS" or manifest.get("version") != 1 or (destination/"failed.json").exists():
            raise BackupError("backup is incomplete or failed")
        if _sha(_safe(destination, manifest["dump"]["path"])) != manifest["dump"]["sha256"]:
            raise BackupError("dump hash integrity failed")
        for entry in manifest["market_files"]:
            path = _safe(destination/"market", entry["path"])
            _closed(path)
            if path.stat().st_size != entry["size"] or _sha(path) != entry["sha256"]:
                raise BackupError("market hash integrity failed")
        _check_references(destination/"market", manifest["market_references"])
        return manifest
    except BackupError:
        raise
    except Exception:
        raise BackupError("backup manifest or file integrity verification failed") from None


def restore_disposable(destination, *, target_dsn, clock, pg_bin, execution_control_dir, confirm_disposable=False):
    from psycopg.conninfo import make_conninfo
    if confirm_disposable is not True:
        raise BackupError("explicit disposable restore confirmation required")
    params = _params(target_dsn, disposable=True)
    manifest = verify_backup(destination)
    destination, control = Path(destination), Path(execution_control_dir)
    if control.exists():
        raise BackupError("restore verification requires a new isolated control directory with no kill-switch flag")
    try:
        with open_operational_pg(make_conninfo("", **params)) as conn:
            if int(conn.execute("SHOW server_version_num").fetchone()[0])//10000 != 17:
                raise BackupError("restore verification requires PostgreSQL 17")
            if _database_state(conn)[0]:
                raise BackupError("restore target is not empty; existing databases are never reset")
        env = _env(params, destination)
        _, restore, _ = _tools(pg_bin, env)
        control.mkdir(parents=True, exist_ok=False)  # no flag/secrets restored or written
        _run([str(restore), "--exit-on-error", "--no-password", "--no-owner", "--no-privileges",
              "--dbname="+params["dbname"], str(destination/manifest["dump"]["path"])], env=env)
        with open_operational_pg(make_conninfo("", **params)) as conn:
            actual, references = _database_state(conn, collect=True)
        if actual != manifest["tables"]:
            raise BackupError("restored database counts/hashes differ")
        _check_references(destination/"market", references)
        return {"status":"VERIFIED", "database_hashes_match":True, "verified_at":clock.now().isoformat(),
                "database":params["dbname"], "control_dir":str(control), "execution":"DISABLED: isolated flag missing"}
    except Exception:
        raise BackupError("disposable restore verification failed; target was not reset or deleted") from None
