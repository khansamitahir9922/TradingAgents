"""PortfolioSnapshot: an exact, point-in-time view of an account (architecture Part F Portfolio; docs/tasks/M3-07.md).

In M3 the only source is the declared starting state (D14: $100,000 cash and
no positions by default), labelled DECLARED: there are no fills before M4 and
no ledger before M5, which then replaces it. Declaring a start is Admin-only,
audited, and allowed once per account; a RESEARCH start takes an explicit
replay time and a PAPER start can't be backdated (M3-05 rule 5). The state's
identity leaves out provenance (when it was recorded and by whom).

Held positions are valued at the raw close of the bar of the latest completed
regular session at or before as_of, read through the Knowledge port (delivery
aware, M2 B2). A missing or not-yet-known bar for that session makes the
snapshot Unavailable; an older bar is never substituted (Codex re-review S2).
If verified coverage shows a split or dividend since the declared start for a
held instrument, or coverage is missing, the snapshot is Unavailable too:
quantities can't be carried across an action until the ledger exists.

The drawdown baseline (D3, S6): `baseline_at` is the declared start or, when
the account's latest halt event is a clear, that clear's time. `peak_equity`
is the highest equity among the account's stored snapshots in
[baseline_at, as_of] and this one, with a clear's recorded equity (if any) as
a floor. Decimal throughout (Law 16).
"""

import dataclasses
import hashlib
import json
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Context, Decimal
from enum import StrEnum

from investment_engine.audit.events import Actor, AuditEvent, AuditStore
from investment_engine.lineage.records import canonical_json, decode, register
from investment_engine.market.availability import check_utc
from investment_engine.market.corporate_actions import ActionType
from investment_engine.policy.accounts import AccountKind, AccountRegistry, Role
from investment_engine.portfolio.reference import Knowledge, Unavailable
from investment_engine.quant.adjusted import BarRef
from investment_engine.risk.limits import Halt
from investment_engine.storage.sqlite import port

DEFAULT_CASH = Decimal("100000")  # D14
_COVERED = (ActionType.SPLIT, ActionType.DIVIDEND)


def _money(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


class SnapshotSource(StrEnum):
    DECLARED_STARTING_STATE = "DECLARED_STARTING_STATE"  # M3: no ledger yet
    LEDGER = "LEDGER"  # reserved for M5; refused in M3


@dataclass(frozen=True)
class StartingState:
    account_id: str
    effective_at: datetime
    recorded_at: datetime  # provenance
    cash: Decimal
    currency: str
    positions: tuple[tuple[str, Decimal], ...]  # sorted (instrument_id, whole shares)
    declared_by: str  # provenance
    reason: str

    def __post_init__(self) -> None:
        check_utc(self.effective_at, "effective_at")
        check_utc(self.recorded_at, "recorded_at")
        if _money(self.cash, "cash") < 0:
            raise ValueError("starting cash can't be negative")
        if self.currency != "USD":
            raise ValueError("v1 starting states are in USD")
        positions = []
        for instrument_id, quantity in self.positions:
            _money(quantity, "quantity")
            if quantity <= 0 or quantity != quantity.to_integral_value():
                raise ValueError(f"declared quantities are positive whole shares, not {quantity}")
            positions.append((instrument_id, quantity))
        ids = [i for i, _ in positions]
        if len(set(ids)) != len(ids):
            raise ValueError("each instrument is declared once")
        object.__setattr__(self, "positions", tuple(sorted(positions)))

    @property
    def state_id(self) -> str:
        """The deterministic identity, without provenance (recorded_at, declared_by)."""
        content = {"account_id": self.account_id, "effective_at": self.effective_at, "cash": self.cash,
                   "currency": self.currency, "positions": self.positions, "reason": self.reason}
        return "sst-" + hashlib.sha256(canonical_json(content).encode()).hexdigest()


@dataclass(frozen=True)
class PositionValue:
    instrument_id: str
    quantity: Decimal
    price: Decimal  # raw close of the expected session's bar
    price_ref: BarRef
    value: Decimal


@dataclass(frozen=True)
class PortfolioSnapshot:
    account_id: str
    as_of: datetime
    source: SnapshotSource
    currency: str
    cash: Decimal
    positions: tuple[PositionValue, ...]  # held instruments only
    equity: Decimal  # cash + position values
    baseline_at: datetime  # the start, or the latest halt clear
    peak_equity: Decimal  # highest equity in [baseline_at, as_of], this one included
    starting_state_ref: str
    snapshot_id: str = field(init=False)  # "psn-" + SHA-256 of the canonical content

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", SnapshotSource(self.source))
        if self.source is SnapshotSource.LEDGER:
            raise ValueError("ledger-derived snapshots arrive in M5")
        check_utc(self.as_of, "as_of")
        object.__setattr__(self, "snapshot_id", "psn-" + hashlib.sha256(self.content().encode()).hexdigest())

    def held(self, instrument_id: str) -> Decimal:
        """Shares held; zero when not held. Absence means none held, never a missing price."""
        return next((p.quantity for p in self.positions if p.instrument_id == instrument_id), Decimal(0))

    def content(self) -> str:
        return canonical_json({f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init})


for _cls in (SnapshotSource, StartingState, PositionValue, PortfolioSnapshot):
    register(_cls)


def _expected_session(calendar, at: datetime) -> date:
    """The latest regular session that has completed at or before `at`."""
    from zoneinfo import ZoneInfo

    d = at.astimezone(ZoneInfo(calendar.timezone)).date()
    if calendar.is_session(d) and calendar.session(d).close <= at:
        return d
    return calendar.previous_session(d).date


def _covers(coverage, source: str, instrument_id: str, first: date, last: date) -> bool:
    return (coverage is not None and coverage.established and coverage.source == source
            and coverage.instrument_id == instrument_id and set(_COVERED) <= set(coverage.types)
            and coverage.first <= first and last <= coverage.last)


def build_snapshot(account_id: str, *, at: datetime, starting: StartingState, knowledge: Knowledge, calendar,
                   coverage, last_clear: Halt | None, history: Sequence[PortfolioSnapshot],
                   source: str) -> PortfolioSnapshot | Unavailable:
    """The declared snapshot at `at`. Its peak is the highest equity since the drawdown epoch: the latest clear
    (`last_clear`, with its recorded equity as a floor) or else the declared start (D3)."""
    at = check_utc(at, "at")
    if starting.account_id != account_id:
        raise ValueError("the starting state is another account's")
    if at < starting.effective_at:
        return Unavailable(f"{account_id}'s declared start ({starting.effective_at.isoformat()}) is after "
                           f"{at.isoformat()}")
    ctx = Context(prec=34)
    positions = []
    if starting.positions:
        from zoneinfo import ZoneInfo

        session = _expected_session(calendar, at)
        zone = ZoneInfo(calendar.timezone)
        first, last = starting.effective_at.astimezone(zone).date(), at.astimezone(zone).date()
        for instrument_id, quantity in starting.positions:
            if not _covers(coverage, source, instrument_id, first, last):
                return Unavailable(f"no established {source} action coverage for {instrument_id} from {first} to "
                                   f"{last}; quantities can't be carried without it")
            actions = [a for a in knowledge.actions_between(source, instrument_id, first, last, at=at)
                       if a.action_type in _COVERED and a.ex_date > first]
            if actions:
                return Unavailable(f"{actions[0].action_type} on {actions[0].ex_date} for {instrument_id} since the "
                                   "declared start; ledger needed (M5)")
            bar = knowledge.latest_closed(source, instrument_id, session, at=at, calendar=calendar)
            if bar is None:
                return Unavailable(f"bar for {session} ({source} {instrument_id} D1) not known at {at.isoformat()}")
            ref = BarRef(bar.source, bar.instrument_id, bar.timeframe, bar.start_time, bar.revision, bar.import_id,
                         bar.available_from, bar.availability_basis)
            positions.append(PositionValue(instrument_id, quantity, bar.close, ref, ctx.multiply(quantity, bar.close)))
    equity = starting.cash
    for p in positions:
        equity = ctx.add(equity, p.value)
    baseline_at, floor = starting.effective_at, None
    if last_clear is not None:
        if last_clear.halted or last_clear.account_id != account_id:
            raise ValueError("last_clear must be this account's clear, not a halt")
        if last_clear.at >= starting.effective_at:
            baseline_at, floor = last_clear.at, last_clear.baseline_equity
    candidates = [equity] + [h.equity for h in history
                             if h.account_id == account_id and baseline_at <= h.as_of <= at]
    if floor is not None:
        candidates.append(floor)
    return PortfolioSnapshot(account_id, at, SnapshotSource.DECLARED_STARTING_STATE, starting.currency,
                             starting.cash, tuple(positions), equity, baseline_at, max(candidates), starting.state_id)


class PortfolioSnapshotStore:
    """Starting states and snapshots: append-only, PostgreSQL only (schema 0008)."""

    def __init__(self, db, audit: AuditStore, accounts: AccountRegistry, clock) -> None:
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("portfolio snapshots are PostgreSQL only (docs/tasks/M3-07.md)")
        if getattr(audit, "_db", None) is not self._db or getattr(accounts, "_db", None) is not self._db:
            raise ValueError("the audit store and account registry must share this store's database port")
        self._audit, self._accounts, self._clock = audit, accounts, clock

    def declare_start(self, account_id: str, *, by: Actor, reason: str, cash: Decimal = DEFAULT_CASH,
                      positions: Sequence[tuple[str, Decimal]] = (),
                      effective_at: datetime | None = None) -> StartingState:
        now = check_utc(self._clock.now(), "now")
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            self._accounts.authorize(by, (Role.ADMIN,), now)
            kind = self._accounts.account(account_id).kind
            if kind is AccountKind.PAPER:
                if effective_at is not None:
                    raise ValueError("a PAPER account's start takes effect when declared; it can't backdate")
                effective, business = now, None
            else:
                if effective_at is None:
                    raise ValueError("a RESEARCH account's start needs an explicit effective_at (replay time)")
                effective, business = check_utc(effective_at, "effective_at"), effective_at
            if self._db.fetchone("SELECT 1 FROM starting_states WHERE account_id = :id", {"id": account_id}):
                raise ValueError(f"{account_id} already has a declared start; M3 allows it once")
            declared = StartingState(account_id, effective, now, cash, "USD", tuple(positions), by.actor_id, reason)
            self._db.execute("INSERT INTO starting_states VALUES (:id, :state_id, :effective, :recorded, :by, "
                             ":reason, :content)",
                             {"id": account_id, "state_id": declared.state_id, "effective": effective,
                              "recorded": now, "by": by.actor_id, "reason": reason,
                              "content": zlib.compress(canonical_json(declared).encode(), 6)})
            self._audit.append(AuditEvent(by, "portfolio.declare_start", "account", account_id, None, declared, now,
                                          business, reason, f"portfolio.declare_start:{account_id}",
                                          f"portfolio.declare_start:{account_id}"))
        return declared

    def starting_state(self, account_id: str) -> StartingState:
        row = self._db.fetchone("SELECT content FROM starting_states WHERE account_id = :id", {"id": account_id})
        if row is None:
            raise KeyError(f"{account_id} has no declared starting state")
        return decode(json.loads(zlib.decompress(bytes(row[0])).decode()))

    def append(self, snapshot: PortfolioSnapshot) -> None:
        if not isinstance(snapshot, PortfolioSnapshot):
            raise TypeError(f"expected a PortfolioSnapshot, not {type(snapshot).__name__}")
        content = canonical_json(snapshot)  # the type-tagged record; its id hashes snapshot.content()
        with self._db.transaction():
            existing = self._db.fetchone("SELECT content FROM portfolio_snapshots WHERE snapshot_id = :id",
                                         {"id": snapshot.snapshot_id})
            if existing is not None:
                if zlib.decompress(bytes(existing[0])).decode() != content:
                    raise ValueError(f"{snapshot.snapshot_id} is already stored with different content")
                return
            self._db.execute("INSERT INTO portfolio_snapshots VALUES (:id, :account, :as_of, :equity, :content)",
                             {"id": snapshot.snapshot_id, "account": snapshot.account_id, "as_of": snapshot.as_of,
                              "equity": snapshot.equity, "content": zlib.compress(content.encode(), 6)})

    @staticmethod
    def _load(blob) -> PortfolioSnapshot:
        return decode(json.loads(zlib.decompress(bytes(blob)).decode()))

    def get(self, snapshot_id: str) -> PortfolioSnapshot:
        row = self._db.fetchone("SELECT content FROM portfolio_snapshots WHERE snapshot_id = :id",
                                {"id": snapshot_id})
        if row is None:
            raise KeyError(snapshot_id)
        snapshot = self._load(row[0])
        if snapshot.snapshot_id != snapshot_id:
            raise ValueError(f"stored content for {snapshot_id} hashes to {snapshot.snapshot_id}")
        return snapshot

    def latest(self, account_id: str, at: datetime) -> PortfolioSnapshot | None:
        row = self._db.fetchone("SELECT content FROM portfolio_snapshots WHERE account_id = :id AND as_of <= :at "
                                "ORDER BY as_of DESC, snapshot_id DESC LIMIT 1",
                                {"id": account_id, "at": check_utc(at, "at")})
        return None if row is None else self._load(row[0])

    def peak(self, account_id: str, *, since: datetime, at: datetime) -> PortfolioSnapshot | None:
        """The stored snapshot with the highest equity in [since, at]: all `build_snapshot` needs from history."""
        row = self._db.fetchone("SELECT content FROM portfolio_snapshots WHERE account_id = :id AND as_of >= :since "
                                "AND as_of <= :at ORDER BY equity DESC, as_of, snapshot_id LIMIT 1",
                                {"id": account_id, "since": check_utc(since, "since"), "at": check_utc(at, "at")})
        return None if row is None else self._load(row[0])

    def history(self, account_id: str, *, since: datetime, at: datetime) -> list[PortfolioSnapshot]:
        rows = self._db.fetchall("SELECT content FROM portfolio_snapshots WHERE account_id = :id AND as_of >= :since "
                                 "AND as_of <= :at ORDER BY as_of, snapshot_id",
                                 {"id": account_id, "since": check_utc(since, "since"), "at": check_utc(at, "at")})
        return [self._load(r[0]) for r in rows]
