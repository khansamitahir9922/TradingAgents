# M3 specification package v0.3 (Claude, 2026-10-16)

## v0.3: Codex's re-review of `e7ec7e1` (R1–R3, S1–S4)

**Snapshot:** the third documentation commit on `docs/m3-specs`, the one adding this section. Review range: `e7ec7e1..docs/m3-specs`. Codex accepted the B1–B6 and S1–S7 changes in v0.2 (`docs/reviews/codex-m3-spec-rereview-e7ec7e1.md`, imported byte-for-byte, SHA-256 `8f082288…`). They're preserved unchanged.

| Finding | Change | Where | Acceptance tests added |
|---|---|---|---|
| **R1** callers outside M3-02's scope | M3-02 lists every existing constructor caller, re-inventoried at `e7ec7e1`: `cli.py` and seven test files (`test_cli`, `test_data_health`, `test_feature_snapshot`, `test_view_pipeline`, `test_yfinance_actions`, `test_yfinance_bars`, `test_walk_forward`). Changes are set-up only: wrap in `SqliteDatabase`, with no weakened assertions or monkeypatching. An unlisted caller triggers the stop rule. The CLI stays transitionally on wrapped SQLite until M3-03. The external M2 report script is updated outside the repository; nothing is promised in it. | M3-02 (allowed files, rule 7) | The whole pre-existing suite passes its baseline at the end of M3-02, before M3-03; a scan finds no raw connection passed to a store constructor |
| **R2** replay approvals vs today's operators | Authorization and attribution use the real command time (LiveClock); business checks and `approved_at` use the replay time. `AuditEvent.business_at`; `StoredIntent.approval_recorded_at`. The operator registry is live-time only and never backdated. Applies to every privileged research command. | M3-04 (contract, rule 5), M3-05 (rule 5), M3-06, M3-07, M3-09, M3-13 (contract, rule 2) | Through the CLI: today's operator approves a 2021 intent before its simulated deadline; a deactivated operator or a Viewer is refused even with an earlier `--at`; both times are displayed and audited; PAPER still refuses replay times |
| **R3** expiry crossing account timelines | `expire_due(account_id, at)`, `due_for_expiry(account_id, at)` and a separate `expire_paper_due(clock)` for PAPER on live time. `propose` validates the account and time mode before any mutation. CLI `intents expire --account A [--at T]` and `--paper`. | M3-09, M3-12 (rules 1, 10), M3-13 (rule 5) | Two RESEARCH accounts at different replay times in one database: B's proposals and expiry leave A untouched; A's expiry changes only A; a missing-account proposal expires nothing; PAPER refuses `--at`, also on expiry |
| **S1** neutralize vs reject | Chosen: neutralize ambient `PG*`, then allow the connection with a pinned loopback. Explicit unsupported parameters are still refused. The acceptance text now matches. | M3-00 | Split probe lists: refused explicit forms; ambient values neutralized and never reaching the recorder |
| **S2** replay identity vs provenance | Hashed identities exclude `recorded_at`, command time and OS user; those are stored beside the record and in audit. Replay determinism is stated for the same setup inputs. | M3-05 (rule 5), M3-06, M3-07, M3-12 (rule 9) | Two setups at different real times with the same inputs give identical ids, with their provenance kept |
| **S3** admission membership | `RiskInputs.admitted_buys_excluding_self` and `already_admitted`; `daily_buys` fails exactly when `not already_admitted and count >= limit`. A version above 1 is not evidence of admission. | M3-09 (`was_admitted`, `excluding`), M3-11 (input, rule 8), M3-12 (rule 4) | At the cap: an unadmitted reduced v2 is rejected; an already-admitted intent passes; neither takes a second slot |
| **S4** D18 wording | Partial selling is a sizing rule; the remainder isn't scheduled or guaranteed, later views decide again, and M3 has no fills. | README D18, M3-11 | — |

Numbers unchanged: 15 tasks, 52 h, seven 4 h tasks (planning exception), backward dependencies. D1–D18 remain proposals.

---

# v0.2 package (kept for history)

For Codex: a re-review of the revised M3 pack. The owner asked for the complete package revised in one pass against `docs/reviews/codex-m3-spec-review-1ce5250.md`: B1–B6 and the integration suggestions, one fixed snapshot, a correction table and the consolidated owner decisions, kept as proposals. **No M3 code, merge, push, keys or downloads.**

**Snapshot:** the second documentation commit on `docs/m3-specs`, the one that adds this version of this file. It follows `1ce5250` (v0.1), which was based on `main` `b7c5d2a`. Worktree `C:/Users/LOQ/TradingAgents-m3-specs`. Review range: `1ce5250..docs/m3-specs`.

## Correction table

| Finding | Change | Where | Acceptance tests added |
|---|---|---|---|
| **B1** first BUY has no raw price | New `RawReference`: exactly the view's decision-bar revision, read through a delivery-aware `Knowledge` port, raw Decimal, currency-checked; independent of holdings. `size` and `RiskInputs` take it; `held()` returns 0 for no position; the adjusted float is refused by type. | M3-07 (contracts, rule 1), M3-08 (rule 4, `size`), M3-11 (`RiskInputs`), M3-12 (rule 1) | First BUY from the empty default account (M3-07, M3-08, M3-12); held SELL; missing reference; wrong provider, instrument or revision; FORMING bar; currency mismatch; correction delivered after T; float or adjusted input refused |
| **B2** frozensets can't be encoded | Codec **not** extended. `PolicyRules.restricted` and `view_timeframes` become sorted, de-duplicated tuples. `audit/registry.py` lists the registering modules so a fresh process decodes; later tasks add to it. | M3-06 (contract), M3-04 (rule 3, files), registry line in M3-05/06/07/09/12 | Order and duplicate independence of ids and bytes; empty and non-empty lists through the store and audit; fresh-subprocess decode; the `57d4316` record and a lineage record keep their ids with all M3 types registered |
| **B3** rejected paths need decisions never run | `NotRun(stage, reason)` contract. PREREQUISITE_MISSING (no intent) is separate from POLICY_REJECTED (an intent exists). An explicit outcome matrix defines which records exist. IntentLineage is per version, superseded versions included. `check_policy` raises on inconsistent input instead of fabricating a result. | M3-08 (contract), M3-09 (`StoredIntent`), M3-10 (rule 3), M3-12 (contracts, rule 2) | Table-driven matrix over every outcome, asserting exactly which records and decisions exist; atomic rollback at each write |
| **B4** mapping locks miss provider+symbol | Two transaction advisory locks, on (provider, instrument) and (provider, symbol), SHA-256-keyed and taken in ascending order. They work before any row exists. | M3-01 (rule 4), M3-02 (rule 6) | PostgreSQL races ×50: different instruments with the same symbol, and the same instrument with different symbols; exactly one commits. Non-overlapping reuse and other providers still commit. |
| **B5** daily cap races | A `"buy-admission"` advisory lock per (account, target session), after the account-control lock. The count is read under it and the qualifying transition commits under it. `admitted_buys` counts distinct intent ids. | M3-09 (`admitted_buys`), M3-11 (input, rule 8), M3-12 (rule 4) | Two connections with four of five slots taken: exactly one admitted (×50). Reduced v2, waiting -> approved, reruns, expiry, decline and rollback take no extra slot. |
| **B6** host-only guard | The effective parameters are checked: `PG*` connection variables removed during tests, keyword allowlist, single loopback host, `hostaddr`, `service` and multi-host refused, `hostaddr` pinned to numeric loopback. Every psycopg entry point is wrapped. | M3-00 (rule 4) | Fake-connect probes for explicit and ambient `hostaddr`, `PGHOST`, service files, multi-host, URI and keyword overrides, unmarked tests and an allowed local DSN, all before the real connect |
| **S1** transaction ownership | Autocommit connections. The port owns managed transactions; nested scopes join with no savepoint; `in_transaction` means the managed scope; audit requires it. | M3-01 (contract), M3-02 (rule 1), M3-04 (rule 1) | Read-then-write visibility from another connection; nested failure rolls back the outer scope; store writes join the caller's scope |
| **S2** research setup and replay knowledge | RESEARCH settings take an explicit `effective_at` with the live `recorded_at` beside it; PAPER can't backdate. Documented setup commands. Reads go through `Knowledge` (ReplayKnowledgeReader in replay). `proposal_delay` is named separately from feed latency. A missing expected session is never replaced by an older bar. | M3-05 (rule 5), M3-06 (rule 6), M3-07 (rules 2–3), M3-11 (liquidity), M3-12 (rule 9), M3-14 (setup) | CLI setup plus replay; late-delivered correction; equal-time order; missing session; settings after `at` unused; 2019 lookups of limits published today with `--effective-at` |
| **S3** migration calendars | `copy_sqlite_to_postgres(..., calendars=...)`; an unknown version aborts atomically. Source schemas 1–4. Lazy psycopg import. | M3-03 (rules 4, 5, 8) | Schemas 1, 2, 3 and 4; unsupported calendar aborts; base-install CLI import and `--help` |
| **S4** control history and races | `AutonomySetting.sequence` and `setting_id`. Approval compares the setting id (so 1 -> 2 -> 1 is detected) and the limits and rules versions. An account-control lock covers changes and approvals; a bootstrap lock gives one admin. | M3-05 (contract, rule 6), M3-06 (rule 7), M3-13 (rules 2–3) | 1 -> 2 -> 1 refused; equal times ordered by sequence; concurrent bootstrap, publish, and approve-vs-change races |
| **S5** G2 and expiry wording | Late proposals take legal edges only (AWAITING_APPROVAL -> EXPIRED, APPROVED -> EXPIRED; `>=`), with outcome EXPIRED_ON_ARRIVAL. The exhaustive test separates the frozen `ALLOWED` table from M3's CONVERTED guard. Race tests start from states where both moves are legal. | M3-09 (tests), M3-12 (rule 5) | Boundary at exactly the deadline; two-part exhaustive test; races from AWAITING_APPROVAL, APPROVED and PROPOSED |
| **S6** SELL semantics, halt clearing | Position and cash checks apply to BUYs only; liquidity-limited SELLs are reduced (new owner decision D18). Clearing a halt resets the drawdown baseline (D3 amended, with its alternative stated). | M3-06 (rule 4, `Halt`), M3-07 (rule 5), M3-11 (rules 1–2), README D3/D18 | The $100,000-holding example; post-clear baseline and re-halt after a further 15% |
| **S7** review records not in the tree | `codex-m2-accepted-b7c5d2a.md` and `codex-m3-spec-review-1ce5250.md` imported byte-for-byte from the root checkout (SHA-256 `ce1c7fc4…` and `42e55de8…`). | `docs/reviews/` | — |
| Review answers 1–5 | Recorded in the README: Policy placement OK with no ADR; SQLite legacy/test-only (M3-02 rule 5, with no writable shim); guard per B6; estimate revised to 52 h with the 4 h planning exception; D5 wording. | M3-README, M3-02 | — |

**Also corrected while revising:**
- **Approval refuses when controls changed:** it refuses when the limits or rules version differs from the intent's, or a halt is active for a BUY. This is consistent with the Pre-Execution Gate in M4.
- **Missing limits:** they now give PREREQUISITE_MISSING, not a rejection.
- **Dependencies:** M3-07 now depends on M3-06 (for halts).

All dependencies still point backward.

## Consolidated owner decisions (proposed)

In `docs/tasks/M3-README.md`, in plain English:

- **D1–D9:** risk limits (OPEN-07). D3 now resets the starting point when an Admin clears a halt.
- **D10–D12:** approval and view validity (OPEN-08).
- **D13–D17:** order price, starting cash, promotion rule, local PostgreSQL, CLI approvers.
- **D18 (new):** partial selling when volume limits a sale.

None is accepted. The proposed limits file applies only when an Admin publishes it.

## Checks

Documents only:
- `git diff --check` is clean;
- the estimates sum to 52 h, and every M3 dependency points to an earlier task (the same check as Codex's script);
- the imported review files are byte-identical to the root copies.

No runtime file changed, so no tests were run. CI not yet run. Nothing was merged or pushed. Other checkouts were not edited; the root files were only read.
