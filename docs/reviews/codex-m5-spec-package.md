# M5 specification package: Codex backup implementation

**v0.2 accepted by the owner, 2026-10-21. Implementation authorized; finished milestone not independently reviewed.**

The owner asked Codex to start M5 while Claude is unavailable. Codex has prepared the design and full task package. M5 runtime implementation is now owner-authorized; no runtime code existed at acceptance. Self-review below is not independent acceptance.

## v0.2: continued implementer self-review

The owner asked Codex to continue while Claude's limit remains exhausted. Four concrete design findings are fixed in this proposal before seeking implementation approval. The task count and 55 h estimate are unchanged; these clarify correctness already required by the package.

| Finding / concrete counterexample | Draft correction and planned regression |
|---|---|
| F1: six shares costing 0.0004; five independently rounded 0.0001 disposals consume 0.0005 before the last share | ADR-010/D35 and M5-03 now require cumulative exact-rational half-even targets, nonnegative allocations, grouping invariance and split allocation epochs. An external arithmetic worksheet checks the case and 400 small quantity/cost combinations. These are arithmetic checks, not application tests. |
| F2: worker captures at T, Core matches it, clock/capture immediately creates a new token requirement and the next gate cannot use the old result | M5 C4/M5-10 specify fixed-time worker -> Core -> worker handshake, idempotent unchanged captures/books, a pinned readiness token, and deferred NEW while waiting. Real submissions still run every gate check; cancels and recovery continue. Planned tests require convergence before the first order and after a fill. |
| F3: two consumers pass the processed-event SELECT, the first posts/marks, the second waits on ledger then hits the processed-mark unique constraint | M5-10 adds opt-in Consumer serialization before the SELECT, with a distinct accounting-ledger consumer name, fixed consumer -> account -> ledger order and per-event transaction boundaries. Existing consumers retain their defaults. A two-instance regression must have one effect and no spurious failure. |
| F4: Admin reads a MATCH/operator role, then a new mismatch or deactivation commits before resolution | M5 C2/C5 and M5-09 require account/incident/operator locks, current command time after locking, and fresh matching evidence under the same locks. Acknowledge/resolve remain Admin-only and never change journal values. |

F2-F4 are source-based interleaving analyses, not claims of observed new runtime-test failures. Relevant existing code was inspected: Consumer._apply, processed_events constraints, worker.step/gate submission, AccountRegistry.authorize/deactivate_operator and the replay harness. No existing M4 acceptance is reopened by these proposed M5 extensions.

## Snapshot and scope

- Worktree `C:/Users/LOQ/TradingAgents-m5-specs`, branch `docs/m5-specs`, base accepted M4 `5cd93637cfa0a820102196b2da31294c5f908b0c`.
- Changes are **uncommitted and unstaged**. Review the recorded patch/hash package, not a claimed new commit. Main remains `4c56ac1`; M4's accepted head remains `5cd9363`.
- New ADR-010, M5 README and 15 task specs (00-14), this review package; narrow ADR/task indexes, roadmap proposal and PROGRESS updates.
- No edits to runtime, tests, existing migration scripts, dependencies, CI, frozen architecture/diagrams, accepted ADR bodies, secrets, owner databases or other worktrees' implementation files.
- Root PROGRESS is updated only as the operational handoff; owner work and the earlier logs/reminder are retained. M4 tidy-ups and their passing checks remain isolated in their own worktree.

## Read in this order

1. [ADR-010](../../architecture/adr/ADR-010-securities-ledger-model.md): the deliberately deferred securities model.
2. [M5 README](../tasks/M5-README.md): D35-D44, estimates, ownership, interfaces, comparison/backup protocol and exclusions.
3. M5-00 through M5-14 in task order, including allowed file scope and acceptance tests.
4. Actual accepted M4 source for the interfaces being extended: OrderStore, portfolio snapshots/provisional projection, broker port/simulator, Core/worker, Consumer, account authorization, database migrator and the offline harness.

## Main design proposals

- Separate balanced USD and instrument-share books; FIFO with explicit residual allocation; fees expensed once; source-linked opening capital and lots.
- Bitemporal effective/knowledge cutoffs plus a pinned book head, including equal-time deliveries. Corrections append audited full dependency reversals/replacements rather than reset history.
- Splits preserve lot cost. Dividends become receivables; the source does not establish payment dates. Unsupported fractions/missing basis remain unavailable.
- Explicit activation switches an account to the authoritative ledger; legacy record IDs/history remain unchanged. Reservations and execution state stay owned by OMS.
- Worker-only broker snapshot collection; simulator accounting is independent of OMS/ledger balances. Comparable cash/shares/open orders are reconciled, with no automatic repair or hidden tolerance.
- Admin-only acknowledgement/resolution proposed under OPEN-12; acknowledgement is not resolution. Missing accounting or unresolved mismatch blocks new account submissions under proposed D39 and never blocks cancels or writes the kill-switch file.
- CLI/JSON/static HTML research accounting reports; verified DB/market backups and a disposable restore drill; operational schedule installation remains a separate owner action.

## Implementer self-review and points needing independent judgment

1. **Architecture scope:** ADR-010 fills Part K's planned decision; does it fully specify Law 17 while leaving process ownership/G3/promotion unchanged? No architecture text has been altered. Only after acceptance does M5-00 allow narrow cross-references.
2. **Accounting policy:** judge D35's FIFO, fee expense and 0.0001 allocation/residual policy. USD/share books balance independently; opening holdings require explicit basis. A no-borrowing policy cannot erase a known accepted fill that produces negative cash; record the breach. Missing basis leaves the new book visibly incomplete, never an apparently current old balance. This is not a tax-compliance assertion.
3. **Temporal completeness:** examine late fill -> split -> disposal -> dividend dependency correction, repeated corrections, equal-time book heads and unavailable source closure. A supposedly convenient latest-only aggregate is not sufficient.
4. **Concurrent reads:** actual M4 conversion takes `account-control|<account>`, but direct OrderStore state/fill writes do not. M5-10 explicitly permits those narrow writers to take the shared lock and reread before economic mutations. Review the combined lock graph and source/processed-mark transaction, not just individual unit tests.
5. **Incremental build:** M5-02's SELL cost basis is an injected port defined by 00, implemented by 03. M5-04 defers dependent restatements to 05. Modules 00-09 remain uninstalled until complete wiring in 10, so no task imports a future module.
6. **Legacy compatibility:** new snapshot fields cannot enter old canonical payloads/IDs. Capture a real M4 snapshot fixture before extending the interface. No reset permission is inherited from M3's disposable-database exception.
7. **Snapshot independence:** the simulator must derive its own broker-side opening/fill/action book, never mirror the internal ledger. Snapshot capability adds no Core broker access and preserves bounded/reconnect/cancel behavior. Check status normalization and source-completeness claims carefully.
8. **Safety/incident choice:** D39 is deliberately an owner proposal; assess whether Missing readiness inputs implement it without expanding execution authority. No auto-halt/resume or automatic repair. OPEN-12 Admin-only resolution needs fresh matching evidence and current operator authorization.
9. **Backups:** pg_dump covers a consistent single database, not an atomic DB-plus-filesystem snapshot. The market copy is a verified append-only superset with reference checking. Restore is local/disposable and cannot enable trading. A real daily schedule is not claimed configured.
10. **Scope and estimates:** 15 tasks, 55 h, eight over three hours; above the roadmap's provisional 35-45 h. D43 needs explicit approval after review. None of the estimates is a delivery promise.

## Checks and evidence

This is documentation only. **Observed validation passed:** 22-file documentation-only scope, all 15 specs' required sections, backward-only dependency order, safe allowed paths, local links, 55 h total/eight over-three-hour tasks, proposed decision statuses, worked Decimal P&L/split/residual examples, whitespace (including new untracked files), no staged changes and preserved earlier session histories/deferred M2 reminder. Runtime/frozen files are unchanged. Command: `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe C:/Users/LOQ/TradingAgents-proposals/codex-m5-specs/validate_specs.py`; this uses standard-library document/arithmetic checks, not application tests. Final results and patch hashes are recorded in PROGRESS and that evidence directory.

**Not run for M5:** runtime tests, full suites, fresh installs, database migrations/queries, backup/restore tools, CI, keys, market downloads or broker calls. M4's earlier check results do not count as M5 implementation tests.

PostgreSQL reference checks used only official documentation: [constraint triggers](https://www.postgresql.org/docs/17/sql-createtrigger.html), [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html). These support the proposed mechanics, not acceptance of our accounting policy.

## Gates before implementation

1. Owner-authorized merge of accepted M4, or a separately explicit dependency/worktree exception; neither happened here.
2. Independent/owner review and acceptance of ADR-010 and the M5 specs; self-review is not that acceptance.
3. Answers to D35-D44 and approval of the whole implementation package, including automatic local task commits and task-size estimate exception.

Keep these decisions together. Once authorized, implement the whole milestone uninterrupted with per-task commits and one combined independent review. Do not merge, push or begin M6 as a consequence of M5 authorization.

## Subsequent owner acceptance

Owner approval, 2026-10-21: answer `1` to the consolidated `approval-package.md` authorization question. This accepts ADR-010 v0.2, M5 specifications and D35-D44; authorizes the local M4 fast-forward, spec commit and all 15 M5 tasks with local task/fix commits, 55 h planning estimate and eight tasks over 3 h. This is owner acceptance, not independent AI acceptance. M5 merge, push, keys, market downloads, real backup schedule installation, owner database restore/reset and M6 are excluded.

Earlier proposal/review text above is the unchanged preparation history.
