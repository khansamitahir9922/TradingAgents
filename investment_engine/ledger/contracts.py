"""Immutable accounting contracts. Currency and quantity are independent books.

IDs contain business/source content, never a live operator command timestamp.
Exact balance checks use rational arithmetic, independent of the caller's Decimal context.
"""
import hashlib
from collections import defaultdict
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Protocol

from investment_engine.lineage.records import canonical_json, decode, encode, register
from investment_engine.market.availability import (
    check_instrument_id,
    check_name,
    check_revision,
    check_utc,
)
from investment_engine.market.corporate_actions import AmountBasis, CorporateAction
from investment_engine.money import Money


def identity(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def content(record, *, exclude=()):
    return {f.name: getattr(record, f.name) for f in fields(record) if f.init and f.name not in exclude}


def amount(value, name="amount", *, signed=False, whole=False):
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or (not signed and value < 0):
        raise ValueError(f"{name} must be finite{' and nonnegative' if not signed else ''}")
    if whole and Fraction(value).denominator != 1:
        raise ValueError(f"{name} must be whole shares")
    return value


def digest(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f"{name} must be a SHA-256 hex digest")


def sources_tuple(values):
    values = tuple(values)
    if not all(isinstance(s, SourceRef) for s in values):
        raise TypeError("source references required")
    result = tuple(sorted(values, key=lambda s: (s.kind, s.identity, s.revision, s.provider)))
    keys = [(s.kind, s.identity, s.revision, s.provider) for s in result]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate source reference")
    return result


@dataclass(frozen=True)
class Unit:
    kind: str
    code: str

    def __post_init__(self):
        if self.kind == "CURRENCY":
            if self.code != "USD":
                raise ValueError("only USD is supported")
        elif self.kind == "SECURITY":
            check_instrument_id(self.code)
        else:
            raise ValueError("unit must be CURRENCY or SECURITY")

    @property
    def key(self):
        return f"{self.kind}:{self.code}"


@dataclass(frozen=True)
class SourceRef:
    kind: str
    identity: str
    revision: int
    stored_record_id: str
    content_hash: str
    effective_at: datetime
    available_at: datetime
    delivered_at: datetime
    provider: str

    def __post_init__(self):
        for name in ("kind", "identity", "stored_record_id", "provider"):
            check_name(getattr(self, name), name)
        check_revision(self.revision)
        digest(self.content_hash, "content_hash")
        for name in ("effective_at", "available_at", "delivered_at"):
            check_utc(getattr(self, name), name)

    @property
    def known_at(self):
        return max(self.available_at, self.delivered_at)

    @property
    def source_id(self):
        return identity(content(self))


@dataclass(frozen=True)
class SourceBundle:
    account_id: str
    cutoff: datetime
    records: tuple[object, ...]
    references: tuple[SourceRef, ...]
    provider: str
    coverage_ref: str
    omissions: tuple[str, ...]
    model_version: str

    def __post_init__(self):
        for name in ("account_id", "provider", "coverage_ref", "model_version"):
            check_name(getattr(self, name), name)
        check_utc(self.cutoff, "cutoff")
        object.__setattr__(self, "records", tuple(decode(encode(r)) for r in self.records))
        object.__setattr__(self, "references", sources_tuple(self.references))
        object.__setattr__(self, "omissions", tuple(self.omissions))
        if any(s.known_at > self.cutoff for s in self.references):
            raise ValueError("source not known at cutoff")
        if any(s.provider not in (self.provider, "declared", "oms") for s in self.references):
            raise ValueError("mixed provider sources")
        for reason in self.omissions:
            check_name(reason, "omission")

    @property
    def complete(self):
        return not self.omissions


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    transaction_id: str
    investment_account_id: str
    account: str
    debit: Decimal
    credit: Decimal
    unit: Unit
    effective_at: datetime
    posted_at: datetime
    sources: tuple[SourceRef, ...]
    reverses: str | None = None

    def __post_init__(self):
        for name in ("entry_id", "transaction_id", "investment_account_id", "account"):
            check_name(getattr(self, name), name)
        amount(self.debit, "debit")
        amount(self.credit, "credit")
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError("exactly one positive entry side is required")
        if not isinstance(self.unit, Unit):
            raise TypeError("unit required")
        if self.unit.kind == "SECURITY":
            amount(self.debit, whole=True)
            amount(self.credit, whole=True)
        check_utc(self.effective_at, "effective_at")
        check_utc(self.posted_at, "posted_at")
        object.__setattr__(self, "sources", sources_tuple(self.sources))
        if not self.sources or any(s.known_at > self.posted_at for s in self.sources):
            raise ValueError("posting source must be known")
        if self.reverses is not None:
            check_name(self.reverses, "reverses")


@dataclass(frozen=True)
class JournalTransaction:
    transaction_id: str
    investment_account_id: str
    effective_at: datetime
    posted_at: datetime
    sources: tuple[SourceRef, ...]
    entries: tuple[LedgerEntry, ...]
    reverses: str | None = None

    def __post_init__(self):
        check_name(self.transaction_id, "transaction_id")
        check_name(self.investment_account_id, "investment_account_id")
        check_utc(self.effective_at, "effective_at")
        check_utc(self.posted_at, "posted_at")
        object.__setattr__(self, "sources", sources_tuple(self.sources))
        object.__setattr__(self, "entries", tuple(self.entries))
        if not self.entries or len({e.entry_id for e in self.entries}) != len(self.entries):
            raise ValueError("nonempty unique entry manifest required")
        totals = defaultdict(Fraction)
        counts = defaultdict(int)
        for entry in self.entries:
            if not isinstance(entry, LedgerEntry):
                raise TypeError("entry required")
            if (entry.transaction_id, entry.investment_account_id, entry.effective_at, entry.posted_at, entry.sources) != (
                    self.transaction_id, self.investment_account_id, self.effective_at, self.posted_at, self.sources):
                raise ValueError("entry transaction/account/time/source mismatch")
            totals[entry.unit] += Fraction(entry.debit) - Fraction(entry.credit)
            counts[entry.unit] += 1
        if any(totals.values()) or any(n < 2 for n in counts.values()):
            raise ValueError("transaction must balance separately in every unit")
        if self.reverses is not None:
            check_name(self.reverses, "reverses")
            if not all(e.reverses for e in self.entries):
                raise ValueError("reversal must identify every original entry")
        elif any(e.reverses for e in self.entries):
            raise ValueError("entry reversals need a reversed transaction")

    @property
    def entry_count(self):
        return len(self.entries)

    @property
    def manifest_hash(self):
        return identity(self.entries)


def journal(account_id, effective_at, posted_at, sources, lines, *, reverses=None, reversed_entries=()):
    """Signed debit lines; zero lines omitted. IDs are derived from the full manifest."""
    refs = sources_tuple(sources)
    lines = tuple((name, unit, amount(value, signed=True)) for name, unit, value in lines if value != 0)
    tid = identity((account_id, effective_at, posted_at, refs, lines, reverses))
    entries = tuple(LedgerEntry(identity((tid, i)), tid, account_id, name,
                               value if value > 0 else Decimal(0),
                               value.copy_abs() if value < 0 else Decimal(0), unit,
                               effective_at, posted_at, refs,
                               reversed_entries[i] if reversed_entries else None)
                    for i, (name, unit, value) in enumerate(lines))
    return JournalTransaction(tid, account_id, effective_at, posted_at, refs, entries, reverses)


def reverse_transaction(original, *, posted_at, account_id=None):
    if account_id is not None and account_id != original.investment_account_id:
        raise ValueError("cannot reverse across investment accounts")
    return journal(original.investment_account_id, original.effective_at, posted_at, original.sources,
                   ((e.account, e.unit, e.debit.copy_negate() if e.debit else e.credit) for e in original.entries),
                   reverses=original.transaction_id, reversed_entries=tuple(e.entry_id for e in original.entries))


@dataclass(frozen=True)
class OpeningLot:
    declaration_id: str
    starting_state_id: str
    account_id: str
    instrument_id: str
    quantity: Decimal
    total_cost: Decimal
    unit: Unit
    effective_at: datetime
    observed_at: datetime
    operator: str
    reason: str

    def __post_init__(self):
        for name in ("declaration_id", "starting_state_id", "account_id", "operator", "reason"):
            check_name(getattr(self, name), name)
        check_instrument_id(self.instrument_id)
        amount(self.quantity, whole=True)
        amount(self.total_cost)
        if not self.quantity or self.unit != Unit("CURRENCY", "USD"):
            raise ValueError("positive whole shares and USD cost required")
        check_utc(self.effective_at, "effective_at")
        check_utc(self.observed_at, "observed_at")


@dataclass(frozen=True)
class LotMatch:
    match_id: str
    book_id: str
    acquisition: str
    disposal: str
    quantity: Decimal
    cost: Decimal
    unit: Unit
    policy_version: str

    def __post_init__(self):
        for name in ("match_id", "book_id", "acquisition", "disposal", "policy_version"):
            check_name(getattr(self, name), name)
        amount(self.quantity, whole=True)
        amount(self.cost)
        if self.quantity <= 0 or self.unit != Unit("CURRENCY", "USD"):
            raise ValueError("positive quantity and currency cost required")


@dataclass(frozen=True)
class BookBatch:
    account_id: str
    parent_id: str | None
    version: int
    policy_version: str
    sources: tuple[SourceRef, ...]
    transactions: tuple[JournalTransaction, ...]
    lot_matches: tuple[LotMatch, ...]
    posted_at: datetime

    def __post_init__(self):
        check_name(self.account_id, "account_id")
        check_name(self.policy_version, "policy_version")
        check_revision(self.version)
        check_utc(self.posted_at, "posted_at")
        if (self.parent_id is None) != (self.version == 1):
            raise ValueError("first version alone has no parent")
        if self.parent_id is not None:
            check_name(self.parent_id, "parent_id")
        object.__setattr__(self, "sources", sources_tuple(self.sources))
        object.__setattr__(self, "transactions", tuple(self.transactions))
        object.__setattr__(self, "lot_matches", tuple(self.lot_matches))
        if any(s.known_at > self.posted_at for s in self.sources):
            raise ValueError("source not known at posting")
        if len({t.transaction_id for t in self.transactions}) != len(self.transactions):
            raise ValueError("duplicate transaction")
        if any(t.investment_account_id != self.account_id or t.posted_at != self.posted_at for t in self.transactions):
            raise ValueError("batch account/posting mismatch")
        if any(s not in self.sources for t in self.transactions for s in t.sources):
            raise ValueError("transaction source missing from batch receipts")

    @property
    def source_set_hash(self):
        return identity(self.sources)

    @property
    def book_id(self):
        values = content(self)
        # A match refers back to this book. Hash its economic content without that
        # redundant back-reference, then bind the reference before append. No old
        # book IDs change: no matches had been stored before this correction.
        values["lot_matches"] = tuple(content(m, exclude=("book_id",)) for m in self.lot_matches)
        return identity(values)


@dataclass(frozen=True)
class BalanceQuery:
    account_id: str
    effective_at: datetime
    known_at: datetime
    book_id: str

    def __post_init__(self):
        check_name(self.account_id, "account_id")
        check_name(self.book_id, "book_id")
        check_utc(self.effective_at, "effective_at")
        check_utc(self.known_at, "known_at")

    @property
    def query_id(self):
        return identity(content(self))


@dataclass(frozen=True)
class LedgerBalances:
    query: BalanceQuery
    cash: Decimal
    currency: str
    positions: tuple[tuple[str, Decimal], ...]
    costs: tuple[tuple[str, Decimal], ...]
    receivables: tuple[tuple[str, Decimal], ...]
    gross_realized: Decimal
    dividend_income: Decimal
    fees: Decimal
    sources: tuple[SourceRef, ...]
    complete: bool
    reasons: tuple[str, ...]

    def __post_init__(self):
        Unit("CURRENCY", self.currency)
        amount(self.cash, signed=True)  # accepted fill facts can reveal a breach
        amount(self.gross_realized, signed=True)
        amount(self.dividend_income, signed=True)
        amount(self.fees, signed=True)
        for name in ("positions", "costs", "receivables"):
            values = tuple(sorted(getattr(self, name)))
            if len({i for i, _ in values}) != len(values):
                raise ValueError("duplicate balance instrument")
            for instrument, value in values:
                check_instrument_id(instrument)
                amount(value, whole=name == "positions")
            object.__setattr__(self, name, values)
        object.__setattr__(self, "sources", sources_tuple(self.sources))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.complete and self.reasons:
            raise ValueError("complete balances cannot have missing reasons")
        if any(s.known_at > self.query.known_at for s in self.sources):
            raise ValueError("balance source is not known")


class AccountingUnavailable(ValueError):
    def __init__(self, account_id, cutoff, reasons, sources=()):
        self.account_id, self.cutoff = account_id, check_utc(cutoff, "cutoff")
        self.reasons, self.sources = tuple(reasons), tuple(sources)
        super().__init__("accounting unavailable: " + "; ".join(self.reasons))


class SourceConflict(ValueError):
    """Different content supplied for one immutable source identity."""


class CostBasisPort(Protocol):
    def consume(self, instrument_id: str, quantity: Decimal, disposal: str) -> tuple[LotMatch, ...]: ...


class SnapshotProvider(Protocol):
    def capture(self, account_id: str, *, at: datetime) -> object: ...


for _type in (Money, AmountBasis, CorporateAction, Unit, SourceRef, SourceBundle, LedgerEntry, JournalTransaction, OpeningLot,
              LotMatch, BookBatch, BalanceQuery, LedgerBalances):
    register(_type)
