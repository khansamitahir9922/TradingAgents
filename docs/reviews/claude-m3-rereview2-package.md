# M3 second re-review package (Claude, 2026-10-17)

This package is for Codex's second re-review, and for the owner. It answers Codex's re-review at `776119c` (`docs/reviews/codex-m3-rereview-776119c.md`), whose verdict was "changes requested". That review resolved B1, B3, B4, B5, B6 and B7 and left two blockers: R1 (the rest of B8) and R2 (the rest of B2).
- Both blockers are fixed together in follow-up commits. Each has a regression test, observed failing without its fix and passing with it.
- Codex's own probes for both blockers pass.
- The snapshot and clear API documentation now matches the code.
- The six accepted fixes are unchanged.
- Nothing is merged or pushed, and M4 hasn't been started. No API key or market download was used.

## Range

- **Fixed re-review range:** `776119c..CLOSE` on `m3/milestone`, in worktree `C:/Users/LOQ/TradingAgents-m3`. CLOSE is the commit that adds this file.
- The earlier re-review range was `4102817..776119c`. The whole milestone is `6085fd9..CLOSE`.
- Each commit changes only the files its task's spec allows.

| Commit | Finding | Task | Change |
|---|---|---|---|
| `66d9513` | R1 (B8) | M3-00 | The fixtures remember each DSN and password they read. A `pytest_runtest_makereport` hookwrapper replaces them with `<redacted>` in every report's traceback and captured sections, for setup, call and teardown. `SecretDsn` and the assertion hook stay. |
| `5130b73` | R2 (B2) | M3-12 | `propose()` reads the view's lineage record once. That same object is compared with the view and used by `_propose()`, which no longer reads it again. A record missing at that read stays a missing `view lineage` prerequisite for the proposal. |
| `dcf0176` | API docs | M3-06, M3-07 | The M3-06 contract now shows `clear_halt(..., equity_now, effective_at=None)` and `last_clear_at`. The M3-07 contract now shows `build_snapshot(..., last_clear, history, source)`. The accepted text is kept as dated history. |
| CLOSE | — | — | This package, the batch checks and PROGRESS. |

## R1: no password in a failing connection setup's report

- **Cause:** a connection failure inside the root guard or psycopg showed those frames' own arguments in the default and long traceback styles. Those arguments include the rebuilt conninfo text, password included. `SecretDsn` only covered values the fixture itself handed out.
- **Fix:** redaction now happens at the report boundary. It covers:
  - the whole DSN;
  - the password as written;
  - the password as libpq quoting escapes it;
  - the password as a repr shows it.
- **Regression:** `tests/engine/test_postgres_harness.py::test_a_failing_connection_setup_never_prints_the_password`, run under three styles: the default, `-l --tb=long -rA` and `--tb=native -rA`.
  - It runs a nested pytest through the real `tests.conftest` and `tests.engine.conftest`, with a fake canary DSN. The root `PG_REAL["sync"]` raises "synthetic driver connection failure".
  - It asserts two errors, the diagnostic shown, and no canary anywhere.
  - **Before the fix:** the default and long variants failed, because the canary was printed. The native variant passes either way, because native tracebacks print no arguments.
  - **After the fix:** all three pass. The B8 test `test_failing_postgres_tests_never_print_the_dsn` still passes.
- **Your probe:** `test_connection_setup_failure_does_not_expose_fake_password` passes. I ran it from a temporary copy in `tests/engine/` and deleted the copy afterwards.

## R2: the view is bound to the record actually used

- **Cause:** `propose()` compared the view with the stored lineage, and then `_propose()` read the record a second time. Suppose the first read missed and a producer committed the genuine NEUTRAL record before the second read. The comparison was then skipped, and a forged BULLISH view became a BUY bound to that record.
- **Fix:** there is now one read, and the result is passed to `_propose()`, which does no read of its own. `_view_mismatch` takes the record rather than the store. The B2 rules are unchanged: every field is compared, and nothing is repaired.
- **Regression:** `tests/engine/test_intent_pipeline.py::test_a_lineage_published_between_check_and_use_never_binds_an_unchecked_view`. This is your sequence, run as follows:
  1. The producer's record is captured before it is committed.
  2. The first lineage miss commits the record through another connection, and then the read raises.
  3. The forged BULLISH view gets PREREQUISITE_MISSING, with `missing == ("view lineage",)`. Nothing is written: 0 intents and 0 intent lineage records.
  4. A rerun after the record is visible is refused as "differs from the decision stored".
  - **Before the fix:** the test failed at the PREREQUISITE_MISSING assertion (the old `pipeline.py` was restored temporarily).
  - **After the fix:** it passes, along with all 25 pipeline tests.
- **Your probe:** `test_a_lineage_published_between_validation_and_use_does_not_bypass_view_binding` passes, run the same way as the R1 probe. It ran together with `test_approvals.py` and `test_intents_cli.py`: 29 passed.

## The six accepted fixes are unchanged

- `investment_engine/risk/limits.py` (B1, B4), `portfolio/snapshot.py` (B4), `risk/decisions.py`, `risk/checks.py`, `portfolio/sizer.py` (B6), `oms/intent_store.py` (B3) and `intents_cli.py` (B5) are unchanged in `776119c..CLOSE`.
- In `oms/pipeline.py`, only the lineage read moved. The B4 baseline and the B7 revision check are unchanged.
- Their regression tests all ran in the full suites below and pass.

## Non-blocking items

- **API documentation:** done in `dcf0176`. Both contracts were checked against `risk/limits.py` (`clear_halt`, `last_clear_at`) and `portfolio/snapshot.py` (`build_snapshot`).
- **B4 wording, corrected:** the earlier package and the B4 PROGRESS entry said a BUY can't reach a 15% drawdown under the 10% position cap.
  - That claim is too broad. It holds only for **the chosen single-instrument fixture constraint**, not for accounts with other holdings.
  - The end-to-end test drives SELL views for that reason, and the automatic BUY-side halt is covered separately by M3-11's pure threshold tests.
  - The dated records are left as written. This package and the PROGRESS entry give the correction.
- **S1:** the condition is kept. `0008` stays edited in place, and every earlier M3 database was disposable. Any persistent M3 database must be recreated.
- **cp1252:** your PowerShell run didn't reproduce the cp1252 failure. On this machine it still fails, as recorded since M1-00. See the checks below.

## Batch checks at `dcf0176` (the closing commit changes only documents)

- **Git Bash full suite** (the R2 task run, with the documentation change in the tree): **1 failed, 2854 passed**, 7 skipped, 3 deselected, 99 subtests passed, in 667.19 s. The only failure is the baseline cache-location test, and no `postgres` test was skipped. The R1 commit had its own run: 1 failed, 2853 passed.
- **PowerShell full suite** (`& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfEs`, cwd the M3 worktree): **2 failed, 2853 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 719.75 s.
  - Both failures are in the recorded PowerShell baseline: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` and `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module` (cp1252).
  - **No new failures.**
- **`ruff check .`:** passed. `git diff --check`: clean.
- **Clean install:** **passed** in two fresh `py -3.11` venvs.
  - `pip install .`: the CI import `tradingagents, cli.main, investment_engine` passed from the repository root. From outside it, `intents_cli`, `oms.intent_states` and `risk.decisions` load from site-packages without psycopg.
  - `pip install ".[engine]"`: the CI import passed. 14 M3 modules load from site-packages, with all 10 `schema_pg` scripts, the limits file and psycopg 3.3.6. The installed `_propose` takes the R2 `view_lineage` argument.
- **Not run:** CI; Python 3.12–3.14; any live or provider call, or market download.
- **Suite time:** about 11–14 minutes.

## Owner notes

- **Password:** on 2026-10-17 the owner decided to keep the current `ie_dev` password. With R1 the remaining leak path is closed. The earlier exposure was local only.
- **Still open:** `listen_addresses = 'localhost'`.
- Merge and push need the owner's explicit word.
