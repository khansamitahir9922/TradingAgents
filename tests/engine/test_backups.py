"""M5-12: immutable, verified backup evidence; no secret-bearing argv."""
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.storage.backups import BackupError, create_backup, verify_backup

PG_BIN = Path("C:/Program Files/PostgreSQL/17/bin")
CLOCK = ReplayClock(datetime(2026,10,22,tzinfo=UTC))


@pytest.mark.postgres
def test_real_dump_manifest_and_corruption_detection(pg_database, tmp_path):
    from tests.engine.test_intent_pipeline import SESSIONS, Env, view_for
    e = Env(pg_database, tmp_path/"market")
    try:
        e.account("R1")
        view_for(e.stores, e.reader, SESSIONS[60])
        dest = tmp_path/"backup"
        manifest = create_backup(pg_database, destination=dest, market_root=e.root, clock=CLOCK, pg_bin=PG_BIN)
        assert manifest["status"] == "SUCCESS" and manifest["market_references"]
        assert manifest["consistency"] == "POSTGRES_EXPORTED_SNAPSHOT_WITH_LATER_IMMUTABLE_MARKET_SUPERSET"
        assert verify_backup(dest)["status"] == "SUCCESS"
        assert "password" not in (dest/"manifest.json").read_text().lower()
        target = dest/"database.dump"
        with target.open("ab") as stream:
            stream.write(b"corrupt")
        with pytest.raises(BackupError, match="hash|integrity"):
            verify_backup(dest)
    finally:
        e.close()


def test_existing_destination_is_never_overwritten(tmp_path):
    dest = tmp_path/"existing"
    dest.mkdir()
    (dest/"owner-file").write_text("keep")
    with pytest.raises(BackupError):
        create_backup("not a connection", destination=dest, market_root=tmp_path/"market", clock=CLOCK, pg_bin=PG_BIN)
    assert (dest/"owner-file").read_text() == "keep"


def test_failed_native_tool_never_exposes_captured_output(monkeypatch):
    from types import SimpleNamespace

    from investment_engine.storage import backups
    monkeypatch.setattr(backups.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=1, stdout="FAKE-PASSWORD-CANARY", stderr="FAKE-PASSWORD-CANARY"))
    with pytest.raises(BackupError) as error:
        backups._run(["pg_dump"], env={"PGPASSWORD":"FAKE-PASSWORD-CANARY"})
    assert "FAKE-PASSWORD-CANARY" not in str(error.value)


def test_native_environment_contains_only_runtime_and_explicit_local_pg_credentials(tmp_path,monkeypatch):
    from investment_engine.storage import backups
    monkeypatch.setenv("GOOGLE_API_KEY", "FAKE-MODEL-KEY")
    monkeypatch.setenv("BROKER_SECRET", "FAKE-BROKER-KEY")
    env = backups._env({"host":"127.0.0.1", "user":"dev", "dbname":"test", "password":"FAKE-PG-ONLY"},tmp_path)
    assert "GOOGLE_API_KEY" not in env and "BROKER_SECRET" not in env
    assert env["PGPASSWORD"] == "FAKE-PG-ONLY" and env["PGHOSTADDR"] == "127.0.0.1"


@pytest.mark.postgres
def test_missing_tool_leaves_failed_evidence_without_success_manifest(pg_database,tmp_path):
    dest = tmp_path/"failed"
    with pytest.raises(BackupError):
        create_backup(pg_database, destination=dest, market_root=tmp_path/"market", clock=CLOCK, pg_bin=tmp_path/"missing")
    assert not (dest/"manifest.json").exists()
    assert json.loads((dest/"failed.json").read_text())["status"] == "FAILED"


def test_verification_refuses_manifest_path_escape(tmp_path):
    dest = tmp_path/"bad"
    dest.mkdir()
    (dest/"manifest.json").write_text(json.dumps({"version":1,"status":"SUCCESS", "dump":{"path":"../owner-file","sha256":"a"*64},"market_files":[],"market_references":[]}))
    with pytest.raises(BackupError, match="unsafe"):
        verify_backup(dest)


@pytest.mark.postgres
def test_later_market_partition_is_included_and_credentials_never_enter_argv(pg_database, tmp_path, monkeypatch):
    from psycopg.conninfo import conninfo_to_dict

    from investment_engine.market.store.writer import MarketDataWriter
    from investment_engine.storage import backups
    from tests.engine.test_intent_pipeline import CAL, SESSIONS, Env, view_for
    from tests.engine.test_raw_reference import observation
    e = Env(pg_database, tmp_path/"market[x]")
    try:
        e.account("R1")
        view_for(e.stores,e.reader,SESSIONS[60])
        password = conninfo_to_dict(pg_database).get("password")
        original = backups._run
        calls = []
        def run(command, *, env):
            assert not password or all(password not in arg for arg in command)
            assert env["PGHOSTADDR"] in ("127.0.0.1", "::1")
            calls.append(tuple(command))
            if "--format=custom" in command:
                e.account("AFTER_EXPORT")  # concurrent database append, outside the exported snapshot
            output = original(command, env=env)
            if "--format=custom" in command:
                day = CAL.next_session(SESSIONS[-1]).date
                MarketDataWriter(e.root).write_candles([observation(day)], import_id="during-dump")
            return output
        monkeypatch.setattr(backups,"_run",run)
        # Deliberate fake secret/flag files are outside the closed market format.
        for name in (".env", "secrets.json", "trading_enabled.json"):
            (e.root/name).write_text("FAKE-LOCAL-TEST-ONLY")
        manifest = create_backup(pg_database,destination=tmp_path/"backup",market_root=e.root,clock=CLOCK,pg_bin=PG_BIN)
        assert any("during-dump" in f["path"] for f in manifest["market_files"])
        assert calls and not list((tmp_path/"backup"/"market").rglob(".env"))
        assert not list((tmp_path/"backup"/"market").rglob("secrets.json"))
        assert manifest["tables"]["public.accounts"]["count"] == 1
        assert e.stores.db.fetchone("SELECT count(*) FROM accounts")[0] == 2
        from tests.engine.conftest import maintenance_dsn, temporary_database
        with temporary_database(maintenance_dsn()) as target:
            checked = backups.restore_disposable(tmp_path/"backup", target_dsn=target, clock=CLOCK, pg_bin=PG_BIN,
                execution_control_dir=tmp_path/"exported-snapshot-control", confirm_disposable=True)
            assert checked["database_hashes_match"]
    finally:
        e.close()


@pytest.mark.postgres
def test_failed_tool_output_is_sanitized_and_partial_copy_never_publishes_success(pg_database,tmp_path,monkeypatch):
    from investment_engine.storage import backups
    from tests.engine.test_intent_pipeline import Env
    e = Env(pg_database, tmp_path/"market")
    try:
        def partial(source,target):
            target.write_bytes(b"partial")
            raise OSError("FAKE-CREDENTIAL-CANARY")
        monkeypatch.setattr(backups.shutil,"copyfile",partial)
        dest = tmp_path/"partial-job"
        with pytest.raises(BackupError) as error:
            create_backup(pg_database,destination=dest,market_root=e.root,clock=CLOCK,pg_bin=PG_BIN)
        assert "FAKE-CREDENTIAL-CANARY" not in str(error.value)
        assert "FAKE-CREDENTIAL-CANARY" not in (dest/"failed.json").read_text()
        assert not (dest/"manifest.json").exists()
    finally:
        e.close()


@pytest.mark.postgres
def test_missing_referenced_bar_is_not_replaced_by_another_import_partition(pg_database,tmp_path):
    from tests.engine.test_intent_pipeline import SESSIONS, Env, view_for
    e = Env(pg_database,tmp_path/"market")
    try:
        e.account("R1")
        view_for(e.stores,e.reader,SESSIONS[60])
        # Remove only this test's immutable source files; references remain in DB.
        for path in e.root.rglob("*.parquet"):
            assert path.resolve().is_relative_to(tmp_path.resolve())
            path.unlink()
        dest = tmp_path/"missing-source"
        with pytest.raises(BackupError):
            create_backup(pg_database,destination=dest,market_root=e.root,clock=CLOCK,pg_bin=PG_BIN)
        assert not (dest/"manifest.json").exists()
    finally:
        e.close()
