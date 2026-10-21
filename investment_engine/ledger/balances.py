"""Bitemporal balances and raw-mark P&L pinned to one immutable book head."""
from collections import defaultdict
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from zoneinfo import ZoneInfo

from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    BalanceQuery,
    LedgerBalances,
    SourceRef,
    identity,
)
from investment_engine.ledger.lots import exact_decimal
from investment_engine.market.availability import check_utc
from investment_engine.market.candles import BarState, Candle, Timeframe


def _totals(query, ledger):
    head = ledger.get(query.book_id)
    if head.account_id != query.account_id or head.posted_at > query.known_at:
        raise AccountingUnavailable(query.account_id, query.known_at, ("book account/knowledge cutoff mismatch",))
    totals = defaultdict(Fraction)
    refs = {}
    for batch in ledger.ancestry(query.book_id):
        if batch.posted_at > query.known_at:
            continue
        for ref in batch.sources:
            if ref.known_at <= query.known_at and ref.effective_at <= query.effective_at:
                refs[ref.source_id] = ref
        for tx in batch.transactions:
            if tx.effective_at <= query.effective_at and tx.posted_at <= query.known_at:
                for entry in tx.entries:
                    totals[(entry.account, entry.unit.key)] += Fraction(entry.debit) - Fraction(entry.credit)
    opening = [r for batch in ledger.ancestry(query.book_id) for r in batch.sources if r.kind == "opening"]
    if opening and query.effective_at < min(r.effective_at for r in opening):
        raise AccountingUnavailable(query.account_id, query.known_at, ("query precedes the declared initial condition",))
    return totals, tuple(refs.values())


def balances(account_id, *, effective_at, known_at, book_id, ledger):
    query = BalanceQuery(account_id, effective_at, known_at, book_id)
    try:
        totals, refs = _totals(query, ledger)
    except KeyError:
        return AccountingUnavailable(account_id, known_at, ("no ledger book at cutoff",))
    except AccountingUnavailable as exc:
        return exc
    cash = totals[("CASH", "CURRENCY:USD")]
    positions, costs, receivables = [], [], []
    realized = income = fees = Fraction()
    reasons = []
    if cash < 0:
        reasons.append("negative cash from accepted facts")
    for (chart, unit), value in totals.items():
        if chart == "CUSTODY_SHARES" and unit.startswith("SECURITY:"):
            if value < 0:
                return AccountingUnavailable(account_id, known_at, ("accepted facts imply an unsupported short position",), refs)
            if value:
                positions.append((unit.removeprefix("SECURITY:"), exact_decimal(value)))
        elif unit == "CURRENCY:USD":
            if chart.startswith("INVENTORY_COST:") and value:
                if value < 0:
                    return AccountingUnavailable(account_id, known_at, ("inventory cost is negative",), refs)
                costs.append((chart.removeprefix("INVENTORY_COST:"), exact_decimal(value)))
            elif chart.startswith("DIVIDEND_RECEIVABLE:") and value:
                receivables.append((chart.removeprefix("DIVIDEND_RECEIVABLE:"), exact_decimal(value)))
            elif chart.startswith("REALIZED_PNL:"):
                realized -= value
            elif chart.startswith("DIVIDEND_INCOME:"):
                income -= value
            elif chart == "FEES":
                fees += value
    if any(instrument not in dict(positions) for instrument, _ in costs):
        reasons.append("inventory cost without held quantity")
    # A valid posted acquisition can have explicit zero remaining basis (including
    # a fully allocated cumulative rounding residual). Preserve known zero as an
    # explicit cost field; an absent cost supplied to the portfolio adapter is missing.
    cost_map = dict(costs)
    for instrument, _ in positions:
        cost_map.setdefault(instrument, Decimal(0))
    costs = tuple(sorted(cost_map.items()))
    return LedgerBalances(query, exact_decimal(cash), "USD", tuple(positions), tuple(costs), tuple(receivables),
                           exact_decimal(realized), exact_decimal(income), exact_decimal(fees), refs,
                           not reasons, tuple(reasons))


@dataclass(frozen=True)
class PnlValuation:
    balances: LedgerBalances
    market_value: Decimal | None
    unrealized: Decimal | None
    equity: Decimal | None
    net_pnl: Decimal | None
    opening_capital: Decimal
    mark_refs: tuple[SourceRef, ...]
    complete: bool
    reasons: tuple[str, ...]


def value_balances(value, *, marks, calendar, source, ledger):
    """Each supplied mark is (raw Candle, actual delivery time), never a float/price alone."""
    if isinstance(value, AccountingUnavailable):
        return value
    query = value.query
    totals, _ = _totals(query, ledger)
    capital = exact_decimal(-totals[("CAPITAL", "CURRENCY:USD")])
    reasons = list(value.reasons)
    refs = []
    market_value = Fraction()
    expected = None
    if value.positions:
        local_date = query.effective_at.astimezone(ZoneInfo(calendar.timezone)).date()
        expected = calendar.session(local_date) if calendar.is_session(local_date) and calendar.session(local_date).close <= query.effective_at else calendar.previous_session(local_date)
    for instrument, quantity in value.positions:
        if instrument not in marks:
            reasons.append(f"raw mark missing for {instrument}")
            continue
        candle, delivered = marks[instrument]
        check_utc(delivered, "mark delivery")
        if not isinstance(candle, Candle) or candle.source != source or candle.instrument_id != instrument or (
                candle.currency != value.currency or candle.timeframe is not Timeframe.D1 or candle.state is not BarState.CLOSED
                or candle.start_time != expected.open or candle.end_time != expected.close
                or candle.end_time > min(query.effective_at, query.known_at) or max(candle.available_from, delivered) > query.known_at):
            reasons.append(f"raw mark unavailable/incompatible for {instrument}")
            continue
        if any(r.kind == "action" and f"/{instrument}/" in r.identity and candle.end_time < r.effective_at <= query.effective_at
               for r in value.sources):
            reasons.append(f"raw mark predates applied action for {instrument}")
            continue
        raw = {f.name: (getattr(candle, f.name).value if isinstance(getattr(candle, f.name), Enum) else getattr(candle, f.name)) for f in fields(candle)}
        ref = SourceRef("mark", f"{source}/{instrument}/{candle.timeframe}/{candle.start_time.isoformat()}",
                        candle.revision, f"{candle.import_id}/{candle.start_time.isoformat()}", identity(raw),
                        candle.end_time, candle.available_from, delivered, source)
        refs.append(ref)
        market_value += Fraction(quantity) * Fraction(candle.close)
    if len(refs) != len(value.positions):
        return PnlValuation(value, None, None, None, None, capital, tuple(refs), False, tuple(reasons))
    cost = sum((Fraction(n) for _, n in value.costs), Fraction())
    receivable = sum((Fraction(n) for _, n in value.receivables), Fraction())
    unrealized = market_value - cost
    equity = Fraction(value.cash) + market_value + receivable
    pnl = Fraction(value.gross_realized) + unrealized + Fraction(value.dividend_income) - Fraction(value.fees)
    if pnl != equity - Fraction(capital):
        reasons.append("P&L does not reconcile to equity minus opening capital")
    return PnlValuation(value, exact_decimal(market_value), exact_decimal(unrealized), exact_decimal(equity),
                        exact_decimal(pnl), capital, tuple(refs), not reasons, tuple(reasons))
