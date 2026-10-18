"""Cancel requests: command rows from a named Admin or Trader (docs/tasks/M4-02.md rule 5; D31)."""

from datetime import timedelta

import pytest

from investment_engine.oms.conversion import convert_approved, request_cancel
from investment_engine.oms.orders import CancelProgress
from investment_engine.policy.accounts import NotAuthorized, Role
from tests.engine.test_conversion import approved, order_store
from tests.engine.test_intent_pipeline import NOW, OWNER, Env


@pytest.fixture
def env(pg_database, tmp_path):
    e = Env(pg_database, tmp_path / "market")
    e.account("R2", level=2)
    e.stores.accounts.add_operator("trader", Role.TRADER, by=OWNER, reason="test")
    e.stores.accounts.add_operator("viewer", Role.VIEWER, by=OWNER, reason="test")
    yield e
    e.close()


def converted_order(env):
    _, view = approved(env)
    orders = order_store(env)
    (order,) = convert_approved("R2", at=view.generated_at, stores=env.stores, orders=orders).converted
    return order, orders


@pytest.mark.postgres
@pytest.mark.unit
@pytest.mark.parametrize("operator", ["owner", "trader"])
def test_an_admin_or_trader_records_a_cancel_without_moving_the_order(env, operator):
    order, orders = converted_order(env)
    before = orders.get(order.order_id)[1]
    request = request_cancel(order.order_id, operator_id=operator, reason="changed my mind", command_at=NOW,
                             stores=env.stores, orders=orders)
    assert orders.get(order.order_id)[1] == before  # no state change, no version change (G3)
    (open_request,) = orders.open_cancels()
    assert open_request == (request, CancelProgress.REQUESTED, 1)
    assert request.requested_by.actor_id == operator


@pytest.mark.postgres
@pytest.mark.unit
def test_a_viewer_or_unknown_operator_cannot_cancel(env):
    order, orders = converted_order(env)
    for operator in ("viewer", "nobody"):
        with pytest.raises(NotAuthorized):
            request_cancel(order.order_id, operator_id=operator, reason="x", command_at=NOW, stores=env.stores,
                           orders=orders)
    assert orders.open_cancels() == []


@pytest.mark.postgres
@pytest.mark.unit
def test_a_cancel_needs_a_reason(env):
    order, orders = converted_order(env)
    with pytest.raises(ValueError, match="reason"):
        request_cancel(order.order_id, operator_id="owner", reason=" ", command_at=NOW + timedelta(seconds=1),
                       stores=env.stores, orders=orders)


@pytest.mark.postgres
@pytest.mark.unit
def test_the_admin_cli_records_a_cancel_and_refuses_a_viewer(env, pg_database, tmp_path, monkeypatch):
    from tests.engine.test_admin_cli_intents import _cli, run

    order, orders = converted_order(env)
    cli = _cli(monkeypatch, pg_database, tmp_path, NOW)
    refused = run(cli, "orders", "cancel", order.order_id, "--operator", "viewer", "--reason", "x")
    assert refused.exit_code == 1 and "Refused" in refused.output and "viewer" in refused.output
    assert orders.open_cancels() == []
    done = run(cli, "orders", "cancel", order.order_id, "--operator", "trader", "--reason", "stop it")
    assert done.exit_code == 0, done.output
    assert "CANCEL REQUESTED" in done.output and "unchanged" in done.output
    (request, progress, version) = orders.open_cancels()[0]
    assert (request.order_id, progress, version) == (order.order_id, CancelProgress.REQUESTED, 1)
