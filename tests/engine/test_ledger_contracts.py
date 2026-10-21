"""M5-00: unit-separated balanced manifests, source time and immutable identities."""
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from investment_engine.ledger.contracts import (
    BalanceQuery,
    BookBatch,
    LedgerEntry,
    LotMatch,
    OpeningLot,
    SourceBundle,
    SourceRef,
    Unit,
    journal,
    reverse_transaction,
)
from investment_engine.lineage.records import canonical_json, decode

T = datetime(2024, 1, 2, tzinfo=UTC)
USD = Unit("CURRENCY", "USD")
SHARES = Unit("SECURITY", "EQ_US_NVDA")


def source(**changes):
    return replace(SourceRef("opening", "R1/start", 1, "stored-start", "a" * 64,
                             T, T, T, "declared"), **changes)


def tx(account="R1", sources=None):
    return journal(account, T, T, (source(),) if sources is None else sources,
                   (("CASH", USD, Decimal("100000")), ("CAPITAL", USD, Decimal("-100000"))))


@pytest.mark.parametrize("value", [1, 1.0, True, Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_entry_only_accepts_finite_nonnegative_decimal(value):
    with pytest.raises((TypeError, ValueError)):
        LedgerEntry("e", "t", "R1", "CASH", value, Decimal(0), USD, T, T, (source(),))


@pytest.mark.parametrize("debit,credit", [("0", "0"), ("1", "1")])
def test_exactly_one_nonzero_side(debit, credit):
    with pytest.raises(ValueError):
        LedgerEntry("e", "t", "R1", "CASH", Decimal(debit), Decimal(credit), USD, T, T, (source(),))


@pytest.mark.parametrize("bad", [datetime(2024, 1, 2), T.astimezone(timezone(timedelta(hours=1))), T.date()])
def test_source_times_must_be_utc(bad):
    with pytest.raises((TypeError, ValueError)):
        source(delivered_at=bad)


def test_units_accounts_and_source_visibility_cannot_be_mixed():
    with pytest.raises(ValueError, match="balance"):
        journal("R1", T, T, (source(),), (("CASH", USD, Decimal(1)), ("SHARE_OFFSET", SHARES, Decimal(-1))))
    original = tx()
    with pytest.raises(ValueError):
        replace(original, entries=(replace(original.entries[0], investment_account_id="R2"), original.entries[1]))
    with pytest.raises(ValueError, match="known"):
        tx(sources=(source(delivered_at=T + timedelta(seconds=1)),))


def test_transaction_manifest_immutable_roundtrip_and_normalization():
    original = tx()
    assert original.entry_count == 2
    assert len(original.manifest_hash) == 64
    assert decode(json.loads(canonical_json(original))) == original
    with pytest.raises(FrozenInstanceError):
        original.posted_at = T
    other = source(identity="R1/second", stored_record_id="second")
    assert tx(sources=(source(), other)).transaction_id == tx(sources=(other, source())).transaction_id
    assert tx("R2").transaction_id != original.transaction_id
    assert tx(sources=(source(provider="other"),)).transaction_id != original.transaction_id
    with pytest.raises(ValueError):
        replace(original, entries=original.entries[:1])


def test_reversal_full_directions_and_cross_account_refused():
    original = tx()
    reversal = reverse_transaction(original, posted_at=T + timedelta(days=1))
    assert reversal.effective_at == original.effective_at
    assert reversal.reverses == original.transaction_id
    for old, new in zip(original.entries, reversal.entries, strict=True):
        assert (old.debit, old.credit, old.unit, old.entry_id) == (new.credit, new.debit, new.unit, new.reverses)
    with pytest.raises(ValueError):
        reverse_transaction(original, posted_at=T, account_id="R2")


def test_exact_balance_is_independent_of_decimal_context():
    with localcontext() as ctx:
        ctx.prec = 1
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        value = journal("R1", T, T, (source(),), (("CASH", USD, Decimal("100.001")),
                        ("FEES", USD, Decimal(".009")), ("CAPITAL", USD, Decimal("-100.010"))))
    assert len(value.entries) == 3


def test_batch_parent_version_identity_and_cutoff():
    batch = BookBatch("R1", None, 1, "fifo-v1", (source(),), (tx(),), (), T)
    assert batch.book_id == replace(batch).book_id
    assert batch.source_set_hash != replace(batch, sources=(source(provider="other"),), transactions=()).source_set_hash
    with pytest.raises(ValueError):
        replace(batch, version=2)
    with pytest.raises(ValueError):
        replace(batch, transactions=(tx("R2"),))
    with pytest.raises(ValueError):
        BalanceQuery("R1", T, T.replace(tzinfo=None), batch.book_id)


def test_opening_lot_requires_real_cost_and_whole_shares():
    lot = OpeningLot("decl", "start", "R1", "EQ_US_NVDA", Decimal(6), Decimal(".0004"), USD, T, T,
                     "admin", "declared acquisition cost")
    assert lot.total_cost == Decimal(".0004")
    for changes in ({"quantity": Decimal("1.5")}, {"total_cost": 1.0}, {"reason": ""}):
        with pytest.raises((TypeError, ValueError)):
            replace(lot, **changes)


def test_bundle_coverage_is_evidence_not_bare_boolean():
    bundle = SourceBundle("R1", T, (), (source(),), "declared", "coverage-id", (), "v1")
    assert bundle.complete
    assert not replace(bundle, omissions=("missing actions",)).complete
    with pytest.raises((TypeError, ValueError)):
        replace(bundle, coverage_ref=True)
    with pytest.raises(ValueError):
        replace(bundle, cutoff=T - timedelta(seconds=1))


@pytest.mark.parametrize("lines,expected", [
    ((("INVENTORY_COST:EQ_US_NVDA", "1000"), ("FEES", "1"), ("CASH", "-1001")),
     {"INVENTORY_COST:EQ_US_NVDA": ("1000", "0"), "FEES": ("1", "0"), "CASH": ("0", "1001")}),
    ((("CASH", "479"), ("FEES", "1"), ("INVENTORY_COST:EQ_US_NVDA", "-400"), ("REALIZED_PNL:EQ_US_NVDA", "-80")),
     {"CASH": ("479", "0"), "FEES": ("1", "0"), "INVENTORY_COST:EQ_US_NVDA": ("0", "400"), "REALIZED_PNL:EQ_US_NVDA": ("0", "80")}),
    ((("DIVIDEND_RECEIVABLE:EQ_US_NVDA", "3"), ("DIVIDEND_INCOME:EQ_US_NVDA", "-3")),
     {"DIVIDEND_RECEIVABLE:EQ_US_NVDA": ("3", "0"), "DIVIDEND_INCOME:EQ_US_NVDA": ("0", "3")}),
])
def test_adr_worked_currency_entry_directions(lines, expected):
    value = journal("R1", T, T, (source(),), ((name, USD, Decimal(n)) for name, n in lines))
    assert {e.account: (str(e.debit), str(e.credit)) for e in value.entries} == expected


def test_quantity_book_never_credits_money_and_legacy_codec_unchanged():
    value = journal("R1", T, T, (source(),), (("CUSTODY_SHARES", SHARES, Decimal(90)),
                    ("SHARE_OFFSET", SHARES, Decimal(-90))))
    assert [(e.debit, e.credit) for e in value.entries] == [(Decimal(90), Decimal(0)), (Decimal(0), Decimal(90))]
    assert canonical_json({"old": Decimal("1.00")}) == '{"$map":[["old",{"$decimal":"1.00"}]]}'


def test_lot_book_back_reference_has_no_circular_identity_and_records_are_frozen():
    match = LotMatch("m", "pending", "buy", "sell", Decimal(1), Decimal(1), USD, "fifo-v1")
    batch = BookBatch("R1", None, 1, "fifo-v1", (source(),), (tx(),), (match,), T)
    finalized = replace(batch, lot_matches=(replace(match, book_id=batch.book_id),))
    assert finalized.book_id == batch.book_id
    inputs = [{"declared": [Decimal(1)]}]
    bundle = SourceBundle("R1", T, inputs, (source(),), "declared", "coverage", (), "v1")
    inputs[0]["declared"].append(Decimal(2))
    assert tuple(bundle.records[0]["declared"]) == (Decimal(1),)
