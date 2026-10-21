"""Validated stored economic sources; broker anomalies never become postings."""
from datetime import datetime

from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    SourceBundle,
    SourceConflict,
    SourceRef,
    identity,
)
from investment_engine.market.availability import check_utc
from investment_engine.oms.orders import Fill, Order
from investment_engine.portfolio.snapshot import StartingState


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
