# M6 review-fix package (Claude Code, 2026-10-26)

| | |
|---|---|
| Implementer | Claude Code. **Not independent acceptance**: Codex re-reviews every commit below. |
| Reviews answered | `docs/reviews/codex-m6-review-d09e850.md` (B1–B11, N1–N6), `codex-m6-review-e312999.md` (B7 resolved), `codex-m6-rereview-654130e.md` (R1–R3 and scope/N5 notes). All three are untracked in the root checkout. |
| Range to review | `e312999..` the commit that adds this file: 14 fix commits and this handoff. The earlier range `d277440..e312999` was reviewed in the first pass. |
| Code head checked | `e5c3169`. This handoff commit changes documentation only. |
| Status | Every finding fixed, red then green, one commit per finding (or per tightly coupled pair). Package checks: see below. **M6-11 (live run) still waits** for Codex's acceptance and your separate approval. Nothing merged or pushed. |

## Finding → fix → evidence

| Finding | Commit | What changed | Regression (red before, green after) |
|---|---|---|---|
| B1 event gaps | `d7bedea`, then R1 `f5f0852` | Every job version emits its event. The request publishes page by page until its own event is out, and otherwise says it's pending. | A real Consumer delivers request, claim and completion with no holds, including re-claim, refusal and expiry. A request behind a backlog of 150 Core events is published, and the completion is delivered with held = 0. |
| B2 redaction | `3b713a2` | A single regex pass covers every secret and its JSON-escaped forms; upstream gets the redacted state for its files and memory log; a redacting log-record factory runs during each run; secrets under 8 characters are refused. | An echoing model and a quota error carrying the secret: no plain or escaped secret appears in work-dir files, logs, stdout/stderr or stored record text. |
| B3 Jev/TypeSafe | `8b99308` | Ambient TypeSafe, Vertex AI and `TRADINGAGENTS_*` switches are refused by name at startup, and again by the adapter before any call. | Startup and adapter refusals, with no value printed. |
| B4 provider pinning | `8b99308` | Every run-shaping upstream key is set explicitly; Google only (D45); effective configuration recorded. | Conflicting ambient defaults never reach either tier; an OpenAI job is refused before any call. |
| B5 hidden retry | `65c828b` | `ProviderFailureGuard` refuses every model call after the first provider error; such a run is FAILED; parser fallback unchanged. | A 429 on the Trader's structured call: no further provider call, FAILED; the unsupported-structured-output fallback still succeeds. |
| B6 provenance | `cec4bb8`, then R2 `29d1d5d` | Real vendor per fetch: router entries (fallbacks included), direct social fetchers, identity, and the settlement price fetch. Every fetch keeps its exact, redacted answer as an input snapshot. Cache origin is stated as not distinguished. | Vendors and methods are recorded; a failing vendor is recorded with its error; wrappers are restored; a seeded due decision records both settlement price fetches and their actual closes. |
| B7 clock | `06c1161` | `LiveClock` in the budget view. | The existing no-system-clock scan. |
| B8 lease | `d9a4277`, then R3 `e5c3169` | The fence reads the clock after the final ownership read and requires deadline + 1-minute finish margin ≤ lease; a taken-over claim starts and writes nothing. | A slow reservation, a slow final read, the exact-fit vs one-second-over boundary, and a takeover during the wait. |
| B9 boundary | `fed2ac2` | No `AuditStore` in the worker; the Admin policy command moved to the Core-side CLI; the layering rule also forbids policy code. | A fresh process constructs a real worker and loads no writer-domain module; a deliberate `AuditStore` makes the test fail. |
| B10 look-ahead | `3436bfb` | Evidence must exist by its assessment time, come from a succeeded run, and in a report be assessed at the report's own time. | Future context or record, failed run, before-generation status, and mismatched report time are all refused. |
| B11 bundle binding | `fc40f00` | Settings, instrument and timing are checked on save and on read. Additive migration 0022 enforces them at insert, so no late child context can be added. | Cross-instrument and other-settings bundles are refused; a late SQL context after FAILED is refused; a populated 0021→latest upgrade keeps the context readable. |
| N1 | `654130e` | The budget day is read after one global budget lock; reservation-day accounting policy documented. | A lock wait across midnight books the new day. |
| N2 | `654130e` | Partial capture is kept at abandonment; uncaptured runs show NOT MEASURED. | Partial calls are saved; `research show` never prints 0 for unmeasured usage. |
| N3, N6 | `7f189f5` | The role refusal itself must be the failure; exact per-agent table (15 requests, 12 tools). | Same tests, tightened. |
| N4 | `654130e` | Code version from the package's own checkout. | Launched from an unrelated directory: still this checkout's head; not a checkout: "unversioned". |
| N5 | this commit | PROGRESS next steps updated (below). | — |

## Scope reconciliation (re-review note 6)

All fixes stay inside M6's own files. No upstream TradingAgents file changed after U1. No M1–M5 production module changed, apart from the CLI and report hooks that M6 already lists.

**Owner approval recorded (2026-10-26):** "I approve the listed M6-only scope extensions, including migration 0022 and the cross-task M6 file changes. Record this approval in the handoff." This covers the extensions below, which the original per-task file lists did not name:

| Task list | Files added by review fixes | Commits |
|---|---|---|
| M6-01 contracts | `investment_engine/research/contracts.py` changes for status time, effective config and source metadata (listed under M6-01, changed by fixes recorded under M6-04/09) | `3436bfb`, `8b99308`, `cec4bb8` |
| M6-02 storage | **`investment_engine/storage/schema_pg/0022_research_bundle_guards.sql` (new additive migration)** | `fc40f00` |
| M6-04 adapter | `research/contracts.py`, `research/secrets.py`, `tests/engine/test_research_worker.py` | `8b99308`, `3b713a2` |
| M6-07 worker | `research/budget.py`, `research/store.py`, `research/adapter.py`, `research_cli.py`, `tests/engine/test_research_budget.py` | `fed2ac2`, `654130e` |
| M6-08 CLI | `tests/engine/test_research_store.py` (real-consumer delivery) | `d7bedea` |
| M6-09 display | `research/contracts.py` (`ResearchContext.status`) | `3436bfb` |
| M6-10 proofs | `tests/engine/test_usage_counter.py` | `7f189f5` |

## Package checks on `e5c3169` (code identical to this commit)

| Check | Result |
|---|---|
| Git Bash full suite (`.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rfEs`) | 1 failed, 3968 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 4051.24s (1:07:31) |
| PowerShell full suite (same command) | 1 failed, 3968 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 3390.72s (0:56:30) |
| Failures | Only the baseline `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, in both shells. **No new failures.** |
| `ruff check .` | All checks passed |
| `git diff --check d277440 HEAD` | Clean; tree unchanged after the checks |
| Fresh installs (new base and `[engine]` venvs, installing `e5c3169`) | Passed: modules load from site-packages; base loads no pyarrow/duckdb/psycopg; U1 state keys present; schemas 0001–0022; research worker entry point; CI-style imports for both |
| Affected focused suite (R1–R3) | 161 passed |
| CI | Not run (nothing pushed) |

**Process note.** I stopped an earlier check run at about 06:00, but that stopped only its wrapper. Its child process kept running an unused PowerShell suite and an install step until 08:00:40. It overlapped the R1–R3 focused tests, which passed, and the first hour of the run above, which slowed it. None of its output is counted here.

## Still open (recorded in PROGRESS)

- **M6-11, the live run:** after Codex accepts this package, it needs your explicit key-use approval, removal of the user-level `GOOGLE_API_KEY`, and your `research_worker.env`.
- The ledger tables have no database writer-role guard (an M5 property). Reservation-day budget accounting is a declared policy, not per-call provider-day measurement. Cache origin of data is not distinguished. An abandoned run's thread may continue (its partial capture is saved, and nothing new starts). Carried from M5: R3 and N1–N6.
