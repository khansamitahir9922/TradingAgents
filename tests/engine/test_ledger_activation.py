"""M5-02: explicit opening basis, command authorization and accepted negative cash."""
from dataclasses import replace
from decimal import Decimal

import pytest

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.events.outbox import Outbox
from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    OpeningLot,
    SourceConflict,
    Unit,
)
from investment_engine.ledger.postings import post_fill
from investment_engine.ledger.sources import opening_bundle
from investment_engine.ledger.store import LedgerStore
from investment_engine.oms.order_states import OrderState as S, ProcessRole
from investment_engine.oms.orders import Fill, FillOutcome
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
from tests.engine.test_fill_postings import Cost400, totals
from tests.engine.test_order_store import OWNER, Env

pytestmark = pytest.mark.postgres


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    audit = AuditStore(e.db)
    e.snapshots = PortfolioSnapshotStore(e.db, audit, e.accounts, e.clock)
    e.ledger = LedgerStore(e.db, audit=audit, outbox=Outbox(e.db, writer=ProcessRole.CORE, clock=e.clock),
                           clock=e.clock, command_clock=e.clock)
    yield e
    e.close()


def activate(e, *, cash=Decimal(100000), positions=(), lots=None):
    start = e.snapshots.declare_start("R1", by=OWNER, reason="known starting state", cash=cash,
                                       positions=positions, effective_at=e.clock.now())
    bundle = opening_bundle(start, at=e.clock.now())
    return e.ledger.activate("R1", opening_lots=() if lots is None else lots(start), source_bundle=bundle,
                              by=OWNER, reason="explicit migration to authoritative ledger")


def test_cash_start_buy_sell_activation_and_duplicate_source_retry(env):
    opening = activate(env)
    assert totals(opening.transactions[0])[("CASH", "CURRENCY:USD")] == 100000
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    # Existing Env.fill uses zero fees: accepted facts are immutable.
    env.fill(order, quantity="10", price="100")
    fill = env.core.fills(order.order_id)[0]
    result = post_fill(order, fill, ledger=env.ledger, orders=env.core)
    again = post_fill(order, fill, ledger=env.ledger, orders=env.core)
    assert result.book_id == again.book_id
    assert env.db.fetchone("SELECT count(*) FROM ledger_transactions")[0] == 2
    assert len(env.ledger.history("R1", known_at=env.clock.now())) == 2


@pytest.mark.parametrize("lots", [None, "wrong-quantity", "wrong-start"])
def test_opening_position_without_matching_explicit_cost_does_not_activate(env, lots):
    def declarations(start):
        return (OpeningLot("decl", start.state_id if lots != "wrong-start" else "wrong", "R1", "EQ_US_NVDA",
                           Decimal(9 if lots == "wrong-quantity" else 10), Decimal(1000), Unit("CURRENCY", "USD"),
                           start.effective_at, env.clock.now(), "owner", "recorded acquisition cost"),)
    with pytest.raises((AccountingUnavailable, ValueError)):
        activate(env, positions=(("EQ_US_NVDA", Decimal(10)),), lots=declarations if lots else None)
    assert env.ledger.activation("R1") is None
    assert env.db.fetchone("SELECT count(*) FROM ledger_entries")[0] == 0
    assert env.snapshots.starting_state("R1").positions == (("EQ_US_NVDA", Decimal(10)),)


def test_explicit_opening_lot_is_saved_without_repricing_and_cannot_be_changed(env):
    def declaration(start):
        return (OpeningLot("decl", start.state_id, "R1", "EQ_US_NVDA", Decimal(10), Decimal("123.4567"),
                           Unit("CURRENCY", "USD"), start.effective_at, env.clock.now(), "owner", "actual cost"),)
    book = activate(env, positions=(("EQ_US_NVDA", Decimal(10)),), lots=declaration)
    assert totals(book.transactions[0])[("INVENTORY_COST:EQ_US_NVDA", "CURRENCY:USD")] == Decimal("123.4567")
    start = env.snapshots.starting_state("R1")
    changed = replace(declaration(start)[0], total_cost=Decimal(9999))
    with pytest.raises(SourceConflict):
        env.ledger.activate("R1", opening_lots=(changed,), source_bundle=opening_bundle(start, at=env.clock.now()),
                            by=OWNER, reason="attempt rewrite")


def test_forged_admin_actor_refused_and_accepted_negative_cash_is_not_erased(env):
    activate(env, cash=Decimal(1))
    start = env.snapshots.starting_state("R1")
    fake = Actor(ActorKind.OPERATOR, "unregistered", "ADMIN", "test")
    with pytest.raises(PermissionError):
        env.ledger.activate("R1", opening_lots=(), source_bundle=opening_bundle(start, at=env.clock.now()),
                            by=fake, reason="forged admin")
    order = env.created()
    env.walk(order, S.SUBMITTING, S.SUBMITTED)
    env.fill(order, quantity="10", price="100")
    fill = env.core.fills(order.order_id)[0]
    result = post_fill(order, fill, ledger=env.ledger, orders=env.core)
    assert "negative cash" in result.breaches
    assert env.ledger.get(result.book_id).transactions[0].sources[0].stored_record_id == fill.fill_id
    assert len(env.core.fills(order.order_id)) == 1


def test_exact_adr_buy_sell_with_recorded_fees_not_research_marks(env):
    activate(env)
    for side, quantity, price, broker_id in (("BUY", "10", "100", "buy"), ("SELL", "4", "120", "sell")):
        order = env.created(side=side, quantity=quantity)
        status = env.walk(order, S.SUBMITTING, S.SUBMITTED)
        fill = Fill(order.order_id, Decimal(quantity), Decimal(price), Decimal(1), "USD", env.clock.now(),
                    env.clock.now(), env.clock.now(), broker_id, "{}")
        assert env.worker.record_fill(fill, expected_aggregate_version=status.aggregate_version) is FillOutcome.RECORDED
        post_fill(order, fill, ledger=env.ledger, orders=env.core, cost_basis=Cost400() if side == "SELL" else None)
    result = {}
    for batch in env.ledger.history("R1", known_at=env.clock.now()):
        for tx in batch.transactions:
            for key, value in totals(tx).items():
                result[key] = result.get(key, Decimal(0)) + value
    assert result[("CASH", "CURRENCY:USD")] == Decimal(99478)
    assert result[("CUSTODY_SHARES", "SECURITY:EQ_US_NVDA")] == Decimal(6)
    assert result[("INVENTORY_COST:EQ_US_NVDA", "CURRENCY:USD")] == Decimal(600)
    assert result[("REALIZED_PNL:EQ_US_NVDA", "CURRENCY:USD")] == Decimal(-80)
    assert result[("FEES", "CURRENCY:USD")] == Decimal(2)
