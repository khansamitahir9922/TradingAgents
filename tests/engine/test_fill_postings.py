"""M5-02: journal facts originate in accepted, immutable OMS fills."""
from dataclasses import replace
from datetime import timedelta
from decimal import Context, Decimal, Inexact, Rounded, localcontext

import pytest

from investment_engine.audit.events import AuditStore
from investment_engine.events.outbox import Outbox
from investment_engine.ledger.contracts import AccountingUnavailable, LotMatch, SourceConflict, Unit
from investment_engine.ledger.postings import plan_fill, post_fill
from investment_engine.ledger.sources import fill_reference, validate_fill
from investment_engine.ledger.store import LedgerStore
from investment_engine.oms.order_states import OrderState as S, ProcessRole
from tests.engine.test_order_store import Env


def totals(transaction):
    with localcontext(Context(prec=34)):
        result = {}
        for entry in transaction.entries:
            key = (entry.account, entry.unit.key)
            result[key] = result.get(key, Decimal(0)) + entry.debit - entry.credit
        return result


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    yield e
    e.close()


@pytest.mark.postgres
def test_buy_journal_directions_and_source_validation(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    env.fill(order, quantity="10", price="100")
    fill = env.core.fills(order.order_id)[0]
    ref = validate_fill(order, fill, account_id="R1", at=env.clock.now(), orders=env.core)
    assert ref == fill_reference(order, fill)
    plan = plan_fill(order, fill, ref=ref, posted_at=env.clock.now())
    assert totals(plan.transaction) == {("INVENTORY_COST:EQ_US_NVDA", "CURRENCY:USD"): Decimal(1000),
        ("CASH", "CURRENCY:USD"): Decimal(-1000), ("CUSTODY_SHARES", "SECURITY:EQ_US_NVDA"): Decimal(10),
        ("SHARE_OFFSET", "SECURITY:EQ_US_NVDA"): Decimal(-10)}
    with pytest.raises(SourceConflict):
        validate_fill(order, replace(fill, price=Decimal(1)), account_id="R1", at=env.clock.now(), orders=env.core)
    with pytest.raises(SourceConflict):
        validate_fill(order, fill, account_id="R2", at=env.clock.now(), orders=env.core)


class Cost400:
    def consume(self, instrument_id, quantity, disposal):
        return (LotMatch("match", "pending", "acquisition", disposal, quantity, Decimal(400),
                         Unit("CURRENCY", "USD"), "fifo-cumulative-v1"),)


@pytest.mark.postgres
@pytest.mark.parametrize("sale_price,fee", [("120", "1"), ("80", "1"), ("100", "0"), (".01", "5")])
def test_sell_explicit_cost_plan_profit_loss_zero_and_fee_exceeds_proceeds(env, sale_price, fee):
    order = env.created(side="SELL", quantity="4")
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    # Use actual accepted fill fields; fees do not enter cost basis.
    env.fill(order, quantity="4", price=sale_price)
    accepted = env.core.fills(order.order_id)[0]
    fill = replace(accepted, fee=Decimal(fee))
    ref = fill_reference(order, fill)
    plan = plan_fill(order, fill, ref=ref, posted_at=env.clock.now(), cost_basis=Cost400())
    result = totals(plan.transaction)
    with localcontext(Context(prec=34)):
        proceeds = Decimal(sale_price) * 4
        assert result[("CASH", "CURRENCY:USD")] == proceeds - Decimal(fee)
        assert result[("INVENTORY_COST:EQ_US_NVDA", "CURRENCY:USD")] == -400
        assert result.get(("REALIZED_PNL:EQ_US_NVDA", "CURRENCY:USD"), Decimal(0)) == 400 - proceeds
    assert plan.lot_matches[0].cost == 400
    with pytest.raises(AccountingUnavailable, match="cost"):
        plan_fill(order, fill, ref=ref, posted_at=env.clock.now())


@pytest.mark.postgres
def test_partial_and_accepted_cancelled_late_fill_have_distinct_sources(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    env.fill(order, quantity="3", fill_id="part")
    env.walk(order, S.CANCEL_PENDING, S.CANCELLED)
    env.fill(order, quantity="7", fill_id="late")
    refs = [validate_fill(order, f, account_id="R1", at=env.clock.now(), orders=env.core) for f in env.core.fills(order.order_id)]
    assert len(refs) == 2 and len({r.source_id for r in refs}) == 2
    assert env.worker.get(order.order_id)[1].state is S.CANCELLED


@pytest.mark.postgres
def test_unknown_refused_or_not_yet_delivered_fill_cannot_post(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    env.fill(order)
    fill = env.core.fills(order.order_id)[0]
    with pytest.raises(AccountingUnavailable):
        validate_fill(order, fill, account_id="R1", at=fill.recorded_at - timedelta(seconds=1), orders=env.core)
    with pytest.raises(SourceConflict):
        validate_fill(order, replace(fill, broker_fill_id="never-accepted"), account_id="R1", at=env.clock.now(), orders=env.core)


@pytest.mark.postgres
def test_post_fill_idempotent_and_decimal_context_independent(env):
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    env.fill(order)
    fill = env.core.fills(order.order_id)[0]
    ref = fill_reference(order, fill)
    expected = plan_fill(order, fill, ref=ref, posted_at=env.clock.now())
    with localcontext() as ctx:
        ctx.prec = 1
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        assert plan_fill(order, fill, ref=ref, posted_at=env.clock.now()) == expected
    ledger = LedgerStore(env.db, audit=AuditStore(env.db), outbox=Outbox(env.db, writer=ProcessRole.CORE, clock=env.clock),
                         clock=env.clock, command_clock=env.clock)
    # Activation is deliberately required: a fresh ledger cannot invent capital.
    with pytest.raises(AccountingUnavailable, match="activat"):
        post_fill(order, fill, ledger=ledger, orders=env.core)
