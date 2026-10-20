# M4 review-fix package: R5 (Claude, 2026-10-20)

For Codex's review of `fd73684` (`docs/reviews/codex-m4-rereview-fd73684.md`): R1–R4 resolved; one blocking regression, R5, from the N1 follow-up. Codex's handoff asked for one follow-up for R5 and counts as the owner's instruction for this step. The resolved fixes are not repeated. **Nothing has been merged or pushed.**

## Range

`fd73684..` the commit that adds this file (named in the hand-off): `ebb44e8` (the fix) and this documents-only close. Architecture, migrations, packaging and CI are unchanged. The fix changes `execution/worker.py` and its test file only.

## The fix

**What went wrong.** N1 normalized every broker-call exception into `BrokerCallFailed`, an ordinary unknown outcome. That also caught `psycopg` connection-loss errors from the simulator's own connection, which is separate from the worker's in production. So `run`'s reconnect never ran, and a new order became UNKNOWN.

**What changes.**
- A lost database connection (`storage.postgres.connection_lost_errors()`) now keeps its type across the broker boundary. `_bounded` re-raises it unwrapped.
- The broad handlers (a submit, UNKNOWN lookups, SUBMITTING reconciliation) re-raise it, so it reaches the reconnect, which rebuilds both connections and recovers.
- A submit interrupted this way stays SUBMITTING and is looked up after the rebuild, never resent.

**Unchanged:**
- ordinary broker errors stay isolated, with their anomaly (N1);
- B5's deadline and stalled-call protection;
- reconciliation (looked up, never blindly resent).

## Requirement → test → evidence

| Requirement | Test | Evidence |
|---|---|---|
| A lost simulator connection reaches the running loop's reconnect; submission exactly once; lookups, cancels and message reads resume | `test_worker_resilience.py::test_a_lost_broker_connection_reaches_the_running_loops_reconnect` (separate real connections, as deployed; only the simulator's is closed) | failed first ("the reconnect was never called"); Codex's probe (SHA-256 `4104ac56…`) passes; 82 worker, deadline, cancel, submission, recovery, layering, simulated-run and fault-injection tests pass |
| Ordinary broker errors still isolated (N1) | `test_worker_cancels.py::test_a_broker_error_on_one_cancel_leaves_it_retryable…` | passes, unchanged |
| The worker's own lost connection still reconnects (B4) | `test_worker_resilience.py::test_the_running_worker_loop_reconnects_recovers_and_carries_on` | passes, unchanged |

## Checks

- **Git Bash, on `ebb44e8`'s exact tree** (verified equal to the commit's tree before committing): **1 failed, 3340 passed**, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed, in 3891.30 s; the only failure is the baseline cache-location test. **No new failures.** ruff passed; whitespace clean.
- **PowerShell full suite, on code identical to `ebb44e8`:** **2 failed, 3339 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 3872.59 s. Both failures are the recorded PowerShell baseline (the cp1252 CLI test and the cache-location test). **No new failures**.
- **Clean install** of a fresh worktree of `ebb44e8` (base and engine venvs; `-I` smoke from outside the repository): **passed**. Base: 6 M4 modules, psycopg absent. Engine: 22 modules; schemas `0001`–`0015`, the limits, fees and thresholds files; `simulated` refuses PAPER; psycopg 3.3.6; the CI import passes in both.
- **Not run:** CI (nothing pushed); other Python versions, OSes or the TZ job; live providers or brokers; a PostgreSQL server restart.
