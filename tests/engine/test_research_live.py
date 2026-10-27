"""M6-11: the measured live run's checks. Integration-marked, so excluded from the default run (-m integration).

The live run itself is an owner-approved, single `python -m investment_engine.research run --once` step; these tests
never call a model. They check that the worker refuses to start without its secrets file, and that the measurement
document reports exactly the usage stored in the run's ResearchRecord.
"""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

MEASUREMENT = Path(__file__).resolve().parents[2] / "docs" / "reviews" / "m6-measurement.md"


def test_the_worker_refuses_to_start_without_its_secrets_file(tmp_path, monkeypatch, capsys):
    from investment_engine.research.__main__ import main
    from investment_engine.research.secrets import LLM_KEYS, ambient_switches

    monkeypatch.setenv("INVESTMENT_ENGINE_DATA_DIR", str(tmp_path))
    for name in (*LLM_KEYS, *ambient_switches(os.environ)):
        monkeypatch.delenv(name, raising=False)

    assert main(["run", "--once"]) == 2
    out = capsys.readouterr().out
    assert "Research Worker not started" in out and "research_worker.env is missing" in out


@pytest.mark.postgres
def test_the_measurement_document_matches_the_stored_record():
    dsn, run_id = os.environ.get("INVESTMENT_ENGINE_PG_DSN"), os.environ.get("INVESTMENT_ENGINE_M6_LIVE_RUN_ID")
    if not dsn or not run_id:
        pytest.skip("set INVESTMENT_ENGINE_PG_DSN (the live run's database) and INVESTMENT_ENGINE_M6_LIVE_RUN_ID")
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
