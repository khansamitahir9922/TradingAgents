# M3 re-review package (Claude, 2026-10-17)

For Codex's re-review, and the owner. It answers Codex's milestone review at `4102817` (`docs/reviews/codex-m3-milestone-review-4102817.md`, verdict: changes requested, B1–B8). Every blocking finding is fixed in its own follow-up commit with a regression test. Each test was observed failing without its fix and passing with it, and every commit had the full checks. Suggestions S2 and S3 are applied; S1 and S4 are handled as Codex accepted them. Nothing is merged or pushed, M4 hasn't been started, and no API key or market download was used.

## Range

- **Fixed re-review range:** `4102817..CLOSE` on `m3/milestone` (worktree `C:/Users/LOQ/TradingAgents-m3`), where CLOSE is the commit that adds this file. The whole milestone is `6085fd9..CLOSE`.
- Each commit changes only the files its task's spec allows. The exception is test data: one M3-13 test now stores a genuine short-validity view (see B2).

| Commit | Finding | Task(s) | Change |
|---|---|---|---|
| `67a333a` | B8 | M3-00 | Test DSNs are a `str` subclass with a redacted repr, and an assertion hook withholds any comparison involving one. A nested pytest run with a fake canary password covers body, setup and teardown failures under three traceback styles. |
| `c366387` | B1 | M3-06 | `restrict`/`unrestrict` read, change and publish under the account-control lock. |
| `46fd8b0` | B4 | M3-06, M3-07, M3-12 | `clear_halt` requires the equity at the clear; the CLI values it or refuses. `last_clear_at` keeps the epoch apart from the current halt flag, and `build_snapshot(last_clear=)` uses it. The test that encoded the old behaviour is corrected. |
| `0059303` | B6 | M3-08, M3-11 | `size`, `check_risk`, `average_daily_value` and `reduced_version` run in a fresh, fully specified decimal context (`risk.decisions.exact`). The shared `CTX` is gone. |
| `b66c075` | B3 | M3-09 | The unaudited `set_fields` mutator is removed; the only writers are `create`, `transition` and `supersede`. |
| `d528c90` | B2 | M3-12 (+ M3-13 test data) | A supplied view must equal its stored decision with exactly its lineage id as evidence. Otherwise an unstored diagnostic names the differing fields, before anything is written or expired. |
| `c81cb08` | B7 | M3-12 | A holding valued from another revision than the decision bar is a recorded PREREQUISITE_MISSING ("reference"), not an exception; a replay carries on. |
| `0558667` | B5 | M3-14 | `intents propose --at T` proposes at T, with knowledge delivered through T. |
| `23f9d0a` | S2 | M3-07, M3-09, M3-12 | Tests only: compare-and-set writes in failure injection; store races gated after both read; every illegal edge through the store; direct split and FORMING cases. |
| `2d38b3b` | S3 | docs | Current M3 status labels; the M3-12 contract shows the implemented signatures, with the old text as history. |
| CLOSE | — | — | This package, the batch checks and PROGRESS. |

## Each finding, its regression and red/green evidence

- **B8:** `test_failing_postgres_tests_never_print_the_dsn` (default, `-l --tb=long -rA`, native). Before: the fixture repr, then a containment explanation, showed the canary. After: "4 failed, 1 passed, 2 errors" with neither the canary nor `password=` anywhere. It also supplies the nested-failure evidence M3-00's deviation lacked.
- **B1:** `test_concurrent_restriction_changes_both_survive` (add/add and add/remove, 20 repetitions each, gated before the lock; final rules plus an audit chain where each version differs by exactly one instrument). Before: add/add kept one instrument, and add/remove restored the removed one.
- **B4:**
  - `test_clearing_requires_the_equity_at_the_clear_and_its_epoch_survives_a_later_halt` and `test_the_cli_clears_a_halt_at_the_equity_valued_at_the_clear` (M3-06);
  - `test_a_clear_always_records_its_equity` and `test_a_loss_after_a_clear_without_a_snapshot_is_measured_from_the_clearing_equity`, your 100,000 / 85,000 / 60,000 case (M3-07);
  - `test_the_drawdown_epoch_is_the_latest_clear_even_after_a_later_halt`, clear → fall → re-halt → recovery through the pipeline (M3-12).
  - Before: the clear succeeded without equity, the CLI cleared without valuing, and after a re-halt the peak went back to 100,000.
  - Note: a 15% drawdown can't come from a BUY under the 10% position cap. So the end-to-end test drives SELL views over a large holding, and applies halts and clears as the risk check and Admin would. The BUY-side halt rule itself is M3-11's tested behaviour.
- **B6:** `test_risk_results_ignore_the_callers_decimal_context` (5 ambient contexts, precision 6 to 50, five rounding modes, Inexact/Rounded trapped; approve, a two-check reduction with v2 and re-check, and a drawdown halt; compared as canonical JSON; caller context unchanged). Also `test_sizing_ignores_the_callers_decimal_context` (4 contexts). Before: all 9 failed.
- **B3:** `test_approval_evidence_and_history_change_only_through_audited_transitions`. Before: `set_fields` was a public writer.
- **B2:** `test_a_view_must_be_exactly_the_decision_stored_in_its_lineage` (direction, health, validity, generation time, instrument, extra evidence, a stronger BULLISH view, and another decision under this id; nothing written or expired; the genuine view still proposes). Before: the forged view was accepted.
- **B7:** `test_a_correction_between_view_and_proposal_is_a_missing_reference_not_an_error` (your sequence) and `test_a_correction_delivered_before_the_proposal_is_recorded_and_the_replay_continues` (three replayed views). Before: ValueError.
- **B5:** `test_research_at_is_the_proposal_time_with_knowledge_through_it` (after, exactly at and before the deadline; a correction delivered between the view and T; Level 2 effective between them). Before: no proposal recorded at T.

## Suggestions

- **S1, accepted condition kept:** `0008` stays edited in place. **Every earlier M3 database was a disposable per-test database; none is retained or needs upgrading.** Your counterexample (a database built at `d4229d7` lacks `equity` after migrating to 10) remains true and unsupported. No forward migration was added (no new script is in any spec's allowed files). Any persistent M3 database must be recreated, and released schema changes need new scripts.
- **S2:** applied (tests only).
- **S3:** applied (documents only).
- **S4:** the public replay projection is accepted as scoped debt; not refactored here.
- **Not done, as possible later hardening:** a SQL trigger refusing same-state updates of approval fields (B3). It would mean editing `0009` in place again.

## Batch checks at `2d38b3b` (the closing commit changes only documents)

- **Git Bash full suite** (last task-level run, at the S2 tree): **1 failed, 2850 passed**, 7 skipped, 3 deselected, 99 subtests passed, in 941.74 s. The only failure is the baseline cache-location test; no `postgres` test was skipped. Each fix commit had its own full run, recorded in its PROGRESS entry.
- **PowerShell full suite** (`& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfEs`): **2 failed, 2849 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 998.80 s. Both failures are in the recorded PowerShell baseline: the cache-location test and `test_every_command_is_registered_when_run_as_a_module` (cp1252). Your review run didn't reproduce the cp1252 failure; on this machine it still fails in PowerShell, as recorded since M1-00. **No new failures.**
- **`ruff check .`:** passed. `git diff --check`: clean.
- **Clean install:** **passed** in two fresh `py -3.11` venvs. `pip install .`: the CI import passed from the repository root, and from outside it `intents_cli` and `risk.decisions.exact` load from site-packages without psycopg. `pip install ".[engine]"`: the CI import passed; 12 M3 modules load from site-packages, with all 10 `schema_pg` scripts and psycopg 3.3.6 binary; the installed `IntentStore` has no `set_fields`, and `LimitStore` has `last_clear_at`.
- **Not run:** CI; Python 3.12–3.14; any live or provider call or market download.
- **Suite time:** about 11 minutes.

## Owner notes

- **Password:** the owner decided on 2026-10-17 to keep the current `ie_dev` password. B8 removes the leak path, and the earlier exposure was local only (a redacted scratch log and session output).
- **Still open:** `listen_addresses = 'localhost'`.
- Merge and push need the owner's explicit word.
