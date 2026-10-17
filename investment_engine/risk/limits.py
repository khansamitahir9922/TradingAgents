"""Versioned risk limits, policy rules and drawdown halts per account (architecture Part F; docs/tasks/M3-06.md).

Every decision names the exact versions it used. Publishing creates the next
version ("risk-<n>", "policy-<n>") under the account-control lock, so versions
are consecutive even under concurrency (Codex S4), and records it with one
audit event in the same transaction. Old versions stay readable; nothing is
updated or deleted.

Fail closed: an account without effective limits or rules raises NoLimits,
which the intent pipeline records as a missing prerequisite (M3-12). The
packaged proposed_limits.json holds the owner decisions D1-D9 and D13 and is
applied only when an Admin publishes it explicitly. Files are strict: unknown
keys and floats are refused, so binary rounding never enters a money rule.

Times (Codex re-review R2): a RESEARCH account's versions take an explicit
`effective_at` replay time (it can't move back); a PAPER account's take effect
when published and can't be backdated. Authorization always uses the real
command time.

A drawdown halt (D3) is latched: it stays until an Admin clears it, even if
the account recovers. Clearing records the account's equity at that moment,
when known, as the new drawdown baseline (M3-07 rule 5), so a clear doesn't
re-trigger at once.
"""

import json
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal

from investment_engine.audit.events import Actor, ActorKind, AuditEvent, AuditStore
from investment_engine.lineage.records import canonical_json, decode, register
from investment_engine.market.availability import check_utc
from investment_engine.policy.accounts import AccountKind, AccountRegistry, Role
from investment_engine.policy.rules import PolicyRules, fraction
from investment_engine.storage.sqlite import port

CORE = Actor(ActorKind.PROCESS, "core-engine", None, None)


class NoLimits(LookupError):
    """No risk limits or policy rules are effective for the account at that time."""


@dataclass(frozen=True)
class RiskLimits:
    version: str  # "risk-<n>" per account, assigned on publish
    max_position_fraction: Decimal  # D1: 0.10 of account value
    max_gross_exposure_fraction: Decimal  # D2: 1.00 (no borrowing)
    long_only: bool  # D2: True; v1 refuses False
    drawdown_halt_fraction: Decimal  # D3: 0.15
    max_order_adv_fraction: Decimal  # D4: 0.01
    adv_sessions: int  # D4: 20
    max_new_buys_per_session: int  # D5: 5
    min_price: Decimal  # D6: 5 (USD)
    min_quantity: Decimal  # D9: 1 share; whole shares only

    def __post_init__(self) -> None:
        for name in ("max_position_fraction", "max_gross_exposure_fraction", "drawdown_halt_fraction",
                     "max_order_adv_fraction"):
            fraction(getattr(self, name), name)
        if self.long_only is not True:
            raise ValueError("long_only must be true in v1 (D2: no short selling)")
        for name in ("adv_sessions", "max_new_buys_per_session"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer, not {value!r}")
        for name in ("min_price", "min_quantity"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be positive, not {value}")
        if self.min_quantity != self.min_quantity.to_integral_value() or self.min_quantity < 1:
            raise ValueError("min_quantity must be at least one share, in whole shares")


@dataclass(frozen=True)
class Halt:
    account_id: str
    halted: bool
    at: datetime  # business time: replay time for RESEARCH, live for PAPER
    by: str
    reason: str
    limits_version: str
    baseline_equity: Decimal | None  # a clear's equity at the clear: the new drawdown baseline (D3, S6)

    def __post_init__(self) -> None:
        if self.halted:
            if self.baseline_equity is not None:
                raise ValueError("a halt records no baseline; the clear that ends it does")
        elif not isinstance(self.baseline_equity, Decimal) or not self.baseline_equity.is_finite() \
                or self.baseline_equity < 0:
            raise ValueError("a cleared halt records the account's equity at the clear, a finite non-negative "
                             "Decimal: the high-water mark restarts from it (D3)")


for _cls in (RiskLimits, Halt):
    register(_cls)

_RISK_FIELDS = {f.name: f.type for f in fields(RiskLimits) if f.name != "version"}
_POLICY_FIELDS = {f.name: f.type for f in fields(PolicyRules) if f.name != "version"}


def _no_float(text: str):
    raise ValueError(f"floats are refused in limit files ({text}); write numbers as strings or integers")


def _typed(section: Mapping, spec: Mapping, what: str) -> dict:
    unknown = sorted(set(section) - set(spec))
    if unknown:
        raise ValueError(f"unknown {what} key(s): {', '.join(unknown)}")
    out = {}
    for name, value in section.items():
        kind = spec[name]
        if kind is Decimal or kind == "Decimal":
            if not isinstance(value, str | int) or isinstance(value, bool):
                raise ValueError(f"{name} must be written as a string or integer")
            out[name] = Decimal(str(value))
        elif isinstance(value, list):
            out[name] = tuple(value)
        else:
            out[name] = value
    return out


def load_limits_file(text: str) -> tuple[dict, dict]:
    """The risk and policy fields of a limit file (JSON with "header", "risk" and "policy"); strict."""
    data = json.loads(text, parse_float=_no_float)
    unknown = sorted(set(data) - {"header", "risk", "policy"})
    if unknown:
        raise ValueError(f"unknown top-level key(s): {', '.join(unknown)}")
    return _typed(data.get("risk", {}), _RISK_FIELDS, "risk"), _typed(data.get("policy", {}), _POLICY_FIELDS, "policy")


def _check_fields(values: Mapping, spec: Mapping, what: str) -> None:
    unknown = sorted(set(values) - set(spec))
    if unknown:
        raise ValueError(f"unknown {what} field(s): {', '.join(unknown)}")
    missing = sorted(set(spec) - set(values))
    if missing:
        raise ValueError(f"missing {what} field(s): {', '.join(missing)}")


class LimitStore:
    def __init__(self, db, audit: AuditStore, accounts: AccountRegistry, clock) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("limits are PostgreSQL only (docs/tasks/M3-06.md)")
        if getattr(audit, "_db", None) is not self._db or getattr(accounts, "_db", None) is not self._db:
            raise ValueError("the audit store and account registry must share this store's database port")
        self._audit, self._accounts, self._clock = audit, accounts, clock

    # ---------------------------------------------------------------- versions

    def _times(self, account_id: str, effective_at: datetime | None, now: datetime):
        kind = self._accounts.account(account_id).kind
        if kind is AccountKind.PAPER:
            if effective_at is not None:
                raise ValueError("a PAPER account's limits take effect when published; they can't backdate")
            return now, None
        if effective_at is None:
            raise ValueError("a RESEARCH account's limits need an explicit effective_at (replay time)")
        return check_utc(effective_at, "effective_at"), effective_at

    def _publish(self, table: str, prefix: str, action: str, account_id: str, make, *, by: Actor, reason: str,
                 effective_at: datetime | None):
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            self._accounts.authorize(by, (Role.ADMIN,), now)
            effective, business = self._times(account_id, effective_at, now)
            last = self._db.fetchone(f"SELECT number, effective_at FROM {table} WHERE account_id = :id "
                                     "ORDER BY number DESC LIMIT 1", {"id": account_id})
            if last is not None and effective < last[1]:
                raise ValueError(f"effective_at {effective.isoformat()} is earlier than the latest version's "
                                 f"({last[1].isoformat()}); a timeline can't move back")
            number = 1 if last is None else last[0] + 1
            version = make(f"{prefix}-{number}")
            self._db.execute(f"INSERT INTO {table} VALUES (:id, :number, :effective, :recorded, :by, :reason, "
                             ":content)",
                             {"id": account_id, "number": number, "effective": effective, "recorded": now,
                              "by": by.actor_id, "reason": reason,
                              "content": zlib.compress(canonical_json(version).encode(), 6)})
            previous = None if last is None else self._version(table, account_id, last[0])
            self._audit.append(AuditEvent(by, action, "account", account_id, previous, version, now, business,
                                          reason, f"{action}:{account_id}:{now.isoformat()}",
                                          f"{action}:{account_id}:{number}"))
        return version

    def _version(self, table: str, account_id: str, number: int):
        row = self._db.fetchone(f"SELECT content FROM {table} WHERE account_id = :id AND number = :n",
                                {"id": account_id, "n": number})
        return decode(json.loads(zlib.decompress(bytes(row[0])).decode()))

    def _at(self, table: str, account_id: str, at: datetime):
        row = self._db.fetchone(f"SELECT content FROM {table} WHERE account_id = :id AND effective_at <= :at "
                                "ORDER BY effective_at DESC, number DESC LIMIT 1",
                                {"id": account_id, "at": check_utc(at, "at")})
        if row is None:
            raise NoLimits(f"no {table.replace('_', ' ')} are effective for {account_id} at {at.isoformat()}")
        return decode(json.loads(zlib.decompress(bytes(row[0])).decode()))

    def publish_risk(self, account_id: str, limits_without_version: Mapping, *, by: Actor, reason: str,
                     effective_at: datetime | None = None) -> RiskLimits:
        _check_fields(limits_without_version, _RISK_FIELDS, "risk")
        return self._publish("risk_limit_versions", "risk", "risk.publish", account_id,
                             lambda v: RiskLimits(v, **limits_without_version), by=by, reason=reason,
                             effective_at=effective_at)

    def publish_policy(self, account_id: str, rules_without_version: Mapping, *, by: Actor, reason: str,
                       effective_at: datetime | None = None) -> PolicyRules:
        _check_fields(rules_without_version, _POLICY_FIELDS, "policy")
        return self._publish("policy_rule_versions", "policy", "policy.publish", account_id,
                             lambda v: PolicyRules(v, **rules_without_version), by=by, reason=reason,
                             effective_at=effective_at)

    def risk_at(self, account_id: str, at: datetime) -> RiskLimits:
        return self._at("risk_limit_versions", account_id, at)

    def policy_at(self, account_id: str, at: datetime) -> PolicyRules:
        return self._at("policy_rule_versions", account_id, at)

    def _restricted(self, account_id: str, instrument_id: str, add: bool, *, by: Actor, reason: str,
                    effective_at: datetime | None) -> PolicyRules:
        """Read the current list, change it and publish, all under the account-control lock (Codex M3 review B1):
        a concurrent change commits entirely before this one, which then builds on it, or entirely after."""
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            when = effective_at or check_utc(self._clock.now(), "now")
            current = self.policy_at(account_id, when)
            listed = set(current.restricted)
            listed = listed | {instrument_id} if add else listed - {instrument_id}
            values = {name: getattr(current, name) for name in _POLICY_FIELDS}
            return self.publish_policy(account_id, {**values, "restricted": tuple(listed)}, by=by, reason=reason,
                                       effective_at=effective_at)

    def restrict(self, account_id: str, instrument_id: str, *, by: Actor, reason: str,
                 effective_at: datetime | None = None) -> PolicyRules:
        return self._restricted(account_id, instrument_id, True, by=by, reason=reason, effective_at=effective_at)

    def unrestrict(self, account_id: str, instrument_id: str, *, by: Actor, reason: str,
                   effective_at: datetime | None = None) -> PolicyRules:
        return self._restricted(account_id, instrument_id, False, by=by, reason=reason, effective_at=effective_at)

    # ---------------------------------------------------------------- halts

    def _insert_halt(self, halt: Halt, now: datetime) -> None:
        last = self._db.fetchone("SELECT max(sequence) FROM halts WHERE account_id = :id",
                                 {"id": halt.account_id})[0]
        self._db.execute("INSERT INTO halts VALUES (:id, :seq, :halted, :at, :recorded, :by, :reason, :version, "
                         ":baseline)",
                         {"id": halt.account_id, "seq": (last or 0) + 1, "halted": halt.halted, "at": halt.at,
                          "recorded": now, "by": halt.by, "reason": halt.reason, "version": halt.limits_version,
                          "baseline": halt.baseline_equity})

    def set_halt(self, account_id: str, *, at: datetime, limits_version: str, reason: str) -> Halt:
        """Latch a drawdown halt (requested by the risk check, M3-11); written by the Core Engine."""
        now = check_utc(self._clock.now(), "now")
        kind = self._accounts.account(account_id).kind
        halt = Halt(account_id, True, check_utc(at, "at"), CORE.actor_id, reason, limits_version, None)
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            self._insert_halt(halt, now)
            self._audit.append(AuditEvent(CORE, "risk.halt", "account", account_id, None, halt, now,
                                          at if kind is AccountKind.RESEARCH else None, reason,
                                          f"risk.halt:{account_id}:{at.isoformat()}",
                                          f"risk.halt:{account_id}:{at.isoformat()}"))
        return halt

    def clear_halt(self, account_id: str, *, by: Actor, reason: str, equity_now: Decimal,
                   effective_at: datetime | None = None) -> Halt:
        """Clear a halt (Admin). `equity_now`, the account's equity at the clear, is required: the high-water mark
        restarts from it (D3; Codex M3 review B4). A caller that can't establish it can't clear."""
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            self._accounts.authorize(by, (Role.ADMIN,), now)
            at, business = self._times(account_id, effective_at, now)
            previous = self.halt_at(account_id, at)
            if previous is None or not previous.halted:
                raise ValueError(f"{account_id} is not halted at {at.isoformat()}")
            if not isinstance(equity_now, Decimal) or not equity_now.is_finite():
                raise TypeError("equity_now must be the equity at the clear, a finite Decimal")
            cleared = Halt(account_id, False, at, by.actor_id, reason, previous.limits_version, equity_now)
            self._insert_halt(cleared, now)
            self._audit.append(AuditEvent(by, "risk.clear_halt", "account", account_id, previous, cleared, now,
                                          business, reason, f"risk.clear_halt:{account_id}:{now.isoformat()}",
                                          f"risk.clear_halt:{account_id}:{at.isoformat()}"))
        return cleared

    def last_clear_at(self, account_id: str, at: datetime) -> Halt | None:
        """The latest clear at or before `at`, whatever happened since: the drawdown epoch starts there, and a later
        halt doesn't end it (D3; Codex M3 review B4)."""
        row = self._db.fetchone(
            "SELECT account_id, halted, at, actor_id, reason, limits_version, baseline_equity FROM halts "
            "WHERE account_id = :id AND at <= :at AND NOT halted ORDER BY at DESC, sequence DESC LIMIT 1",
            {"id": account_id, "at": check_utc(at, "at")})
        return None if row is None else Halt(*row)

    def halt_at(self, account_id: str, at: datetime) -> Halt | None:
        row = self._db.fetchone(
            "SELECT account_id, halted, at, actor_id, reason, limits_version, baseline_equity FROM halts "
            "WHERE account_id = :id AND at <= :at ORDER BY at DESC, sequence DESC LIMIT 1",
            {"id": account_id, "at": check_utc(at, "at")})
        return None if row is None else Halt(*row)
