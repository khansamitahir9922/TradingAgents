"""M6-11: the measured live run's checks. Integration-marked, so excluded from the default run (-m integration).

The live run itself is an owner-approved, single `python -m investment_engine.research run --once` step; these tests
never call a model. They check that the worker refuses to start without its secrets file, and that the measurement
document reports exactly the usage stored in the run's ResearchRecord.
"""

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MEASUREMENT = ROOT / "docs" / "reviews" / "m6-measurement.md"
ENV_LIVE_RUN = "INVESTMENT_ENGINE_M6_LIVE_RUN_ID"


@pytest.mark.integration
def test_the_worker_refuses_to_start_without_its_secrets_file(tmp_path, monkeypatch, capsys):
    from investment_engine.research.__main__ import main
    from investment_engine.research.secrets import LLM_KEYS, ambient_switches

    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    for name in (*LLM_KEYS, *ambient_switches(os.environ)):
        monkeypatch.delenv(name, raising=False)

    assert main(["run", "--once"]) == 2
    out = capsys.readouterr().out
    assert "Research Worker not started" in out and "research_worker.env is missing" in out


@pytest.mark.integration
@pytest.mark.postgres
def test_the_measurement_document_matches_the_stored_record():
    from investment_engine.config import ENV_PG_DSN
    from tests.engine.conftest import SecretDsn, _remember

    # Codex M6-11 review B1: remembered before anything can fail, so the report boundary scrubs the DSN and its
    # password from tracebacks, locals and the driver's normalized connection text; the local is a SecretDsn.
    dsn, run_id = SecretDsn(os.environ.get(ENV_PG_DSN, "")), os.environ.get(ENV_LIVE_RUN)
    if not dsn or not run_id:
        pytest.skip(f"set {ENV_PG_DSN} (the live run's database) and {ENV_LIVE_RUN}")
    _remember(dsn)
    import psycopg

    import investment_engine.research.contracts  # noqa: F401  (registers the record types for decode)
    from investment_engine.lineage.records import decode
    from investment_engine.research.contracts import RunOutcome

    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT content FROM research_records WHERE run_id = %s", (run_id,)).fetchone()
    assert row is not None, "no such research record"
    record = decode(json.loads(row[0]))
    assert record.run_id == run_id and record.outcome is RunOutcome.SUCCEEDED
    usage = record.usage
    text = MEASUREMENT.read_text(encoding="utf-8")
    assert f"`rrn-{run_id[4:12]}…`, SUCCEEDED" in text
    assert f"| Model requests | **{usage.requests}**" in text
    assert f"**{usage.input_tokens:,} in / {usage.output_tokens:,} out**" in text
    assert f"| Tool calls | {usage.tool_calls} " in text


@pytest.mark.unit
@pytest.mark.parametrize("options", [[], ["-l", "--tb=long", "-rA"]], ids=["default", "locals"])
def test_a_failing_evidence_connection_never_prints_the_password(tmp_path, options):
    """Codex M6-11 review B1: the evidence check reads its DSN from the environment; when its connection fails, the
    traceback (and, with -l, its locals and the driver's normalized connection text) must not show the password."""
    import subprocess
    import sys

    from psycopg.conninfo import make_conninfo

    password = "IE_M6_LIVE_PASSWORD_CANARY"
    dsn = make_conninfo(host="localhost", port="1", dbname="ie_m6_live", user="fake", password=password,
                        connect_timeout="1")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("INVESTMENT_ENGINE_", "PG"))}
    env.update({"INVESTMENT_ENGINE_PG_DSN": dsn, ENV_LIVE_RUN: "rrn-not-a-real-run", "PYTHONPATH": str(ROOT)})
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "integration",
                          *options, f"{Path(__file__)}::test_the_measurement_document_matches_the_stored_record"],
                         capture_output=True, text=True, timeout=120, cwd=ROOT, env=env)
    text = out.stdout + out.stderr
    assert "1 failed" in text, text[-3000:]
    assert password not in text and password[:12] not in text
