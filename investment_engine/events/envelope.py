"""The event envelope and the outbox-writer port (architecture Part H, Law 11; ADR-005; docs/tasks/M4-00.md).

An envelope announces one write: its `aggregate_version` is the version that
write created, so each aggregate's events are numbered 1, 2, 3, ... with no
gap and no reuse (M4-00 rule 7). The `event_id` is derived from the
aggregate, its version and the event type, so republishing the same row after
a crash carries the same id (ADR-005 section 6). The payload is canonical JSON.

`OutboxWriter` is the port the stores write through; M4-01's Outbox
implements it, and tests use a recording double. Writing an envelope outside
a transaction is refused, because the event and the state change it announces
must commit together (Law 11).
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from investment_engine.lineage.records import register
from investment_engine.market.availability import check_utc

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EventEnvelope:
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    occurred_at: datetime  # business time of the change
    recorded_at: datetime  # when it was written (injected clock)
    correlation_id: str
    causation_id: str | None
    payload: str  # canonical JSON
    event_id: str = field(init=False)  # "evt-" + SHA-256 of (aggregate_type, aggregate_id, version, event_type)

    def __post_init__(self) -> None:
        for name in ("event_type", "aggregate_type", "aggregate_id", "correlation_id", "payload"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"an event needs {name}")
        if not isinstance(self.aggregate_version, int) or self.aggregate_version < 1:
            raise ValueError("aggregate_version starts at 1")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version is {SCHEMA_VERSION} in M4")
        check_utc(self.occurred_at, "occurred_at")
        check_utc(self.recorded_at, "recorded_at")
        key = f"{self.aggregate_type}|{self.aggregate_id}|{self.aggregate_version}|{self.event_type}"
        object.__setattr__(self, "event_id", "evt-" + hashlib.sha256(key.encode()).hexdigest())


register(EventEnvelope)


class OutboxWriter(Protocol):
    def add(self, envelope: EventEnvelope) -> None:
        """Record the envelope in the caller's open transaction; raise if none is open."""


__all__ = ["SCHEMA_VERSION", "EventEnvelope", "OutboxWriter"]
