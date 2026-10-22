"""M5-01: deferred SQL invariants, atomic effects, idempotence and parent races."""
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from psycopg import Error as PgError

from investment_engine.audit.events import Actor, ActorKind, AuditStore
from investment_engine.clock import ReplayClock
from investment_engine.events.outbox import Outbox
from investment_engine.ledger.contracts import (
    BookBatch,
    JournalTransaction,
    LedgerEntry,
    LotMatch,
    SourceBundle,
    SourceConflict,
    Unit,
    identity,
    journal,
    reverse_transaction,
)
from investment_engine.ledger.store import LedgerStore, StaleBook
from investment_engine.lineage.records import canonical_json
from investment_engine.oms.order_states import ProcessRole
from investment_engine.policy.accounts import AccountRegistry
from investment_engine.portfolio.snapshot import PortfolioSnapshotStore
from investment_engine.storage.database import IntegrityViolation, PostgresDatabase
from investment_engine.storage.postgres import apply_pg_schema, open_operational_pg
from tests.engine.test_ledger_contracts import source

T = datetime(2024, 1, 2, tzinfo=UTC)
pytestmark = pytest.mark.postgres


def make_batch(account="R1", parent=None, version=1, when=T, refs=None, transactions=None):
    refs = (source(),) if refs is None else refs
    transactions = (journal(account, T, when, refs, (("CASH", Unit("CURRENCY", "USD"), Decimal(100)),
                            ("CAPITAL", Unit("CURRENCY", "USD"), Decimal(-100)))),) if transactions is None else transactions
    return BookBatch(account, parent, version, "fifo-v1", refs, transactions, (), when)


def open_store(dsn):
    conn = open_operational_pg(dsn)
    apply_pg_schema(conn)
    db = PostgresDatabase(conn)
    with db.transaction():
        db.execute("INSERT INTO accounts VALUES ('R1','RESEARCH','USD',:t,:t) ON CONFLICT DO NOTHING", {"t": T})
        db.execute("INSERT INTO accounts VALUES ('R2','RESEARCH','USD',:t,:t) ON CONFLICT DO NOTHING", {"t": T})
    clock = ReplayClock(T)
    return conn, db, LedgerStore(db, audit=AuditStore(db), outbox=Outbox(db, writer=ProcessRole.CORE, clock=clock),
                               clock=clock, command_clock=ReplayClock(T + timedelta(days=1)))


@pytest.fixture
def env(pg_database):
    conn, db, store = open_store(pg_database)
    yield conn, db, store
    conn.close()


def counts(db):
    return tuple(db.fetchone(f"SELECT COUNT(*) FROM {name}")[0] for name in (
        "ledger_batches", "ledger_transactions", "ledger_entries", "ledger_source_receipts", "audit_events", "outbox"))


def test_idempotent_atomic_batch_and_historical_head(env):
    _, db, store = env
    batch = make_batch()
    assert store.append_batch(batch) == batch
    before = counts(db)
    assert store.append_batch(batch) == batch
    assert counts(db) == before == (1, 1, 2, 1, 1, 1)
    assert store.read_head("R1", known_at=T) == batch
    assert store.history("R1", known_at=T) == (batch,)
    with pytest.raises(KeyError):
        store.read_head("R1", known_at=T - timedelta(seconds=1))


@pytest.mark.parametrize("table", ["ledger_batches", "ledger_transactions", "ledger_entries", "ledger_source_receipts", "audit_events", "outbox"])
def test_failure_at_each_write_rolls_back_every_effect(env, monkeypatch, table):
    _, db, store = env
    before = counts(db)
    original = db.execute

    def fail(sql, params=None):
        original(sql, params)
        if sql.startswith("INSERT INTO " + table + " "):
            raise RuntimeError("injected failure after table write")

    monkeypatch.setattr(db, "execute", fail)
    with pytest.raises(RuntimeError, match="injected"):
        store.append_batch(make_batch())
    assert counts(db) == before


@pytest.mark.parametrize("sql", [
    "UPDATE ledger_entries SET debit=debit", "DELETE FROM ledger_entries", "TRUNCATE ledger_entries CASCADE",
    "UPDATE ledger_transactions SET entry_count=entry_count", "DELETE FROM ledger_batches", "TRUNCATE ledger_batches CASCADE",
    "INSERT INTO ledger_entries SELECT * FROM ledger_entries ON CONFLICT(entry_id) DO UPDATE SET debit=excluded.debit",
])
def test_sql_cannot_replace_or_remove_saved_facts(env, sql):
    conn, _, store = env
    store.append_batch(make_batch())
    with pytest.raises(Exception, match="append-only"), conn.transaction():
        conn.execute(sql)


def test_header_without_entries_and_late_balanced_pair_refused(env):
    conn, _, store = env
    batch = make_batch()
    store.append_batch(batch)
    with pytest.raises(PgError), conn.transaction():
        conn.execute("INSERT INTO ledger_transactions SELECT 'empty',book_id,account_id,effective_at,posted_at,2,manifest_hash,NULL "
                     "FROM ledger_transactions LIMIT 1")
    with pytest.raises(PgError), conn.transaction():
        conn.execute("INSERT INTO ledger_entries SELECT entry_id || '-late', transaction_id,book_id,account_id,ordinal+10,"
                     "chart_account,unit,debit,credit,effective_at,posted_at,NULL,content FROM ledger_entries")


def test_parent_cas_and_full_reversal_once(env):
    _, _, store = env
    first = store.append_batch(make_batch())
    reversal = reverse_transaction(first.transactions[0], posted_at=T + timedelta(days=1))
    second = make_batch(parent=first.book_id, version=2, when=reversal.posted_at, transactions=(reversal,))
    assert store.append_batch(second) == second
    with pytest.raises(StaleBook):
        store.append_batch(replace(second, posted_at=T + timedelta(days=2), transactions=()))
    third = make_batch(parent=second.book_id, version=3, when=T + timedelta(days=2),
                       transactions=(reverse_transaction(first.transactions[0], posted_at=T + timedelta(days=2)),))
    with pytest.raises(IntegrityViolation):
        store.append_batch(third)


def test_two_connections_same_parent_cannot_lose_an_update(pg_database):
    conn, _, store = open_store(pg_database)
    first = store.append_batch(make_batch())
    barrier = threading.Barrier(2)
    results = []

    def writer(n):
        c, _, s = open_store(pg_database)
        try:
            batch = make_batch(parent=first.book_id, version=2, when=T + timedelta(seconds=n), transactions=())
            barrier.wait(timeout=20)
            try:
                s.append_batch(batch)
                results.append("ok")
            except StaleBook:
                results.append("stale")
        finally:
            c.close()

    threads = [threading.Thread(target=writer, args=(n,)) for n in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    assert sorted(results) == ["ok", "stale"]
    assert len(store.history("R1", known_at=T + timedelta(days=1))) == 2
    conn.close()


def test_store_activation_is_explicit_and_idempotent_under_live_authorization(env):
    _, db, store = env
    live = ReplayClock(T + timedelta(days=1))
    audit = AuditStore(db)
    accounts = AccountRegistry(db, audit, live)
    accounts.bootstrap_admin("owner", os_user="test")
    owner = Actor(ActorKind.OPERATOR, "owner", "ADMIN", "test")
    snapshots = PortfolioSnapshotStore(db, audit, accounts, live)
    start = snapshots.declare_start("R1", by=owner, reason="declared research start", effective_at=T)
    ref = source(kind="opening", identity=start.state_id, stored_record_id=start.state_id,
                 content_hash=start.state_id.removeprefix("sst-"))
    bundle = SourceBundle("R1", T, (start,), (ref,), "declared", "declared-start", (), "v1")
    book = store.activate("R1", opening_lots=(), source_bundle=bundle, by=owner, reason="explicit activation")
    assert book.transactions[0].entries[0].debit == Decimal(100000)
    assert store.activate("R1", opening_lots=(), source_bundle=bundle, by=owner, reason="explicit activation") == book
    accounts.deactivate_operator("owner", by=owner, reason="end authorization")
    with pytest.raises(PermissionError):
        store.activate("R1", opening_lots=(), source_bundle=bundle, by=owner, reason="retry after deactivation")


@pytest.mark.parametrize("units,values", [
    (("CURRENCY:USD", "CURRENCY:USD", "SECURITY:EQ_US_NVDA", "SECURITY:EQ_US_NVDA"), ("1", "-1", "2", "-1")),
    (("SECURITY:EQ_US_NVDA", "SECURITY:EQ_US_MSFT"), ("1", "-1")),
])
def test_raw_sql_per_unit_balance_even_when_global_sum_matches(env, units, values):
    """Bypass the dataclass transaction validator, not the database guards."""
    conn, _, _ = env
    tx = object.__new__(JournalTransaction)
    entries = tuple(LedgerEntry(str(n), "raw", "R1", "CUSTODY_SHARES" if raw.startswith("SECURITY") else "CASH",
                               Decimal(value) if Decimal(value) > 0 else Decimal(0),
                               abs(Decimal(value)) if Decimal(value) < 0 else Decimal(0),
                               Unit(*raw.split(":")), T, T, (source(),))
                    for n, (raw, value) in enumerate(zip(units, values, strict=True)))
    for name, value in {"transaction_id": "raw", "investment_account_id": "R1", "effective_at": T,
                        "posted_at": T, "sources": (source(),), "entries": entries, "reverses": None}.items():
        object.__setattr__(tx, name, value)
    batch = make_batch(transactions=(tx,))
    with pytest.raises(PgError, match="balance independently"), conn.transaction():
        conn.execute("INSERT INTO ledger_batches VALUES (%s,'R1',NULL,1,%s,%s,0,1,0,%s)",
                     (batch.book_id, T, batch.source_set_hash, canonical_json(batch)))
        conn.execute("INSERT INTO ledger_transactions VALUES('raw',%s,'R1',%s,%s,%s,%s,NULL)",
                     (batch.book_id, T, T, tx.entry_count, tx.manifest_hash))
        for n, entry in enumerate(entries):
            conn.execute("INSERT INTO ledger_entries VALUES(%s,'raw',%s,'R1',%s,%s,%s,%s,%s,%s,%s,NULL,%s)",
                         (entry.entry_id, batch.book_id, n, entry.account, entry.unit.key,
                          entry.debit, entry.credit, T, T, canonical_json(entry)))
        conn.execute("SET CONSTRAINTS ledger_transaction_sealed IMMEDIATE")


def test_raw_sql_altered_manifest_and_cross_account_orphan_refused(env):
    conn, _, store = env
    first = store.append_batch(make_batch())
    tx = first.transactions[0]
    with pytest.raises(PgError), conn.transaction():
        conn.execute("INSERT INTO ledger_entries SELECT entry_id || 'x',transaction_id,book_id,'R2',ordinal+10,"
                     "chart_account,unit,debit,credit,effective_at,posted_at,NULL,content FROM ledger_entries")
    with pytest.raises(PgError), conn.transaction():
        conn.execute("INSERT INTO ledger_entries SELECT entry_id || 'x','no-transaction',book_id,account_id,ordinal+10,"
                     "chart_account,unit,debit,credit,effective_at,posted_at,NULL,content FROM ledger_entries")
    with pytest.raises(PgError, match="manifest"), conn.transaction():
        conn.execute("INSERT INTO ledger_transactions VALUES ('altered',%s,'R1',%s,%s,2,%s,NULL)",
                     (first.book_id, T, T, "0" * 64))
        conn.execute("SET CONSTRAINTS ledger_transaction_sealed IMMEDIATE")
    reverse = reverse_transaction(tx, posted_at=T + timedelta(days=1))
    bad = replace(reverse, entries=tuple(replace(e, account="FEES") for e in reverse.entries))
    with pytest.raises(PgError, match="fully negate"):
        store.append_batch(make_batch(parent=first.book_id, version=2, when=bad.posted_at, transactions=(bad,)))
    assert canonical_json(store.get(first.book_id)) == canonical_json(first)


def test_lot_match_must_point_to_its_containing_book(env):
    _, _, store = env
    match = LotMatch("m", "wrong-book", "buy", "sell", Decimal(1), Decimal(1), Unit("CURRENCY", "USD"), "fifo-v1")
    batch = replace(make_batch(), lot_matches=(match,))
    with pytest.raises(ValueError, match="lot.*book"):
        store.append_batch(batch)
    finalized = replace(batch, lot_matches=(replace(match, book_id=batch.book_id),))
    assert store.append_batch(finalized) == finalized


def _divergent_sql_batch(db, first, component):
    """Claude's P1, with valid source keys, plus independent receipt/lot variants."""
    when = T + timedelta(hours=1)
    refs = (*first.sources, source(identity="R1/extra", stored_record_id="x"))
    usd = Unit("CURRENCY", "USD")
    real = journal("R1", T, when, refs, (("CASH", usd, Decimal(5)), ("CAPITAL", usd, Decimal(-5))))
    fake = real
    if component == "transaction":
        inflated = journal("R1", T, when, refs,
                           (("CASH", usd, Decimal(1000000)), ("CAPITAL", usd, Decimal(-1000000))))
        fake = replace(inflated, transaction_id=real.transaction_id,
                       entries=tuple(replace(e, transaction_id=real.transaction_id) for e in inflated.entries))
    batch_refs = refs if component != "source" else (refs[0], replace(refs[1], content_hash="b" * 64))
    if component == "source":
        fake = replace(fake, sources=batch_refs,
                       entries=tuple(replace(e, sources=batch_refs) for e in fake.entries))
    match = LotMatch("review-match", "pending", "buy", "sell", Decimal(1), Decimal(1), usd, "fifo-v1")
    matches = (replace(match, cost=Decimal(999)),) if component == "lot" else ()
    batch = BookBatch("R1", first.book_id, 2, first.policy_version, batch_refs, (fake,), matches, when)
    if matches:
        batch = replace(batch, lot_matches=(replace(matches[0], book_id=batch.book_id),))
        match = replace(match, book_id=batch.book_id)
    with db.transaction():
        db.execute("INSERT INTO ledger_batches VALUES(:id,'R1',:p,2,:t,:h,:ns,1,:nl,:c)",
                   {"id": batch.book_id, "p": first.book_id, "t": when,
                    "h": "0" * 64 if component == "source_hash" else batch.source_set_hash,
                    "ns": len(refs), "nl": len(matches), "c": canonical_json(batch)})
        for ref in refs:
            db.execute("INSERT INTO ledger_source_receipts VALUES(:b,:id,:k,:h,:c)",
                       {"b": batch.book_id, "id": ref.source_id,
                        "k": identity(("R1", ref.kind, ref.identity, ref.revision, ref.provider)),
                        "h": "b" * 64 if component == "receipt_hash" else ref.content_hash,
                        "c": canonical_json(replace(ref, stored_record_id="forged"))
                             if component == "receipt_content" else canonical_json(ref)})
        db.execute("INSERT INTO ledger_transactions VALUES(:id,:b,'R1',:e,:p,:n,:h,NULL)",
                   {"id": real.transaction_id, "b": batch.book_id, "e": real.effective_at,
                    "p": when, "n": real.entry_count, "h": real.manifest_hash})
        for n, entry in enumerate(real.entries):
            db.execute("INSERT INTO ledger_entries VALUES(:id,:tx,:b,'R1',:n,:chart,:unit,:d,:c,:e,:p,NULL,:content)",
                       {"id": entry.entry_id, "tx": real.transaction_id, "b": batch.book_id, "n": n,
                        "chart": entry.account, "unit": entry.unit.key, "d": entry.debit,
                        "c": entry.credit, "e": entry.effective_at, "p": when, "content": canonical_json(entry)})
        if matches:
            db.execute("INSERT INTO ledger_lot_matches VALUES(:b,:id,:c)",
                       {"b": batch.book_id, "id": match.match_id, "c": canonical_json(match)})
    return batch


@pytest.mark.parametrize("component", ["transaction", "source", "lot", "source_hash", "receipt_hash", "receipt_content"])
def test_sql_batch_copy_must_match_its_sealed_rows(env, component):
    """P1 red/green: reject the commit, rather than asserting the exploit succeeds."""
    _, db, store = env
    first = store.append_batch(make_batch())
    before = counts(db)
    with pytest.raises((PgError, IntegrityViolation), match="ledger.*(payload|source|manifest)"):
        _divergent_sql_batch(db, first, component)
    assert counts(db) == before
    assert store.read_head("R1", known_at=T + timedelta(days=1)) == first


@pytest.mark.parametrize("component", ["transaction", "source", "lot", "source_hash", "receipt_hash", "receipt_content"])
def test_load_refuses_pre_0019_divergent_book(pg_database, monkeypatch, component):
    """Legacy corruption is refused without editing history or disabling any trigger."""
    from investment_engine.storage import postgres as pg

    scripts = pg._pg_schema_scripts()
    monkeypatch.setattr(pg, "_pg_schema_scripts", lambda: [(n, s) for n, s in scripts if n <= 18])
    conn, db, store = open_store(pg_database)
    try:
        first = store.append_batch(make_batch())
        bad = _divergent_sql_batch(db, first, component)
        with pytest.raises(SourceConflict, match="stored ledger.*(payload|source|manifest)"):
            store.get(bad.book_id)
    finally:
        conn.close()


@pytest.mark.parametrize("text", ['normal', '\x7f', 'é漢😀', 'quote" slash\\ newline\n', '\b\f\t\r\x01'])
def test_sql_canonical_codec_matches_existing_identity_bytes(env, text):
    _, db, _ = env
    value = (source(identity="x" + text + "x"), {"z": text, "a": (None, 17, True)})
    encoded = canonical_json(value)
    assert db.fetchone("SELECT ledger_canonical_json(CAST(:value AS jsonb))", {"value": encoded})[0] == encoded


def test_sql_activation_cannot_name_a_later_book(env):
    _, db, store = env
    first = store.append_batch(make_batch())
    second = store.append_batch(make_batch(parent=first.book_id, version=2, when=T + timedelta(hours=1)))
    with pytest.raises((PgError, IntegrityViolation), match="first account book"), db.transaction():
        db.execute("INSERT INTO ledger_activations VALUES ('R1',:b,:t,'[]')", {"b": second.book_id, "t": T})
