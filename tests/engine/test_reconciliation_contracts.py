"""M5-00: neutral broker evidence preserves unavailable versus a flat account."""
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.lineage.records import canonical_json, decode
from investment_engine.reconciliation.contracts import (
    BrokerOpenOrder,
    BrokerPosition,
    BrokerSnapshot,
    Difference,
    IncidentTransition,
    ReconciliationResult,
)

T = datetime(2024, 1, 2, tzinfo=UTC)


def snapshot(**changes):
    return replace(BrokerSnapshot("R1", "sim", "sim-R1", "simulated", T, T, T, "USD",
                                  Decimal(100), (), (), "SETTLED_PLUS_UNSETTLED", "coverage", "a" * 64,
                                  (), True, ()), **changes)


def test_missing_cash_positions_orders_never_become_zero():
    missing = snapshot(cash=None, positions=None, open_orders=None, complete=False, reasons=("missing",))
    assert missing.cash is missing.positions is missing.open_orders is None
    with pytest.raises(ValueError):
        replace(missing, complete=True, reasons=())
    assert snapshot().positions == ()
    assert decode(json.loads(canonical_json(missing))) == missing


@pytest.mark.parametrize("changes", [{"received_at": T - timedelta(seconds=1)}, {"raw_hash": ""},
                                     {"account_id": ""}, {"taken_at": T.replace(tzinfo=None)}])
def test_snapshot_refuses_false_provenance(changes):
    with pytest.raises((TypeError, ValueError)):
        snapshot(**changes)


def test_order_and_position_units():
    assert BrokerPosition("EQ_US_NVDA", Decimal(10), "SHARES").quantity == 10
    for qty in [1.0, Decimal("NaN"), Decimal("-1")]:
        with pytest.raises((TypeError, ValueError)):
            BrokerPosition("EQ_US_NVDA", qty, "SHARES")
    with pytest.raises(ValueError):
        BrokerOpenOrder("o", "c", "EQ_US_NVDA", "BUY", "OPEN", Decimal(".5"))


def test_identical_snapshot_is_idempotent_but_account_changes_identity():
    value = snapshot()
    assert value.snapshot_id == snapshot().snapshot_id
    assert value.snapshot_id != snapshot(account_id="R2").snapshot_id


def test_match_cannot_hide_differences_or_incomplete_evidence():
    diff = Difference("cash", "USD", Decimal(100), Decimal(99), "mismatch")
    with pytest.raises(ValueError):
        ReconciliationResult("R1", T, "book", "snap", "oms", "MATCH", (diff,), ())
    with pytest.raises(ValueError):
        ReconciliationResult("R1", T, "book", "snap", "oms", "MATCH", (), ("missing",))
    result = ReconciliationResult("R1", T, "book", "snap", "oms", "MISMATCH", (diff,), ())
    assert decode(json.loads(canonical_json(result))) == result


def test_incident_transition_requires_reason_and_sequence():
    item = IncidentTransition("i", "R1", 1, "OPEN", "recon", "system", "mismatch", T, T)
    assert item.sequence == 1
    with pytest.raises(ValueError):
        replace(item, reason="")
    with pytest.raises(ValueError):
        replace(item, sequence=0)
