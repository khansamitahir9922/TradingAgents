# M2 specification pack: draft for independent review

Prepared 2026-10-13 on `docs/m2-specs`. Claude drafted M2-00 through M2-07; Codex revised those contracts and drafted M2-08 through M2-12 while Claude was unavailable. **No M2 code has been written or authorized.**

**Accepted for implementation (owner, 2026-10-14)** as one milestone package: the owner approved the whole M2 build on `m2/milestone`, with automatic local task commits and one combined Codex review at the end. Codex's package review (`docs/reviews/codex-m2-package-review-2026-10-14.md`) is applied: the prerequisite amendment below, branch-based integration, the mechanical M2-11 split, stop rules for blocking gaps, and the completed-bar cutoff in M2-00/M2-03.

**Prerequisite (owner's scheduling amendment, 2026-10-14: M2 starts on M1's **merged daily scope** (`main` `53c51bd`); M1's hourly parts stay unfinished and M1 completion criteria are unchanged. No M2 code reads H1 data.)** Law 9 still applies to each strategy's declared sources, which are yfinance D1 plus SPLIT actions.

**Provisional research configuration (owner, 2026-10-14).** Research assumptions, versioned and disclosed; they are not evidence of profitability, do not enable trading and can change (changing them reruns the evaluation):

| Setting | Value |
|---|---|
| OPEN-06 | Option A: two daily NVDA rule strategies (M2-05) |
| OPEN-08 `valid_until` | Close of the next session after T; final choice still due by M3 |
| Outcome horizon and target | 5 sessions, split-adjusted price return; total return reported separately |
| Costs | 5 bps per side; stress run at 10 bps |
| Walk-forward windows | 24 months train, 6 months test, 6-month step |
| Promotion thresholds | **Not accepted**: the report shows `PROMOTION NOT ASSESSED` |


| Proposed batch | Task specs | Dependency before implementation |
|---|---|---|
| M2-A: data and features | [00](M2-00.md) split-adjusted view, [01](M2-01.md) definitions, [02](M2-02.md) indicators, [03](M2-03.md) snapshot | M1 daily scope merged (`53c51bd`); specs/configuration accepted 2026-10-14 |
| M2-B: views and lineage | [04](M2-04.md) interface, [05](M2-05.md) strategies, [06](M2-06.md) policy, [07](M2-07.md) pipeline/lineage | M2-A merged, or earlier committed/checked tasks in an explicitly approved combined batch |
| M2-C: outcomes and evaluation | [08](M2-08.md) returns/labels, [09](M2-09.md) metrics, [10](M2-10.md) research simulation | M2-A/B; OPEN-09 experiment assumptions accepted |
| M2-D: folds and report | [11](M2-11.md) split into [11a](M2-11a.md) folds/leakage guards and [11b](M2-11b.md) run records; [12](M2-12.md) HTML report | M2-C |

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

**Implementation order (14 tasks, one commit each):** M2-00, 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11a, 11b, 12. The groups above are planning labels only; the whole milestone is one package. Copilot reviewed the drafts independently (R-07); Codex reviews the implemented milestone.
