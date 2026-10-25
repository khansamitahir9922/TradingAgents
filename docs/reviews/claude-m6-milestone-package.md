# M6 milestone package: Research Worker and TradingAgents adapter (Claude Code, 2026-10-26)

| | |
|---|---|
| Implementer | Claude Code. **Not independent acceptance**: Codex reviews every commit. |
| Branch / range | `m6/milestone`, worktree `C:/Users/LOQ/TradingAgents-m6`. Review **`d277440..` the commit that adds this file**: the spec commit `e49c670`, 11 task commits, one fix and this documentation close. |
| Authorization | Owner, 2026-10-25: D45–D54 as recommended, monthly budget USD 0, and the package M6-00 to M6-10. The M6-11 live LLM run, merge, push and M7 are **not** authorized. |
| Status | M6-00 to M6-10 committed (checked). **M6-11 not started.** It needs the owner's key-use approval and the removal of the user-level `GOOGLE_API_KEY` (D48). |

## Commit map

| Task | Commit | What it adds |
|---|---|---|
| specs | `e49c670` | The M6 pack (D45–D54, C1–C5) and the owner's acceptance |
| M6-00 | `767b2f0` | Offline usage counter: every model request, token count and tool call, attributed to its agent. Unknown tokens are unknown, never 0. |
| M6-03 | `1f80ce6` | **Upstream change U1:** the parsed Trader and Portfolio Manager objects stay in the final state (`docs/dev/upstream-changes.md`) |
| M6-01 | `10d1498` | Research contracts (job, versions, record, context, untrusted levels, budget); `ProcessRole.RESEARCH`. No LangChain import. |
| M6-02 | `88e29c3` | Migration 0021: append-only research tables; SQL writer-role, job-edge and lease triggers; atomic save-then-publish. The outbox now accepts the research writer. |
| M6-04 | `70af044` | The TradingAgents adapter and capture: pinned settings, no retries or checkpoints, the current date only, secrets redacted. The layering exception is owner-approved: only `research/adapter.py` may import `tradingagents`. |
| M6-05 | `711504d` | `ResearchContext` from typed output only: free-text fallback labelled, levels untrusted, five-session validity on the exchange calendar |
| M6-06 | `7c087d8` | Daily budget: Admin-only versioned policy; reservation under the day lock; fails closed; unknown tokens count the reservation |
| M6-07 | `ab72383` | The Research Worker process: claim and lease, bounded run, stall guard, typed reconnect. Startup checks (D48). A layering rule bars execution, ledger, risk and kill-switch code. |
| M6-08 | `5872958`, fix `06c1161` | `research request / status / show / budget set / budget show`; roles, reasons, read-only views. The fix makes the budget view use the injected clock. |
| M6-09 | `b183b96` | Advisory research panel (text and escaped HTML) beside the MarketView; the M2 report is byte-identical without research; `research view` |
| M6-10 | `d09e850` | Isolation proofs: the synthetic M5 run is byte-identical with or without research, with zero research SQL on the order and ledger paths; the research role is refused by the OMS triggers; a hard-killed worker process is re-claimed once without a duplicate |

Every task's exact commands, red-then-green evidence and design choices are in its `docs/tasks/M6-NN.md` check record and in PROGRESS.

## Deviations, each recorded in its task

- **Layering (M6-04, owner-approved in session, 2026-10-26).** The M1 rule "never import tradingagents" now allows exactly the one adapter that ADR-001 calls for. New rules keep LangChain and the research runtime inside `investment_engine/research`, and keep research away from execution, ledger, risk, portfolio and OMS writers.
- **Outbox writer (M6-02).** 0021 widens the outbox `writer` check to include `research-worker`; 0012 itself is unchanged.
- **No in-place lease renewal (M6-02/07).** The lease outlives the deadline (plus 5 minutes), so a running job is never re-claimable. A crashed claim is re-claimed once after it expires.
- **USD cap (M6-06).** It can't be enforced before per-run prices are measured, so a policy with one refuses runs. D47's USD 0 is enforced as free-tier request and token caps.
- **Data-source references (M6-04)** name the upstream router (`tradingagents-router`) and the tool, since upstream picks the vendor per tool.

## Package checks on `06c1161` (code identical to this close commit)

| Check | Result |
|---|---|
| Git Bash, `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rfEs` | **1 failed, 3925 passed**, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 3315.54s (02:00–02:55 PST) |
| PowerShell, same command | **1 failed, 3925 passed**, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 3280.67s (02:55–03:50 PST) |
| Failures | Only the recorded baseline `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, in both shells. **No new failure.** The skips are the known SQLite concurrency, POSIX file-mode and `langchain_aws` cases; the PostgreSQL tests ran. |
| Ruff, `git diff --check d277440 HEAD` | Passed; clean |
| Fresh installs | A fresh worktree of `06c1161` was installed into new base and `[engine]` venvs, then smoke-tested with `-I` from outside the repository. **Base:** 9 M6 modules from site-packages; pyarrow, duckdb and psycopg not loaded; the U1 state keys present. **Engine:** 16 modules; schemas 0001–0021; the Research Worker entry point; psycopg 3.3.6. The CI-style `import investment_engine, tradingagents` passes in both. |

**Earlier run, not accepted.** The first Git Bash run on `d09e850` gave 2 failed and 3924 passed. The second failure was **new**: `tests/engine/test_no_system_clock.py`, because `research budget show` read the system clock. It was fixed in `06c1161`, and both suites above were rerun on the fixed head.

Two of my own check-script defects were corrected and are recorded here rather than hidden:
- the PowerShell summary is UTF-16 and was decoded for reading;
- the first engine install passed a Git Bash path with `[engine]`, which pip rejected silently. It was repeated with a Windows path and passed.

CI has not run (nothing pushed).

## Not done / open

- **M6-11, the measured live run:** needs the owner's explicit approval, the user-level `GOOGLE_API_KEY` removed, `research_worker.env` created by the owner, and pinned model names. Until then, D46's budget remains the provisional 3 runs a day.
- **The ledger tables have no database writer-role guard** (an M5 property). Research is kept off the ledger by code structure and layering only; the OMS tables refuse the research role in SQL.
- **An abandoned (past-deadline) run's thread may keep using quota** until it returns. Its reservation stays counted and its actual usage is unknown. The worker starts nothing new until the thread ends.
- Carried from M5: R3 and N1–N6 (PROGRESS open issues).

## What to review hardest

1. The 0021 triggers: role writers, job edges, leases, the claim holder's finish, append-only guards, the outbox widening.
2. The layering and boundary rules, and the isolation proof (`test_research_isolation.py`).
3. U1 is minimal, and the upstream suite is unchanged.
4. Budget fail-closed behaviour and the concurrency of reservations.
5. Secrets: the startup refusals, redaction, and that no value is ever printed.
6. The deadline and stall path, and the crash re-claim.
7. The context comes from typed fields only; levels never become orders; the display is honest about status and missing data.

Nothing is merged or pushed. Main stays at `d277440`.
