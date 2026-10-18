"""M3 snapshots keep their content and ids under M4's added fields (docs/tasks/M4-09.md rule 6; Codex M4 review B6)."""

import json
from pathlib import Path

import pytest

from investment_engine.lineage.records import decode
from investment_engine.portfolio.snapshot import PortfolioSnapshot

FIXTURE = Path(__file__).parent / "fixtures" / "m3_snapshot_record.json"


@pytest.mark.unit
def test_a_snapshot_written_by_mains_m3_code_decodes_with_the_same_id():
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert record["written_by"].startswith("main 4c56ac1")
    fields = decode(json.loads(record["content"]))
    snapshot = PortfolioSnapshot(**fields)
    assert snapshot.snapshot_id == record["snapshot_id"]
    assert snapshot.content() == record["content"]  # byte for byte: no M4 field appears
    assert snapshot.reservations is None and snapshot.available_cash() == snapshot.cash
