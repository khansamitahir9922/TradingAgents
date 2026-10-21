# M5 milestone review package

**Implementer: Codex, backing up unavailable Claude Code. Not independent acceptance.** Owner authorized the entire local M5 package by answer `1` on 2026-10-21 to `C:/Users/LOQ/TradingAgents-proposals/codex-m5-specs/approval-package.md`. This accepted ADR-010 v0.2, D35-D44, 15 task commits / 55-hour planning estimate and eight task-size exceptions. It authorized local M4 fast-forward, planning and implementation commits, not an M5 merge or push.

**Status: task implementation/checks in progress; final package checks pending.** See the final supplement and PROGRESS for observed results before requesting independent review. Never treat this draft status or implementer self-review as reviewer acceptance.

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
| 12 backup/restore | `e425ad4` | exported PG17 snapshot counts/hashes, later immutable file superset, exact source references, actual disposable restore and P&L 228 bridge, secrets/unsafe targets refused |
| 13 invariants | `ad58728` | 200 fixed-seed flows, 50 repetitions each of posting/fill-proposal/incident races, real process kills and retained M4 harness/compatibility checks |
| 14 demonstration | pending local task commit | exact synthetic BUY/split/dividend/SELL, byte-identical fresh runs, seeded mismatch/ACK without repair, missing mark/session explicit |

Every task and follow-up contains its exact focused test commands/results and implementation choices in its task check record and PROGRESS. Before task 14, the read-only scope checker verified all 20 implementation/fix commits individually against their task's exact allowed paths: zero outside paths. It will be repeated for the finished range. Planning documents were separately owner-approved. The only frozen-architecture edits are accepted ADR-010 cross-references in Parts H/K; diagrams, package dependencies and CI are untouched.

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
4. Independent broker/book setup, open orders, cancelled late fills, scoped captures, fixed-time readiness and fresh current prefix invalidation. Core has no broker capability/private simulator reads; Worker cannot post ledger effects.
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

Pending: completed task-14 checks, actual report artifact/hash, full Git Bash suite, full PowerShell suite, genuinely fresh base and engine installs, final scope/Ruff/whitespace checks. CI **not run**: no push authorized. No independent review or M5 merge yet.

Independent reviewer should review every fixed commit and integrated behavior in a separate detached checkout; report concrete file/line, failure scenario and fix. Owner must separately approve any M5 merge. Preserve the deferred M2-improvement reminder in PROGRESS; it does not authorize M6 or new strategy work.
