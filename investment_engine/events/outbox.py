"""The outbox and its publisher: save, then publish (Law 11; ADR-005; G4 "any restart"; docs/tasks/M4-01.md).

A store adds its envelope to the outbox inside the transaction of the state
change it announces, so neither commits without the other. `publish_pending`
then moves unpublished rows into the shared event log in one transaction: the
log insert and the published mark commit or roll back together, so a crashed
publish leaves the row unpublished and the next run publishes it once, with
its original `event_id`. `ON CONFLICT (event_id) DO NOTHING` covers a second
publisher and an event already in the log; it is not the crash path.

Each process calls `publish_pending` on start-up, before any other work, and
in its loop. Published rows and the log are kept; nothing is pruned in M4.
"""

from investment_engine.events.envelope import EventEnvelope
from investment_engine.market.availability import check_utc
from investment_engine.oms.order_states import ProcessRole
from investment_engine.storage.sqlite import port

_COLUMNS = ("event_id, event_type, schema_version, aggregate_type, aggregate_id, aggregate_version, occurred_at, "
            "recorded_at, correlation_id, causation_id, payload")


class Outbox:
    def __init__(self, db, *, writer: ProcessRole, clock) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("the outbox is PostgreSQL only (docs/tasks/M4-01.md)")
        self.writer, self._clock = ProcessRole(writer), clock

    def add(self, envelope: EventEnvelope) -> None:
        if not isinstance(envelope, EventEnvelope):
            raise TypeError("expected an EventEnvelope")
        if not self._db.in_transaction:
            raise RuntimeError("an outbox row is written only inside the state change's transaction (Law 11)")
        self._db.execute(
            f"INSERT INTO outbox ({_COLUMNS}, writer) VALUES (:id, :type, :schema, :agg_type, :agg_id, :version, "
            ":occurred, :recorded, :correlation, :causation, :payload, :writer)",
            {"id": envelope.event_id, "type": envelope.event_type, "schema": envelope.schema_version,
             "agg_type": envelope.aggregate_type, "agg_id": envelope.aggregate_id,
             "version": envelope.aggregate_version, "occurred": envelope.occurred_at,
             "recorded": envelope.recorded_at, "correlation": envelope.correlation_id,
             "causation": envelope.causation_id, "payload": envelope.payload, "writer": self.writer.value})

    def pending(self) -> int:
        return self._db.fetchone("SELECT COUNT(*) FROM outbox WHERE writer = :w AND published_at IS NULL",
                                 {"w": self.writer.value})[0]

    def publish_pending(self, *, limit: int = 100) -> int:
        """Move up to `limit` of this writer's unpublished rows to the event log; returns how many."""
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            rows = self._db.fetchall(
                "SELECT event_id FROM outbox WHERE writer = :w AND published_at IS NULL "
                "ORDER BY aggregate_type, aggregate_id, aggregate_version LIMIT :limit FOR UPDATE SKIP LOCKED",
                {"w": self.writer.value, "limit": limit})
            ids = [r[0] for r in rows]
            if not ids:
                return 0
            self._db.execute(
                f"INSERT INTO event_log ({_COLUMNS}, published_at) SELECT {_COLUMNS}, :now FROM outbox "
                "WHERE event_id = ANY(:ids) ORDER BY aggregate_type, aggregate_id, aggregate_version "
                "ON CONFLICT (event_id) DO NOTHING", {"ids": ids, "now": now})
            self._db.execute("UPDATE outbox SET published_at = :now WHERE event_id = ANY(:ids)",
                             {"ids": ids, "now": now})
            self._db.execute("NOTIFY investment_engine_events")
        return len(ids)


def read_envelope(row) -> EventEnvelope:
    """An envelope from a row of `_COLUMNS`; its derived id must match the stored one."""
    envelope = EventEnvelope(*row[1:])
    if envelope.event_id != row[0]:
        raise ValueError(f"stored event {row[0]} doesn't match its content")
    return envelope


__all__ = ["Outbox", "read_envelope"]
