"""The broker contract suite (architecture Part J "contract tests"; docs/tasks/M4-06.md rule 10).

Plain functions over a `BrokerPort` factory, so every adapter runs the same
checks: the simulator and the test double now (tests/engine/test_simulated_broker.py and
test_broker_double_contract.py), M7's paper adapter later. Each
function raises AssertionError on a breach. A case gets a fresh broker from
`make()` and an order from `make_order(n)`; `before_open` is a time before the
order's target session opens.
"""

from collections.abc import Callable
from datetime import datetime, timedelta


def submit_then_lookup(make: Callable, make_order: Callable, before_open: datetime) -> None:
    broker, order = make(), make_order(1)
    result = broker.submit(order, at=before_open)
    assert result.accepted and result.broker_order_id, result
    report = broker.lookup(order.client_order_id, at=before_open)
    assert report is not None and report.client_order_id == order.client_order_id
    assert report.broker_order_id == result.broker_order_id


def submit_is_idempotent(make: Callable, make_order: Callable, before_open: datetime) -> None:
    broker, order = make(), make_order(2)
    first = broker.submit(order, at=before_open)
    again = broker.submit(order, at=before_open + timedelta(seconds=1))
    assert again.broker_order_id == first.broker_order_id, (first, again)


def unknown_order_has_no_record(make: Callable, make_order: Callable, before_open: datetime) -> None:
    broker = make()
    assert broker.lookup("ie-never-submitted", at=before_open) is None
    assert broker.cancel("ie-never-submitted", at=before_open).outcome == "UNKNOWN_ORDER"


def cancel_before_the_open_is_conclusive(make: Callable, make_order: Callable, before_open: datetime) -> None:
    broker, order = make(), make_order(3)
    broker.submit(order, at=before_open)
    result = broker.cancel(order.client_order_id, at=before_open + timedelta(seconds=1))
    assert result.outcome == "CANCELLED", result
    again = broker.cancel(order.client_order_id, at=before_open + timedelta(seconds=2))
    assert again.outcome == "CANCELLED"


def messages_are_stable_and_filtered_by_delivery(make: Callable, make_order: Callable, before_open: datetime) -> None:
    broker, order = make(), make_order(4)
    broker.submit(order, at=before_open)
    later = before_open + timedelta(seconds=5)
    first = broker.messages(after=None, at=later)
    assert first == broker.messages(after=None, at=later), "repeated delivery must give the same messages"
    assert all(m.delivered_at <= later for m in first)
    assert broker.messages(after=None, at=before_open - timedelta(days=1)) == []
    if first:
        assert broker.messages(after=first[-1].message_id, at=later) == []


def cancel_after_a_fill_is_too_late(make: Callable, make_order: Callable, before_open: datetime, *,
                                    fill: Callable) -> None:
    """`fill(broker, order)` makes the adapter fill the order completely and returns a time after the fill is
    delivered (Codex M4 review B12)."""
    broker, order = make(), make_order(5)
    assert broker.submit(order, at=before_open).accepted
    after = fill(broker, order)
    assert any(m.kind == "FILL" for m in broker.messages(after=None, at=after)), "the fill must be delivered"
    result = broker.cancel(order.client_order_id, at=after)
    assert result.outcome == "TOO_LATE", result


CASES = (submit_then_lookup, submit_is_idempotent, unknown_order_has_no_record, cancel_before_the_open_is_conclusive,
         messages_are_stable_and_filtered_by_delivery)
CASES_AFTER_A_FILL = (cancel_after_a_fill_is_too_late,)  # these need the adapter's `fill` hook

__all__ = ["CASES", "CASES_AFTER_A_FILL"]
