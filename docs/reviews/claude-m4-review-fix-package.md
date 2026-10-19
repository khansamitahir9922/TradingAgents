# M4 review-fix package (Claude, 2026-10-18)

For Codex's re-review of the M4 milestone after its review at `8e683f0` (`docs/reviews/codex-m4-milestone-review-8e683f0.md`, changes requested: B1–B13). Codex's handoff asked for B1–B13 in one follow-up package, with separate fix commits and a requirement-to-test table. It counts as the owner's instruction for that step. **Nothing has been merged or pushed.**

## Range and branch

- **Branch** `m4/milestone`, worktree `C:/Users/LOQ/TradingAgents-m4`. **Re-review range:** `8e683f0..` the commit that adds this file (named in the hand-off): one commit per finding, the B7 follow-up, and this documents-only close.
- **Architecture:** v1.0 frozen and unchanged; no ADR proposed. The G3 state machine, PAPER refusal, no-resubmit and kill-switch authority rules are unchanged. **One new migration** (`0015`); no retained schema is edited or reset.
- **How each commit was checked.** Every commit's full Git Bash suite ran on that commit's **exact tree**: a fresh detached worktree at its parent plus the fix's files, before committing. The commit script then refuses to commit unless the staged tree equals the checked tree (PROGRESS.md aside). This answers the review's check-provenance note: no per-commit result below was observed on a different tree.

## Commits

| Commit | Finding | Summary |
|---|---|---|
| `982adcc` | B13 | Fresh readers decode M4 snapshots (registry). |
| `91b44fa` | B10 | Consumers select runnable next versions; a held aggregate starves no other. |
| `00df7eb` | B2 | M4 money and quantities in one fully specified Decimal context (M3's `exact`). |
| `ddee260` | B8 | A missing flag is UNRESOLVED; UNRESOLVED stays open and blocks every resume. |
| `e8221ad` | B1 | The gate reads its time under its locks; the broker call and outcome read their own. |
| `6a021b8` | B5 | D26's ten-second deadline at the worker's call boundary; the broker has its own connection. |
| `7cf8b2e` | B4 | SUBMITTING and UNKNOWN reconciled every step; per-item isolation; reconnecting role loops. |
| `85ecaa3` | B9 | Simulation scoped to its account: worker and simulator (`0015`). |
| `86a5cc7` | B3 | First CLOSED revision in sequence order; each proposal bounded at its view's bar. |
| `0cfc913` | B7 | Actions compared by instant at the start; knowledge says where it begins; whole-history feed. |
| `36a8ad4` | B6 | Every proposal path on the order store; omission fails closed. |
| `94ce169` | B11 | The saved log keeps stops, versions and cutoff; honest UNKNOWN; truthful safety headers. |
| `920f7b3` | B12 | The acceptance matrix completed; red evidence for all 13 invariants. |
| `bbad2ea` | B7 follow-up | Replay knowledge that doesn't say where it begins is never trusted with a holding (found by re-running the probes). |
| (this commit) | Close | This package, PROGRESS, contract-text alignment (M4-00, M4-04). Documents only. |

## Requirement → test → evidence

| Finding / requirement | Tests | Red evidence |
|---|---|---|
| B1: time sampled after the locks (session, approval, controls); fresh broker time | `test_worker_submission.py::test_the_gate_decides_at_the_time_it_holds_its_locks_not_before[open,approval]`, `::test_a_control_that_takes_effect_during_the_lock_wait_is_seen`, `::test_the_broker_call_carries_its_own_time_never_the_gates` | all four failed first; probe passes |
| B2: results independent of the caller's precision, rounding, traps | `test_order_store.py`, `test_simulated_broker.py`, `test_provisional_positions.py` `::…ignore(s)_the_callers_decimal_context[3 contexts]` | 5 of 9 failed first; 3 probes pass; M3 ids unchanged |
| B3: first CLOSED keeps its sequence; per-view proposal boundary | `test_raw_reference.py` (5 cases), `test_order_log.py::test_a_proposal_never_sees_an_equal_time_event_its_view_did_not` | 3 + 1 failed first; probe passes |
| B4: SUBMITTING retried each step; isolation; reconnect in the running loops | `test_worker_resilience.py` (5 tests, including server-side `pg_terminate_backend` for both loops) | all 5 failed first; probe passes |
| B5: an actual stalled call meets the deadline; no resend; no concurrent use | `test_broker_deadline.py` (5 tests, one with the real 10 s deadline) | probe failed first (SUBMITTED after 10.2 s); passes now |
| B6: every proposal path on the order store; omission fails closed | `test_order_log.py` (post-fill SELL via CLI; pending second BUY; fail-closed), `test_layering.py::test_no_module_of_the_package_asks_for_the_declared_only_portfolio` | the pending-BUY case was APPROVED before the fix |
| B7: instants at the start; short or unlabelled history refused; feed from the whole history | `test_provisional_positions.py` (start-date split ×3, dividend ×2, knowledge window, unlabelled replay knowledge), `test_order_log.py::test_simulate_feeds_the_whole_local_history…` | 3 + 1 failed first; probe 1 passes; probe 2 now Unavailable (fails closed) |
| B8: no inferred NOT_APPLIED; UNRESOLVED blocks every retry | `test_kill_switch.py` (6 new or changed) | 5 failed first; 2 probes pass |
| B9: another account's work untouched, including on a refused run | `test_simulated_run.py` (3 tests) | probe failed first (OTHER's order FILLED); passes |
| B10: no starvation at page boundaries (failure and gap) | `test_consumers.py` (2 tests) | both failed first; probe passes |
| B11: stop in a later and a fresh-process log; versions and cutoff; UNKNOWN wording; headers | `test_simulated_run.py` (3), `test_order_log.py::test_an_unknown_order_never_claims_a_lookup…` | all failed first; 4 probes pass |
| B12: rejected intents; post-submission cancels; replay determinism; contract on both adapters; role objects; scenario 6; 20 races per writer; skip reasons | `test_order_invariants.py`, `test_broker_double_contract.py`, `test_simulated_broker.py::test_the_contract_suite_after_a_fill`, `process_harness.py` (CoreEngine), `test_execution_process.py::test_the_worker_stops_gracefully_too`, `test_fault_injection.py::test_6…`, `test_gate_concurrency.py` (2 free-race tests), `test_conversion.py` (4 skip reasons) | 13 of 13 sabotaged builds failed (see B12's entry) |
| B13: a fresh process decodes adjustments and reservations | `test_simulated_run.py::test_a_fresh_process_reads_snapshots…` | failed first (`'Adjustment'`); probe passes |

**Codex's probes, re-run** (the canonical file, SHA-256 `28e821d0…`, kept outside the commits): **18 of 20 pass** at `bbad2ea`. Two expectations no longer apply, by design and by the review's own fix text:
- **`test_normal_proposal_path_uses_recorded_fills`** calls `propose` *without* the order store and expects a SELL. B6 makes exactly that call fail closed; the CLI paths are tested instead.
- **`test_simulation_knowledge_window_includes_actions_since_declared_start`** builds knowledge from a truncated feed with no `known_from` and expects the full answer. That can't be known: B7 makes production knowledge declare its start, and a shorter history is Unavailable ("or report that it is unavailable").

## Deviations and scope, for explicit settlement

1. **Files outside the original task lists** (the review asked for a complete record):
   - `audit/registry.py` (B13);
   - `storage/postgres.py` (`connection_lost_errors`, B4);
   - `storage/schema_pg/0015_sim_broker_account.sql` (new, B9);
   - `core/engine.py` and `core/__main__.py` (B4, B12);
   - `oms/pipeline.py` (B6);
   - `execution/factory.py` (B9);
   - the M3 test `test_intents_cli.py` (B6, B11);
   - the helpers `test_intent_pipeline.py`, `worker_env.py` and `broker_doubles.py`;
   - plus the M4 deviations already listed by the review (`worker_env.py` in M4-07/11/12, `execution/__main__.py`, the factory and layering files).
2. **`declared_only=True`** (B6) is an explicit, test-only way to size on the declared start. A layering test pins that no package module sets it.
3. **The private `_decision_bar` import** (B3) keeps both replay paths on one lookup; it joins the replay-reader access debt.
4. **M3-14 rule 1's literal labels** are superseded by the true current state (B11; M4-13 rule 8).
5. **The test double** now follows the broker contract where it speaks (B12). Its scripted outcomes remain for everything else.
6. **CANCEL_PENDING with an EXPIRED message** stays an anomaly (G3 frozen, D25). The generators produce only valid timelines.

## Decisions for the owner

1. **Kill-switch acknowledgement (B8).** After a crash whose outcome can't be proven, a resume stays refused until an Admin acknowledgement procedure exists; a halt always works. Codex asked for any such procedure to be specified and reviewed, so none was improvised.
2. **No broker cursor (non-blocking 2).** Ingestion still reads the whole delivered stream each step; de-duplication by `broker_ref` and fill id is intact. A cursor needs a new migration and its own review.

## Non-blocking suggestions

| # | State |
|---|---|
| 1 | Done: `ChangeResult` and the accounting states aligned in M4-04 and M4-00; `order-log` read-only; stale "NOT BUILT" wording replaced (B11). |
| 2 | Recorded above (owner decision 2). |
| 3 | Open: duplicate stored views are still all proposed; a documented selection belongs to a later task. The layering fixture's bare `investment_engine.execution` import is unchanged. |
| 4 | Open: Fill validation still checks UTC only; quarantining impossible broker timestamps belongs with the external adapter (M7). The test fixtures now model earlier execution and later delivery (scenario 6). |
| 5 | Carried: M3's retained-database upgrade requirement, the pytest-internals password regressions, and the owner's PostgreSQL setup items. |

## Batch checks

- **Git Bash per commit:** see each entry; only the baseline cache-location test fails, every time.
- **Incident, recorded:** B11's and B12's first runs crossed midnight (2026-10-18 to 19) and showed 12 extra failures. They were upstream TradingAgents tests in `test_yahoo_rate_limit.py` and `test_undated_tools_as_of.py`, which fix "today" at session start and compare it with `date.today()` later. This package changes neither those tests nor `tradingagents/`; they passed alone on the same trees. Both commits were held until reruns on the unchanged trees were clean. The midnight sensitivity is an upstream test fragility, worth its own small fix later.
- **PowerShell full suite at `bbad2ea`:** **2 failed, 3327 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 2122.09 s. Both failures are the recorded PowerShell baseline (the cp1252 CLI test and the cache-location test). **No new failures.** An earlier run on the same head, during a period when the machine was three times slower (7607.82 s), also had `test_postgres_harness.py::test_a_failing_connection_setup_never_prints_the_password[default-short]` fail with a `subprocess.TimeoutExpired`: a nested pytest run exceeded its 120 s limit. No leak was asserted; that file then passed alone in PowerShell (66 passed in 88 s), and the full rerun above is clean. Both runs are kept.
- **Clean install** (fresh `py -3.11` venvs, base and engine; installed smoke from outside the repository with `-I`; schemas `0001`–`0015`): **passed** at `bbad2ea`, installed with `--force-reinstall --no-deps` from a fresh detached worktree of that commit. **Base:** 6 M4 modules from site-packages, psycopg absent. **Engine:** 22 modules; `schema_pg` `0001`–`0015`, the limits, fees and thresholds files packaged; `simulated` refuses PAPER; psycopg 3.3.6; the CI import passes in both.
- **Not run:** CI (nothing pushed); Python 3.12–3.14 and the TZ job; live providers or brokers; a PostgreSQL server restart (B4's tests terminate the backends server-side instead).
