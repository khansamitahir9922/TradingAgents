"""Split and dividend plans with explicit source, entitlement and correction evidence."""
from fractions import Fraction

from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    SourceConflict,
    Unit,
    amount,
    journal,
    reverse_transaction,
)
from investment_engine.ledger.lots import exact_decimal
from investment_engine.ledger.sources import action_reference
from investment_engine.market.availability import check_utc
from investment_engine.market.corporate_actions import ActionType
from investment_engine.oms.order_states import OPEN


class ClosureRequired(AccountingUnavailable):
    def __init__(self, account_id, cutoff, dependencies):
        self.dependencies = tuple(dependencies)
        super().__init__(account_id, cutoff, ("correction requires complete downstream dependency closure",), self.dependencies)


def plan_action(action, *, ref, posted_at, fifo, calendar, prior_close_quantity=None, orders=None):
    """Plan against a rebuildable FIFO object; never infer dividend payment."""
    check_utc(posted_at, "posted_at")
    if ref != action_reference(action, delivered_at=ref.delivered_at, calendar=calendar):
        raise SourceConflict("action reference differs from its source content")
    if ref.known_at > posted_at:
        raise AccountingUnavailable(fifo.account_id, posted_at, ("action not known at cutoff",), (ref,))
    effective = calendar.session(action.ex_date).open
    if effective > posted_at:
        return None
    if action.currency != "USD":
        raise AccountingUnavailable(fifo.account_id, posted_at, ("unsupported action currency",), (ref,))
    if orders is not None:
        for order, state, _filled in orders.as_of(fifo.account_id, posted_at):
            if state in OPEN and order.instrument_id == action.instrument_id and order.created_at < effective <= posted_at:
                raise AccountingUnavailable(fifo.account_id, posted_at, ("unresolved order crosses corporate action",), (ref,))
    if action.action_type is ActionType.SPLIT:
        delta = fifo.split(action.instrument_id, action.ratio)
        if not delta:
            return None
        unit = Unit("SECURITY", action.instrument_id)
        lines = (("CUSTODY_SHARES", unit, delta), ("SHARE_OFFSET", unit, delta.copy_negate()))
    elif action.action_type is ActionType.DIVIDEND:
        if prior_close_quantity is None:
            raise AccountingUnavailable(fifo.account_id, posted_at, ("dividend needs established prior-close ownership",), (ref,))
        amount(prior_close_quantity, "prior_close_quantity", whole=True)
        value = exact_decimal(Fraction(prior_close_quantity) * Fraction(action.amount.amount))
        if not value:
            return None
        unit = Unit("CURRENCY", "USD")
        lines = ((f"DIVIDEND_RECEIVABLE:{action.instrument_id}", unit, value),
                 (f"DIVIDEND_INCOME:{action.instrument_id}", unit, value.copy_negate()))
    else:
        raise AccountingUnavailable(fifo.account_id, posted_at, (f"unsupported action {action.action_type}",), (ref,))
    return journal(fifo.account_id, effective, posted_at, (ref,), lines)


def correction_plan(original, replacement, *, dependent_sources):
    """Only a complete local edge here; M5-05 supplies full restatement closure."""
    if dependent_sources:
        raise ClosureRequired(original.investment_account_id, replacement.posted_at, dependent_sources)
    if original.investment_account_id != replacement.investment_account_id or original.effective_at != replacement.effective_at:
        raise SourceConflict("correction account/effective time mismatch")
    old = original.sources
    new = replacement.sources
    if len(old) != 1 or len(new) != 1 or old[0].identity != new[0].identity or old[0].provider != new[0].provider or new[0].revision <= old[0].revision:
        raise SourceConflict("correction must identify a newer revision of the same provider action")
    return reverse_transaction(original, posted_at=replacement.posted_at), replacement


def restate_dependents(account_id, *, through, sources, ledger):
    """M5-05's complete source-validated closure; never a broker discrepancy repair."""
    from investment_engine.ledger.restate import sync_account

    return sync_account(account_id, through=through, sources=sources, ledger=ledger)
