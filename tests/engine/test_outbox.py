"""The outbox and its publisher (docs/tasks/M4-01.md rules 1, 2, 7 and 8)."""

import threading
from datetime import UTC, datetime

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.events.envelope import SCHEMA_VERSION, EventEnvelope
from investment_engine.events.outbox import Outbox, read_envelope
from investment_engine.oms.order_states import ProcessRole
from investment_engine.storage.database import PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def envelope(aggregate_id="a1", version=1, event_type="test.happened", payload='{"n":1}') -> EventEnvelope:
    return EventEnvelope(event_type, SCHEMA_VERSION, "test", aggregate_id, version, NOW, NOW, "c", None, payload)


class Env:
    def __init__(self, dsn):
        self.dsn, self.opened = dsn, []
        self.db = self.connect()
        apply_pg_schema(self.db.connection)

    def connect(self) -> PostgresDatabase:
        self.opened.append(open_operational_pg(self.dsn))
        return PostgresDatabase(self.opened[-1])

    def outbox(self, role=ProcessRole.CORE, db=None) -> Outbox:
        return Outbox(db or self.connect(), writer=role, clock=ReplayClock(NOW))

    def log(self) -> list[str]:
        return [r[0] for r in self.db.fetchall("SELECT event_id FROM event_log ORDER BY sequence")]


@pytest.fixture
def env(pg_database):
    e = Env(pg_database)
    yield e
    for c in e.opened:
        c.close()


@pytest.mark.postgres
@pytest.mark.unit
def test_an_outbox_row_needs_the_changes_transaction(env):
    outbox = env.outbox()
    with pytest.raises(RuntimeError, match="inside the state change"):
        outbox.add(envelope())
    with pytest.raises(ZeroDivisionError), outbox._db.transaction():
        outbox.add(envelope())
        raise ZeroDivisionError("the state change fails: its event goes with it")
    assert outbox.pending() == 0


@pytest.mark.postgres
@pytest.mark.unit
def test_publishing_moves_rows_once_with_their_original_ids(env):
    outbox = env.outbox()
    with outbox._db.transaction():
        outbox.add(envelope("a1", 1))
        outbox.add(envelope("a1", 2))
    assert outbox.publish_pending() == 2
    assert outbox.publish_pending() == 0
    assert env.log() == [envelope("a1", 1).event_id, envelope("a1", 2).event_id]
    row = env.db.fetchone("SELECT event_id, event_type, schema_version, aggregate_type, aggregate_id, "
                          "aggregate_version, occurred_at, recorded_at, correlation_id, causation_id, payload "
                          "FROM event_log WHERE aggregate_version = 2")
    assert read_envelope(row) == envelope("a1", 2)


@pytest.mark.postgres
@pytest.mark.unit
def test_a_publisher_crash_before_commit_leaves_the_row_for_the_next_run(env, monkeypatch):
    outbox = env.outbox()
    with outbox._db.transaction():
        outbox.add(envelope())
    real = outbox._db.execute

    def crash(sql, params=None):
        if sql.startswith("UPDATE outbox"):
            raise KeyboardInterrupt("killed between the log insert and the mark")
        return real(sql, params)

    monkeypatch.setattr(outbox._db, "execute", crash)
    with pytest.raises(KeyboardInterrupt):
        outbox.publish_pending()
    monkeypatch.undo()
    assert env.log() == [] and outbox.pending() == 1  # the insert rolled back with the mark
    assert outbox.publish_pending() == 1
    assert env.log() == [envelope().event_id]


@pytest.mark.postgres
@pytest.mark.unit
def test_an_event_already_in_the_log_and_concurrent_publishers_give_one_copy(env):
    outbox = env.outbox()
    with outbox._db.transaction():
        for i in range(1, 41):
            outbox.add(envelope("b", i))
    e = envelope("b", 1)  # already logged, as a restore or a second publisher would have done
    env.db.execute("INSERT INTO event_log (event_id, event_type, schema_version, aggregate_type, aggregate_id, "
                   "aggregate_version, occurred_at, recorded_at, correlation_id, causation_id, payload, published_at) "
                   "VALUES (:id, :t, 1, 'test', 'b', 1, :at, :at, 'c', NULL, :p, :at)",
                   {"id": e.event_id, "t": e.event_type, "at": NOW, "p": e.payload})
    publishers = [env.outbox(), env.outbox()]
    barrier, counts = threading.Barrier(2), []

    def publish(p):
        barrier.wait()
        counts.append(sum(iter(lambda: p.publish_pending(limit=7), 0)))

    threads = [threading.Thread(target=publish, args=(p,)) for p in publishers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(counts) == 40 and outbox.pending() == 0
    assert sorted(env.log()) == sorted(envelope("b", i).event_id for i in range(1, 41))


@pytest.mark.postgres
@pytest.mark.unit
def test_outbox_content_never_changes_and_is_marked_published_once(env):
    from investment_engine.storage.database import AppendOnlyViolation

    outbox = env.outbox()
    with outbox._db.transaction():
        outbox.add(envelope())
    outbox.publish_pending()
    for sql in ("UPDATE outbox SET payload = 'x'", "UPDATE outbox SET published_at = NOW()", "DELETE FROM outbox",
                "DELETE FROM event_log"):
        with pytest.raises(AppendOnlyViolation):
            env.db.execute(sql)


@pytest.mark.postgres
@pytest.mark.unit
def test_the_order_store_writes_through_the_real_outbox(pg_database):
    """M4-00's injected port, filled by M4-01: an order's creation and its event commit together, then publish."""
    from investment_engine.audit.events import AuditStore
    from tests.engine.test_order_store import CORE_ACTOR, Env as OrderEnv

    orders = OrderEnv(pg_database)
    try:
        db = orders.core._db
        orders.core._outbox = Outbox(db, writer=ProcessRole.CORE, clock=ReplayClock(NOW))
        assert isinstance(orders.core._audit, AuditStore)
        order = orders.order()
        orders.core.create(order, by=CORE_ACTOR, correlation_id="c")
        assert orders.core._outbox.pending() == 1
        assert orders.core._outbox.publish_pending() == 1
        logged = db.fetchall("SELECT event_type, aggregate_id, aggregate_version FROM event_log")
        assert logged == [("order.created", order.order_id, 1)]
    finally:
        orders.close()
