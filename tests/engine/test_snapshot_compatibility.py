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


def test_accepted_m4_code_fixture_keeps_content_id_and_nested_codec_payload():
    import hashlib

    from investment_engine.lineage.records import canonical_json

    record = json.loads((FIXTURE.parent/"m4_snapshot_record.json").read_text(encoding="utf-8"))
    assert record["written_by"] == "m4/milestone 5cd93637cfa0a820102196b2da31294c5f908b0c"
    assert record["synthetic"] is True
    assert hashlib.sha256(record["content"].encode()).hexdigest() == record["content_sha256"]
    snapshot = PortfolioSnapshot(**decode(json.loads(record["content"])))
    assert snapshot.snapshot_id == record["snapshot_id"] and snapshot.content() == record["content"]
    assert snapshot.ledger_book_id is snapshot.ledger_query_id is None
    assert "ledger_book_id" not in canonical_json(snapshot) and "ledger_query_id" not in canonical_json(snapshot)
