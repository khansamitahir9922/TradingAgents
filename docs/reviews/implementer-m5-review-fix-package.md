# M5 independent-review follow-up package

**Implementer: Codex. Independent reviewer: Claude Code. Not independently accepted.**

Original snapshot: `e0a668e`. Claude's review is at `C:/Users/LOQ/TradingAgents/docs/reviews/claude-m5-review-e0a668e.md`: B1 blocking, N1-N6 non-blocking. The owner explicitly authorized the B1 migration/read guards, probe variants, follow-up commits and this handoff. Nothing is merged or pushed; main remains at accepted M4 `5cd9363`. No M6, keys, market downloads, owner database restore/reset or installed backup schedule.

## Commit map

| Commit | Change |
|---|---|
| `c2a2b5e` | B1: additive schema 0019, read-time row cross-checks, red/green regressions, upgrade test and PROGRESS/open findings |
| `1700ced` | B1 self-review: locale-independent row ordering; valid opaque-ID reads and idempotent retries |
| This documentation follow-up | Final observed package checks and independent re-review handoff; no runtime/test changes |

## B1: journal/read-model agreement

0016-0018 are unchanged. Migration 0019 replaces the deferred **function**, retaining the existing triggers and invariant checks. It verifies batch header/count fields, transaction IDs/account/times/reversal links, ordered entry content/count/manifest hashes, source IDs/keys/full receipt payloads/content hashes/source-set hash, and lot IDs/full payloads/book references. The SQL canonical codec matches the existing Python codec, including ASCII escaping and Unicode surrogate pairs; no serializer, economic ID or financial policy changed. A separate deferred activation check requires the account's version-1 book.

`LedgerStore._load` also checks decoded batches against the stored header, transaction manifests and ordered entry payloads, complete source receipts and lot evidence. This refuses inconsistent pre-0019 records without rewriting them, even though the new SQL trigger does not retroactively rewrite or repair historical rows. Activation reads also verify account and first-book identity.

Claude's original P1 probe is unchanged, SHA-256 `80a484d5a6f105606aca398930cc5c9c930a4c96d3c4cbd7830afb9653b4577d`. Its exploit is adapted into a **refusal** regression in `tests/engine/test_ledger_store.py`, with valid source keys so the transaction case reaches the actual ledger mismatch. The original success-of-exploit assertion is not treated as an acceptance test that must continue to pass.

| Tampering scenario | New database refuses | Pre-0019 read refuses |
|---|---|---|
| Sealed CASH 5, batch copy CASH 1,000,000 | Yes | Yes |
| Batch source differs from stored receipt | Yes | Yes |
| Batch lot cost differs from sealed lot evidence | Yes | Yes |
| Wrong source-set hash | Yes | Yes |
| Receipt hash differs from receipt content | Yes | Yes |
| Receipt content differs under the same source ID | Yes | Yes |

Additional tests cover codec parity (DEL, escaped controls/quotes/backslashes, accented/CJK and supplementary characters), refusal of a later-book activation, and a populated valid 0018-to-0019 upgrade that preserves every existing row and then refuses the exploit. Existing restatement, historical-query, reporting, demo and consumer-recovery tests passed.

## Observed focused checks

`ROOTPY` is `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe`. Evidence/helper directories are `C:/Users/LOQ/TradingAgents-proposals/codex-m5-implementation/` (red and broad green) and `C:/Users/LOQ/TradingAgents-proposals/codex-m5-review-fixes/` (final focused and full-package checks). The redacting runners inherit the private PostgreSQL test DSN; credentials are not passed in command arguments or printed.

- **Red, original `e0a668e`:** `ROOTPY <implementation>/run_b1_baseline.py bash m5-b1-final-red tests/engine/test_ledger_store.py::test_sql_batch_copy_must_match_its_sealed_rows tests/engine/test_ledger_store.py::test_load_refuses_pre_0019_divergent_book`: **12 failed in 20.40s**, all DID NOT RAISE. The implementer-owned baseline checkout contains only copied new tests; the reviewer's checkout/probe was not edited.
- **Broad green:** `ROOTPY <implementation>/run_check.py bash m5-b1-green-final tests/engine/test_ledger_store.py tests/engine/test_ledger_upgrade.py tests/engine/test_ledger_restatements.py tests/engine/test_ledger_time.py tests/engine/test_postgres_schema.py tests/engine/test_m5_accounting_demo.py tests/engine/test_accounting_reports.py tests/engine/test_ledger_consumer_recovery.py`: **102 passed in 237.85s**, no skips.
- **Focused green for the first B1 commit:** `ROOTPY <review-fixes>/run_check.py bash b1-focused-final tests/engine/test_ledger_store.py tests/engine/test_ledger_upgrade.py`: **42 passed in 65.03s**, no skips, after the lint-only import-order correction. The final implementation's 104-test check follows below.
- `ROOTPY -m ruff check .`: **passed** before the B1 commit. Staged whitespace check: **passed**.
- Early test iterations had fixture errors (unchanged source hash, inconsistent fake references, trailing whitespace in a name and wrong expected deferred exception type). These were corrected and the final red run repeated against original runtime; no original acceptance test or production restriction was weakened.

## B1 self-review correction: opaque IDs and database collation

`c2a2b5e` assumed native database ordering equalled Python string ordering. Two valid books with opaque transaction or lot IDs `B` and `a` committed successfully but then falsely raised `SourceConflict` on this Windows PostgreSQL locale. Isolated `b1-collation-red` on `c2a2b5e`: **2 failed in 14.16s**, at the intended read assertions. The new read queries explicitly use `COLLATE "C"`, including entry grouping and receipt/lot ordering. All row-content and hash checks remain exact; IDs are neither narrowed to lowercase nor rewritten. Migration 0019 is unchanged.

`ROOTPY <review-fixes>/run_check.py bash b1-collation-green` with the same eight own/affected files as broad green above: **104 passed in 283.32s**, no skips. The new cases also verify idempotent retry. Ruff passed before commit `1700ced`.

The intermediate daytime full check on `c2a2b5e` was deliberately interrupted after the defect was reproduced, before implementation changes. Only its verified owned pytest process was stopped, not PostgreSQL. It has no final result and is not counted as a pass. Partial log: `full-git-bash-interrupted-collation-fix.log`, SHA-256 `cef4cda780cb9bffa39911d0c313b4c76340d0099883eba098763f984a532f43`. Full verification was restarted on `1700ced`; its completed results are below. No mixed-code run is accepted. This correction was implementer self-review, not a new Claude finding or an independent acceptance.

## N1-N6 remain open

All six findings are explicitly recorded in PROGRESS's open-issues table. None is claimed fixed here.

- **N1:** retain specific planning-gap reason and unposted source reference in a separate diagnostics follow-up, covering insufficient FIFO basis, fractional split and unresolved-order/action failures. Deferred to isolate the storage correction; current behavior remains fail-closed but its generic reason is insufficient. No claim that the missing detail is harmless reporting compliance.
- **N2:** advancing-clock/cutoff equality and readiness freshness need M7 design and moving-clock tests before PAPER/live use.
- **N3:** classify expected stale/missing accounting evidence into typed proposal unavailability without swallowing actual database faults, before concurrent live operation.
- **N4:** repeated sources, unindexed source-key scans, full ancestry reads and repeated broker-message scans need profiling/index/cursor work before long runs. B1 adds read verification, not a performance improvement.
- **N5:** replace the harness's full Core service on the Worker with a narrow read-only verifier and composition-level boundary tests before production wiring. No write was observed; AST import tests do not establish capability isolation.
- **N6:** only the hand-constructed accounting scenario was delivered. The full saved-range offline NVDA report remains an owner choice; it was not run in this fix and is not profitability evidence. No downloads are authorized.

## Full package verification

Verification on unchanged runtime/test commit `1700ced`:

- `ROOTPY C:/Users/LOQ/TradingAgents-proposals/codex-m5-review-fixes/run_check.py bash full-git-bash`: **1 failed, 3803 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 4476.75s (1:14:36)**.
- `ROOTPY C:/Users/LOQ/TradingAgents-proposals/codex-m5-review-fixes/run_check.py powershell full-powershell`: **1 failed, 3803 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 23073.07s (6:24:33)**.
- Actual failure IDs: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`. These are recorded baseline failures, not new findings. No setup errors or PostgreSQL credential skips. See complete logs for all skip reasons; no test was weakened or excluded for this fix.
- `ROOTPY C:/Users/LOQ/TradingAgents-proposals/codex-m5-review-fixes/fresh_installs.py`: **PASS**, genuinely fresh base and engine installations retained at `C:\Users\LOQ\AppData\Local\Temp\ie-m5-install-0jtcxxzf`. Installed SQL resources include **0019**. Root CI-style imports and outside-repository installed imports passed; optional engine libraries remain lazy and are absent from base, present in engine.
- The helper `package_checks.py` ran the complete suites sequentially on unchanged code. The earlier failed date-boundary run and the interrupted intermediate-collation run are retained in this package; full checks were repeated only after those unresolved concerns, not per commit. A temporary thread-scoped Windows system-awake request was cleared on exit; no power-plan setting changed.
- `ROOTPY -m ruff check .`, whitespace and exact task-path checks passed before handoff; final scope check is repeated after the documentation commit. Main remains clean at `5cd9363`. Old migrations 0001-0018, architecture/diagrams, original TradingAgents paths, dependencies, CI and shared-rules files are unchanged from `e0a668e`.
- The original synthetic demonstration artifacts were not regenerated or relabelled as a historical run. New-code end-to-end accounting/demo assertions passed in the focused and full checks. No new data source, keys, owner database restore/reset or backup schedule.
- CI not run; no M5 merge, push or M6. B1 awaits Claude's independent re-review; N1-N6 remain open, not fixed by this package.

`ROOTPY` = `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe`. Full evidence root: `C:/Users/LOQ/TradingAgents-proposals/codex-m5-review-fixes`. Git Bash log SHA-256 `4c21a19ac22f5bc70cd97bb80e5faf5f981adcf3697a88202a50acb349ebce42`; PowerShell log SHA-256 `cd13d41d293e1a08324a5a2d8b79ea057df94cbf2cdb38787cb4e111386ed6b2`; fresh-install log SHA-256 `ca9448a0ed301ebadcbcbf9d1ca4cc34f117d3cfb970aa7971896dc0ed20e93e`.



### Unaccepted first full Bash run: collection date crossed midnight

The first full run crossed from 2026-10-22 into 2026-10-23: **13 failed, 3789 passed, 7 skipped, 3 deselected, 99 subtests passed in 35766.41s (9:56:06)**. One failure is the cache-location baseline; the other twelve are **new for this run, not baseline failures**. The runner stopped before PowerShell/install checks. The trace shows `2026-10-22` cached by parameter construction at collection, while unchanged vendor point-in-time guards compare against the actual execution date and withhold past-date live data. All affected code/tests are unchanged from `e0a668e`; no date was frozen, test excluded or behavior changed.

Failed IDs:

- `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`
- `tests/test_undated_tools_as_of.py::test_a_yfinance_failure_is_a_vendor_error_not_a_report[get_balance_sheet-args1]`
- `tests/test_undated_tools_as_of.py::test_a_yfinance_failure_is_a_vendor_error_not_a_report[get_cashflow-args2]`
- `tests/test_undated_tools_as_of.py::test_a_yfinance_failure_is_a_vendor_error_not_a_report[get_income_statement-args3]`
- `tests/test_undated_tools_as_of.py::test_a_yfinance_failure_is_a_vendor_error_not_a_report[get_insider_transactions-args4]`
- `tests/test_yahoo_rate_limit.py::test_a_yahoo_request_that_fails_is_unavailable_not_absent[fundamentals]`
- `tests/test_yahoo_rate_limit.py::test_a_yahoo_request_that_fails_is_unavailable_not_absent[statement]`
- `tests/test_yahoo_rate_limit.py::test_a_yahoo_request_that_fails_is_unavailable_not_absent[insider]`
- `tests/test_yahoo_rate_limit.py::test_a_request_that_yfinance_would_swallow_is_unavailable[fundamentals]`
- `tests/test_yahoo_rate_limit.py::test_a_request_that_yfinance_would_swallow_is_unavailable[statement]`
- `tests/test_yahoo_rate_limit.py::test_a_request_that_yfinance_would_swallow_is_unavailable[insider]`
- `tests/test_yahoo_rate_limit.py::test_yahoo_answering_not_found_is_no_data[fundamentals]`
- `tests/test_yahoo_rate_limit.py::test_yahoo_answering_not_found_is_no_data[insider]`

The complete redacted log is retained as `C:/Users/LOQ/TradingAgents-proposals/codex-m5-review-fixes/full-git-bash-midnight-crossing.log`, SHA-256 `1396a9494892339946d816b17135d184024a43e7fda81554b58fba72689efb29`. Exact diagnostic rerun: `ROOTPY C:/Users/LOQ/TradingAgents-proposals/codex-m5-review-fixes/run_check.py bash date-failures-rerun tests/test_undated_tools_as_of.py tests/test_yahoo_rate_limit.py`: **61 passed in 8.70s** on unchanged code. That focused rerun did not replace the full check. Source was still `c2a2b5e` at this checkpoint; the next daytime attempt was interrupted for the collation correction, followed by the completed full checks on `1700ced` above. The existing upstream midnight-test debt is not fixed by B1.

## Re-review

Claude should review the fixed follow-up range after `e0a668e`, confirm B1's database and legacy read guards with the probe variants, and confirm the accepted original behavior remains. N1-N6 remain unresolved as recorded. This is an implementer fix package, not independent acceptance. Do not merge, push or start M6.
