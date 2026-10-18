"""Converting approved intents into orders (docs/tasks/M4-02.md rules 1–4 and 6)."""

import threading
from datetime import timedelta

import pytest

from investment_engine.events.outbox import Outbox
from investment_engine.oms import intent_states
from investment_engine.oms.conversion import convert_approved, intent_content_id
from investment_engine.oms.intents import IntentState
from investment_engine.oms.order_states import OrderState, ProcessRole
from investment_engine.oms.order_store import OrderStore
from investment_engine.portfolio.fingerprint import DeclaredFingerprints, fingerprint_of
from tests.engine.test_intent_pipeline import CAL, DAY, TARGET, Env, view_for
from tests.engine.test_order_store import CORE_ACTOR as CORE


def order_store(env, stores=None, role=ProcessRole.CORE):
    stores = stores or env.stores
    return OrderStore(stores.db, role=role, audit=stores.audit,
                      outbox=Outbox(stores.db, writer=role, clock=env.clock), clock=env.clock)


@pytest.fixture
def env(pg_database, tmp_path):
    e = Env(pg_database, tmp_path / "market")
    e.account("R2", level=2)
    yield e
    e.close()


def approved(env, day=DAY, **kw):
    view = view_for(env.stores, env.reader, day, **kw)
    record = env.propose("R2", view)
    return env.stores.intents.get(record.intent_id), view


@pytest.mark.postgres
@pytest.mark.unit
def test_an_approved_version_becomes_one_new_order_with_its_references_pinned(env):
    stored, view = approved(env)
    orders = order_store(env)
    report = convert_approved("R2", at=view.generated_at, stores=env.stores, orders=orders)
    (order,) = report.converted
    assert report.skipped == ()
    intent = stored.intent
    assert (order.side, order.quantity, order.limit_price, order.order_type, order.time_in_force,
            order.target_session) == (intent.side, intent.quantity, intent.limit_price, intent.order_type,
                                      intent.time_in_force, intent.target_session)
    assert order.intent_content_id == intent_content_id(intent)
    snapshot = env.stores.snapshots.get(intent.snapshot_id)
    assert order.position_fingerprint == fingerprint_of(snapshot)
    # the declared provider gives the same fingerprint later, at another time: an unchanged portfolio (B4)
    assert DeclaredFingerprints(env.stores.snapshots).at("R2", view.generated_at + timedelta(days=3),
                                                         excluding_order=order.order_id) == order.position_fingerprint
    assert env.stores.intents.get(intent.intent_id).state is IntentState.CONVERTED
    assert orders.get(order.order_id)[1].state is OrderState.NEW
    assert orders._outbox.pending() == 1


@pytest.mark.postgres
@pytest.mark.unit
def test_a_failure_inside_the_conversion_leaves_nothing_behind(env, monkeypatch):
    stored, view = approved(env)
    orders = order_store(env)
    monkeypatch.setattr(orders._outbox, "add", lambda e: (_ for _ in ()).throw(RuntimeError("crash at the event")))
    with pytest.raises(RuntimeError, match="crash at the event"):
        convert_approved("R2", at=view.generated_at, stores=env.stores, orders=orders)
    monkeypatch.undo()
    assert env.stores.intents.get(stored.intent.intent_id).state is IntentState.APPROVED
    assert env.count("orders") == 0 and env.count("outbox") == 0


@pytest.mark.postgres
@pytest.mark.unit
def test_only_approved_unexpired_latest_versions_convert_and_others_are_reported(env):
    stored, view = approved(env)
    orders = order_store(env)
    late = CAL.session(TARGET).close
    report = convert_approved("R2", at=late, stores=env.stores, orders=orders)
    assert report.converted == () and report.skipped == ((stored.intent.intent_id, 1, "approval expired"),)
    report = convert_approved("R2", at=view.generated_at, stores=env.stores, orders=orders)
    assert len(report.converted) == 1
    again = convert_approved("R2", at=view.generated_at, stores=env.stores, orders=orders)
    assert again.converted == () and again.skipped == ()  # CONVERTED is no longer APPROVED: nothing to report


@pytest.mark.postgres
@pytest.mark.unit
def test_two_core_engines_converting_the_same_version_make_one_order(env):
    stored, view = approved(env)
    a, b = env.connect(), env.connect()
    barrier, reports = threading.Barrier(2), []

    def run(stores):
        barrier.wait()
        reports.append(convert_approved("R2", at=view.generated_at, stores=stores, orders=order_store(env, stores)))

    threads = [threading.Thread(target=run, args=(s,)) for s in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(len(r.converted) for r in reports) == 1
    assert env.count("orders") == 1
    skipped = [s for r in reports for s in r.skipped]
    assert all(reason in ("no longer APPROVED (CONVERTED)", "already converted",
                          "intent changed meanwhile (stale write)") for *_, reason in skipped)


@pytest.mark.postgres
@pytest.mark.unit
def test_a_bare_transition_to_converted_is_still_refused(env):
    stored, _ = approved(env)
    with pytest.raises(intent_states.OrdersNotBuilt):
        env.stores.intents.transition(stored.intent.intent_id, 1, IntentState.CONVERTED,
                                      expected_aggregate_version=stored.aggregate_version, at=env.clock.now(),
                                      by=CORE, reason="x")


@pytest.mark.postgres
@pytest.mark.unit
def test_the_execution_worker_can_not_convert(env):
    _, view = approved(env)
    with pytest.raises(ValueError, match="Core Engine"):
        convert_approved("R2", at=view.generated_at, stores=env.stores,
                         orders=order_store(env, role=ProcessRole.EXECUTION))
