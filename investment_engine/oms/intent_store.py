"""The intent store: intent versions, the G2 state machine and compare-and-set (Laws 10 and 12; docs/tasks/M3-09.md).

One aggregate per intent id covers all its versions: every write moves
`aggregate_version` from the expected value to the next in the same
statement, so a stale writer changes nothing and gets StaleWrite. Creating a
reduced version moves the aggregate too, so a reduction and a decision on the
old version can't both succeed.

An intent version's fields are written once at creation and never change
(Law 12); a database trigger refuses any update of them. Only the state,
decisions, approval fields and lineage id change, and only through
`transition`, which checks the shared G2 table (intent_states) and logs every
move append-only. Each create and transition writes one audit event in the
same managed transaction; its command time comes from the injected clock, and
for RESEARCH accounts the business time is recorded as `business_at`.

Transitions act on the latest version only. Expiry queries are per account
(Codex re-review R3). `admitted_buys` counts distinct intent ids whose BUY
version ever entered AWAITING_APPROVAL or APPROVED, from the log: later
expiry or decline doesn't free a slot (D5). PostgreSQL only (schema 0009).
"""

import json
import zlib
from dataclasses import dataclass
from datetime import date, datetime

from investment_engine.audit.events import Actor, AuditEvent, AuditStore
from investment_engine.lineage.records import canonical_json, decode, register
from investment_engine.market.availability import check_utc
from investment_engine.oms import intent_states
from investment_engine.oms.intents import IntentState, OrderIntent, Side
from investment_engine.policy.accounts import AccountKind, AccountRegistry
from investment_engine.policy.decisions import PolicyDecision
from investment_engine.risk.decisions import NotRun, RiskDecision
from investment_engine.storage.sqlite import port

FIELDS = ("policy_decision", "risk_decision", "approval_deadline", "approved_by", "approved_at",
          "approval_expires_at", "approval_recorded_at", "lineage_id")


class StaleWrite(RuntimeError):
    """The intent changed since it was read; nothing was written."""


@dataclass(frozen=True)
class StoredIntent:
    intent: OrderIntent
    state: IntentState
    aggregate_version: int
    policy_decision: PolicyDecision | NotRun | None  # None: not yet reached
    risk_decision: RiskDecision | NotRun | None
    approval_deadline: datetime | None  # D11: the target session's open
    approved_by: str | None
    approved_at: datetime | None  # business time
    approval_expires_at: datetime | None  # D11: the target session's close
    approval_recorded_at: datetime | None  # real command time of the approval (R2)
    lineage_id: str | None


@dataclass(frozen=True)
class Transition:
    intent_id: str
    version: int
    sequence: int
    from_state: IntentState | None
    to_state: IntentState
    at: datetime  # business time
    recorded_at: datetime  # command time
    actor_id: str
    reason: str


register(StoredIntent)
register(Transition)


def _blob(value) -> bytes | None:
    return None if value is None else zlib.compress(canonical_json(value).encode(), 6)


def _value(blob):
    return None if blob is None else decode(json.loads(zlib.decompress(bytes(blob)).decode()))


_SELECT = ("SELECT v.content, v.state, a.aggregate_version, v.policy_decision, v.risk_decision, v.approval_deadline, "
           "v.approved_by, v.approved_at, v.approval_expires_at, v.approval_recorded_at, v.lineage_id "
           "FROM intent_versions v JOIN intents a ON a.intent_id = v.intent_id")


class IntentStore:
    def __init__(self, db, audit: AuditStore, accounts: AccountRegistry, clock) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("intents are PostgreSQL only (docs/tasks/M3-09.md)")
        if getattr(audit, "_db", None) is not self._db or getattr(accounts, "_db", None) is not self._db:
            raise ValueError("the audit store and account registry must share this store's database port")
        self._audit, self._accounts, self._clock = audit, accounts, clock

    # ---------------------------------------------------------------- reads

    def _row(self, row) -> StoredIntent:
        intent = _value(row[0])
        return StoredIntent(intent, IntentState(row[1]), row[2], _value(row[3]), _value(row[4]), row[5], row[6],
                            row[7], row[8], row[9], row[10])

    def get(self, intent_id: str, version: int | None = None) -> StoredIntent:
        if version is None:
            row = self._db.fetchone(_SELECT + " WHERE v.intent_id = :id AND v.version = a.latest_version",
                                    {"id": intent_id})
        else:
            row = self._db.fetchone(_SELECT + " WHERE v.intent_id = :id AND v.version = :v",
                                    {"id": intent_id, "v": version})
        if row is None:
            raise KeyError(f"unknown intent {intent_id}" + ("" if version is None else f" version {version}"))
        return self._row(row)

    def versions(self, intent_id: str) -> list[StoredIntent]:
        return [self._row(r) for r in self._db.fetchall(_SELECT + " WHERE v.intent_id = :id ORDER BY v.version",
                                                        {"id": intent_id})]

    def history(self, intent_id: str) -> list[Transition]:
        rows = self._db.fetchall("SELECT intent_id, version, sequence, from_state, to_state, at, recorded_at, "
                                 "actor_id, reason FROM intent_transitions WHERE intent_id = :id ORDER BY sequence",
                                 {"id": intent_id})
        return [Transition(r[0], r[1], r[2], None if r[3] is None else IntentState(r[3]), IntentState(r[4]), *r[5:])
                for r in rows]

    def for_account(self, account_id: str) -> list[StoredIntent]:
        return [self._row(r) for r in self._db.fetchall(
            _SELECT + " WHERE a.account_id = :id ORDER BY v.created_at, v.intent_id, v.version", {"id": account_id})]

    def due_for_expiry(self, account_id: str, at: datetime) -> list[StoredIntent]:
        """One account's waiting intents past their deadline and approved ones past their expiry (R3)."""
        at = check_utc(at, "at")
        rows = self._db.fetchall(
            _SELECT + " WHERE a.account_id = :id AND v.version = a.latest_version AND ("
            "(v.state = 'AWAITING_APPROVAL' AND v.approval_deadline <= :at) OR "
            "(v.state = 'APPROVED' AND v.approval_expires_at <= :at)) ORDER BY v.intent_id",
            {"id": account_id, "at": at})
        return [self._row(r) for r in rows]

    def admitted_buys(self, account_id: str, target_session: date, *, excluding: str | None = None) -> int:
        return self._db.fetchone(
            "SELECT COUNT(DISTINCT t.intent_id) FROM intent_transitions t "
            "JOIN intent_versions v ON v.intent_id = t.intent_id AND v.version = t.version "
            "JOIN intents a ON a.intent_id = t.intent_id "
            "WHERE a.account_id = :account AND v.side = 'BUY' AND v.target_session = :session "
            "AND t.to_state IN ('AWAITING_APPROVAL', 'APPROVED') AND t.intent_id <> :excluding",
            {"account": account_id, "session": target_session, "excluding": excluding or ""})[0]

    def was_admitted(self, intent_id: str) -> bool:
        return self._db.fetchone(
            "SELECT 1 FROM intent_transitions t JOIN intent_versions v ON v.intent_id = t.intent_id "
            "AND v.version = t.version WHERE t.intent_id = :id AND v.side = 'BUY' "
            "AND t.to_state IN ('AWAITING_APPROVAL', 'APPROVED') LIMIT 1", {"id": intent_id}) is not None

    # ---------------------------------------------------------------- writes

    def _business(self, account_id: str, at: datetime) -> datetime | None:
        return at if self._accounts.account(account_id).kind is AccountKind.RESEARCH else None

    def _log(self, intent: OrderIntent, from_state, to_state, at, now, by: Actor, reason: str) -> None:
        sequence = self._db.fetchone("SELECT COALESCE(MAX(sequence), 0) + 1 FROM intent_transitions "
                                     "WHERE intent_id = :id", {"id": intent.intent_id})[0]
        self._db.execute("INSERT INTO intent_transitions VALUES (:id, :version, :seq, :from_state, :to_state, :at, "
                         ":recorded, :actor, :reason)",
                         {"id": intent.intent_id, "version": intent.version, "seq": sequence,
                          "from_state": None if from_state is None else IntentState(from_state).value,
                          "to_state": IntentState(to_state).value, "at": at, "recorded": now,
                          "actor": by.actor_id, "reason": reason})

    def _insert_version(self, intent: OrderIntent) -> None:
        self._db.execute(
            "INSERT INTO intent_versions (intent_id, version, side, quantity, order_type, limit_price, time_in_force, "
            "instrument_id, account_id, target_session, created_at, content, state) VALUES (:id, :version, :side, "
            ":quantity, :order_type, :limit_price, :tif, :instrument, :account, :session, :created, :content, "
            "'PROPOSED')",
            {"id": intent.intent_id, "version": intent.version, "side": intent.side.value,
             "quantity": intent.quantity, "order_type": intent.order_type, "limit_price": intent.limit_price,
             "tif": intent.time_in_force, "instrument": intent.instrument_id, "account": intent.account_id,
             "session": intent.target_session, "created": intent.created_at, "content": _blob(intent)})

    def create(self, intent: OrderIntent, *, by: Actor, correlation_id: str) -> StoredIntent:
        """Version 1, in PROPOSED; identical re-creation is a no-op, a different intent under the id raises."""
        if not isinstance(intent, OrderIntent):
            raise TypeError("expected an OrderIntent")
        if intent.version != 1 or intent.supersedes is not None:
            raise ValueError("create makes version 1; later versions come from supersede (a risk reduction)")
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            existing = self._db.fetchone("SELECT content FROM intent_versions WHERE intent_id = :id AND version = 1",
                                         {"id": intent.intent_id})
            if existing is not None:
                if _value(existing[0]) != intent:
                    raise ValueError(f"{intent.intent_id} version 1 already exists with different content")
                return self.get(intent.intent_id, 1)
            self._db.execute("INSERT INTO intents VALUES (:id, :account, :instrument, 1, 1)",
                             {"id": intent.intent_id, "account": intent.account_id,
                              "instrument": intent.instrument_id})
            self._insert_version(intent)
            self._log(intent, None, IntentState.PROPOSED, intent.created_at, now, by, "proposed")
            self._audit.append(AuditEvent(by, "intent.create", "intent", intent.intent_id, None, intent, now,
                                          self._business(intent.account_id, intent.created_at), "proposed",
                                          correlation_id, f"intent.create:{intent.intent_id}:1"))
        return self.get(intent.intent_id, 1)

    def _move(self, intent_id: str, expected: int, latest: int | None = None) -> None:
        """The compare-and-set: one step of the aggregate (and, for a new version, its latest version)."""
        moved = self._db.fetchone(
            "UPDATE intents SET aggregate_version = aggregate_version + 1, "
            "latest_version = COALESCE(:latest, latest_version) WHERE intent_id = :id "
            "AND aggregate_version = :expected RETURNING aggregate_version",
            {"id": intent_id, "expected": expected, "latest": latest})
        if moved is None:
            raise StaleWrite(f"{intent_id} changed since aggregate version {expected}; nothing was written")

    def transition(self, intent_id: str, version: int, to: IntentState, *, expected_aggregate_version: int,
                   at: datetime, by: Actor, reason: str, correlation_id: str = "", **fields) -> StoredIntent:
        to = IntentState(to)
        unknown = sorted(set(fields) - set(FIELDS))
        if unknown:
            raise ValueError(f"transition can't set {', '.join(unknown)}")
        at, now = check_utc(at, "at"), check_utc(self._clock.now(), "now")
        with self._db.transaction():
            current = self.get(intent_id, version)
            latest = self._db.fetchone("SELECT latest_version FROM intents WHERE intent_id = :id",
                                       {"id": intent_id})[0]
            if version != latest:
                raise intent_states.IllegalTransition(f"{intent_id} version {version} is not the latest ({latest})")
            intent_states.check(current.state, to)
            if to is IntentState.SUPERSEDED:
                raise ValueError("SUPERSEDED is written by supersede(), which creates the new version atomically")
            self._move(intent_id, expected_aggregate_version)
            assignments = ", ".join(f"{name} = :{name}" for name in fields)
            values = {name: (_blob(v) if name in ("policy_decision", "risk_decision") else v)
                      for name, v in fields.items()}
            self._db.execute(f"UPDATE intent_versions SET state = :state{', ' + assignments if fields else ''} "
                             "WHERE intent_id = :id AND version = :version",
                             {"state": to.value, "id": intent_id, "version": version, **values})
            self._log(current.intent, current.state, to, at, now, by, reason)
            self._audit.append(AuditEvent(by, f"intent.{to.value.lower()}", "intent", intent_id,
                                          current.state.value, to.value, now,
                                          self._business(current.intent.account_id, at), reason,
                                          correlation_id or f"intent:{intent_id}:{now.isoformat()}",
                                          f"intent.transition:{intent_id}:{version}:{to.value}:{at.isoformat()}"))
        return self.get(intent_id, version)

    def convert(self, intent_id: str, version: int, *, expected_aggregate_version: int, at: datetime, by: Actor,
                reason: str, correlation_id: str = "") -> StoredIntent:
        """APPROVED -> CONVERTED, for `oms.conversion` only, inside the transaction that creates the Order (M4-02)."""
        if not self._db.in_transaction:
            raise RuntimeError("a conversion is written in the same transaction as its Order (M4-02 rule 1)")
        at, now = check_utc(at, "at"), check_utc(self._clock.now(), "now")
        current = self.get(intent_id, version)
        latest = self._db.fetchone("SELECT latest_version FROM intents WHERE intent_id = :id", {"id": intent_id})[0]
        if version != latest:
            raise intent_states.IllegalTransition(f"{intent_id} version {version} is not the latest ({latest})")
        intent_states.check(current.state, IntentState.CONVERTED, converting=True)
        self._move(intent_id, expected_aggregate_version)
        self._db.execute("UPDATE intent_versions SET state = 'CONVERTED' WHERE intent_id = :id AND version = :version",
                         {"id": intent_id, "version": version})
        self._log(current.intent, current.state, IntentState.CONVERTED, at, now, by, reason)
        self._audit.append(AuditEvent(by, "intent.converted", "intent", intent_id, current.state.value,
                                      IntentState.CONVERTED.value, now,
                                      self._business(current.intent.account_id, at), reason,
                                      correlation_id or f"intent:{intent_id}:{now.isoformat()}",
                                      f"intent.convert:{intent_id}:{version}"))
        return self.get(intent_id, version)

    def supersede(self, intent_id: str, version: int, new: OrderIntent, *, expected_aggregate_version: int,
                  at: datetime, by: Actor, reason: str, correlation_id: str = "", **fields) -> StoredIntent:
        """Mark `version` SUPERSEDED and create `new` (version + 1, PROPOSED) in one compare-and-set write."""
        if new.intent_id != intent_id or new.version != version + 1 or new.supersedes != version:
            raise ValueError("the new version must be the next version of the same intent and supersede the old one")
        at, now = check_utc(at, "at"), check_utc(self._clock.now(), "now")
        with self._db.transaction():
            current = self.get(intent_id, version)
            changed = [n for n in OrderIntent.MATERIAL if n != "quantity"
                       and getattr(current.intent, n) != getattr(new, n)]
            if changed:
                raise ValueError(f"a reduction changes only the quantity, not {', '.join(changed)}")
            intent_states.check(current.state, IntentState.SUPERSEDED)
            self._move(intent_id, expected_aggregate_version, latest=new.version)
            assignments = "".join(f", {name} = :{name}" for name in fields)
            values = {name: (_blob(v) if name in ("policy_decision", "risk_decision") else v)
                      for name, v in fields.items()}
            self._db.execute(f"UPDATE intent_versions SET state = 'SUPERSEDED'{assignments} WHERE intent_id = :id "
                             "AND version = :version", {"id": intent_id, "version": version, **values})
            self._insert_version(new)
            self._log(current.intent, current.state, IntentState.SUPERSEDED, at, now, by, reason)
            self._log(new, None, IntentState.PROPOSED, at, now, by, f"reduced version of v{version}")
            self._audit.append(AuditEvent(by, "intent.superseded", "intent", intent_id, current.intent, new, now,
                                          self._business(new.account_id, at), reason,
                                          correlation_id or f"intent:{intent_id}:{now.isoformat()}",
                                          f"intent.supersede:{intent_id}:{version}"))
        return self.get(intent_id, new.version)



__all__ = ["IntentStore", "StaleWrite", "StoredIntent", "Transition", "Side"]
