"""Validated stored economic sources; broker anomalies never become postings."""
from datetime import datetime, timedelta

from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    SourceBundle,
    SourceConflict,
    SourceRef,
    identity,
)
from investment_engine.market.availability import check_utc
from investment_engine.market.corporate_actions import CorporateAction
from investment_engine.oms.orders import Fill, Order
from investment_engine.portfolio.snapshot import StartingState
from investment_engine.quant.adjusted import AdjustmentUnavailable, require_coverage


def opening_bundle(start: StartingState, *, at: datetime) -> SourceBundle:
    """Declared research capital is an explicit initial condition, not market history.

    The saved economic identity excludes the live declaration command's timestamp.
    The original stored state (including that provenance) is compared on activation.
    """
    if not isinstance(start, StartingState):
        raise TypeError("stored StartingState required")
    check_utc(at, "at")
    ref = SourceRef("opening", start.state_id, 1, start.state_id, start.state_id.removeprefix("sst-"),
                    start.effective_at, start.effective_at, start.effective_at, "declared")
    return SourceBundle(start.account_id, at, (start,), (ref,), "declared", f"declared-start:{start.state_id}", (), "v1")


def fill_reference(order: Order, fill: Fill) -> SourceRef:
    if not isinstance(order, Order) or not isinstance(fill, Fill):
        raise TypeError("Order and Fill required")
    if fill.order_id != order.order_id or fill.currency != "USD":
        raise SourceConflict("fill/order currency or identity mismatch")
    return SourceRef("fill", f"{order.account_id}/{order.order_id}/{fill.fill_id}", 1, fill.fill_id,
                     identity((order, fill)), fill.executed_at, fill.recorded_at, fill.delivered_at, "oms")


def validate_fill(order: Order, fill: Fill, *, account_id: str, at: datetime, orders) -> SourceRef:
    """Require the actual immutable accepted fill, not merely a plausible DTO."""
    check_utc(at, "at")
    if order.account_id != account_id:
        raise SourceConflict("fill belongs to another investment account")
    try:
        stored_order, _ = orders.get(order.order_id)
    except KeyError:
        raise SourceConflict("order is not stored") from None
    if stored_order != order:
        raise SourceConflict("order does not match its stored immutable content")
    matches = tuple(f for f in orders.fills(order.order_id) if f.fill_id == fill.fill_id)
    if matches != (fill,):
        raise SourceConflict("fill does not match an accepted OMS record")
    ref = fill_reference(order, fill)
    if max(ref.known_at, ref.effective_at) > at:
        raise AccountingUnavailable(account_id, at, ("accepted fill not yet effective/delivered at cutoff",), (ref,))
    return ref


def action_reference(action, *, delivered_at, calendar):
    """Delivery comes from the public replay event or observed ingestion evidence.

    Never substitute the action's availability or its later provider-download time
    for actual replay delivery. The source selector supplies that evidence explicitly.
    """
    if not isinstance(action, CorporateAction):
        raise TypeError("CorporateAction required")
    check_utc(delivered_at, "delivered_at")
    if delivered_at < action.available_from:
        raise ValueError("action cannot be delivered before availability")
    effective = calendar.session(action.ex_date).open
    key = f"{action.source}/{action.instrument_id}/{action.action_type}/{action.ex_date}"
    return SourceRef("action", key, action.revision, f"{key}/{action.revision}/{action.import_id}",
                     identity(action), effective, action.available_from, delivered_at, action.source)


def validate_action(action, *, account_id, reader, provider, instrument_id, delivered_at, at, calendar, coverage):
    check_utc(at, "at")
    if action.source != provider or action.instrument_id != instrument_id:
        raise SourceConflict("action provider/instrument mismatch")
    stored = reader.action_revision_history(provider, instrument_id, action.ex_date,
                                             action.ex_date + timedelta(days=1), types=(action.action_type,))
    matches = [a for a in stored if a.source == provider and a.instrument_id == instrument_id
               and a.ex_date == action.ex_date and a.action_type == action.action_type and a.revision == action.revision]
    if matches != [action]:
        raise SourceConflict("action differs from its stored immutable revision")
    try:
        require_coverage(coverage, source=provider, instrument_id=instrument_id, action_type=action.action_type,
                         first=action.ex_date, last=action.ex_date, at=at)
    except AdjustmentUnavailable as exc:
        raise AccountingUnavailable(account_id, at, (str(exc),)) from None
    ref = action_reference(action, delivered_at=delivered_at, calendar=calendar)
    if ref.known_at > at:
        raise AccountingUnavailable(account_id, at, ("action revision not available/delivered at cutoff",), (ref,))
    return ref
