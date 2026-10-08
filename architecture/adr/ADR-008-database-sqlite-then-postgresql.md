# ADR-008: Database: SQLite in M1–M2, PostgreSQL from M3

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Laws 10, 11 · Parts A, E (Operational Database, Market-Data Store), K |
| **Milestone** | M1 (SQLite) · M3 (move to PostgreSQL) |

## Context
The Operational Database holds the authoritative stores, the outbox, job tables, commands and broker snapshots (Part E). From M4, two processes write the order store concurrently with compare-and-set (ADR-004), and every process relies on transactional outbox writes (ADR-005).

Early milestones (M1 market foundation, M2 quant and evaluation) are mostly single-process and benefit from zero setup. Later milestones need real concurrency and transaction behaviour, and that behaviour must be **tested on the database that will actually run**.

The drafts differed: v0.1 proposed PostgreSQL with SQLite in development; the v0.95 review proposed SQLite only for M1–M2.

## Decision
1. **SQLite for M1–M2.**
2. **PostgreSQL from M3**, before versioned intents, audit, the order store and multi-process writes arrive. From then on, development and tests use PostgreSQL, not SQLite.
3. Market data is kept separately in the **Market-Data Store**: Parquet files queried with DuckDB (Part E). This ADR covers the Operational Database only.

## Alternatives considered
**Documented in the architecture lineage:**
- **PostgreSQL as the target, with SQLite in development** (Claude v0.1; Part A, "Database"). Replaced: SQLite's locking and transaction behaviour differs from PostgreSQL's, so concurrency tests could pass in development and fail later.
- **SQLite only for M1–M2** (v0.95 review). Adopted, with PostgreSQL from M3.

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **PostgreSQL in every environment from M1.** Setup cost before there's any concurrency to need it.
- **A document or key-value store.** The domain needs multi-row transactions (state plus outbox) and relational integrity.

## Consequences
- **Positive.** A fast start in M1–M2. From M3, concurrency, transactions and compare-and-set are tested for real before M4 depends on them.
- **Negative.** A migration at M3. Schemas and queries written in M1–M2 should avoid SQLite-only behaviour so the move is mechanical. Developers need a local PostgreSQL from M3.
- **Follow-ups.** M3 task specs choose the migration approach and the local PostgreSQL setup. Backups start from M5 (Part M).

## How we check it
- From M3: the full suite, including the concurrency tests (stale compare-and-set write fails; concurrent cancel request and fill), runs against PostgreSQL.
- Fault injection: DB restart.

## References
Architecture Parts A, E, K, M. ADR-004, ADR-005.
