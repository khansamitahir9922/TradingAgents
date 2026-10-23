# M5 milestone review package

**Follow-up after independent review:** Claude did not accept `e0a668e` (B1 blocking; N1-N6 non-blocking). The owner authorized follow-up corrections. Use [the review-fix package](implementer-m5-review-fix-package.md) and current PROGRESS for the new commit range, checks and unresolved issues; the evidence below records the original milestone snapshot.

**Implementer: Codex, backing up unavailable Claude Code. Not independent acceptance.** Owner authorized the entire local M5 package by answer `1` on 2026-10-21 to `C:/Users/LOQ/TradingAgents-proposals/codex-m5-specs/approval-package.md`. This accepted ADR-010 v0.2, D35-D44, 15 task commits / 55-hour planning estimate and eight task-size exceptions. It authorized local M4 fast-forward, planning and implementation commits, not an M5 merge or push.

**Status: all 15 task implementations committed (checked); package checks complete, awaiting independent review.** See the final supplement and PROGRESS for observed results before requesting independent review. Never treat implementer self-review as reviewer acceptance.

Base: accepted M4 `5cd93637cfa0a820102196b2da31294c5f908b0c`. Planning commit `0f93c75`. Isolated worktree `C:/Users/LOQ/TradingAgents-m5`, branch `m5/milestone`. Main remains at M4; root checkout and its owner changes, other branches/worktrees and excluded M4 tidy-ups are preserved. No M6, keys, market downloads, actual backup schedule or owner database restore/reset.

## Tasks, commits and evidence

| Task | Commit / follow-ups | Main acceptance evidence |
|---|---|---|
| 00 contracts | `94d057f`, `c8a3e78`, `f2c803d` | unit-separated immutable journals; full frozen source payloads; non-circular lot/book IDs; neutral broker DTOs |
| 01 journal/store | `a9b25e8`, `f1c619b` | atomic sealed manifests, per-unit SQL balance, immutable replacement/update/delete/truncate guards, explicit audited activation/upgrade |
| 02 fill posting | `8ecf064` | actual accepted OMS fills, provider/account/times, source dedup, rollback; accepted negative-cash facts retained |
| 03 FIFO | `68db691` | independent rational cumulative half-even allocation, exact residual conservation, split epochs, hostile Decimal contexts |
| 04 corporate actions | `cfa3f80` | ex-open chronology, prior-close dividend entitlement, unpaid receivable, unsupported/fractional/unresolved sources fail closed |
| 05 temporal corrections | `0cfe161`, `b01c800`, `33779f5` | pinned E/K/head; full dependency reversal/replacement; late fills/actions; explicit zero basis; equal-time changed lot attribution |
| 06 portfolio | `daa201f` | post-activation LEDGER only; reservations as of cutoff; actual M4 fixture preserves ID/content/absent fields |
| 07 independent broker | `3464787`, `064b485` | public Admin setup; independent private broker book; Worker-only immutable snapshots/ingestion; no ledger/OMS derivation; command-time-independent capture IDs |
| 08 pure reconciliation | `719e3d4` | exact comparable cash/quantity/open orders/executions, strict prefix completeness, no repairs |
| 09 incidents | `dd9aba4` | account/incident/operator lock order, current Admin auth, durable evidence, ACK does not resolve, later fresh MATCH/CAS required |
| 10 integration | `1649a39` | distinct atomic consumer, account locks, current source prefix before proposal/gate, bounded Worker captures, zero-order convergence, finite fixed-time harness, R5 preservation |
| 11 reports/CLI | `8a5d229` | pinned read-only JSON/text/escaped HTML, sources/times/units, missing ≠ zero, accessible labels; separate audited Admin commands |
| 12 backup/restore | `e425ad4`, `cd867f9` (runbook clarification only) | exported PG17 snapshot counts/hashes, later immutable file superset, exact source references, actual disposable restore and P&L 228 bridge, secrets/unsafe targets refused |
| 13 invariants | `ad58728` | 200 fixed-seed flows, 50 repetitions each of posting/fill-proposal/incident races, real process kills and retained M4 harness/compatibility checks |
| 14 demonstration | `b7e1c13` | exact synthetic BUY/split/dividend/SELL, byte-identical fresh runs, seeded mismatch/ACK without repair, missing mark/session explicit |

Every task and follow-up contains its exact focused test commands/results and implementation choices in its task check record and PROGRESS. Before the final check record, the read-only scope checker verified all 22 task/fix/documentation commits individually against their task's exact allowed paths: zero outside paths. It will be repeated for the finished range. Planning documents were separately owner-approved. The only frozen-architecture edits are accepted ADR-010 cross-references in Parts H/K; diagrams, package dependencies and CI are untouched.

## Self-review and corrections

This is implementer self-review, not independent acceptance. Follow-ups preserve history rather than rewriting earlier commits. Regressions were observed before their fixes:

- Removed circular book identity from lot evidence, froze source records and registered complete corporate action/Money payloads without rewriting the serializer or older record IDs.
- Distinguished explicit known zero cost from missing cost; bound lot matches to their containing stored book.
- Rebuilt full downstream allocations on late/corrected sources. A same-time replacement with unchanged debit/credit values but different lot attribution gets causal evidence rather than reusing a committed transaction ID or advancing the replay clock.
- Actual independent-broker setup command dates originally contaminated economic snapshot hashes; the fix binds the immutable economic setup ID and retains live attribution in setup/audit provenance.
- Integration checks found a stale order transition was checked against the state graph before its locked expected-version check; the account-locked reread now reports the existing StaleWrite contract. No lifecycle edge changed.
- Expected accounting gaps are caught outside failed sync transactions, or before leaving a caller-owned gate transaction, avoiding a poisoned transaction masquerading as an ordinary missing input. Actual persistence/connection failures retain their type.
- The new test fixtures were corrected when an assertion named nonexistent schema columns, a seeded discrepancy lacked a valid SHA-256 and an older test scenario lacked its referenced synthetic market file. These corrected test setup/expectations, not production validation.

Task 13 independently calculates rational conservation, exercises actual concurrent connections and hard-kills only generated test children; it does not stop the owner's PostgreSQL server. Existing process-harness fault hooks/timeouts are unchanged. The M4 persisted snapshot fixture was produced by the actual accepted M4 code and checked by its original content hash/ID, rather than fabricated with current classes.

## Review hardest

1. SQL seal/manifest completeness and all mutation/conflict routes; stored hash checks and legacy IDs.
2. Point-in-time pinned ancestry, actual delivery, equal-time versions, FIFO and full correction closure, fees only once and dividend AR never cash.
3. Source completeness: actual stored declarations, accepted fills, per-provider action revisions and typed verified coverage; no bare success boolean establishes history.
4. Independent broker/book setup, open orders, cancelled late fills, scoped captures, fixed-time readiness and fresh current prefix invalidation. Core code calls no broker/private simulator API; Worker code posts no ledger effects. The AST probes are regression guards on imports/calls, not a claim of production OS-level capability isolation; deployment permissions remain M7 work.
5. Account/control/ledger/consumer lock graph; simultaneous fill/proposal and incident control changes; current Admin authorization; ACK is not resolution and no broker discrepancy writes a repair.
6. No provisional fallback after explicit activation; NEW waits for the Core token but still runs the actual gate; cancels/recovery and accepted UNKNOWN behavior remain.
7. Read-only reporting, incomplete/null values, source/mark cutoffs, HTML escaping, replay command-time provenance and deterministic economic IDs.
8. Backup snapshot consistency: exact exported DB snapshot, immutable file superset rather than false cross-store atomicity, source resolution and fresh empty local test-target restore only.

## Deliberate limitations / inherited conditions

- USD, long-only whole shares, no FX/tax/settlement/payment-date inference. Unsupported facts, incomplete coverage and unavailable basis block the current account instead of guessing.
- Only explicitly activated accounts switch to LEDGER. Existing accounts remain historical PROVISIONAL until explicit activation; no hidden bootstrap or migration of their economic history.
- Live feed/snapshot freshness and production service configuration remain M7 work. Missing accounting injection after activation fails closed. PAPER remains blocked by the accepted promotion rules; M1 hourly remains unresolved.
- The compact simulation accounting result supplies no guessed mark delivery. Held inventory has null valuation there; use the explicit-mark read-only accounting report for a complete marked endpoint.
- Backup copies are locally hash-verified, not cryptographic authenticity attestations or an atomic snapshot across PG/files. Same-disk risk is labelled; no deletion/retention automation, schedule installation, remote backup or owner restore.
- Existing M4 kill-switch unresolved-crash lockout, broker message-stream cursor debt and upstream midnight-sensitive tests remain. The excluded task README/check-table tidy-up is not silently folded into M5.
- M3's accepted test harness depends on pytest internals; keep its password regressions on upgrades. The owner's PostgreSQL/password/listen-address decisions are unchanged. Secrets are never printed/staged by this package.

## Final verification

Observed task-14 own/affected command: `ROOTPY run_check.py bash m5-14-final tests/engine/test_m5_accounting_demo.py tests/engine/test_simulated_run.py tests/engine/test_m5_process_integration.py tests/engine/test_accounting_reports.py`: **43 passed in 193.14s**. `ROOTPY` is `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe`; helper/evidence root is `C:/Users/LOQ/TradingAgents-proposals/codex-m5-implementation/`. Ruff passed. Captured synthetic JSON with explicit hand-constructed-data/view annotation is 9,540 bytes, SHA-256 `0e4a6db39a54e7beb4b9952add0a406a2e519e74901ac0796bb5717f019dfbf0`; full source/code/book/query provenance and the unannotated product output hash are in [the demonstration record](m5-accounting-demo.md). The wrapper does not alter economic values or production code.

Full Git Bash, unchanged production code `b7e1c13`: `ROOTPY run_check.py bash full-git-bash` -> **3782 passed, 1 failed, 7 skipped, 3 deselected, 99 subtests passed in 3187.71s (53:07)**. The failure is the recorded baseline `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`. Skips: three SQLite-only branches of mapping concurrency tests (the PostgreSQL branches run), three POSIX-file-mode cases on Windows, one optional `langchain_aws` dependency. No PostgreSQL credential skip. Full log is `full-git-bash.log` in the evidence root. The wrapper runs the actual pytest process inside Git Bash, inherits the private test DSN and redacts credential material before any output/log.

Package checks completed; observed details below. CI **not run**. No independent review or M5 merge yet.

### First PowerShell run: new transport failure, retained and not accepted

The first complete PowerShell run reported **3781 passed, 2 failed, 7 skipped, 3 deselected, 99 subtests passed in 19321.74s (5:22:01)**. One failure is the known cache baseline; the other is **new**, `tests/engine/test_limits.py::test_concurrent_restriction_changes_both_survive[add-remove]`. It raised `psycopg.errors.ConnectionTimeout` while establishing a racer connection, before any race thread or policy assertion. Neither `risk/limits.py` nor `test_limits.py` changed in M5. Windows recorded sleep/resume events during the long run. This is not silently treated as a baseline or a passing package check.

The full sanitized log is preserved as `full-powershell-connection-timeout.log`. The whole unchanged limits module was rerun via `ROOTPY run_check.py powershell m5-limits-timeout-rerun tests/engine/test_limits.py`: **25 passed in 50.53s**. No timeout/repetition/test change or production retry was introduced. The subsequent complete PowerShell rerun finished with only the cache baseline failure, then both fresh installs passed, as recorded below. The external `awake_package.py` used a thread-scoped Windows idle-sleep request around verification and cleared it on exit; no power-plan settings changed. Its status is finished, and no duplicate heavy checks are running.

Independent reviewer should review every fixed commit and integrated behavior in a separate detached checkout; report concrete file/line, failure scenario and fix. Owner must separately approve any M5 merge. Preserve the deferred M2-improvement reminder in PROGRESS; it does not authorize M6 or new strategy work.

## Final observed package evidence (2026-10-22)

Final package checks on unchanged runtime/test code `b7e1c13`:

- `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe C:/Users/LOQ/TradingAgents-proposals/codex-m5-implementation/run_check.py bash full-git-bash`: **1 failed, 3782 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 3187.71s (0:53:07)**.
- Same runner, `powershell full-powershell`: **1 failed, 3782 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 3815.33s (1:03:35)**.
- Failure IDs: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`. These are recorded baseline cases; the cache failure's original Windows-temp-inside-home cause was checked against M1-00. No new test failure or missing-PostgreSQL-DSN skip. Seven skips are the three SQLite concurrency variants, three POSIX permission cases and the optional `langchain_aws` import; three integration cases are deselected. PostgreSQL branches ran.
- The first PowerShell run was **not accepted**: 3781 passed with the cache baseline plus NEW `tests/engine/test_limits.py::test_concurrent_restriction_changes_both_survive[add-remove]`, a PostgreSQL connection-establishment timeout before race logic. Its complete log is retained as `full-powershell-connection-timeout.log`, SHA-256 `26d6178def92fe03077efe67c3e1bf26240c66f69c68296d8df4cc6ff8be7065`. Windows recorded sleep/resume during that run. The unchanged complete limits module rerun passed all **25 tests in 50.53s**, then the full suite was repeated. No code, test, repetition or timeout changed; the passing package result above comes from the complete repeat, not from discounting a new failure. The repeat/install sequence used a thread-scoped Windows awake request, cleared on helper exit, without editing power-plan settings.
- `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe C:/Users/LOQ/TradingAgents-proposals/codex-m5-implementation/fresh_installs.py`: **PASS**, genuinely new base and engine environments retained at `C:\Users\LOQ\AppData\Local\Temp\ie-m5-install-6xzftcgf`. The base has no pyarrow/duckdb/psycopg; the engine has them. Both import the installed M5 modules from outside the repository without eagerly loading those libraries, and include schema resources 0016-0018. Both also pass the root CI-style imports. Exact commands and output: `fresh-installs.log`; completion proof: `fresh-installs-result.json`.
- Read-only `final_evidence.py`: code/test tree unchanged, main clean at `5cd9363`, old SQL migrations/diagrams/dependencies/CI/original TradingAgents paths preserved, AGENTS/CLAUDE shared rules identical, artifact hash/size/equity bridge verified. Per-commit exact-path checker passed all 22 task/fix commits before this final documentation record; rerun after this commit for the full review head.
- Synthetic demo JSON: **9540 bytes**, SHA-256 `0e4a6db39a54e7beb4b9952add0a406a2e519e74901ac0796bb5717f019dfbf0`. Source/code hashes, book/query IDs and the raw product-output hash are in `docs/reviews/m5-accounting-demo.md` and the external artifact manifest. The separate explicit annotation says data and views are hand-constructed; the artifact is not a historical NVDA backtest or profitability evidence.
- Actual exported-snapshot dump/disposable restore, exact table hashes, per-unit balance and synthetic P&L 228 bridge passed in task M5-12 and the full suites. No owner database restore/reset or backup schedule installation.
- CI not run; no push, M5 merge, API keys, market downloads or M6. Independent review is still required; Codex implemented and self-reviewed, and does not independently accept its own work.

Full logs/hashes and helper commands are retained outside the repository at `C:/Users/LOQ/TradingAgents-proposals/codex-m5-implementation`. Git Bash log SHA-256 `5d305e0e410474fadfaeacb5d19cfcfc79ea151cddae4f69558e0100d74246ec`; PowerShell log SHA-256 `07959dd03b37c746fd4d56279b2cd7bc6aec8e988b4d44372b927e27b3500621`; fresh-install log SHA-256 `d3e6e1c0b5bde58269cd0ea76581c2158f19cd4c8e9e7ee312a93cf2fd0b14d0`.
