# ADR-010: Separate currency and security-quantity books

| | |
|---|---|
| Status | **Accepted v0.2 by the owner, 2026-10-21.** |
| Date / author | 2026-10-21 / Codex, backup implementer |
| Architecture | Laws 5, 7-11, 16-18, 20; Parts F, G1 steps 15-16, H, J, K and M |
| Milestone | M5 ledger and reconciliation |
| Starting code | Accepted M4 `5cd93637cfa0a820102196b2da31294c5f908b0c`; M4 merged into local main on 2026-10-21 |

## Context

Law 17 deliberately leaves the securities model open until this ADR. A cash debit cannot balance a credit measured in shares. M4's labelled provisional projection is not a journal, has no cost basis, and cannot become the authoritative ledger merely by changing its label. M5 must retain the order store as the execution record and make the ledger authoritative for internal cash, holdings and P&L (Part F).

This proposal fills that deferred design. It changes no process, broker authority, order transition, promotion gate or frozen diagram. Architecture v1.0 is unchanged in this draft. After acceptance, add a reviewed cross-reference under Part H's LedgerEntry and Part K's M5 row; do not silently edit the freeze before acceptance.

## Accepted decision

### 1. Two books, independently balanced

Every journal transaction belongs to one investment account. Every entry has the frozen fields `entry_id`, `transaction_id`, `account`, `debit`, `credit`, `unit`, `posted_at`, `reverses`, and adds explicit `investment_account_id`, economic `effective_at`, source references and book revision. `account` is a chart-of-accounts name, not the investment account ID. One side is positive and the other zero. Values are finite Decimal, never floats.

- Currency book: units such as `CURRENCY:USD`. Chart accounts: CASH, INVENTORY_COST:<instrument>, DIVIDEND_RECEIVABLE:<instrument>, CAPITAL, REALIZED_PNL:<instrument>, DIVIDEND_INCOME:<instrument>, FEES.
- Quantity book: `SECURITY:<instrument_id>`. Chart accounts: CUSTODY_SHARES and SHARE_OFFSET. The offset is a balancing quantity, not a second portfolio holding.
- For each transaction, investment account and unit, total debit equals total credit exactly. Currency and instrument units never cancel each other. At least two nonzero entries must exist in every represented unit.
- Holdings are net CUSTODY_SHARES only; cash is net CASH only. Neither broker buying power nor open-order reservations is ledger cash. USD, whole-share, long-only accounts remain the initial supported scope.
- Use a specified local Decimal context with precision 34, independent of the caller. Reject nonrepresentable operations instead of silently losing material digits. Source prices/fees retain their recorded precision. FIFO costs use the cumulative half-even allocation rule below at USD 0.0001, conserving exact total cost. This is an internal research accounting policy, not a tax-reporting claim.

### 2. Hand-worked postings

`Dr` / `Cr` below are entry directions, not signed mixed-unit amounts.

| Event | Currency entries (USD) | Quantity entries (shares of the named instrument) |
|---|---|---|
| Declare 100000 starting cash | Dr CASH 100000; Cr CAPITAL 100000 | None |
| Buy 10 at 100, fee 1 | Dr INVENTORY_COST 1000; Dr FEES 1; Cr CASH 1001 | Dr CUSTODY_SHARES 10; Cr SHARE_OFFSET 10 |
| Sell 4 at 120, fee 1, FIFO cost 400 | Dr CASH 479; Dr FEES 1; Cr INVENTORY_COST 400; Cr REALIZED_PNL 80 | Dr SHARE_OFFSET 4; Cr CUSTODY_SHARES 4 |
| 10-for-1 split of 10 shares | None; total cost is unchanged | Dr CUSTODY_SHARES 90; Cr SHARE_OFFSET 90 |
| Dividend entitlement of 3 | Dr DIVIDEND_RECEIVABLE 3; Cr DIVIDEND_INCOME 3 | None |

A loss uses the opposite REALIZED_PNL direction. Sales with fees exceeding proceeds may credit CASH rather than producing a negative debit; the validator still requires one nonnegative side per entry. If a validated accepted fill produces known negative cash, record that fact and a breach incident, and block new proposals; a no-borrowing trading policy cannot erase an execution. An insufficient/unestablished lot basis instead makes the new book incomplete, retaining the unposted accepted-fill reference and reason visibly. Never fabricate cost or funding, hide the fill, or display the older book as a current complete balance.

For the buy/sell example: cash 99478; six shares; remaining cost 600. With a known raw mark of 125: market value 750, unrealized P&L 150, gross realized P&L 80, fees 2, net P&L 228, equity 100228. These are synthetic acceptance numbers, never displayed as an NVDA result.

### 3. Opening state and fees

Opening cash is posted once from the existing declared starting state, with its ID retained. A nonzero starting position also needs an explicit declared lot cost. A market close is not evidence of acquisition cost. Without that declaration, activation for the account is refused, rather than inventing P&L or resetting its history.

FIFO matches acquisitions in `(executed_at, fill_id, lot_id)` order. An opening lot precedes later fills. Buy and sell fees are expensed when incurred; gross realized P&L excludes fees, and net P&L subtracts fees exactly once. No settlement calendar, margin, tax lot election, FX or tax reporting is introduced. CASH is labelled trade-date accounting cash; M7 must separately verify the broker's settled/available cash semantics.

**Cumulative allocation, fixed in v0.2:** for an allocation epoch with quantity Q and exact cost C, let d be total disposed quantity in that epoch and A the cost already allocated. Compute the cumulative target by rounding exact `C*d/Q` half-even at 0.0001, bounded between A and C. The current disposal receives `target - A`; full disposal sets target to exact C. Use exact rational/integer tie comparison, never binary float or an insufficient intermediate Decimal division. Amounts cannot become negative or exceed remaining cost. A split begins a new allocation epoch with the remaining quantity transformed and remaining exact cost unchanged; previous disposed cost remains historical evidence.

For C=0.0004 and Q=6, independently rounding each one-share allocation to 0.0001 would spend 0.0005 after five shares. The cumulative allocations are instead `[0.0001, 0, 0.0001, 0.0001, 0, 0.0001]`, summing to 0.0004. Grouping two or more disposals at the same final cumulative quantity has the same total allocation. This replaces v0.1's underspecified per-disposal rounding.

### 4. Corporate actions

Use the same provider and established coverage as the account's raw prices. Include only revisions actually available and delivered at the knowledge cutoff. An action becomes economically effective at the ex-session open, before fills at that open; never apply it merely because it was announced. Source identity includes provider, instrument, action type, ex-date and revision.

- A split changes quantity and FIFO lot quantities, preserving each lot's total cost. A fractional outcome is unsupported until evidenced cash-in-lieu handling exists; report unavailability and keep reservations.
- Dividend entitlement uses holdings at the prior session close. Recognize a receivable at ex-open; it contributes to equity but not spendable cash. The current source has no payment date. Never invent one or infer payment from a market-price move. Automatic dividend payment posting is out of scope for this first M5 package.
- Preserve M4's rule for an unresolved order across an action, and its refusal to value post-action shares with a pre-action raw close. Ledger introduction neither rewrites approved terms nor releases UNKNOWN reservations.

### 5. Time, deduplication and corrections

Queries specify **economic time E**, **knowledge cutoff K** and a pinned **book head ID**. An entry contributes only within that head's ancestor batches and if `effective_at <= E` and `posted_at <= K`. Two arrivals with the same timestamp remain distinguishable by book version; a saved earlier head cannot see a later batch. `posted_at` is when this book learned and committed it on the injected processing clock; audit attribution also retains the real command time for replay administration. No historical posting time is invented. Upstream revision availability and actual replay delivery both restrict source selection.

One account-control lock protects source selection, posting, FIFO allocations and book activation. Posting uses a stable finite source set and identifies its exact OMS/order/action revisions. Economic ordering is `(effective time, action-before-fill, stable source ID)`; late arrival is not silently treated as late execution.

Each immutable book batch has deterministic identity derived from account, policy version, parent book ID and selected source identities/content, excluding real command time. Identical retries return the saved batch; different content for one source identity is refused. Journal effects, source receipt, lot matches, audit, outbox and consumer processed mark commit together. Existing event IDs are reused; one new book aggregate version emits one event. No broker call occurs in a transaction.

A late fill or action revision may alter earlier lot consumption and later dividends. The implementation must calculate the affected dependency closure, append exact reversals of affected existing transactions and append corrected replacements, atomically. Reversals retain the original economic effective time and have the new observed posting time. Historical reads with an earlier K remain unchanged. Reverse each entry in its own unit; never update or delete it. An ordinary partial SELL is not reversed just because an order changes state.

This is a correction protocol, not permission to reset/rebuild the ledger from fills to hide a discrepancy. A broker mismatch creates an incident. It never authorizes journal adjustment. Until a dependency closure can be established from complete sources, retain the prior book and return INCOMPLETE/unavailable for the new cutoff. Never publish a partly corrected book.

### 6. Database enforcement and upgrades

Add new migrations after 0015. Existing scripts and stored M2/M3/M4 content IDs remain unchanged. Protect entries, transactions, batches, source receipts and lot matches against UPDATE, DELETE, TRUNCATE and conflict-update replacement. A deferred constraint trigger validates complete per-unit balance at commit, including empty headers and entries added to an already committed transaction. A transaction must be sealed with its content hash; a later append to it is refused. Header insertion without entries cannot commit.

Python validation improves errors but does not substitute for database enforcement. Ordinary application roles cannot disable triggers or use privileged bypasses; these protections are consistency checks, not protection against a database superuser. Snapshot and incident writes keep their separate process ownership.

The PostgreSQL documentation permits AFTER constraint-trigger checks to run at transaction end; evaluate cross-row invariants there, not in a row CHECK. See [CREATE TRIGGER](https://www.postgresql.org/docs/17/sql-createtrigger.html). An owner-approved retained database receives additive migrations and an explicit, audited ledger activation; never reset it. Legacy disposable-test-database assumptions from M3 do not authorize an M5 reset.

### 7. Cutover and authority

Existing records retain their IDs and decoded content. New accounts select LEDGER only after an explicit activation batch verifies starting data and all required source history. Portfolio snapshots, sizing, fingerprints and the worker's gate then use ledger balances plus the existing OMS reservations. Incomplete accounting must not fall back silently to M4's provisional book. Before activation, historical M4 records remain honestly labelled PROVISIONAL; after activation, new snapshots say LEDGER.

Core owns ledger writes. The Execution Worker fetches broker snapshots and persists them; Core never calls a broker or reads the private simulator schema. A neutral snapshot DTO/store can be shared without granting a broker capability. No new process or cross-process call is introduced.

## Alternatives considered

**Documented in the architecture lineage:** Part A records append-only versus double-entry, and defers the precise securities model. It does not record a historical choice of FIFO, average cost, fee treatment or separate quantity accounts.

**New analysis for this proposal (Codex, 2026-10-21):**
- Balance shares directly against dollars: rejected; units are incompatible.
- Monetary book plus an unbalanced quantity side table: workable, but this proposal instead makes quantity conservation independently testable in the journal.
- Moving-average cost: simpler for one aggregate holding; FIFO is proposed for explicit auditable disposal-to-acquisition links. Neither is a profitability improvement.
- Capitalize buy fees into cost: valid alternative accounting policy; immediate expensing is proposed for a transparent single fee total. Do not switch silently after acceptance.
- Rebuild/delete history after corrections: rejected by Law 17.
- Adopt an external accounting service: unnecessary process and operational scope for this milestone.

## Consequences

Reports can reconcile currency, quantity, lots and P&L independently, and explain changes. Correction cascades and activation are substantial implementation work. Data without opening cost, action coverage or comparable broker semantics remains unavailable. M5 neither promotes a strategy nor makes PAPER/live trading available.

## How we check it

Hand-worked examples; per-unit conservation; cross-account/unit rejection; all SQL mutation paths; late-fill/FIFO/dividend correction cascades at earlier and later K; deterministic IDs; retry and concurrency; consumer crash rollback; independent simulator snapshots with seeded cash, share and order mismatches; legacy-record compatibility; and fresh upgrade/backup/restore proofs. Exact tests and file scopes are in the proposed M5 task pack.

**Acceptance required:** independent review and owner's acceptance of this ADR and D35-D44 in M5-README. This draft authorizes no ledger code, merge, reset, backup schedule installation or API use.

## Acceptance record

Owner approval, 2026-10-21: answer `1` to the consolidated `approval-package.md` authorization question. This accepts ADR-010 v0.2, M5 specifications and D35-D44; authorizes the local M4 fast-forward, spec commit and all 15 M5 tasks with local task/fix commits, 55 h planning estimate and eight tasks over 3 h. This is owner acceptance, not independent AI acceptance. M5 merge, push, keys, market downloads, real backup schedule installation, owner database restore/reset and M6 are excluded.
