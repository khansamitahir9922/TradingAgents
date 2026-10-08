# ADR-003: Internal instrument IDs and effective-dated symbol mappings

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Law 8 · Parts A, F (Instruments), H (`Instrument`, `SymbolMapping`, `CorporateAction`) |
| **Milestone** | M1 |

## Context
Tickers aren't stable identifiers:
- companies change ticker symbols;
- companies delist or are taken private (e.g. TWTR, which already appears in the repository's tests as a ticker that can no longer be settled);
- different providers (yfinance, a broker, a data vendor) can use different symbols for the same instrument;
- a ticker can later be reused by a different company.

If the ticker is the key, history breaks when it changes, two instruments can collide, and point-in-time backtests can silently join the wrong data.

## Decision
1. Every instrument has an **internal, stable `instrument_id`** (e.g. `EQ_US_NVDA`) that never changes and is never reused.
2. An **Instrument** carries its lifecycle: `asset_class`, `currency`, `exchange`, `timezone`, `status: ACTIVE | DELISTED | SUSPENDED`, `active_from`, `active_to`.
3. Provider symbols live in **SymbolMapping** rows: `instrument_id`, `provider`, `symbol`, `valid_from`, `valid_to`. A lookup always uses a date: "which instrument did provider P mean by symbol S on date D?".
4. Symbol changes and delistings are also recorded as **CorporateActions** (`SYMBOL_CHANGE`, `DELISTING`) with their revisions (ADR-009).
5. All internal records (candles, features, views, intents, orders, fills, ledger entries) reference `instrument_id`, never a ticker.

## Alternatives considered
**Documented in the architecture lineage:**
- **Internal ID plus vendor symbols, without lifecycle or dated mappings** (Claude v0.1; Part A, "Instruments"). Replaced by lifecycle plus effective-dated mappings (v0.95 review), because tickers change and firms delist.

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **Ticker as the key**, with a rename table. Reuse and collisions still break history, and every join depends on dates being handled correctly.
- **One vendor's ID as the key** (e.g. a broker's asset ID). It ties the domain model to a vendor chosen later (ADR-011) and doesn't cover research providers.
- **An industry identifier (FIGI, ISIN, CUSIP) as the key.** Availability and licensing vary by provider. Such identifiers could be added later as extra mappings without changing this decision.

## Consequences
- **Positive.** History survives ticker changes and delistings. Point-in-time backtests resolve symbols as they were. Adding a provider means adding mappings, not migrating data.
- **Negative.** Every ingest and every user-facing lookup needs a mapping step and a date. Mappings must be maintained, and a missing mapping must surface as an error or DataHealth issue, never as a guess.
- **Follow-ups.** The M1 tasks define the ID format rules, the mapping lookup and its tests. Crypto (Part L) uses the same model with its own `asset_class`.

## How we check it
- Unit tests: lookups with dates before, inside and after a mapping's validity; a reused symbol resolves to different instruments on different dates; overlapping mappings for the same provider and symbol are rejected.
- Replay tests: a ticker change mid-history produces one continuous instrument series.

## References
Architecture Part A ("Instruments" row), Part F, Part H. PRD M1 scope.
