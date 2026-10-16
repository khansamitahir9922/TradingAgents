"""Accounts, their autonomy levels, and the local operators who act on them (architecture B3; docs/tasks/M3-05.md).

Every account starts advisory (Level 0). Levels 1 and 2 are set by an Admin;
Levels 3 and 4 are disabled in v1. An account is RESEARCH (replay only; it can
never trade) or PAPER (D15). Operators are local named identities with a role
(D17): attribution on a trusted local CLI, not authentication, which arrives
with logins in M8.

Two times, never merged (Codex re-review R2):
- authorization uses the real command time from the injected LiveClock: the
  named operator must be active with the needed role now, whatever replay time
  a command acts at;
- a RESEARCH account's settings take an explicit `effective_at` replay time,
  stored beside the live `recorded_at`; a PAPER account's settings take effect
  when recorded and can't be backdated.

Identities hash deterministic content only: an account's id, kind, currency
and effective time; a setting's account, level, effective time, sequence and
reason. Provenance (`recorded_at`, who ran it, the OS user) is stored beside
them and in the audit event, so two setups with the same replay inputs give
the same ids (Codex re-review S2).

Every change takes the account-control advisory lock, reads the next sequence
under it, writes an append-only row and one audit event in the same managed
transaction (S4). Bootstrapping the first Admin takes a global lock and checks
again inside it, so concurrent bootstraps make exactly one. Nothing is
deleted, and ids are never reused.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from investment_engine.audit.events import Actor, ActorKind, AuditEvent, AuditStore
from investment_engine.lineage.records import canonical_json, register
from investment_engine.market.availability import check_utc
from investment_engine.storage.database import IntegrityViolation
from investment_engine.storage.sqlite import port

LEVEL_NAMES = {0: "Advisory", 1: "Approved paper", 2: "Automatic paper"}


class AccountKind(StrEnum):
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"


class Role(StrEnum):
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"


class NotAuthorized(PermissionError):
    """The named operator may not do this now; nothing was changed."""


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class Account:
    account_id: str
    kind: AccountKind
    currency: str
    effective_at: datetime  # when it exists in its own timeline (replay time for RESEARCH)
    recorded_at: datetime  # provenance: when the command actually ran

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", AccountKind(self.kind))
        check_utc(self.effective_at, "effective_at")
        check_utc(self.recorded_at, "recorded_at")
        if self.currency != "USD":
            raise ValueError("v1 accounts are in USD")

    @property
    def identity(self) -> str:
        return "acc-" + _sha({"account_id": self.account_id, "kind": self.kind, "currency": self.currency,
                              "effective_at": self.effective_at})


@dataclass(frozen=True)
class AutonomySetting:
    account_id: str
    level: int  # 0, 1 or 2
    effective_at: datetime
    recorded_at: datetime  # provenance
    sequence: int  # strictly increasing per account; orders equal effective times
    set_by: str  # provenance
    reason: str
    setting_id: str = field(init=False)  # "aut-" + SHA-256 of the deterministic content

    def __post_init__(self) -> None:
        check_utc(self.effective_at, "effective_at")
        check_utc(self.recorded_at, "recorded_at")
        if self.level not in LEVEL_NAMES:
            raise ValueError(f"autonomy level must be 0, 1 or 2, not {self.level}")
        object.__setattr__(self, "setting_id", "aut-" + _sha({
            "account_id": self.account_id, "level": self.level, "effective_at": self.effective_at,
            "sequence": self.sequence, "reason": self.reason}))

    @property
    def name(self) -> str:
        return LEVEL_NAMES[self.level]


@dataclass(frozen=True)
class Operator:
    operator_id: str
    role: Role
    active: bool
    changed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", Role(self.role))
        check_utc(self.changed_at, "changed_at")


for _cls in (AccountKind, Role, Account, AutonomySetting, Operator):
    register(_cls)


def _level(level: int) -> int:
    if level in (3, 4):
        raise ValueError(f"Level {level} is disabled in v1 (architecture B3)")
    if isinstance(level, bool) or level not in LEVEL_NAMES:
        raise ValueError(f"autonomy level must be 0, 1 or 2, not {level}")
    return level


class AccountRegistry:
    def __init__(self, db, audit: AuditStore, clock) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("accounts are PostgreSQL only (docs/tasks/M3-05.md)")
        if getattr(audit, "_db", None) is not self._db:
            raise ValueError("the audit store must share this registry's database port (one managed transaction)")
        self._audit = audit
        self._clock = clock

    # ---------------------------------------------------------------- reads

    def account(self, account_id: str) -> Account:
        row = self._db.fetchone("SELECT account_id, kind, currency, effective_at, recorded_at FROM accounts "
                                "WHERE account_id = :id", {"id": account_id})
        if row is None:
            raise KeyError(f"unknown account {account_id!r}")
        return Account(*row)

    def accounts(self) -> list[Account]:
        return [Account(*r) for r in self._db.fetchall(
            "SELECT account_id, kind, currency, effective_at, recorded_at FROM accounts ORDER BY account_id")]

    def autonomy_at(self, account_id: str, at: datetime) -> AutonomySetting:
        row = self._db.fetchone(
            "SELECT account_id, level, effective_at, recorded_at, sequence, set_by, reason FROM autonomy_settings "
            "WHERE account_id = :id AND effective_at <= :at ORDER BY effective_at DESC, sequence DESC LIMIT 1",
            {"id": account_id, "at": check_utc(at, "at")})
        if row is None:
            raise LookupError(f"no autonomy setting of {account_id} is effective at {at.isoformat()}")
        return AutonomySetting(*row)

    def latest_autonomy(self, account_id: str) -> AutonomySetting:
        row = self._db.fetchone(
            "SELECT account_id, level, effective_at, recorded_at, sequence, set_by, reason FROM autonomy_settings "
            "WHERE account_id = :id ORDER BY sequence DESC LIMIT 1", {"id": account_id})
        if row is None:
            raise LookupError(f"{account_id} has no autonomy setting")
        return AutonomySetting(*row)

    def operator(self, operator_id: str, at: datetime) -> Operator:
        row = self._db.fetchone(
            "SELECT operator_id, role, active, changed_at FROM operators WHERE operator_id = :id "
            "AND changed_at <= :at ORDER BY sequence DESC LIMIT 1", {"id": operator_id, "at": check_utc(at, "at")})
        if row is None:
            raise KeyError(f"unknown operator {operator_id!r} at {at.isoformat()}")
        return Operator(*row)

    def operators(self) -> list[Operator]:
        return [Operator(*r) for r in self._db.fetchall(
            "SELECT DISTINCT ON (operator_id) operator_id, role, active, changed_at FROM operators "
            "ORDER BY operator_id, sequence DESC")]

    # ---------------------------------------------------------------- authorization

    def authorize(self, by: Actor, roles: tuple[Role, ...], now: datetime) -> Operator:
        """The named operator, active now with one of `roles` (registry role, never the actor's claim)."""
        if not isinstance(by, Actor) or by.kind is not ActorKind.OPERATOR:
            raise NotAuthorized("only a named operator may do this")
        try:
            operator = self.operator(by.actor_id, now)
        except KeyError:
            raise NotAuthorized(f"{by.actor_id} is not a registered operator") from None
        if not operator.active:
            raise NotAuthorized(f"{by.actor_id} is not an active operator")
        if by.role != operator.role.value:
            raise NotAuthorized(f"{by.actor_id} is registered as {operator.role}, not {by.role}")
        if operator.role not in roles:
            raise NotAuthorized(f"{by.actor_id} ({operator.role}) may not do this; needs {', '.join(roles)}")
        return operator

    def _times(self, kind: AccountKind, effective_at: datetime | None, now: datetime) -> tuple[datetime, datetime | None]:
        """(effective time, audit business time) for a change to an account of `kind`."""
        if kind is AccountKind.PAPER:
            if effective_at is not None:
                raise ValueError("a PAPER account's settings take effect when recorded; they can't backdate")
            return now, None
        if effective_at is None:
            raise ValueError("a RESEARCH account's change needs an explicit effective_at (replay time)")
        return check_utc(effective_at, "effective_at"), effective_at

    def _event(self, by: Actor, action: str, target_type: str, target_id: str, before, after, now, business_at,
               reason: str, key: str) -> None:
        self._audit.append(AuditEvent(by, action, target_type, target_id, before, after, now, business_at, reason,
                                      correlation_id=f"{action}:{target_id}:{now.isoformat()}", idempotency_key=key))

    # ---------------------------------------------------------------- accounts

    def create_account(self, account_id: str, kind: AccountKind, currency: str, *, by: Actor, reason: str,
                       effective_at: datetime | None = None) -> Account:
        kind = AccountKind(kind)
        now = check_utc(self._clock.now(), "now")
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("an account needs an id")
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            self.authorize(by, (Role.ADMIN,), now)
            effective, business = self._times(kind, effective_at, now)
            account = Account(account_id, kind, currency, effective, now)
            try:
                self._db.execute("INSERT INTO accounts VALUES (:id, :kind, :currency, :effective, :recorded)",
                                 {"id": account_id, "kind": kind.value, "currency": currency,
                                  "effective": effective, "recorded": now})
            except IntegrityViolation as exc:
                if exc.kind == "unique":
                    raise ValueError(f"account {account_id} already exists; ids are never reused") from None
                raise
            setting = self._insert_setting(account_id, 0, effective, now, 1, by.actor_id, "default: advisory")
            # One change, one event: the account together with its default Level 0 setting.
            self._event(by, "account.create", "account", account_id, None, (account, setting), now, business, reason,
                        f"account.create:{account_id}")
        return account

    def _insert_setting(self, account_id, level, effective, now, sequence, set_by, reason) -> AutonomySetting:
        setting = AutonomySetting(account_id, level, effective, now, sequence, set_by, reason)
        self._db.execute("INSERT INTO autonomy_settings VALUES (:id, :sequence, :level, :effective, :recorded, "
                         ":set_by, :reason, :setting_id)",
                         {"id": account_id, "sequence": sequence, "level": level, "effective": effective,
                          "recorded": now, "set_by": set_by, "reason": reason, "setting_id": setting.setting_id})
        return setting

    def set_autonomy(self, account_id: str, level: int, *, by: Actor, reason: str,
                     effective_at: datetime | None = None) -> AutonomySetting:
        level = _level(level)
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            self.authorize(by, (Role.ADMIN,), now)
            account = self.account(account_id)
            effective, business = self._times(account.kind, effective_at, now)
            previous = self.latest_autonomy(account_id)
            if effective < previous.effective_at:
                raise ValueError(f"effective_at {effective.isoformat()} is earlier than the latest setting "
                                 f"({previous.effective_at.isoformat()}); a timeline can't move back")
            setting = self._insert_setting(account_id, level, effective, now, previous.sequence + 1, by.actor_id,
                                           reason)
            self._event(by, "account.set_autonomy", "account", account_id, previous, setting, now, business, reason,
                        f"account.set_autonomy:{setting.setting_id}")
        return setting

    # ---------------------------------------------------------------- operators

    def _insert_operator(self, operator_id, sequence, role, active, now, changed_by, reason) -> Operator:
        self._db.execute("INSERT INTO operators VALUES (:id, :sequence, :role, :active, :changed_at, :by, :reason)",
                         {"id": operator_id, "sequence": sequence, "role": Role(role).value, "active": active,
                          "changed_at": now, "by": changed_by, "reason": reason})
        return Operator(operator_id, role, active, now)

    def bootstrap_admin(self, operator_id: str, *, os_user: str | None) -> Operator:
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            self._db.lock("operators-bootstrap")
            if self._db.fetchone("SELECT 1 FROM operators LIMIT 1") is not None:
                raise ValueError("an operator already exists; bootstrap works only once")
            operator = self._insert_operator(operator_id, 1, Role.ADMIN, True, now, "admin-cli", "bootstrap")
            self._event(Actor(ActorKind.PROCESS, "admin-cli", None, os_user), "operator.bootstrap", "operator",
                        operator_id, None, operator, now, None, "the first Admin", f"operator.bootstrap:{operator_id}")
        return operator

    def add_operator(self, operator_id: str, role: Role, *, by: Actor, reason: str) -> Operator:
        now = check_utc(self._clock.now(), "now")
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise ValueError("an operator needs an id")
        with self._db.transaction():
            self._db.lock("operators-bootstrap", f"operator|{operator_id}")
            self.authorize(by, (Role.ADMIN,), now)
            if self._db.fetchone("SELECT 1 FROM operators WHERE operator_id = :id", {"id": operator_id}):
                raise ValueError(f"operator {operator_id} already exists; ids are never reused")
            operator = self._insert_operator(operator_id, 1, role, True, now, by.actor_id, reason)
            self._event(by, "operator.add", "operator", operator_id, None, operator, now, None, reason,
                        f"operator.add:{operator_id}")
        return operator

    def deactivate_operator(self, operator_id: str, *, by: Actor, reason: str) -> Operator:
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            self._db.lock(f"operator|{operator_id}")
            self.authorize(by, (Role.ADMIN,), now)
            previous = self.operator(operator_id, now)
            sequence = self._db.fetchone("SELECT max(sequence) FROM operators WHERE operator_id = :id",
                                         {"id": operator_id})[0]
            operator = self._insert_operator(operator_id, sequence + 1, previous.role, False, now, by.actor_id,
                                             reason)
            self._event(by, "operator.deactivate", "operator", operator_id, previous, operator, now, None, reason,
                        f"operator.deactivate:{operator_id}:{sequence + 1}")
        return operator
