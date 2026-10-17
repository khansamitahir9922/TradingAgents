# M4 specification package, v0.3 (Claude, 2026-10-18)

This package is for Codex's review and the owner's decisions. **v0.3** answers Codex's re-review of v0.2 (`docs/reviews/codex-m4-draft-rereview-v02-2026-10-18.md`; R1–R4 plus three small corrections). The owner's instruction was:
> "Address R1–R4 and the three small corrections in that review together, in one uninterrupted documentation pass. Preserve the resolved fixes. Return one revised package, still uncommitted, with no M4 code, merge or push."

## v0.3 corrections

| Finding | Where | What changed |
|---|---|---|
| **R1** a cancel needing a price not yet known | M4-06 rules 5–7 and tests; M4-03 `CancelResult`; M4-07 rule 3 | Receipt is separate from outcome. A cancel before the open is conclusive, with no price needed. After the open it is **PENDING**, with the first receipt time persisted (retries and restarts keep it), and the request stays SENT. The session is decided once, at its **decision moment**: the earliest CLOSED-bar availability, on the revision known then, independent of polling. An open fill stands; an intraday-only fill loses to the cancel. A missing bar resolves at the cutoff (EXPIRED, or CANCELLED if a cancel was pending), with no fill. The two-future-bars case is a test: the same response before delivery, distinct outcomes after. |
| **R2** a journal outcome after publication; recovery before overwrite | M4-04 rules 4, 5, 7 and tests; D28 | The flag replace is the **publication point**. Under the lock, outstanding intents are resolved against the current flag **before** any new sequence is published: APPLIED (recovered), NOT_APPLIED, UNRESOLVED (flag unreadable, never invented), or recovered "intent not journalled". The failure table, per step, for halt and resume: a resume fails only before publication; after publication it reports "applied; recording incomplete". `sync-audit` takes the same lock and resolution. A test covers the 7-then-8 overwrite case. |
| **R3** action ordering and unresolved orders | M4-09 rules 1–3 and tests; M4-13 rule 4; D34 | A chronological projection: the start, fills at `executed_at` and actions at their effective time, filtered by what was known at `at`, with the provider kept and revision references kept. A split applies at the ex-date open (10 + split + 10 = **110**). Dividend entitlement is fixed at the previous close. Same-time order is defined. A delayed fill is placed at its execution position from its `recorded_at`. An unresolved order crossing an action makes the projection **Unavailable** for proposals, with its terms and reservation kept in original units. Unsupported actions or currencies are Unavailable. The "can't occur" claim is removed. |
| **R4** the recipe identity | M4-10 rule 1 and tests | The recipe comes from the runs' `lineage_refs`, through `LineageStore.get`: `policy_version`, `strategy_versions`, `feature_versions`, `config` and `health_thresholds`, normalized and hashed (`rcp-`). Session fields are excluded. Missing, empty or mixed lineage, or an instrument mismatch, refuses. The evidence context (record id, costs, walk-forward settings, versions) is pinned separately. A view matches on recipe identity, source and instrument. M2 records and ids are untouched. |
| Small 1 | M4-00 rule 10 | `as_of` uses writes whose recorded time is ≤ `at`; boundary test at exactly `at`. |
| Small 2 | M4-05 tests | Each input's expected value is stated (`reference_current` True; the flags False; versions equal; times in window), with Missing failing independently. |
| Small 3 | M4-00 rules 7, 9; M4-07 rule 2 | An exhaustive event table: one event per version. A fill changing the state is one `order.fill_recorded`; a fill before the ack is two versions and two events. Anomalies create no version and publish no event (audit only). |

**Preserved:** every B1–B9 resolution Codex confirmed in its disposition table. **Estimate:** ≈ 73 h (M4-06 9 h, M4-09 7 h), still twelve tasks above 3 h. **D19–D34 remain proposals.**

## v0.2 (earlier) record

v0.2 answered Codex's preliminary review of the uncommitted v0.1 draft (`docs/reviews/codex-m4-draft-review-2026-10-18.md`, in the root checkout; verdict: changes requested, B1–B9).

The owner's instruction was:
> "Address B1–B9 from Codex's review in one uninterrupted documentation pass. Return one revised package, keeping D19–D33 proposed. No per-finding approval pauses, M4 code, merge or push. Committing still needs my approval."

Documents only. No M4 code exists or is authorized. Nothing is committed, merged or pushed.

## What is in it

- **[M4 pack v0.2](../tasks/M4-README.md):** 14 task specs, M4-00 – M4-13, ≈ 71 h (v0.1: 64 h). Twelve tasks are above 3 h.
- **Owner decisions D19–D34, all still proposals.** D34 (splits and dividends in the projection) is new. D25 (fill timing), D27 (Admin-only control) and D28 (lock and journal) are refined.
- **M3's labels**, made current in v0.1 and accepted by Codex as editorial. v0.2 also turns M3-README's stale "Current" line into history.

## Corrections

| Finding | Where | What changed |
|---|---|---|
| **B1** fill accounting against the G3 edges | M4-00 rules 1, 4; M4-07 rule 2 | A fill updates the totals by compare-and-set (+1 version, one event), and the state changes only along a G3 edge. PARTIALLY_FILLED with a further partial fill: an accounting update only, with no self-edge. A delayed fill on CANCELLED or EXPIRED: accounting only, the state stays final, with an anomaly if it completes the order. A fill on REJECTED or GATE_REJECTED: refused and stored as an anomaly, never as a fill. A message needing several edges writes each edge as its own version. The full message × state table is in M4-07. |
| **B2** cancel recovery | M4-00 rule 6; M4-07 rule 3; M4-08 rule 1 and tests | Cancel requests are their own aggregate, with durable progress: REQUESTED, SENDING (attempt n), SENT, CLOSED with an outcome. An order already CANCEL_PENDING is **resent** (the broker treats the repeat idempotently). Requests close only when the order is final. Crash points before the call and after the broker accepted are tested, both with trading disabled. |
| **B3** event versions, and broker calls outside transactions | M4-00 rule 7; M4-01 rules 2, 3, 6; M4-07 rule 1 | One event per +1 version, with the table in M4-00. Gate decisions and anomalies attach to a version; cancel requests version separately. Consumers do database work only. **The worker takes its submission work from the order store's NEW orders, not from an event handler.** Submission is gate transaction, commit, `submit` outside any transaction, then outcome transaction. The publisher's crash claim is corrected: insert and mark roll back together, and the real duplicate boundary is a consumer crash before commit. |
| **B4** gate inputs and concurrency | M4-05 (rewritten); M4-00 `Order`; M4-02 rule 1 | Typed `GateInputs` with `Missing` kept apart from False, plus `account_kind`. The order pins `intent_content_id` and the proposal's `position_fingerprint`: an **economic** fingerprint of cash, shares and reservations, with no valuation or time, excluding this order on both sides. The lock protocol: the account-control lock, then the order row, **then** fresh reads. Every writer of a gate input takes the same lock. Interleaving tests cover limits, fills and new reservations. |
| **B5** causal daily fills | M4-06 rules 2–6; M4-05 rule 1.7; M4-13 rule 2 | Submitted, executed, delivered and recorded times are separate. Orders must be submitted before the open; the gate requires it and the broker refuses otherwise. Open fills are stamped at the open; intraday-only touches at the close, as "intraday, time unknown". A cancel after the open beats an intraday-only fill (an assumption, recorded). Missing bar: EXPIRED with "no market data" at the next open cutoff, and a later bar changes nothing. Each fill carries provenance (bar reference, model, slippage, fees), stored in the order store, so the reporter never reads the simulator's state. Replay phases: pre-open submission, then ingestion when the bar is known, then proposals sized on the post-fill portfolio. |
| **B6** exposure, actions, history and ids | M4-09 (rewritten); D30, D34; M4-00 rule 10 | Pending BUYs count against the position cap and gross exposure as well as cash, and unfilled SELLs never reduce holdings (the two-$10,000-buys test). Point in time: order states come from the history as of `at`. Splits and dividends are adjusted within M3's coverage (D34); a fraction or no coverage gives Unavailable. Fields added in M4 are omitted when absent, so M3 snapshot ids are unchanged, tested against a real row written by `main`. |
| **B7** kill-switch protocol and roles | M4-04 (rewritten); D27, D28 | An OS file lock serializes sequences without the database. The journal records INTENT, the flag replace, then APPLIED; recovery marks a change APPLIED (recovered) or NOT_APPLIED from the flag's own sequence. A truncated tail is ignored. A journal failure never blocks a halt (reported incomplete), and does refuse a resume. **Halt and resume are Admin-only** (PRD §4, UC-06). An unverifiable emergency halt is a fail-safe stop marked "identity unverified", not a granted right. |
| **B8** order, files and contracts | M4-README "Order"; M4-00 `OutboxWriter`; M4-02 `ConversionReport`, `fingerprint.py`; M4-03 ports, factory and double; M4-06, M4-09, M4-10 wiring | Each port is introduced by the task that first needs it. M4-03 has no production broker: the factory refuses until M4-06 wires the simulator for RESEARCH only, and tests use a test-only double. The layering exception is narrow: only `simulation/` may import four named execution modules, and never `execution.secrets`. Every intermediate task passes the full suite without future imports. |
| **B9** promotion evidence and formulas | M4-10 (rewritten); D21, D22 | An assessment pins one `EvaluationRecord` by `record_id`, and the decision recipe it evaluated; promotion attaches to that recipe, never to one component strategy. An incomplete record, or costs below the minimum, is refused. Formulas: Sharpe from the concatenated out-of-sample **daily** series (×√252, M2's convention); drawdown on chained equity against buy-and-hold chained the same way; trades in total across the folds; the share of positive folds. Assessments record the thresholds version and `as_of`. No outcome is predicted. D22's shadow band is left explicitly unresolved. |

**Clarifications applied:**
- conflicting duplicate fills are a refused anomaly (M4-00 rule 4);
- a dropped connection is kept apart from a server restart, which is not run on the owner's server (M4-08 rule 6, M4-12);
- graceful shutdown is kept apart from a hard kill on Windows (M4-03 rule 6);
- schema-version-constant references are removed, because the migrator discovers files;
- audit-registry changes are assigned to their tasks;
- the order-log label is ASCII, and the header carries provider, cutoff, timezone, versions and units (M4-13 rule 5, T-01 – T-04);
- D22's band is unresolved.

## Codex's answers, adopted

The answers on D23, D24, the trigger, the provisional portfolio and the estimate are recorded in the README and reflected in M4-00, M4-03, M4-09 and M4-13. D23's roadmap reading still needs the owner's explicit acceptance.

## Checks

- Documents only: `git diff --check` clean. The file references were re-checked against `4c56ac1`, including the evaluation fields M4-10 uses: `EvaluationRun.equity_curve`, `trades` and the `buy_and_hold` benchmark curve.
- No runtime tests were run (no code changed). CI not yet run.
