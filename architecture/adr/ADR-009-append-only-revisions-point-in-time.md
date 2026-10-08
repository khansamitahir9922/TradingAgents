# ADR-009: Append-only revisions and point-in-time views

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Laws 5, 7, 8, 17, 18 · Parts A, H (`Candle`, `CorporateAction`, `LedgerEntry`, `AuditEvent`, `LineageRecord`) |
| **Milestone** | M1 (market data, corporate actions) · M3+ (audit) · M5 (ledger) |

## Context
Real data vendors **correct** data after publishing it: bars are revised, corporate actions are added late. If corrections overwrite the original:
- a backtest silently uses information that wasn't available at the time (look-ahead bias);
- a past decision can't be explained with the data it actually saw (Law 18);
- financial and audit history loses its original record.

Draft v0.1 proposed immutable market data. That avoids overwrites but has no answer for legitimate corrections. The v0.95 review proposed append-only revisions.

## Decision
1. **History is never overwritten** (Law 8). Market data, corporate actions, ledger entries and audit events are **append-only**.
2. **A correction is a new revision.** `Candle` and `CorporateAction` carry a `revision`. Ledger errors are fixed with **reversing entries** (Law 17), never by editing or rebuilding.
3. **Point-in-time views** answer "what did we know at time T?", using each record's timing fields (`event_time`, `received_at`, `processed_at`, all UTC; Law 5) and its revision.
4. **Prices are stored raw (unadjusted).** Adjustments are derived from corporate actions when needed, so the original values are always available.
5. **Lineage references exact revisions.** A LineageRecord points to bars **with their revisions**, plus feature, strategy, model and policy versions, so a past decision can be shown with the exact values it used (design principles T-05).

## Alternatives considered
**Documented in the architecture lineage:**
- **Immutable market data without revisions** (Claude v0.1; Part A, "Market data"). Replaced by append-only revisions (v0.95 review), because real vendors correct data.

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **Overwrite on correction.** Look-ahead bias and lost history.
- **Store only adjusted prices.** Adjustment depends on later corporate actions, which would rewrite history.
- **Snapshot copies of the whole dataset per run.** Large, and they still don't say when each value became known.

## Consequences
- **Positive.** Honest backtests; explainable past decisions; a complete financial and audit record.
- **Negative.** More storage, and queries must choose "latest" or "as of T" explicitly. A missing choice is a bug. The current view and the historical view of the same quantity can differ, and the UI must label them (design principles T-05).
- **Follow-ups.** M1 task specs define the revision rules, the point-in-time query API and their tests. ADR-010 defines the securities ledger model before M5.

## How we check it
- Part J: ledger transactions balance and ledger rows are never updated.
- Replay tests: the same data and versions give the same views, intents and orders.
- Fault injection: a data revision mid-run; a point-in-time query before a revision returns the original value.

## References
Architecture Laws 5, 7, 8, 17, 18; Parts A, H. Design principles T-05, E-01 (reconciliation via reversing entries).
