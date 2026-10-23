"""Atomic append-only PostgreSQL accounting batches (accepted ADR-010; M5-01)."""
import json
from collections import defaultdict
from decimal import Context, Decimal, localcontext

from investment_engine.audit.events import Actor, ActorKind, AuditEvent
from investment_engine.events.envelope import EventEnvelope
from investment_engine.ledger.contracts import (
    AccountingUnavailable,
    BookBatch,
    OpeningLot,
    SourceBundle,
    SourceConflict,
    Unit,
    identity,
    journal,
)
from investment_engine.lineage.records import canonical_json, decode
from investment_engine.market.availability import check_name, check_utc
from investment_engine.policy.accounts import AccountRegistry, Role
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore, StartingState
from investment_engine.storage.sqlite import port


class StaleBook(ValueError):
    """The caller must rebuild against the current immutable book head."""


class LedgerStore:
    def __init__(self, db, *, audit, outbox, clock, command_clock):
        self._db = port(db)
        if self._db.backend != "postgresql":
            raise TypeError("ledger is PostgreSQL only")
        self._audit, self._outbox = audit, outbox
        self._clock, self._command_clock = clock, command_clock

    @property
    def db(self):
        return self._db

    def _load(self, row):
        if row is None:
            raise KeyError("no ledger book at cutoff")
        book = decode(json.loads(row[1]))
        if not isinstance(book, BookBatch) or book.book_id != row[0]:
            raise SourceConflict("stored ledger book content/hash mismatch")
        if any(match.book_id != book.book_id for match in book.lot_matches):
            raise SourceConflict("stored lot match book reference mismatch")
        # Read guards also cover immutable records committed before migration 0019.
        header = self._db.fetchone(
            "SELECT account_id,parent_id,version,posted_at,source_set_hash,source_count,transaction_count,lot_count "
            "FROM ledger_batches WHERE book_id=:b", {"b": book.book_id})
        if header != (book.account_id, book.parent_id, book.version, book.posted_at, book.source_set_hash,
                      len(book.sources), len(book.transactions), len(book.lot_matches)):
            raise SourceConflict("stored ledger batch payload/source manifest mismatch")
        transactions = self._db.fetchall(
            "SELECT transaction_id,account_id,effective_at,posted_at,entry_count,manifest_hash,reverses "
            'FROM ledger_transactions WHERE book_id=:b ORDER BY transaction_id COLLATE "C"', {"b": book.book_id})
        expected = sorted((t.transaction_id, t.investment_account_id, t.effective_at, t.posted_at,
                           t.entry_count, t.manifest_hash, t.reverses) for t in book.transactions)
        if list(transactions) != expected:
            raise SourceConflict("stored ledger transaction payload/manifest mismatch")
        entries = self._db.fetchall(
            'SELECT transaction_id,ordinal,content FROM ledger_entries WHERE book_id=:b '
            'ORDER BY transaction_id COLLATE "C",ordinal',
            {"b": book.book_id})
        if [(r[0], r[1], json.loads(r[2])) for r in entries] != [
                (t.transaction_id, n, json.loads(canonical_json(e)))
                for t in sorted(book.transactions, key=lambda t: t.transaction_id) for n, e in enumerate(t.entries)]:
            raise SourceConflict("stored ledger entry payload/manifest mismatch")
        receipts = self._db.fetchall(
            "SELECT source_id,source_key,content_hash,content FROM ledger_source_receipts "
            'WHERE book_id=:b ORDER BY source_id COLLATE "C"', {"b": book.book_id})
        if [(r[0], r[1], r[2], json.loads(r[3])) for r in receipts] != [
                (s.source_id, identity((book.account_id, s.kind, s.identity, s.revision, s.provider)),
                 s.content_hash, json.loads(canonical_json(s))) for s in sorted(book.sources, key=lambda s: s.source_id)]:
            raise SourceConflict("stored ledger source receipt payload/hash mismatch")
        matches = self._db.fetchall(
            'SELECT match_id,content FROM ledger_lot_matches WHERE book_id=:b ORDER BY match_id COLLATE "C"',
            {"b": book.book_id})
        if [(r[0], json.loads(r[1])) for r in matches] != [
                (m.match_id, json.loads(canonical_json(m))) for m in sorted(book.lot_matches, key=lambda m: m.match_id)]:
            raise SourceConflict("stored ledger lot match payload mismatch")
        return book

    def get(self, book_id):
        check_name(book_id, "book_id")
        return self._load(self._db.fetchone("SELECT book_id,content FROM ledger_batches WHERE book_id=:id", {"id": book_id}))

    def read_head(self, account_id, *, known_at):
        check_name(account_id, "account_id")
        return self._load(self._db.fetchone("SELECT book_id,content FROM ledger_batches WHERE account_id=:a "
                          "AND posted_at<=:t ORDER BY version DESC LIMIT 1",
                          {"a": account_id, "t": check_utc(known_at, "known_at")}))

    def history(self, account_id, *, known_at):
        check_name(account_id, "account_id")
        return tuple(self._load(row) for row in self._db.fetchall(
            "SELECT book_id,content FROM ledger_batches WHERE account_id=:a AND posted_at<=:t ORDER BY version",
            {"a": account_id, "t": check_utc(known_at, "known_at")}))

    def ancestry(self, book_id):
        """Pinned parent chain; equal-time later batches are never accidentally included."""
        result = []
        current = self.get(book_id)
        while True:
            result.append(current)
            if current.parent_id is None:
                return tuple(reversed(result))
            current = self.get(current.parent_id)

    def activation(self, account_id):
        row = self._db.fetchone("SELECT book_id FROM ledger_activations WHERE account_id=:a", {"a": account_id})
        if row is None:
            return None
        book = self.get(row[0])
        if book.account_id != account_id or book.version != 1:
            raise SourceConflict("stored ledger activation does not name the first account book")
        return book

    def activate(self, account_id, *, opening_lots, source_bundle, by, reason):
        """Explicit Admin activation from the saved declared start; no repricing old holdings.

        StartingState's economic state_id deliberately excludes live command provenance.
        Its receipt hash is that captured identity; the complete saved StartingState is
        also compared before posting, and the live activation command is separately audited.
        """
        check_name(reason, "reason")
        if not isinstance(source_bundle, SourceBundle) or source_bundle.account_id != account_id:
            raise ValueError("activation needs this account's source bundle")
        if not source_bundle.complete:
            raise AccountingUnavailable(account_id, source_bundle.cutoff, source_bundle.omissions, source_bundle.references)
        lots = tuple(opening_lots)
        with self._db.transaction():
            self._db.lock(f"account-control|{account_id}")
            self._db.lock(f"ledger|{account_id}")
            self._db.lock(f"operator|{by.actor_id}")
            now = check_utc(self._command_clock.now(), "command time")
            accounts = AccountRegistry(self._db, self._audit, self._command_clock)
            accounts.authorize(by, (Role.ADMIN,), now)
            accounts.account(account_id)
            snapshots = PortfolioSnapshotStore(self._db, self._audit, accounts, self._command_clock)
            start = snapshots.starting_state(account_id)
            supplied = tuple(r for r in source_bundle.records if isinstance(r, StartingState))
            refs = tuple(r for r in source_bundle.references if r.kind == "opening")
            if supplied != (start,) or len(refs) != 1 or refs[0].identity != start.state_id or (
                    refs[0].stored_record_id != start.state_id or refs[0].content_hash != start.state_id.removeprefix("sst-")):
                raise SourceConflict("opening source does not match the stored declared start")
            if start.effective_at > source_bundle.cutoff:
                raise AccountingUnavailable(account_id, source_bundle.cutoff, ("starting state is not effective",))
            quantities = defaultdict(Decimal)
            lines = []
            with localcontext(Context(prec=34)):
                if start.cash:
                    lines.extend((("CASH", Unit("CURRENCY", "USD"), start.cash),
                                  ("CAPITAL", Unit("CURRENCY", "USD"), -start.cash)))
                if len({lot.declaration_id for lot in lots}) != len(lots):
                    raise ValueError("duplicate opening lot declaration")
                for lot in lots:
                    if not isinstance(lot, OpeningLot) or lot.account_id != account_id or lot.starting_state_id != start.state_id:
                        raise ValueError("opening lot account/start mismatch")
                    if lot.effective_at != start.effective_at or lot.observed_at > source_bundle.cutoff:
                        raise ValueError("opening lot time mismatch")
                    quantities[lot.instrument_id] += lot.quantity
                    if lot.total_cost:
                        lines.extend(((f"INVENTORY_COST:{lot.instrument_id}", lot.unit, lot.total_cost),
                                      ("CAPITAL", lot.unit, -lot.total_cost)))
                    security = Unit("SECURITY", lot.instrument_id)
                    lines.extend((("CUSTODY_SHARES", security, lot.quantity), ("SHARE_OFFSET", security, -lot.quantity)))
                if dict(quantities) != dict(start.positions):
                    raise AccountingUnavailable(account_id, source_bundle.cutoff, ("opening quantities need explicit matching lot costs",))
            activation_content = canonical_json((start.state_id, lots, source_bundle.references))
            saved = self._db.fetchone("SELECT book_id,content FROM ledger_activations WHERE account_id=:a", {"a": account_id})
            if saved is not None:
                if saved[1] != activation_content:
                    raise SourceConflict("account already activated with different opening declarations")
                return self.get(saved[0])
            if self._db.fetchone("SELECT 1 FROM ledger_batches WHERE account_id=:a", {"a": account_id}) is not None:
                raise ValueError("activation must be the first accounting book")
            transactions = (journal(account_id, start.effective_at, source_bundle.cutoff, source_bundle.references, lines),) if lines else ()
            batch = BookBatch(account_id, None, 1, "fifo-cumulative-v1", source_bundle.references, transactions, (), source_bundle.cutoff)
            self.append_batch(batch)
            self._db.execute("INSERT INTO ledger_activations (account_id,book_id,command_at,content) VALUES(:a,:b,:t,:c)",
                             {"a": account_id, "b": batch.book_id, "t": now, "c": activation_content})
            self._audit.append(AuditEvent(by, "ledger.activate", "account", account_id, None, (batch.book_id, lots),
                               now, source_bundle.cutoff, reason, batch.book_id, f"activate:{account_id}"))
            return batch

    def append_batch(self, batch):
        if not isinstance(batch, BookBatch):
            raise TypeError("BookBatch required")
        if any(match.book_id != batch.book_id for match in batch.lot_matches):
            raise ValueError("lot match must refer to its containing book")
        with self._db.transaction():
            self._db.lock(f"account-control|{batch.account_id}")
            self._db.lock(f"ledger|{batch.account_id}")
            saved = self._db.fetchone("SELECT book_id,content FROM ledger_batches WHERE book_id=:id", {"id": batch.book_id})
            if saved is not None:
                if self._load(saved) != batch:
                    raise SourceConflict("book identity conflict")
                return self._load(saved)
            head = self._db.fetchone("SELECT book_id,version,posted_at FROM ledger_batches WHERE account_id=:a "
                                     "ORDER BY version DESC LIMIT 1", {"a": batch.account_id})
            if (head is None and (batch.parent_id is not None or batch.version != 1)) or (
                    head is not None and (batch.parent_id != head[0] or batch.version != head[1] + 1 or batch.posted_at < head[2])):
                raise StaleBook("ledger parent/version is stale")
            self._db.execute("INSERT INTO ledger_batches (book_id,account_id,parent_id,version,posted_at,source_set_hash,"
                             "source_count,transaction_count,lot_count,content) VALUES(:id,:a,:parent,:v,:t,:hash,:ns,:nt,:nl,:c)",
                             {"id": batch.book_id, "a": batch.account_id, "parent": batch.parent_id, "v": batch.version,
                              "t": batch.posted_at, "hash": batch.source_set_hash, "ns": len(batch.sources),
                              "nt": len(batch.transactions), "nl": len(batch.lot_matches), "c": canonical_json(batch)})
            for ref in batch.sources:
                key = identity((batch.account_id, ref.kind, ref.identity, ref.revision, ref.provider))
                previous = self._db.fetchone("SELECT content FROM ledger_source_receipts WHERE source_key=:key LIMIT 1", {"key": key})
                if previous is not None and previous[0] != canonical_json(ref):
                    raise SourceConflict("immutable source revision has different content")
                self._db.execute("INSERT INTO ledger_source_receipts (book_id,source_id,source_key,content_hash,content) "
                                 "VALUES(:b,:id,:key,:hash,:c)", {"b": batch.book_id, "id": ref.source_id,
                                 "key": key, "hash": ref.content_hash, "c": canonical_json(ref)})
            for tx in batch.transactions:
                self._db.execute("INSERT INTO ledger_transactions (transaction_id,book_id,account_id,effective_at,posted_at,"
                                 "entry_count,manifest_hash,reverses) VALUES(:id,:b,:a,:e,:p,:n,:h,:r)",
                                 {"id": tx.transaction_id, "b": batch.book_id, "a": batch.account_id, "e": tx.effective_at,
                                  "p": tx.posted_at, "n": tx.entry_count, "h": tx.manifest_hash, "r": tx.reverses})
                for ordinal, entry in enumerate(tx.entries):
                    self._db.execute("INSERT INTO ledger_entries (entry_id,transaction_id,book_id,account_id,ordinal,"
                                     "chart_account,unit,debit,credit,effective_at,posted_at,reverses,content) "
                                     "VALUES(:id,:tx,:b,:a,:n,:chart,:unit,:d,:c,:e,:p,:r,:content)",
                                     {"id": entry.entry_id, "tx": tx.transaction_id, "b": batch.book_id,
                                      "a": batch.account_id, "n": ordinal, "chart": entry.account, "unit": entry.unit.key,
                                      "d": entry.debit, "c": entry.credit, "e": entry.effective_at, "p": entry.posted_at,
                                      "r": entry.reverses, "content": canonical_json(entry)})
            for match in batch.lot_matches:
                self._db.execute("INSERT INTO ledger_lot_matches (book_id,match_id,content) VALUES(:b,:id,:c)",
                                 {"b": batch.book_id, "id": match.match_id, "c": canonical_json(match)})
            self._audit.append(AuditEvent(Actor(ActorKind.PROCESS, "core-engine", None, None), "ledger.append",
                               "ledger", batch.account_id, head[0] if head else None, batch,
                               self._command_clock.now(), batch.posted_at, "validated source batch", batch.book_id, batch.book_id))
            self._outbox.add(EventEnvelope("ledger.book_appended", 1, "ledger", batch.account_id, batch.version,
                             batch.posted_at, batch.posted_at, batch.book_id, None, canonical_json(batch)))
        return batch
