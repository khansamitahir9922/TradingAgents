"""M5-05: full late-source closure, current replacements and atomic rollback."""
from dataclasses import fields, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.config import market_store_dir
from investment_engine.ledger.balances import balances
from investment_engine.ledger.contracts import AccountingUnavailable, SourceBundle, SourceConflict
from investment_engine.ledger.restate import sync_account
from investment_engine.ledger.sources import action_reference, fill_reference, opening_bundle
from investment_engine.lineage.records import canonical_json
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import ActionObservation, MarketDataWriter
from investment_engine.money import Money
from tests.engine.test_ledger_actions import CAL, NVDA, corporate, coverage
from tests.engine.test_ledger_activation import env as env
from tests.engine.test_ledger_time import accepted
from tests.engine.test_order_store import OWNER

pytestmark = pytest.mark.postgres


def persist(a):
    names = {f.name for f in fields(ActionObservation)} - {"backfill_available_from"}
    obs = ActionObservation(**{n: getattr(a, n) for n in names}, backfill_available_from=a.available_from if a.revision == 1 else None)
    MarketDataWriter(market_store_dir()).write_corporate_actions([obs], a.import_id)
    return next(v for v in MarketDataReader(market_store_dir()).action_revision_history(a.source, a.instrument_id, a.ex_date, a.ex_date+timedelta(days=1))
                if v.revision == a.revision)


def bundle(e, actions=(), deliveries=None, pairs=None):
    through = e.clock.now()
    start = e.snapshots.starting_state("R1")
    initial = opening_bundle(start, at=through)
    pairs = [(o, f) for o, _ in e.core.for_account("R1") for f in e.core.fills(o.order_id)] if pairs is None else pairs
    records = [start, *pairs, *actions, coverage(through)]
    refs = [*initial.references, *(fill_reference(o, f) for o, f in pairs)]
    refs.extend(action_reference(a, delivered_at=deliveries[a.import_id], calendar=CAL) for a in actions)
    return SourceBundle("R1", through, tuple(records), tuple(refs), "yfinance", "fixture-verified-coverage", (), "v1")


def setup(e):
    start = e.snapshots.declare_start("R1", by=OWNER, reason="historical declared initial condition",
                                      effective_at=datetime(2019,1,2,tzinfo=e.clock.now().tzinfo))
    e.ledger.activate("R1",opening_lots=(),source_bundle=opening_bundle(start,at=e.clock.now()),
                       by=OWNER,reason="explicit historical accounting activation")
    now = e.clock.now()
    buy, fill = accepted(e, "BUY", "10", "100", executed=datetime(2024,5,28,15,tzinfo=now.tzinfo), recorded=now, fee="0", broker_id="old-buy")
    sale, out = accepted(e, "SELL", "50", "20", executed=datetime(2024,6,12,15,tzinfo=now.tzinfo), recorded=now, fee="0", broker_id="sale")
    split = persist(corporate(known=datetime(2024,6,10,4,tzinfo=now.tzinfo), import_id="split1"))
    dividend = persist(corporate(ActionType.DIVIDEND, known=datetime(2024,6,11,4,tzinfo=now.tzinfo),
                                 ex_date=date(2024,6,11), amount=Money(Decimal(".3"),"USD"), import_id="div1"))
    deliveries = {split.import_id: now, dividend.import_id: now}
    selected = bundle(e, (split, dividend), deliveries)
    first = sync_account("R1", through=now, sources=selected, ledger=e.ledger)
    return split, dividend, deliveries, first


def current(e, book):
    return balances("R1", effective_at=e.clock.now(), known_at=e.clock.now(), book_id=book, ledger=e.ledger)


def test_late_pre_split_acquisition_restates_sale_and_dividend_and_old_queries_stay_identical(env):
    split, dividend, deliveries, report = setup(env)
    old_at = env.clock.now()
    original = current(env, report.book_id)
    assert original.positions == ((NVDA, Decimal(50)),) and original.gross_realized == 500
    assert original.dividend_income == 30
    encoded = canonical_json(original)
    later = old_at + timedelta(days=1)
    accepted(env, "BUY", "5", "200", executed=datetime(2024,5,27,15,tzinfo=later.tzinfo), recorded=later, fee="0", broker_id="late-buy")
    result = sync_account("R1", through=later, sources=bundle(env,(split,dividend),deliveries), ledger=env.ledger)
    changed = current(env, result.book_id)
    assert changed.positions == ((NVDA, Decimal(100)),) and changed.gross_realized == 0
    assert changed.dividend_income == 45 and changed.costs == ((NVDA,Decimal(1000)),)
    assert canonical_json(balances("R1", effective_at=old_at, known_at=old_at, book_id=report.book_id, ledger=env.ledger)) == encoded
    assert sync_account("R1", through=later, sources=bundle(env,(split,dividend),deliveries), ledger=env.ledger).book_id == result.book_id


def test_successive_split_corrections_reverse_active_replacements_not_originals(env):
    split, dividend, deliveries, first = setup(env)
    active = first.book_id
    for n, ratio in ((2,"8"),(3,"6")):
        env.clock.advance_by(timedelta(days=1))
        changed = persist(corporate(revision=n, known=env.clock.now(), ratio=Decimal(ratio), import_id=f"split{n}"))
        deliveries[changed.import_id] = env.clock.now()
        result = sync_account("R1", through=env.clock.now(), sources=bundle(env,(changed,dividend),deliveries), ledger=env.ledger)
        assert result.book_id != active
        assert current(env,result.book_id).positions == ((NVDA,Decimal(int(ratio)*10-50)),)
        active = result.book_id
    reversed_ids = [tx.reverses for b in env.ledger.ancestry(active) for tx in b.transactions if tx.reverses]
    assert len(reversed_ids) == len(set(reversed_ids))


def test_missing_accepted_fill_or_forged_action_cannot_advance_a_complete_head(env):
    split, dividend, deliveries, first = setup(env)
    before = env.ledger.read_head("R1",known_at=env.clock.now())
    with pytest.raises(AccountingUnavailable):
        sync_account("R1",through=env.clock.now(),sources=bundle(env,(split,dividend),deliveries,pairs=[]),ledger=env.ledger)
    forged = replace(split,ratio=Decimal(4))
    with pytest.raises(SourceConflict):
        sync_account("R1",through=env.clock.now(),sources=bundle(env,(forged,dividend),deliveries),ledger=env.ledger)
    assert env.ledger.read_head("R1",known_at=env.clock.now()) == before
    assert before.book_id == first.book_id


def test_mid_correction_failure_keeps_all_previous_records_and_no_new_head(env,monkeypatch):
    split, dividend, deliveries, first = setup(env)
    env.clock.advance_by(timedelta(days=1))
    changed = persist(corporate(revision=2,known=env.clock.now(),ratio=Decimal(8),import_id="split2"))
    deliveries[changed.import_id] = env.clock.now()
    original = env.db.execute

    def fail(sql,params=None):
        original(sql,params)
        if sql.startswith("INSERT INTO ledger_entries "):
            raise RuntimeError("crash during correction")

    monkeypatch.setattr(env.db,"execute",fail)
    with pytest.raises(RuntimeError,match="crash"):
        sync_account("R1",through=env.clock.now(),sources=bundle(env,(changed,dividend),deliveries),ledger=env.ledger)
    assert env.ledger.read_head("R1",known_at=env.clock.now()).book_id == first.book_id


def test_same_total_disposal_cost_still_restates_changed_fifo_attribution(env):
    split, dividend, deliveries, first = setup(env)
    original_sale = next(tx for b in env.ledger.ancestry(first.book_id) for tx in b.transactions
                         if any(e.account.startswith("REALIZED_PNL:") for e in tx.entries))
    later = env.clock.now() + timedelta(days=1)
    _, late_fill = accepted(env,"BUY","5","100",executed=datetime(2024,5,27,15,tzinfo=later.tzinfo),
                            recorded=later,fee="0",broker_id="late-same-price")
    result = sync_account("R1",through=later,sources=bundle(env,(split,dividend),deliveries),ledger=env.ledger)
    assert original_sale.transaction_id in result.reversed_transactions
    assert current(env,result.book_id).gross_realized == 500
    assert any(m.acquisition == late_fill.fill_id for m in env.ledger.get(result.book_id).lot_matches)


def test_equal_time_fifo_correction_has_new_identity_even_when_amounts_do_not_change(env):
    split, dividend, deliveries, first = setup(env)
    at = env.clock.now()
    before = canonical_json(current(env, first.book_id))
    old_sale = next(tx for batch in env.ledger.ancestry(first.book_id) for tx in batch.transactions
                    if any(e.account.startswith("REALIZED_PNL:") for e in tx.entries))
    _, late = accepted(env, "BUY", "5", "100", executed=datetime(2024,5,27,15,tzinfo=at.tzinfo),
                       recorded=at, fee="0", broker_id="same-instant-late-acquisition")
    sources = bundle(env, (split, dividend), deliveries)
    changed = sync_account("R1", through=at, sources=sources, ledger=env.ledger)
    assert changed.changed and old_sale.transaction_id in changed.reversed_transactions
    assert current(env, changed.book_id).gross_realized == 500
    assert any(m.acquisition == late.fill_id for m in env.ledger.get(changed.book_id).lot_matches)
    assert canonical_json(current(env, first.book_id)) == before
    assert sync_account("R1", through=at, sources=sources, ledger=env.ledger).book_id == changed.book_id
