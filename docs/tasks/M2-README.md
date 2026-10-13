# M2 specification pack: draft for independent review

Prepared 2026-10-13 on `docs/m2-specs`. Claude drafted M2-00 through M2-07; Codex revised those contracts and drafted M2-08 through M2-12 while Claude was unavailable. **No M2 code has been written or authorized.**

The owner selected OPEN-06 option A as the initial research scope: two daily NVDA rule strategies. Exact parameters/formulas remain draft contracts. OPEN-09 costs, fold windows, metrics and promotion thresholds remain provisional; OPEN-08 validity is also pending. Implementation waits for completed M1, accepted task specs and owner approval of the implementation batch. An accepted protocol or a partial daily import does not complete M1.

| Proposed batch | Task specs | Dependency before implementation |
|---|---|---|
| M2-A: data and features | [00](M2-00.md) split-adjusted view, [01](M2-01.md) definitions, [02](M2-02.md) indicators, [03](M2-03.md) snapshot | Completed M1; accepted specs/configuration |
| M2-B: views and lineage | [04](M2-04.md) interface, [05](M2-05.md) strategies, [06](M2-06.md) policy, [07](M2-07.md) pipeline/lineage | M2-A merged, or earlier committed/checked tasks in an explicitly approved combined batch |
| M2-C: outcomes and evaluation | [08](M2-08.md) returns/labels, [09](M2-09.md) metrics, [10](M2-10.md) research simulation | M2-A/B; OPEN-09 experiment assumptions accepted |
| M2-D: folds and report | [11](M2-11.md) walk-forward/run records, [12](M2-12.md) HTML report | M2-C |

These are reviewable planning groups, not automatic approvals. The owner can authorize a longer combined A/B or C/D run once its dependency graph and all contracts are accepted. Keep separate task commits/checks and one combined self-review/review package. Stop only for the existing stop rules; don't request another approval after each already-approved task. Combining whole milestones must not bypass incomplete dependencies, ADRs, acceptance checks or owner merge approval.

Contracts carried through the pack:

- Only indicators and return calculations use the PIT adjusted view. Execution references, simulated raw transactions, fills and accounting retain as-traded prices.
- Bar/action references contain full provider/instrument/timeframe-or-action identity, revision, import and availability labels. Later corrections cannot rewrite earlier predictions.
- A non-zero replay latency restricts features and health to revisions already delivered by the feed; `available_from <= generated_at` alone does not prevent a correction leaking through a second store read.
- An empty action query is not evidence of verified coverage. Coverage is explicit, versioned and labelled when based on backfill assumptions.
- Rule outputs are direction/strength. Numeric forecasts, learned features and calibrated probability belong to M9.
- Fit data and completed labels cannot cross fold cutoffs; required missing sources force ABSTAIN. A 20-session health check doesn't prove a 200-session indicator window is complete.
- Match baselines to direction or investment performance, and disclose counts/costs/abstentions. Promotion proposals never confer execution authority.
- M2 evaluation is SIMULATED research, not execution replay or ledger P&L. SQLite remains through M2; PostgreSQL begins in M3. No new process, broker connection or outbox is proposed.

Before implementation review, confirm OPEN-08/09 choices, action-coverage evidence, total-return convention and whether M2-11 needs splitting to stay within the 1-3 hour task rule. Another tool must independently review Codex's draft changes; a self-review is not independent approval.
