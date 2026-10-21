"""M5-04: ex-open order, receivables, split conservation and revision refusal."""
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from investment_engine.ledger.actions import ClosureRequired, correction_plan, plan_action
from investment_engine.ledger.contracts import AccountingUnavailable, BookBatch, SourceConflict
from investment_engine.ledger.lots import FifoBook
from investment_engine.ledger.sources import action_reference, validate_action
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.corporate_actions import ActionType
from investment_engine.money import Money
from investment_engine.quant.adjusted import VerificationEvidence, establish_coverage
from tests.engine.test_corporate_actions import action
from tests.engine.test_fill_postings import totals

CAL = load_us_equities_calendar()
EX = date(2024, 6, 10)
OPEN = CAL.session(EX).open
PRIOR = CAL.previous_session(EX).close
NVDA = "EQ_US_NVDA"


def corporate(kind=ActionType.SPLIT, *, revision=1, known=None, **kwargs):
    known = known or datetime(2024, 6, 10, 4, tzinfo=UTC)
    return action(kind, revision=revision, received_at=known, processed_at=known, available_from=known,
                  availability_basis=AvailabilityBasis.OBSERVED, **kwargs)


def coverage(at, source="yfinance", types=(ActionType.SPLIT, ActionType.DIVIDEND)):
    evidence = [VerificationEvidence(source, NVDA, kind, date(2019, 1, 1), date(2026, 12, 31),
                                      date(2019, 1, 1), date(2026, 12, 31), "verification-v1", "COMPLETE") for kind in types]
    return establish_coverage(evidence, source=source, instrument_id=NVDA, types=types,
                              first=date(2019, 1, 1), last=date(2026, 12, 31), as_of=at, reason="fixture verified history")


class Reader:
    def __init__(self, records):
        self.records = records

    def action_revision_history(self, source, instrument_id, start, end, types=None):
        return [a for a in self.records if a.source == source and a.instrument_id == instrument_id
                and start <= a.ex_date <= end and (types is None or a.action_type in types)]


def selected(a, *, at=OPEN, delivered=None, records=None, provider="yfinance", cov=None):
    return validate_action(a, account_id="R1", reader=Reader([a] if records is None else records), provider=provider,
                           instrument_id=NVDA, delivered_at=delivered or a.available_from,
                           at=at, calendar=CAL, coverage=coverage(at) if cov is None else cov)


def fifo(quantity="10"):
    value = FifoBook("R1", at=OPEN + timedelta(days=10))
    value.acquire(NVDA, Decimal(quantity), Decimal(1000), "old-buy", at=PRIOR - timedelta(days=1))
    return value


def test_split_then_open_buy_gives_110_and_starts_new_allocation_epoch():
    value = fifo()
    a = corporate()
    plan = plan_action(a, ref=selected(a), posted_at=OPEN, fifo=value, calendar=CAL)
    assert totals(plan) == {("CUSTODY_SHARES", "SECURITY:EQ_US_NVDA"): Decimal(90),
                            ("SHARE_OFFSET", "SECURITY:EQ_US_NVDA"): Decimal(-90)}
    value.acquire(NVDA, Decimal(10), Decimal(100), "new-buy", at=OPEN)
    assert sum((lot.remaining_quantity for lot in value.lots()), Decimal(0)) == 110
    assert value.lots()[0].remaining_cost == 1000
    assert value.lots()[0].epoch_quantity == 100


@pytest.mark.parametrize("prior_quantity", ["0", "6", "10"])
def test_dividend_uses_explicit_prior_close_shares_and_never_spendable_cash(prior_quantity):
    value = fifo()
    value.acquire(NVDA, Decimal(99), Decimal(99), "buy-at-open", at=OPEN)
    a = corporate(ActionType.DIVIDEND, amount=Money(Decimal(".3"), "USD"))
    plan = plan_action(a, ref=selected(a), posted_at=OPEN, fifo=value, calendar=CAL,
                       prior_close_quantity=Decimal(prior_quantity))
    if prior_quantity == "0":
        assert plan is None
    else:
        entries = totals(plan)
        assert entries[(f"DIVIDEND_RECEIVABLE:{NVDA}", "CURRENCY:USD")] == Decimal(prior_quantity) * Decimal(".3")
        assert not any(e.account == "CASH" for e in plan.entries)
    with pytest.raises(AccountingUnavailable, match="prior.close"):
        plan_action(a, ref=selected(a), posted_at=OPEN, fifo=value, calendar=CAL)


def test_announced_action_is_not_applied_before_ex_open_and_late_revision_is_unknown():
    value = fifo()
    early = OPEN - timedelta(days=1)
    a = corporate(known=early)
    before = value.lots()
    assert plan_action(a, ref=selected(a, at=early), posted_at=early, fifo=value, calendar=CAL) is None
    assert value.lots() == before
    correction = corporate(revision=2, known=OPEN + timedelta(days=1), ratio=Decimal(4))
    with pytest.raises(AccountingUnavailable):
        selected(correction)
    with pytest.raises(AccountingUnavailable):
        selected(a, delivered=OPEN + timedelta(seconds=1))


def test_fraction_or_any_bad_lot_leaves_whole_fifo_unmodified():
    value = fifo("3")
    a = corporate(ratio=Decimal(".5"))
    before = value.lots()
    with pytest.raises(AccountingUnavailable, match="fraction"):
        plan_action(a, ref=selected(a), posted_at=OPEN, fifo=value, calendar=CAL)
    assert value.lots() == before


def test_provider_missing_coverage_and_forged_action_are_refused():
    a = corporate()
    for kwargs in ({"provider": "other"}, {"records": []}, {"cov": replace(coverage(OPEN), established=False)}):
        with pytest.raises((AccountingUnavailable, SourceConflict)):
            selected(a, **kwargs)
    with pytest.raises(SourceConflict):
        selected(replace(a, ratio=Decimal(4)), records=[a])


def test_unresolved_crossing_order_at_ex_open_keeps_lots_and_terms():
    from tests.engine.test_provisional_positions import Orders

    orders = Orders()
    order = orders.add(1, created=PRIOR)
    value = fifo()
    a = corporate()
    before = value.lots()
    with pytest.raises(AccountingUnavailable, match="unresolved"):
        plan_action(a, ref=selected(a), posted_at=OPEN, fifo=value, calendar=CAL, orders=orders)
    assert value.lots() == before
    assert orders.orders[0] == order


def test_complete_local_reversal_or_typed_dependency_closure_no_partial_correction():
    a = corporate(ActionType.DIVIDEND, amount=Money(Decimal(".3"), "USD"))
    original = plan_action(a, ref=selected(a), posted_at=OPEN, fifo=fifo(), calendar=CAL, prior_close_quantity=Decimal(10))
    later = OPEN + timedelta(days=1)
    revised = corporate(ActionType.DIVIDEND, revision=2, known=later, amount=Money(Decimal(".4"), "USD"))
    replacement = plan_action(revised, ref=selected(revised, at=later), posted_at=later,
                              fifo=fifo(), calendar=CAL, prior_close_quantity=Decimal(10))
    reversal, saved = correction_plan(original, replacement, dependent_sources=())
    assert reversal.reverses == original.transaction_id
    assert saved == replacement
    assert reversal.effective_at == OPEN and reversal.posted_at == later
    with pytest.raises(ClosureRequired):
        correction_plan(original, replacement, dependent_sources=("later-sell",))


def test_split_after_partial_disposal_preserves_remaining_cost_under_hostile_context():
    value = fifo()
    value.consume(NVDA, Decimal(3), "old-sale")
    a = corporate()
    with localcontext() as ctx:
        ctx.prec = 1
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        plan_action(a, ref=action_reference(a, delivered_at=a.available_from, calendar=CAL),
                     posted_at=OPEN, fifo=value, calendar=CAL)
    lot = value.lots()[0]
    assert lot.remaining_quantity == 70 and lot.remaining_cost == 700
    assert lot.epoch_quantity == 70 and lot.epoch_cost == 700


def test_fraction_in_second_lot_does_not_partially_transform_first_and_reverse_split_directions():
    value = fifo("2")
    value.acquire(NVDA, Decimal(1), Decimal(100), "fractional-second-lot", at=PRIOR)
    a = corporate(ratio=Decimal(".5"))
    before = value.lots()
    with pytest.raises(AccountingUnavailable):
        plan_action(a, ref=selected(a), posted_at=OPEN, fifo=value, calendar=CAL)
    assert value.lots() == before
    value = fifo("10")
    a = corporate(ratio=Decimal(".1"))
    plan = plan_action(a, ref=selected(a), posted_at=OPEN, fifo=value, calendar=CAL)
    assert totals(plan)[("CUSTODY_SHARES", "SECURITY:EQ_US_NVDA")] == -9
    assert value.lots()[0].remaining_cost == 1000


@pytest.mark.postgres
def test_local_correction_appends_one_atomic_reversal_and_replacement(pg_database):
    from tests.engine.test_ledger_store import open_store

    conn, db, ledger = open_store(pg_database)
    try:
        a = corporate(ActionType.DIVIDEND, amount=Money(Decimal(".3"), "USD"))
        ref = selected(a)
        original = plan_action(a, ref=ref, posted_at=OPEN, fifo=fifo(), calendar=CAL, prior_close_quantity=Decimal(10))
        first = ledger.append_batch(BookBatch("R1", None, 1, "fifo-cumulative-v1", (ref,), (original,), (), OPEN))
        later = OPEN + timedelta(days=1)
        revised = corporate(ActionType.DIVIDEND, revision=2, known=later, amount=Money(Decimal(".4"), "USD"))
        new_ref = selected(revised, at=later)
        replacement = plan_action(revised, ref=new_ref, posted_at=later, fifo=fifo(), calendar=CAL, prior_close_quantity=Decimal(10))
        transactions = correction_plan(original, replacement, dependent_sources=())
        second = ledger.append_batch(BookBatch("R1", first.book_id, 2, first.policy_version,
                                               (ref, new_ref), transactions, (), later))
        assert len(ledger.history("R1", known_at=OPEN)) == 1
        assert ledger.get(first.book_id) == first
        assert len(second.transactions) == 2
        entries = [e for batch in ledger.ancestry(second.book_id) for tx in batch.transactions for e in tx.entries]
        assert sum((e.debit-e.credit for e in entries if e.account == f"DIVIDEND_RECEIVABLE:{NVDA}"), Decimal(0)) == 4
        assert db.fetchone("SELECT count(*) FROM ledger_transactions")[0] == 3
    finally:
        conn.close()
