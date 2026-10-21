"""Source-driven opening/fill plans. FIFO is injected through M5-00's port."""
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Context, Decimal, localcontext
from fractions import Fraction

from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    BookBatch,
    CostBasisPort,
    JournalTransaction,
    LotMatch,
    SourceConflict,
    SourceRef,
    Unit,
    journal,
)
from investment_engine.ledger.lots import FifoBook
from investment_engine.ledger.sources import fill_reference, validate_fill
from investment_engine.oms.intents import Side
from investment_engine.oms.orders import Fill, Order


@dataclass(frozen=True)
class FillPosting:
    transaction: JournalTransaction
    lot_matches: tuple[LotMatch, ...]


@dataclass(frozen=True)
class PostingResult:
    book_id: str
    source: SourceRef
    breaches: tuple[str, ...]


def plan_fill(order: Order, fill: Fill, *, ref: SourceRef, posted_at: datetime,
              cost_basis: CostBasisPort | None = None) -> FillPosting:
    """Pure journal shape; callers must select sources through validate_fill first."""
    if ref != fill_reference(order, fill):
        raise SourceConflict("fill reference/content mismatch")
    unit = Unit("CURRENCY", fill.currency)
    shares = Unit("SECURITY", order.instrument_id)
    matches = ()
    with localcontext(Context(prec=34)):
        notional = fill.quantity * fill.price
        if order.side is Side.BUY:
            lines = ((f"INVENTORY_COST:{order.instrument_id}", unit, notional),
                     ("FEES", unit, fill.fee), ("CASH", unit, -(notional + fill.fee)),
                     ("CUSTODY_SHARES", shares, fill.quantity), ("SHARE_OFFSET", shares, -fill.quantity))
        else:
            if cost_basis is None:
                raise AccountingUnavailable(order.account_id, posted_at, ("SELL needs an explicit cost plan",), (ref,))
            try:
                matches = tuple(cost_basis.consume(order.instrument_id, fill.quantity, fill.fill_id))
            except AccountingUnavailable as exc:
                raise AccountingUnavailable(order.account_id, posted_at, exc.reasons, (ref,)) from None
            if not matches or sum((Fraction(m.quantity) for m in matches), Fraction()) != Fraction(fill.quantity):
                raise AccountingUnavailable(order.account_id, posted_at, ("cost plan does not cover the sale quantity",), (ref,))
            if any(m.disposal != fill.fill_id or m.unit != unit for m in matches):
                raise SourceConflict("lot plan disposal/unit mismatch")
            cost = sum((m.cost for m in matches), Decimal(0))
            lines = (("CASH", unit, notional - fill.fee), ("FEES", unit, fill.fee),
                     (f"INVENTORY_COST:{order.instrument_id}", unit, -cost),
                     (f"REALIZED_PNL:{order.instrument_id}", unit, cost - notional),
                     ("CUSTODY_SHARES", shares, -fill.quantity), ("SHARE_OFFSET", shares, fill.quantity))
    return FillPosting(journal(order.account_id, fill.executed_at, posted_at, (ref,), lines), matches)


def _cash_breaches(book, ledger):
    with localcontext(Context(prec=34)):
        cash = sum((entry.debit - entry.credit for batch in ledger.ancestry(book.book_id)
                    for tx in batch.transactions for entry in tx.entries
                    if entry.account == "CASH" and entry.unit == Unit("CURRENCY", "USD")), Decimal(0))
    return ("negative cash",) if cash < 0 else ()


def plan_fifo_fill(order, fill, *, ref, posted_at, fifo: FifoBook):
    """Apply a validated source to a rebuildable FIFO plan, never a price mark."""
    if not isinstance(fifo, FifoBook) or fifo.account_id != order.account_id:
        raise SourceConflict("FIFO plan belongs to another investment account")
    plan = plan_fill(order, fill, ref=ref, posted_at=posted_at, cost_basis=fifo)
    if order.side is Side.BUY:
        cost = next(e.debit for e in plan.transaction.entries if e.account == f"INVENTORY_COST:{order.instrument_id}")
        fifo.acquire(order.instrument_id, fill.quantity, cost, fill.fill_id, at=fill.executed_at)
    return plan


def post_fill(order, fill, *, ledger, orders, cost_basis=None):
    """Commit a selected accepted fill exactly once, including a real cash breach."""
    at = ledger._clock.now()
    with ledger.db.transaction():
        ledger.db.lock(f"account-control|{order.account_id}")
        ledger.db.lock(f"ledger|{order.account_id}")
        ref = validate_fill(order, fill, account_id=order.account_id, at=at, orders=orders)
        if ledger.activation(order.account_id) is None:
            raise AccountingUnavailable(order.account_id, at, ("ledger activation required",), (ref,))
        history = ledger.history(order.account_id, known_at=at)
        for old in history:
            if ref in old.sources:
                return PostingResult(old.book_id, ref, _cash_breaches(old, ledger))
        head = history[-1]
        plan = (plan_fifo_fill(order, fill, ref=ref, posted_at=at, fifo=cost_basis) if isinstance(cost_basis, FifoBook)
                else plan_fill(order, fill, ref=ref, posted_at=at, cost_basis=cost_basis))
        batch = BookBatch(order.account_id, head.book_id, head.version + 1, head.policy_version,
                          (*head.sources, ref), (plan.transaction,), plan.lot_matches, at)
        batch = replace(batch, lot_matches=tuple(replace(m, book_id=batch.book_id) for m in batch.lot_matches))
        ledger.append_batch(batch)
        return PostingResult(batch.book_id, ref, _cash_breaches(batch, ledger))
