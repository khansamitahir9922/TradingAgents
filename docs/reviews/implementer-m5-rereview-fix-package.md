# M5 R1/R2 follow-up for Claude re-review

**Implementer: Codex. Independent reviewer: Claude Code. Not independently accepted.**

Review base: `93559f9`. Runtime fix: `6b3fab68d54021b3683fd6308396d0002675c3e3`. The final documentation commit adds package results; it changes no runtime code or tests. No merge, push, M6, API keys or market downloads. Main remains `5cd9363`; the owner's root checkout is untouched.

Claude's review: `C:/Users/LOQ/TradingAgents/docs/reviews/claude-m5-rereview-93559f9.md`. B1 was accepted for correctness, R1 blocked acceptance, R2/R3 were non-blocking. The owner authorized follow-up commits, a red/green timing regression, preservation of B1, optional R2 and recording R3, followed by package checks and re-review.

## Change and evidence

- **R1:** additive migration `0020_ledger_seal_cost.sql`. Only the batch-row trigger firing performs the full B1 payload/hash comparisons. Every child firing retains immutable count and parent/version/time checks. Late rows are refused both after commit and after an early constraint flush. ASCII strings use a C-collation fast path; Unicode/DEL keep the original codec. Applied migrations 0016-0019 are unchanged.
- **Measured Python cost:** after the SQL fix, the 400-source append still took 8.185s. Profiling found 408 whole-book ID calculations. `append_batch` now computes the frozen book's ID once and reuses it locally; the ID function and canonical serializer are unchanged. There is no persistent cache or skipped read check.
- **R2 fixed:** transaction source membership uses JSON equality instead of containment. The regression removes a field from transaction/entry sources, retaining full valid receipts and self-consistent entry manifests. SQL now refuses the transaction.
- **R3 recorded:** SQL still does not recompute the book ID from all content, including non-manifest fields. `_load` independently checks that identity and refuses divergence. This is explicitly open in PROGRESS; no SQL-only bypassing consumer is introduced.
- **N1-N6 remain open.** N4's remaining repeated receipts, unindexed source keys, ancestry/read verification and broker-stream rereads are not solved by this append benchmark. The budget demonstrates 400-source append cost on this host, not arbitrary-scale linearity. No synthetic demo is relabelled as a historical NVDA result.

## Red and green

Evidence directory: `C:/Users/LOQ/TradingAgents-proposals/codex-m5-r1-fixes/`. `ROOTPY` means `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe`. All test helpers inherit the private PostgreSQL test DSN without putting it in argv; stored reports are redacted.

| Check | Observed result |
|---|---|
| `ROOTPY <evidence>/run_check.py bash r1-timing-red tests/engine/test_ledger_store.py::test_400_source_append_stays_within_lock_time_budget` | 1 failed, append **369.463s**, against **5s** budget |
| `ROOTPY <evidence>/run_check.py bash r2-source-red tests/engine/test_ledger_store.py::test_transaction_source_must_equal_a_complete_batch_source` | 1 failed: DID NOT RAISE |
| First SQL-only attempt, `r1-r2-green` | 1 failed, 1 passed; append 8.185s, still over budget. Not committed |
| Diagnostic `run_profile.py bash r1-profile -- -s <timing node>` | Profiled failing run; 408 book-ID calculations dominated. Not a passing timing measurement |
| `ROOTPY <evidence>/run_check.py bash r1-r2-final-green -- -s <timing node> <source node>` | **2 passed in 9.70s**, append **1.296s**, unchanged 5s budget |
| `ROOTPY <evidence>/run_check.py bash r1-affected-green tests/engine/test_ledger_store.py tests/engine/test_ledger_upgrade.py tests/engine/test_ledger_restatements.py tests/engine/test_ledger_time.py tests/engine/test_postgres_schema.py tests/engine/test_m5_accounting_demo.py tests/engine/test_accounting_reports.py tests/engine/test_ledger_consumer_recovery.py` | **111 passed in 263.24s**, no skips |

The first timing test's statement timeout did not interrupt deferred commit and was removed; the elapsed-time assertion is unchanged. An initial `-s` helper invocation was rejected before pytest started, then corrected with `--`. These are recorded rather than counted as passes.

During the slow red run, other tests/imports were added to the same file, shifting the displayed traceback source lines. The running test used its already-loaded timing body; the 5s assertion is unchanged. Migration/store implementation edits began only after the red run finished. The 111-test green and both package suites use the final committed runtime/test files.

The 111 passing tests include every prior B1 tampering/read/codec/collation case, all committed/early-flushed late-child cases, and populated 0018-to-0019 and 0019-to-0020 upgrade tests. Existing tests were not weakened to accept corrupt data.

## Package checks

**Package blocked by a newly observed M4 test failure; no passing package verdict.**

Runtime/test commit: `6b3fab68d54021b3683fd6308396d0002675c3e3`. Exact commands use `ROOTPY C:/Users/LOQ/TradingAgents-proposals/codex-m5-r1-fixes/package_checks.py`, which invokes the shell helpers below with `ROOTPY -m pytest -q -p no:cacheprovider -rfEs` through the actual named shell. Private DSN inherited/redacted, never in argv.

| Check | Observed result | Sanitized log SHA-256 |
|---|---|---|
| `run_check.py bash full-git-bash` | 1 failed, 3810 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 4926.46s (1:22:06) | `a7e7f7eb7316ee8a51f4de7d0cbab46895a1bc30a6b6c685b63255e5ac73f952` |
| `run_check.py powershell full-powershell` | 2 failed, 3809 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 4711.46s (1:18:31) | `57e7c777ce7c596eff7a26657229bd056951a72f06389f3c067382180ea243c0` |

- Recorded baseline failure, both shells: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` (this Windows temp directory is inside home).
- **New failure, PowerShell only:** `tests/engine/test_broker_deadline.py::test_the_default_deadline_is_d26s_ten_seconds_and_a_late_ack_gives_unknown`. UNKNOWN was returned correctly; the following whole-command wall-time assertion failed at **10.203s** against `<10.2s`. This is **not** relabelled as a baseline failure.
- The package runner stopped automatically before fresh installs and cleared its temporary system-awake request. **Fresh base/engine installs: not run for this follow-up. CI: not run.** No final package pass is claimed.
- Unchanged-code diagnostic: `run_check.py powershell deadline-diagnostic tests/engine/test_broker_deadline.py`: **1 failed, 4 passed in 50.87s**. Same assertion failed at **10.219s**, with UNKNOWN again correct.
- Own detached parent checkout `C:/Users/LOQ/TradingAgents-reviews/codex-m5-r1-parent`, at `93559f9`: the original deadline node passed twice, **1 passed in 23.77s**, then **1 passed in 17.96s**. The second command supplied duplicate node arguments with `--keep-duplicates`, but pytest collected only one: **not four runs**. These passing samples do not establish the source of the current failure. Worker/test/fixture bytes are unchanged between the parent and fix; the fixture has no activated ledger and the timed worker path does not append a ledger batch. Whole-command/database scheduling overhead is a hypothesis, not a proven baseline exemption.

All ledger-focused checks, including B1, R1 and R2, remain green (111 tests); both full suites passed the new 400-source budget test. No execution code or deadline test has been changed. A concrete test-only proposal is at `C:/Users/LOQ/TradingAgents-proposals/codex-m5-r1-fixes/deadline-test-proposal.patch`; `git apply --check` passes. It observes the actual 10-second thread-wait argument and withholds the broker answer until UNKNOWN and stalled-call state have been checked, rather than making all database work fit into a 200ms margin. The proposal is **not applied or tested as a fix**. Its scope extension, local follow-up commit and required reruns await the owner's answer to the pending approval question.

AGENTS.md section 4 requires a stop for a new check failure and for a file outside the task's allowed files. `test_broker_deadline.py` is outside M5-01's scope; no exception was inferred. R3 and N1-N6 remain open. No merge, push or M6. Scope check before final documentation: 27 commits, zero problems; applied SQL 0016-0019 and runtime/tests stay unchanged after `6b3fab6`.


## Review request

Review every commit after `93559f9` through the final package head on `m5/milestone` in your own detached checkout. Start here, then M5-01's check record and PROGRESS. Confirm the 400-source budget, B1 preservation, late-child constraints and R2 equality; assess the recorded R3/N1-N6 residuals. Do not merge, push or start M6. Codex's implementation checks and self-review are not independent acceptance.
