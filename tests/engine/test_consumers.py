"""Idempotent consumers: once per event, in order per aggregate (docs/tasks/M4-01.md rules 3–5)."""

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.events.consumer import Consumer
from tests.engine.test_outbox import NOW, Env, envelope


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    e.db.execute("CREATE TABLE test_effects (event_id TEXT PRIMARY KEY, aggregate_id TEXT, version INTEGER)")
    yield e
    for c in e.opened:
        c.close()


def publish(env, *envelopes):
    outbox = env.outbox()
    with outbox._db.transaction():
        for e in envelopes:
            outbox.add(e)
    outbox.publish_pending(limit=1000)


def consumer(env, *, fail=None, name="test-consumer"):
    db = env.connect()

    def effect(e):
        if fail is not None and fail(e):
            raise RuntimeError(f"handler failed on {e.aggregate_id} v{e.aggregate_version}")
        db.execute("INSERT INTO test_effects VALUES (:id, :a, :v)",
                   {"id": e.event_id, "a": e.aggregate_id, "v": e.aggregate_version})

    return Consumer(db, name=name, handles={"test.happened": effect}, clock=ReplayClock(NOW))


def effects(env):
    return [(a, v) for a, v in env.db.fetchall("SELECT aggregate_id, version FROM test_effects ORDER BY aggregate_id, "
                                                "version")]


@pytest.mark.postgres
@pytest.mark.unit
def test_each_event_is_applied_once_and_a_rerun_adds_nothing(env):
    publish(env, envelope("a", 1), envelope("a", 2), envelope("b", 1))
    c = consumer(env)
    assert c.run_once().applied == 3
    assert c.run_once().applied == 0
    assert effects(env) == [("a", 1), ("a", 2), ("b", 1)]


@pytest.mark.postgres
@pytest.mark.unit
def test_a_crash_after_the_handler_before_commit_redelivers_and_applies_once(env, monkeypatch):
    publish(env, envelope("a", 1))
    c = consumer(env)
    real = c._db.execute

    def crash(sql, params=None):
        if sql.startswith("INSERT INTO processed_events"):
            raise KeyboardInterrupt("killed after the effect, before the commit")
        return real(sql, params)

    monkeypatch.setattr(c._db, "execute", crash)
    with pytest.raises(KeyboardInterrupt):
        c.run_once()
    monkeypatch.undo()
    assert effects(env) == []  # the effect rolled back with the mark
    assert c.run_once().applied == 1
    assert effects(env) == [("a", 1)]


@pytest.mark.postgres
@pytest.mark.unit
def test_a_failing_handler_holds_only_its_aggregate_and_applies_once_after_the_fix(env):
    publish(env, envelope("a", 1), envelope("a", 2), envelope("b", 1))
    broken = consumer(env, fail=lambda e: e.aggregate_id == "a" and e.aggregate_version == 1)
    report = broken.run_once()
    assert (report.applied, report.failed, report.held) == (1, 1, 1)
    assert effects(env) == [("b", 1)]
    assert env.db.fetchone("SELECT COUNT(*) FROM consumer_failures")[0] == 1
    assert consumer(env).run_once().applied == 2
    assert effects(env) == [("a", 1), ("a", 2), ("b", 1)]


@pytest.mark.postgres
@pytest.mark.unit
def test_versions_apply_in_order_and_a_gap_holds_only_that_aggregate(env):
    publish(env, envelope("a", 2), envelope("b", 1), envelope("c", 1), envelope("c", 3))  # a1 and c2 not yet published
    c = consumer(env)
    report = c.run_once()
    assert (report.applied, report.held) == (2, 2)
    assert effects(env) == [("b", 1), ("c", 1)]
    publish(env, envelope("a", 1), envelope("c", 2))
    assert c.run_once().applied == 4
    assert effects(env) == [("a", 1), ("a", 2), ("b", 1), ("c", 1), ("c", 2), ("c", 3)]


@pytest.mark.postgres
@pytest.mark.unit
def test_an_unknown_event_type_is_reported_unhandled_never_dropped(env):
    publish(env, envelope("a", 1, event_type="test.unknown"), envelope("a", 2))
    report = consumer(env).run_once()
    assert (report.unhandled, report.applied) == (1, 1)
    outcomes = env.db.fetchall("SELECT aggregate_version, outcome FROM processed_events ORDER BY aggregate_version")
    assert outcomes == [(1, "unhandled"), (2, "applied")]


@pytest.mark.unit
def test_the_envelope_id_is_derived_and_stable():
    assert envelope().event_id == envelope().event_id
    assert envelope("a", 2).event_id != envelope("a", 1).event_id
    with pytest.raises(ValueError):
        envelope(version=0)


@pytest.mark.postgres
@pytest.mark.unit
def test_a_failing_aggregate_larger_than_a_page_never_starves_another(env):
    """B10 (Codex M4 review): a held aggregate filled every page, so later aggregates were never considered."""
    publish(env, *[envelope("a", n) for n in range(1, 101)], envelope("b", 1))
    broken = consumer(env, fail=lambda e: e.aggregate_id == "a")
    for _ in range(3):
        report = broken.run_once(limit=100)
    assert effects(env) == [("b", 1)] and (report.failed, report.held) == (1, 99)
    fixed = consumer(env)
    while fixed.run_once(limit=100).applied:
        pass
    assert effects(env) == [("a", n) for n in range(1, 101)] + [("b", 1)]  # in order, each once


@pytest.mark.postgres
@pytest.mark.unit
def test_a_gap_with_more_than_a_page_behind_it_never_starves_another(env):
    publish(env, *[envelope("a", n) for n in range(2, 103)], envelope("b", 1))  # a1 not yet published
    c = consumer(env)
    report = c.run_once(limit=100)
    assert effects(env) == [("b", 1)] and (report.applied, report.held) == (1, 101)
    publish(env, envelope("a", 1))
    assert c.run_once(limit=60).applied == 60  # bounded work, in version order
    assert c.run_once(limit=100).applied == 42
    assert effects(env) == [("a", n) for n in range(1, 103)] + [("b", 1)]


@pytest.mark.postgres
@pytest.mark.unit
def test_a_page_of_failing_heads_never_starves_a_healthy_aggregate_behind_it(env):
    """R4 (Codex M4 re-review, B10): every call restarted at the same lexical heads, so `limit` failing aggregates
    hid every later one forever: a:1 and b:1 failing at limit 2 kept z:1 from ever running."""
    publish(env, envelope("a", 1), envelope("b", 1), envelope("z", 1))
    broken = consumer(env, fail=lambda e: e.aggregate_id != "z")
    for _ in range(4):
        broken.run_once(limit=2)
    assert effects(env) == [("z", 1)]


@pytest.mark.postgres
@pytest.mark.unit
def test_a_full_page_of_failing_heads_rotates_and_everything_recovers_exactly_once(env):
    failing = [f"f{n}" for n in range(5)]
    publish(env, *[envelope(a, v) for a in failing for v in (1, 2)], envelope("z", 1), envelope("z", 2))
    broken = consumer(env, fail=lambda e: e.aggregate_id in failing)
    for _ in range(3):
        broken.run_once(limit=5)  # a page exactly the size of the failing heads
    assert effects(env) == [("z", 1), ("z", 2)]
    fixed = consumer(env)
    while fixed.run_once(limit=5).applied:
        pass
    assert effects(env) == sorted([(a, v) for a in failing for v in (1, 2)] + [("z", 1), ("z", 2)])
    assert env.db.fetchone("SELECT COUNT(*) FROM processed_events")[0] == 12  # each event once
