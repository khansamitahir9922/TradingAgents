"""A test-only OutboxWriter that records envelopes, refusing any written outside a transaction (M4-00 rule 9)."""


class RecordingOutbox:
    def __init__(self, db) -> None:
        self._db = db
        self.events = []

    def add(self, envelope) -> None:
        if not self._db.in_transaction:
            raise RuntimeError("an outbox row is written only inside the state change's transaction (Law 11)")
        self.events.append(envelope)

    def of(self, aggregate_id: str) -> list[tuple[int, str]]:
        return [(e.aggregate_version, e.event_type) for e in self.events if e.aggregate_id == aggregate_id]
