# M5: Ledger, reconciliation and accounting reports

| | |
|---|---|
| Status | **Accepted for implementation, 2026-10-21.** |
| Author | Codex, backup implementer while Claude is unavailable; self-review is not independent acceptance |
| Planning branch | `docs/m5-specs`, worktree `C:/Users/LOQ/TradingAgents-m5-specs` |
| Base | M4 merged into local main at `5cd9363` on 2026-10-21 |
| Prerequisites | M4 merged; ADR-010 reviewed and accepted; D35-D44 answered; whole milestone authorized |
| Visible result | Auditable P&L and reconciliation reports from the offline NVDA simulation |

The owner's instruction on 2026-10-21 authorizes starting M5 preparation. It supersedes the earlier handoff-only scope for planning, but does not itself accept a ledger model or authorize a merge. This pack and [ADR-010](../../architecture/adr/ADR-010-securities-ledger-model.md) were subsequently accepted by the owner on 2026-10-21; preparation history remains below. No ledger code, API-key use, market download or real account operation occurs in this package.

## Owner decisions, accepted 2026-10-21

Numbering follows accepted M4 D19-D34. Each recommendation is a product/accounting choice for this prototype, not an established financial standard or an expected improvement in returns.

| ID | Proposed choice |
|---|---|
| D35 | Accept ADR-010 v0.2's independent currency/quantity books, FIFO, immediate fee expense and cumulative half-even USD 0.0001 cost allocation with exact residual conservation. |
| D36 | USD, whole shares, long-only. Require explicit opening-lot cost for any declared initial holdings; missing cost blocks ledger activation. Existing cash-only research accounts need no invented basis. |
| D37 | Dividends remain receivables until there is actual payment evidence. No assumed payment date or automatic cash credit in this M5 package. Fractional splits and unsupported actions remain unavailable. |
| D38 / OPEN-12 | **Admin only** acknowledges or resolves incidents, with current command-time authorization and a reason. Trader and Viewer may read. Acknowledgement is not resolution; resolution requires a later comparable MATCH and never edits balances. |
| D39 | An unresolved accounting gap or confirmed reconciliation mismatch makes new account proposals/gates unavailable. It does not change the kill-switch file or block cancels. Missing/uncomparable snapshots never count as MATCH. PAPER remains blocked by the existing promotion rules. |
| D40 / OPEN-17 | Initial reports: read-only CLI plus JSON and a static HTML accounting report; daily and run-to-date P&L, positions/lots/fees/dividend receivables, journal source links, reconciliation differences and incident history. No dashboard, tax or regulatory report. |
| D41 | Compare cash and quantities exactly in their recorded Decimal units after verifying semantic comparability; compare open-order IDs, status and remaining quantity. No unexplained percentage tolerance. Exclude receivables from spendable cash comparisons and state that explicitly. |
| D42 | Daily PostgreSQL dump plus append-only market-file snapshot outside the repository, default `<data dir>/backups`. Retain successful backups initially; no automatic deletion. Same-disk copies are labelled as such. Provide a Windows daily schedule/runbook; installing/enabling a real schedule or restoring an owner database needs separate approval. |
| D43 | Approve M5 as one package after review: 15 task commits, about **55 h**, including the tasks over three hours. Focused checks per task, full suites/fresh installs once per package, one combined independent review. Merge and push remain separate. |
| D44 | Deterministic validated source corrections may append audited reversals/replacements for the full affected dependency closure. A broker discrepancy cannot trigger an automatic journal repair. Unprovable corrections leave the new cutoff incomplete. |

## Tasks and dependencies

| ID | Task | Depends on | Hours |
|---|---|---|---:|
| [M5-00](M5-00.md) | Accounting contracts and source identities | Accepted ADR-010; merged M4 | 3 |
| [M5-01](M5-01.md) | Journal migration and atomic append-only store | 00 | 4 |
| [M5-02](M5-02.md) | Opening and fill posting, source receipts | 01 | 4 |
| [M5-03](M5-03.md) | FIFO lots and fee/P&L policy | 02 | 3 |
| [M5-04](M5-04.md) | Splits, dividends and revision corrections | 03 | 5 |
| [M5-05](M5-05.md) | Temporal balances and correction dependency closure | 04 | 3 |
| [M5-06](M5-06.md) | Ledger-backed portfolio and fingerprints | 05 | 4 |
| [M5-07](M5-07.md) | Independent simulator account and worker snapshots | 06 | 5 |
| [M5-08](M5-08.md) | Comparable-cutoff reconciliation | 07 | 3 |
| [M5-09](M5-09.md) | Incident store and resolution permissions | 08 | 3 |
| [M5-10](M5-10.md) | Core/worker/harness integration and recovery | 09 | 4 |
| [M5-11](M5-11.md) | Read-only accounting reports and Admin commands | 10 | 3 |
| [M5-12](M5-12.md) | Backup, restore verification and daily runbook | 11 | 4 |
| [M5-13](M5-13.md) | Accounting invariants and failure/concurrency proof | 12 | 4 |
| [M5-14](M5-14.md) | Offline NVDA accounting result and final package | 13 | 3 |
| | **Total, planning estimate** | | **55** |

The roadmap's 35-45 h estimate is provisional. This draft adds explicit temporal correction cascades, independent broker accounting, upgrade compatibility and a disposable restore drill; the difference is visible rather than compressed into unrealistic task estimates. Eight tasks exceed three hours. The owner approved that exception with D43 on 2026-10-21. Planning on the accepted M4 head is not permission to bypass the unmerged dependency for implementation.

## Shared contracts

### C1. Ownership, types and storage

`ledger/contracts.py`: `Unit(kind, code)`, `LedgerEntry`, `JournalTransaction`, `BookBatch`, `SourceRef`, `SourceBundle`, `OpeningLot`, `LotMatch`, `BalanceQuery`, `LedgerBalances`, typed `AccountingUnavailable` and `SourceConflict`. All amounts finite Decimal; datetimes aware UTC; date inputs reject datetime; IDs include investment account and source identity. The following fields and C2 signatures are the public contract for this specification review. M5-00 implements their tests first; it does not introduce another approval gate between authorized milestone tasks. An incompatible change triggers the existing stop rule.

| Record | Required content |
|---|---|
| SourceRef | kind, full source identity/revision, stored record ID, canonical content hash, effective/available/delivered times |
| SourceBundle | account, processing cutoff, ordered validated source records/references, provider, completeness evidence/coverage reference, omissions, model version |
| JournalTransaction | transaction ID, investment account, effective/posted times, source references, ordered entries, optional reversed transaction ID |
| LedgerEntry | frozen LedgerEntry fields plus investment account, economic effective time and source references; chart account is separate from investment account |
| BookBatch | deterministic ID, account, immutable parent ID, contiguous aggregate version, policy version, source-set hash, source receipts, transactions, lot matches, posting time |
| OpeningLot | declaration ID, existing starting-state ID, account, instrument, quantity, total declared cost/unit, effective/observed times, operator and reason |
| LotMatch | match ID, book ID, acquisition source/lot, disposal source/fill, consumed quantity, exact allocated cost/unit, policy version |
| BalanceQuery | account, effective time E, knowledge cutoff K, pinned book ID |
| LedgerBalances | query identity, cash/currency, instrument quantities/costs, receivables, gross realized P&L, dividend income, fees, source references and completeness/reasons |

`AccountingUnavailable` carries account, cutoff and missing/unsupported source references with reasons. It is never a zero-valued LedgerBalances. `SourceConflict` identifies the immutable source identity whose supplied content differs, without printing credentials.

`reconciliation/contracts.py`: immutable neutral `BrokerSnapshot`, `BrokerPosition`, `BrokerOpenOrder`, `ReconciliationResult`, `Difference` and `IncidentTransition`. Core may import these records and read their stores. They contain no broker capability or credential reader. Every DTO names investment account, broker/account identity, source, units, cutoffs and completeness. Missing fields are explicitly unavailable, not zero or an assumed empty portfolio.

New PostgreSQL scripts only: `0016_ledger.sql` (01), `0017_broker_snapshots.sql` (07), `0018_reconciliation.sql` (09). Do not edit 0001-0015 or reset retained databases. New accounting stores require PostgreSQL; SQLite remains available for existing M1/M2 historical files, never a second authoritative ledger. Avoid changing the canonical serializer or old registered records.

### C2. Deterministic posting API

Proposed public API, to be checked for implementability in review:

```python
LedgerStore(db, *, audit, outbox, clock, command_clock)
LedgerStore.append_batch(batch: BookBatch) -> BookBatch
LedgerStore.read_head(account_id: str, *, known_at: datetime) -> BookBatch
LedgerStore.history(account_id: str, *, known_at: datetime) -> tuple[BookBatch, ...]
LedgerStore.activate(account_id: str, *, opening_lots: tuple[OpeningLot, ...],
                     source_bundle: SourceBundle, by: Actor, reason: str) -> BookBatch
sync_account(account_id: str, *, through: datetime, sources: SourceBundle,
             ledger: LedgerStore) -> SyncReport
balances(account_id: str, *, effective_at: datetime, known_at: datetime, book_id: str,
         ledger: LedgerStore) -> LedgerBalances | AccountingUnavailable
```

All writes take the existing account-control lock before selecting sources, then the ledger lock in one fixed order. M4's conversion already takes that lock, but direct OrderStore fill/state writers do not; M5-10 explicitly adds locking to reservation/economic mutations, rereading after the lock. Finite input bundles identify actual stored fills and delivered action revisions; caller-created records without matching stored content are refused. A new source receipt and its entries/lot matches/audit/outbox/processed mark commit together. Duplicate source events do not post twice. A failed batch contributes nothing and has no processed mark. The original event envelope and event-ID policy remain unchanged; one completed book batch increments its account-book aggregate by one and publishes one event.

The new consumer is named `accounting-ledger`, separate from the existing `order-log` consumer. M5-10 adds an opt-in serialization flag to the existing Consumer: within each event's own transaction, take `consumer|accounting-ledger` **before** checking the processed mark and before calling the handler. Concurrent instances recheck under that lock, avoiding both duplicate effects and a spurious unique-violation failure. The default for existing consumers remains unchanged. The accounting dispatcher enters outside an existing account-control transaction; lock order is consumer -> account-control -> ledger. Direct sync/activation never calls the dispatcher while holding the account lock. Preserve each event's own rollback/failure handling; wrapping a whole run in an outer transaction would poison all events after one failure.

Economic time and knowledge time remain separate as ADR-010 specifies. Never include a source merely because it exists somewhere in the store, or because its future ex-date is known. Late corrections require the full dependent lot/dividend closure; not just a delta to the newest holding. Snapshot and report readers pin a book head and cutoffs rather than combining changing rows from different reads. The selected `book_id` restricts entries to that head's ancestor batches, and its posting time must be at or before K. This also makes two different arrivals stamped at the same replay time reconstructable: the old saved head never sees the new batch. A newly corrected transaction reverses the active replacement, not an already reversed ancestor.

The injected processing `clock` supplies replay/live book knowledge time. The separately injected live `command_clock` supplies operator authorization and audit attribution; its value does not enter economic IDs. Pass real command time to the existing AccountRegistry authorization API. A RESEARCH account can activate at its declared historical business time today without reviving an operator deactivated today. PAPER rejects supplied historical business time. No module reads the system clock directly.

Activation and every Admin write enforce authorization inside the store transaction against the stored operator state; caller-supplied `Actor.role` is not authority. Core processing posts actual validated fills. If a fill produces known negative cash it is still recorded with a breach/readiness failure; a trading prohibition cannot rewrite reported execution facts. Missing lot basis instead marks the attempted new book incomplete with the accepted-fill reference and leaves the previous book explicitly historical, never current by fallback.

Activation and incident Admin commands take their account lock, then any ledger/incident locks, then `operator|<actor_id>` before authorization. Obtain live command time and reread the operator after this lock; deactivation uses that same operator lock. Thus a deactivation that wins first prevents the command, while a command that wins first completes under the earlier authorization. Merely checking the role before blocking on a lock is insufficient.

### C3. Journal, source and valuation rules

Apply ADR-010's worked buy/sell example in contracts, integration tests and reports. Split 10 old shares then buy 10 after a 10-for-1 action gives 110, with original lot cost conserved. Entitlements use prior-close ownership. No payment is assumed. A fill on a CANCELLED/EXPIRED order still posts if OMS accepted it; REJECTED/GATE_REJECTED or conflicting/refused fills do not become cash movements. Partial fills post individually; order cancellation itself posts no trade.

Portfolio cash/holdings come from the journal after activation; reservations still come from OMS state as of the cutoff. Preserve UNKNOWN and crossing-action safeguards, raw mark compatibility, drawdown clear epochs and pending-buy exposure. No automatic provisional fallback. Missing cost affects accounting validity; missing raw mark makes valuation/P&L unavailable while the known quantity and cost may still be displayed separately, with their own status.

Net cumulative P&L = gross realized P&L + unrealized P&L + dividend income - fees. Also reconcile it to equity minus opening capital (no later contributions in this scope). Daily P&L is the difference between two complete comparable cutoffs, not daily cash flow. Show the formula, book IDs, mark/action revisions and absent endpoints. Never call this tax profit or broker-settled cash.

### C4. Broker snapshot and comparison protocol

The worker calls the broker snapshot method through the existing bounded-call/reconnect path, outside any DB transaction, then atomically persists the immutable result and an event. Core reads only that result. The simulator's own account starts with separately seeded cash/holdings matching the declared setup. It derives cash and shares from its own accepted execution records and action observations, not from OMS fills or LedgerStore, even when those disagree.

Initialize the simulator through an immutable, audited RESEARCH-only setup command in the public database, referencing the declared starting state; the worker applies it to its private simulator account exactly once. Core/Admin never writes the simulator's private schema or calls a seed/snapshot broker method. The worker captures snapshots for activated configured accounts **even with zero orders**. Startup order is setup command -> worker seed/capture -> Core ledger synchronization/reconciliation -> first proposal. Otherwise the first proposal would wait for a snapshot that could only be produced after an order. Real broker accounts cannot be seeded through this command.

Snapshots include account scope, `taken_at` (broker economic cutoff), `received_at`/recorded time, cash basis, position/order coverage, raw content hash, relevant broker execution IDs and a completeness marker with a reason. An unscoped legacy simulator cannot supply an account snapshot. Existing submit/cancel/message semantics, deadlines, stalled-call protection and the accepted R5 connection-loss propagation remain unchanged. Missing snapshot capability is unavailable, not an empty account.

Core first synchronizes the journal through the snapshot's economic time using sources actually known by its selected knowledge cutoff, then compares at that same pair of cutoffs. Label any known delivery/posting gap INCOMPLETE, retaining the missing references; it cannot pass. A fully comparable difference is MISMATCH with an incident and exact expected/reported values. A broker execution absent from the supposedly complete internal prefix is itself a missing-fill discrepancy, never silently ignored. A stale snapshot cannot establish present-time MATCH.

Results: MATCH, MISMATCH or INCOMPLETE. No comparison sets an order state, cancels an order, changes capital, posts a repair, clears an incident or enables trading. Status uses immutable evidence from both sides. A later MATCH may support Admin resolution of an earlier incident; it does not rewrite the earlier comparison.

Open-order normalization is explicit: simulator OPEN/CANCEL_RECEIVED are resting orders; OMS SUBMITTED/PARTIALLY_FILLED must match resting remaining quantities; CANCEL_PENDING is compatible with either resting broker status while its durable cancel is pending. NEW has no submitted broker order. SUBMITTING/UNKNOWN is unresolved and cannot establish a complete MATCH. Terminal orders are excluded from the open-order set, while accepted late fills still enter cash/holdings. Never compare raw OMS state strings to broker state strings or add a new G3 transition to make them equal.

**RESEARCH readiness handshake (v0.2):** keep the ReplayClock fixed while the worker ingests messages/processes cancels/captures account evidence, Core synchronizes and compares it, then the worker gates ready NEW orders. Repeated unchanged capture at the same cutoff reuses the snapshot ID and emits no extra event. An unchanged source set reuses the book head. A readiness token pins account, processing cutoff, book ID, broker snapshot and the normalized reconcilable OMS content. A NEW order is unsubmitted and does not by itself change that normalized broker-open-order content; reservations still independently participate in the real gate/fingerprint checks.

The running worker defers NEW orders while merely waiting for Core to compare a just-captured snapshot; it does not run a knowingly premature gate just to turn the order into GATE_REJECTED. This adds no state edge and never skips the gate on an actual submission. A genuine mismatch/incomplete accounting remains blocked with its reason, expiry is still checked before any later submission, and cancels/recovery continue during the wait. The offline harness drains a finite pinned source prefix at that fixed time within an explicit work budget; no-progress/exhausted budget is reported INCOMPLETE. It never advances time or creates a fresh identical snapshot/book just to invalidate the token. Live PAPER remains blocked; M7 must separately review live freshness policy.

### C5. Incidents and safety

Incident states OPEN -> ACKNOWLEDGED -> RESOLVED, or OPEN -> RESOLVED with matching evidence. Append transitions with compare-and-set sequence, actor, reason, live command time and separate replay business time. Repeated observation of identical evidence is idempotent; a new discrepancy after resolution creates a new incident. Cross-account evidence cannot resolve anything. Concurrent acknowledge/resolve yields one successor, not a lost update.

Creation, acknowledgement and resolution take the same account-control lock used by gate/readiness checks, then the incident lock. Re-read current book/snapshot evidence under it before accepting a resolution; a concurrently created newer mismatch cannot be cleared using an older MATCH. Operator commands also follow C2's operator-lock protocol. No path acquires these locks in reverse order.

The active operator's role is checked at real command time, never at a historical replay date. Admin-only writes follow proposed D38. Acknowledgement leaves D39's block in place. Resolution needs a later complete comparable MATCH against the current affected book/snapshot; corrected book data does not erase the original discrepancy. No command edits the journal as a side effect of acknowledging/resolving. Cancels always continue.

### C6. Integration and compatibility

No M5 write path is installed before its dependencies exist. Modules introduced in 00-09 are independently testable, then 10 wires the real Core, worker and offline harness. M5-06 supplies a typed portfolio adapter exercised directly; 10 switches the live factories after activation. The test suite must pass at each intermediate commit.

Old M2 evaluation, M3 snapshot and M4 snapshot/intent/order records reopen under their original IDs. Historical reports keep historical labels and absent fields, not new zero values. New ledger snapshots use the already reserved LEDGER source. Use a public injection/projection port; do not deepen the existing private replay-reader dependency.

### C7. Backup and restore

Use `pg_dump` custom format, credentials through private libpq environment/service settings, never argv or logs. Record tool/schema versions, dump hash, start/end interval and completion. A DB dump and market directory are not falsely described as one atomic snapshot. After the dump completes, inventory closed immutable market files and copy a verified superset covering every reference in the restored DB; manifests record hashes and safe relative paths. A partial copy or missing reference means FAILED/incomplete, never a successful backup.

Exclude `.env`, keys, worker secrets, kill-switch flag/journal and logs from generic filesystem copying. Database content may still contain confidential research/audit data; backups stay local and uncommitted. Initial retention deletes nothing. Restore verification uses an allowlisted disposable local database and isolated market directory, checks journal/source/audit counts and hashes, and never touches an owner database. Restored execution starts disabled; a restored DB is not approval to resume trading. See PostgreSQL's [pg_dump documentation](https://www.postgresql.org/docs/17/app-pgdump.html) for its single-database consistency guarantee; role/global configuration requires a separate documented setup, not an implied full-machine restore.

### C8. Checks and completion

Use accepted AGENTS/CLAUDE section 6: task and affected-module tests plus Ruff per task; observed red/green for fixes; both full shell suites and fresh base/engine installations once per package. The older task-index table has a separate checked S1 patch and must not override the owner's newer rule. PostgreSQL tests run with disposable local databases and no missing-DSN skips. Do not stop the owner's server or weaken test timeouts/race counts to finish sooner.

M5 is done only after an independently reviewed milestone is merged. Proof includes SQL bypass attempts, per-unit/lot conservation, historical cutoffs and source corrections, real consumer crash rollback, two-instance races, independent seeded broker discrepancies, compatibility, and a restore drill. The offline NVDA result uses saved verified daily fixtures only and remains `SIMULATED | RESEARCH | NOT PROMOTED`; M1 hourly and PAPER gates are unchanged. Actual daily backup scheduling is explicitly pending until the owner approves/configures it; do not claim operational daily protection before then.

## Explicit exclusions

M6 research adapter, M7 live feed/paper broker, dashboard/API/login, tax statements, multicurrency/FX, settlement financing, new order edges, strategy tuning, kill-switch acknowledgement design, broker cursor optimization, and midnight-test fixes. The deferred M2 improvement reminder remains for after the milestone programme.

## Owner acceptance record

Owner approval, 2026-10-21: answer `1` to the consolidated `approval-package.md` authorization question. This accepts ADR-010 v0.2, M5 specifications and D35-D44; authorizes the local M4 fast-forward, spec commit and all 15 M5 tasks with local task/fix commits, 55 h planning estimate and eight tasks over 3 h. This is owner acceptance, not independent AI acceptance. M5 merge, push, keys, market downloads, real backup schedule installation, owner database restore/reset and M6 are excluded.

**M5-00 — committed (checked), not done:** Immutable unit-separated ledger/source/book and neutral broker/reconciliation contracts; deterministic manifests, full reversal construction, audit registrations, two authorized frozen-architecture ADR cross-references. No serializer rewrite. Observed red: run_check.py bash m5-00-red tests/engine/test_ledger_contracts.py tests/engine/test_reconciliation_contracts.py: two expected missing-module collection errors. Final command: run_check.py bash m5-00-final tests/engine/test_ledger_contracts.py tests/engine/test_reconciliation_contracts.py tests/engine/test_layering.py tests/engine/test_lineage.py tests/engine/test_audit.py: 86 passed in 31.21s. Root venv python -m ruff check .: passed. An earlier affected-check command named nonexistent test_audit_store.py; no tests ran; corrected to test_audit.py. No new existing-test failure.

**M5-01 — committed (checked), not done:** Additive schema 0016; per-unit deferred balance, sealed entry manifests, full one-time reversals, immutable journals/receipts/activation; account-then-ledger CAS locking, atomic audit/outbox and explicit current-Admin activation. Upgraded only disposable test databases; retained schema files untouched. Observed red: run_check.py bash m5-01-red tests/engine/test_ledger_store.py tests/engine/test_ledger_upgrade.py: missing store module. Activation test separately failed on missing activate. TDD found OLD trigger alias collision, corrected to prior; SQL-bypass test first hit AuditEvent Python validation, rewritten to direct SQL so the database guard itself is exercised. Final exact command: root venv python run_check.py bash m5-01-final tests/engine/test_ledger_store.py tests/engine/test_ledger_upgrade.py tests/engine/test_postgres_schema.py tests/engine/test_ledger_contracts.py tests/engine/test_reconciliation_contracts.py tests/engine/test_audit.py tests/engine/test_layering.py: 112 passed in 100.20s, no skips. python -m ruff check . passed. Fresh installed SQL discovery will also be checked at package smoke. No existing-test failures.

**M5-00 — committed (checked), not done:** Self-review follow-up: remove redundant LotMatch.book_id from book identity material to avoid a circular hash; retain economic match fields and immutable bound reference. Deep-freeze SourceBundle input records through the unchanged canonical codec. No persisted lot-bearing books existed; empty-match M5 IDs and all legacy IDs unchanged. Observed red: run_check.py bash m5-00-id-red tests/engine/test_ledger_contracts.py::test_lot_book_back_reference_has_no_circular_identity_and_records_are_frozen: 1 failed on circular ID. Green: run_check.py bash m5-00-id-green tests/engine/test_ledger_contracts.py tests/engine/test_reconciliation_contracts.py tests/engine/test_ledger_store.py tests/engine/test_ledger_upgrade.py tests/engine/test_lineage.py: 76 passed in 44.20s, no skips. Root venv python -m ruff check . passed.

**M5-01 — committed (checked), not done:** Self-review follow-up: enforce finalized lot matches reference their containing book, on append and read; complementary guard to the M5-00 non-circular economic identity fix. No migration edited. Observed red: run_check.py bash m5-01-lot-ref-red tests/engine/test_ledger_store.py::test_lot_match_must_point_to_its_containing_book: 1 failed, bad reference was accepted. Green: run_check.py bash m5-01-lot-ref-green tests/engine/test_ledger_store.py tests/engine/test_ledger_contracts.py: 45 passed in 34.38s. Root venv python -m ruff check . passed.
