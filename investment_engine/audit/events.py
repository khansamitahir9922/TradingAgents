"""Audit events: who did what, recorded with the change (architecture Part F "Audit", Part H; docs/tasks/M3-04.md).

An AuditEvent names its actor (a local operator with a role, or a process),
a dotted action, a target, the before and after values (registered domain
values, encoded by the M2-07 canonical codec), the real command time `at` from
the injected LiveClock and, for research-account commands, the simulated
replay time `business_at` (Codex re-review R2). Its id hashes the canonical
content, so an identical append is one event.

The store appends only inside the caller's managed transaction (the database
port's scope, M3-02 rule 1), so an audited change and its event commit or
roll back together. History is append-only: triggers refuse UPDATE, DELETE,
TRUNCATE and inserting an existing id. Events are PostgreSQL only (schema
0005), like every new M3 store.

`os_user` is attribution for the record, not authentication; roles come from
the operator registry (M3-05) and logins from M8. Events hold only values a
caller passes explicitly; nothing here reads the environment.
"""

import dataclasses
import hashlib
import importlib
import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from investment_engine.audit import registry
from investment_engine.lineage.records import canonical_json, decode, encode, register
from investment_engine.market.availability import check_utc
from investment_engine.storage.sqlite import port

ROLES = ("ADMIN", "TRADER", "VIEWER")
_ACTION = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")
MAX_REASON = 1000


class ActorKind(StrEnum):
    OPERATOR = "OPERATOR"
    PROCESS = "PROCESS"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    actor_id: str  # an operator id, or a process name such as "core-engine" or "admin-cli"
    role: str | None  # ADMIN, TRADER or VIEWER for operators; None for processes
    os_user: str | None  # the local login that ran the command; attribution only

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ActorKind(self.kind))
        if not isinstance(self.actor_id, str) or not self.actor_id.strip():
            raise ValueError("an actor needs an id")
        if self.kind is ActorKind.OPERATOR and self.role not in ROLES:
            raise ValueError(f"an operator's role is one of {ROLES}, not {self.role!r}")
        if self.kind is ActorKind.PROCESS and self.role is not None:
            raise ValueError("a process has no role")


@dataclass(frozen=True)
class AuditEvent:
    actor: Actor
    action: str  # dotted verb, e.g. "intent.approve"
    target_type: str
    target_id: str
    before: object | None
    after: object | None
    at: datetime  # the real command time (UTC, injected LiveClock)
    business_at: datetime | None  # RESEARCH only: the replay time the command acted at; None for PAPER
    reason: str
    correlation_id: str  # groups one command's or one pipeline run's events
    idempotency_key: str
    event_id: str = field(init=False)  # "aud-" + SHA-256 of the canonical content

    def __post_init__(self) -> None:
        if not isinstance(self.actor, Actor):
            raise TypeError("actor must be an Actor")
        check_utc(self.at, "at")
        if self.business_at is not None:
            check_utc(self.business_at, "business_at")
        if not isinstance(self.action, str) or not _ACTION.fullmatch(self.action):
            raise ValueError(f"action must be a dotted lower-case verb, not {self.action!r}")
        for name in ("target_type", "target_id", "correlation_id", "idempotency_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if not isinstance(self.reason, str) or len(self.reason) > MAX_REASON:
            raise ValueError(f"reason must be text of at most {MAX_REASON} characters")
        for name in ("before", "after"):  # only codec-registered values; normalized so round trips compare equal
            object.__setattr__(self, name, decode(encode(getattr(self, name))))
        object.__setattr__(self, "event_id", "aud-" + hashlib.sha256(self.content().encode()).hexdigest())

    def content(self) -> str:
        return canonical_json({f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init})

    @classmethod
    def from_content(cls, content: str) -> "AuditEvent":
        return cls(**dict(decode(json.loads(content))))


for _cls in (ActorKind, Actor, AuditEvent):
    register(_cls)


class AuditConflict(ValueError):
    """A different event already exists under this id."""


_COLUMNS = "event_id, at, business_at, actor_kind, actor_id, action, target_type, target_id, correlation_id, content"


class AuditStore:
    """Append-only audit events in the Operational Database (PostgreSQL, schema 0005)."""

    def __init__(self, db) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("the audit store is PostgreSQL only (docs/tasks/M3-04.md)")
        for module in registry.MODULES:  # so a fresh process can decode every stored event
            importlib.import_module(module)

    def append(self, event: AuditEvent) -> None:
        if not isinstance(event, AuditEvent):
            raise TypeError(f"expected an AuditEvent, not {type(event).__name__}")
        if not self._db.in_transaction:
            raise RuntimeError("audit events are appended inside the audited change's managed transaction")
        content = event.content()
        existing = self._db.fetchone("SELECT content FROM audit_events WHERE event_id = :id", {"id": event.event_id})
        if existing is not None:
            if zlib.decompress(bytes(existing[0])).decode() != content:
                raise AuditConflict(f"{event.event_id} is already recorded with different content")
            return
        self._db.execute(
            f"INSERT INTO audit_events ({_COLUMNS}) VALUES (:id, :at, :business_at, :kind, :actor_id, :action, "
            ":target_type, :target_id, :correlation_id, :content)",
            {"id": event.event_id, "at": event.at, "business_at": event.business_at, "kind": event.actor.kind.value,
             "actor_id": event.actor.actor_id, "action": event.action, "target_type": event.target_type,
             "target_id": event.target_id, "correlation_id": event.correlation_id,
             "content": zlib.compress(content.encode(), 6)})

    def _events(self, where: str, params: dict) -> list[AuditEvent]:
        rows = self._db.fetchall(f"SELECT event_id, content FROM audit_events WHERE {where} ORDER BY at, event_id",
                                 params)
        out = []
        for event_id, blob in rows:
            event = AuditEvent.from_content(zlib.decompress(bytes(blob)).decode())
            if event.event_id != event_id:
                raise ValueError(f"stored content for {event_id} hashes to {event.event_id}")
            out.append(event)
        return out

    def for_target(self, target_type: str, target_id: str) -> list[AuditEvent]:
        return self._events("target_type = :t AND target_id = :i", {"t": target_type, "i": target_id})

    def between(self, start: datetime, end: datetime) -> list[AuditEvent]:
        """Events with start <= at < end."""
        return self._events("at >= :start AND at < :end", {"start": check_utc(start, "start"),
                                                           "end": check_utc(end, "end")})
