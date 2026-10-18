"""The Execution Worker and Core Engine processes, and credential separation (docs/tasks/M4-03.md rules 1, 3–6)."""

import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.execution.factory import BrokerUnavailable, build_broker, check_available
from investment_engine.execution.secrets import SecretsFileError, load_worker_secrets
from investment_engine.execution.worker import ExecutionWorker
from investment_engine.policy.accounts import AccountKind
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.broker_doubles import ScriptedBroker

ROOT = Path(__file__).parents[2]
CANARY = "IE_WORKER_SECRET_CANARY"
NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def environment(tmp_path, dsn=None):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "INVESTMENT_ENGINE_DATA_DIR": str(tmp_path / "data")}
    if dsn is not None:
        env["INVESTMENT_ENGINE_PG_DSN"] = dsn
    return env


def schema(dsn):
    conn = open_operational_pg(dsn)
    apply_pg_schema(conn)
    conn.close()


@pytest.mark.unit
def test_no_adapter_is_available_yet_and_the_factory_refuses_every_kind():
    for kind in ("simulated", "paper", "anything"):
        with pytest.raises(BrokerUnavailable, match="no broker adapter"):
            check_available(kind, account_kind=AccountKind.RESEARCH)
        with pytest.raises(BrokerUnavailable):
            build_broker(kind, account_kind=AccountKind.PAPER)


@pytest.mark.unit
def test_the_worker_refuses_to_start_without_an_adapter(tmp_path):
    out = subprocess.run([sys.executable, "-m", "investment_engine.execution", "run", "--broker", "simulated"],
                         capture_output=True, text=True, timeout=120, cwd=ROOT, env=environment(tmp_path))
    assert out.returncode == 2
    assert "Execution Worker not started: no broker adapter 'simulated' is available yet" in out.stdout
    missing = subprocess.run([sys.executable, "-m", "investment_engine.execution", "run"], capture_output=True,
                             text=True, timeout=120, cwd=ROOT, env=environment(tmp_path))
    assert missing.returncode == 2 and "--broker" in missing.stderr


@pytest.mark.postgres
@pytest.mark.unit
def test_a_worker_with_a_test_double_steps_over_an_empty_store(pg_database):
    conn = open_operational_pg(pg_database)
    try:
        apply_pg_schema(conn)
        broker = ScriptedBroker()
        worker = ExecutionWorker(PostgresDatabase(conn), clock=ReplayClock(NOW), broker=broker)
        assert worker.step().published == 0
        assert broker.submits == [] and broker.lookups == []
    finally:
        conn.close()


@pytest.mark.unit
def test_the_secrets_file_is_key_value_lines_and_never_echoes_a_value(tmp_path):
    path = tmp_path / "execution_worker.env"
    assert load_worker_secrets(path) == {}  # absent: the simulator needs none
    path.write_text(f"# broker\nBROKER_KEY={CANARY}\n\n", encoding="utf-8")
    assert dict(load_worker_secrets(path)) == {"BROKER_KEY": CANARY}
    path.write_text(f"{CANARY}\n", encoding="utf-8")
    with pytest.raises(SecretsFileError) as error:
        load_worker_secrets(path)
    assert CANARY not in str(error.value) and "line 1" in str(error.value)


PROBE = """
import builtins, io, os, pathlib, runpy, sys
secret = os.path.normcase(os.path.abspath(sys.argv[1]))
opened = []
real_open, real_io_open = builtins.open, io.open
def watch(file, *a, **k):
    if isinstance(file, (str, bytes, os.PathLike)) and os.path.normcase(os.path.abspath(os.fsdecode(file))) == secret:
        opened.append(file)
    return real_open(file, *a, **k)
builtins.open = io.open = watch
sys.argv = [sys.argv[2], *sys.argv[3:]]
try:
    runpy.run_module(sys.argv[0], run_name="__main__")
except SystemExit:
    pass
finally:
    print("SECRETS-OPENED" if opened else "SECRETS-UNTOUCHED")
"""


@pytest.mark.postgres
@pytest.mark.unit
@pytest.mark.parametrize("module, args", [
    ("investment_engine.core", ["run", "--once"]),
    ("investment_engine", ["intents", "--help"]),
    ("investment_engine", ["orders", "--help"]),
    ("investment_engine.intents_cli", ["--help"]),
], ids=["core", "admin-cli-intents", "admin-cli-orders", "intents-cli"])
def test_no_other_process_reads_the_workers_secrets(tmp_path, pg_database, module, args):
    """D32 and Law 2: a canary secrets file is present; every other entry point runs without opening it."""
    schema(pg_database)
    secrets = tmp_path / "data" / "secrets" / "execution_worker.env"
    secrets.parent.mkdir(parents=True)
    secrets.write_text(f"BROKER_KEY={CANARY}\n", encoding="utf-8")
    out = subprocess.run([sys.executable, "-c", PROBE, str(secrets), module, *args], capture_output=True, text=True,
                         timeout=120, cwd=ROOT, env=environment(tmp_path, pg_database))
    text = out.stdout + out.stderr
    assert "SECRETS-UNTOUCHED" in out.stdout, text[-1500:]
    assert CANARY not in text


@pytest.mark.postgres
@pytest.mark.unit
def test_the_core_engine_runs_one_step_and_republishes_first(tmp_path, pg_database):
    schema(pg_database)
    out = subprocess.run([sys.executable, "-m", "investment_engine.core", "run", "--once"], capture_output=True,
                         text=True, timeout=120, cwd=ROOT, env=environment(tmp_path, pg_database))
    assert out.returncode == 0, out.stderr[-1500:]
    assert "Core Engine: one step done; republished 0, converted 0, published 0." in out.stdout


def _start_core(tmp_path, dsn):
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    process = subprocess.Popen([sys.executable, "-u", "-m", "investment_engine.core", "run", "--poll", "0.2"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT,
                               env=environment(tmp_path, dsn), creationflags=flags)
    deadline = time.monotonic() + 60
    line = process.stdout.readline()
    while "running" not in line and time.monotonic() < deadline:
        line = process.stdout.readline()
    assert "running" in line, process.stderr.read()[-1500:]
    return process


@pytest.mark.postgres
@pytest.mark.unit
def test_a_graceful_stop_and_a_hard_kill(tmp_path, pg_database):
    schema(pg_database)
    process = _start_core(tmp_path, pg_database)
    process.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM)
    rest, _ = process.communicate(timeout=60)
    assert process.returncode == 0 and "Core Engine stopped." in rest
    crashed = _start_core(tmp_path, pg_database)
    crashed.kill()  # TerminateProcess on Windows: a crash, never a graceful stop (rule 6)
    crashed.communicate(timeout=60)
    assert crashed.returncode != 0


@pytest.mark.unit
def test_the_probe_does_see_the_worker_read_its_secrets(tmp_path):
    """A positive control for the canary test: the worker's entry point reads the file, and the probe notices."""
    secrets = tmp_path / "data" / "secrets" / "execution_worker.env"
    secrets.parent.mkdir(parents=True)
    secrets.write_text(f"BROKER_KEY={CANARY}\n", encoding="utf-8")
    out = subprocess.run([sys.executable, "-c", PROBE, str(secrets), "investment_engine.execution", "run", "--broker",
                          "simulated"], capture_output=True, text=True, timeout=120, cwd=ROOT,
                         env=environment(tmp_path))
    assert "SECRETS-OPENED" in out.stdout, out.stdout + out.stderr
    assert CANARY not in out.stdout + out.stderr  # read, never printed
