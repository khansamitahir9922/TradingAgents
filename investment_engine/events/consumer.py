"""Idempotent consumers of the event log (Law 11; ADR-005 sections 5 and 6; docs/tasks/M4-01.md).

A consumer applies each event once, in its own transaction, and records the
`event_id` it processed in that same transaction, so a crash before the
commit redelivers the event and its effect still appears once. Handlers do
database work only: they never call a broker or anything outside the
database, so no external call can fall inside a consumer's transaction (rule 3).

Order is per aggregate. Versions are contiguous by construction (M4-00 rule
7), so a consumer applies version n + 1 only after it has processed n; a gap
holds that aggregate back and lets every other aggregate continue. A failing
handler rolls back its effect and its mark; the failure is recorded in its own
transaction, that aggregate is held for the rest of the run, and nothing is
skipped past it. An event with no handler is marked processed as "unhandled",
never silently dropped.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from investment_engine.events.envelope import EventEnvelope
from investment_engine.events.outbox import _COLUMNS, read_envelope
from investment_engine.market.availability import check_utc
from investment_engine.storage.sqlite import port


@dataclass(frozen=True)
class ConsumerReport:
    applied: int
    unhandled: int
    held: int  # events waiting for an earlier version of their aggregate
    failed: int


class Consumer:
    def __init__(self, db, *, name: str, handles: Mapping[str, Callable[[EventEnvelope], None]], clock) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("consumers are PostgreSQL only (docs/tasks/M4-01.md)")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("a consumer needs a name")
        self.name, self._handles, self._clock = name, dict(handles), clock

    def _processed_version(self, aggregate_type: str, aggregate_id: str) -> int:
        return self._db.fetchone(
            "SELECT COALESCE(MAX(aggregate_version), 0) FROM processed_events WHERE consumer = :c "
            "AND aggregate_type = :t AND aggregate_id = :i", {"c": self.name, "t": aggregate_type, "i": aggregate_id})[0]

    def run_once(self, *, limit: int = 100) -> ConsumerReport:
        rows = self._db.fetchall(
            f"SELECT {', '.join('l.' + c.strip() for c in _COLUMNS.split(','))} FROM event_log l "
            "WHERE NOT EXISTS (SELECT 1 FROM processed_events p WHERE p.consumer = :c AND p.event_id = l.event_id) "
            "ORDER BY l.aggregate_type, l.aggregate_id, l.aggregate_version LIMIT :limit",
            {"c": self.name, "limit": limit})
        applied = unhandled = held = failed = 0
        blocked: set[tuple[str, str]] = set()
        for row in rows:
            envelope = read_envelope(row)
            key = (envelope.aggregate_type, envelope.aggregate_id)
            if key in blocked:
                held += 1
                continue
            if envelope.aggregate_version != self._processed_version(*key) + 1:
                blocked.add(key)
                held += 1
                continue
            handler = self._handles.get(envelope.event_type)
            try:
                with self._db.transaction():
                    if self._db.fetchone("SELECT 1 FROM processed_events WHERE consumer = :c AND event_id = :e",
                                         {"c": self.name, "e": envelope.event_id}) is not None:
                        continue  # another instance of this consumer got there first
                    if handler is not None:
                        handler(envelope)
                    self._db.execute(
                        "INSERT INTO processed_events VALUES (:c, :e, :t, :i, :v, :outcome, :at)",
                        {"c": self.name, "e": envelope.event_id, "t": envelope.aggregate_type,
                         "i": envelope.aggregate_id, "v": envelope.aggregate_version,
                         "outcome": "applied" if handler is not None else "unhandled",
                         "at": check_utc(self._clock.now(), "now")})
            except Exception as exc:  # the effect and the mark rolled back together
                blocked.add(key)
                failed += 1
                with self._db.transaction():
                    self._db.execute("INSERT INTO consumer_failures VALUES (:c, :e, :error, :at)",
                                     {"c": self.name, "e": envelope.event_id,
                                      "error": f"{type(exc).__name__}: {exc}"[:2000],
                                      "at": check_utc(self._clock.now(), "now")})
                continue
            if handler is None:
                unhandled += 1
            else:
                applied += 1
        return ConsumerReport(applied, unhandled, held, failed)


__all__ = ["Consumer", "ConsumerReport"]
