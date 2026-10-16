# M2 second re-review package (Claude, 2026-10-16)

For Codex: a re-review of the fixes to `docs/reviews/codex-m2-rereview-ee12160.md` (stored in the root checkout). The owner approved fixing R1 and R2 together, with regression tests first, follow-up commits and the required checks. No merge, push, M3, keys or downloads.

**Range:** `ee12160..m2/milestone`. It holds one fix commit, `cd20083`, and the closing documentation commit that adds this file. Worktree `C:/Users/LOQ/TradingAgents-m2`. The accepted B1–B6 and S1–S4 fixes are unchanged.

| Finding | Commit | Fix | Regressions |
|---|---|---|---|
| R1 (P1) | `cd20083` | The S3 audit fields of `DirectionEvaluation` (`trailing_refs`, `last_period_sample`, `last_period_excluded`) are `None` when not recorded. The codec omits fields a class lists in `LINEAGE_LATER_FIELDS` while they are `None`. A `57d4316` record therefore decodes with them `None` and re-encodes to its original payload and id, and the hash check is unchanged. `evaluate_direction` always records all three; an empty tuple is a recorded empty sample. They are set together or not at all. The report says "last-period sample not recorded in this record (earlier format)". No rows or ids are rewritten. No lineage class uses the list, so lineage ids are unaffected. | A genuine `57d4316` record (`tests/engine/fixtures/evaluation/record-57d4316.json`, written by that commit's own `EvaluationRunStore.append`; id `eval-8bee2622…`, as in your probe) is inserted into a schema-3 database and upgraded to schema 4. It then reads back with its id and payload intact, and re-appending it is idempotent with the bytes unchanged. Also covered: corruption detected in both formats; a current record round-trips with its sample; a recorded empty sample hashes differently from "not recorded"; partial audit fields are refused; the report's not-recorded label. |
| R2 (P2) | `cd20083` | `check_fold_periods(record, calendars)`: each run's first session must open at its fold's `test_start`, and the session after its last must open at `test_end`, on `calendars[record.calendar_version]`. No guessing from calendar days. `EvaluationRunStore(conn, *, calendars)` checks on append and on read, and `render_research_report(..., calendars=...)` checks before rendering. Each fold now shows its run's actual sessions. An unfinished fold requests its whole window and stays INCOMPLETE (B3). Partial-window evaluations are not supported. `computed_record` now simulates the whole fold (2021-01-04 to 2021-07-01). | Refused by the store and by the check, with nothing stored: truncated start, truncated end (the ten-session case), a start before the fold and an end after it. Accepted: a complete fold and an unfinished fold. An undeclared calendar version is refused. The genuine old record passes the period check. The report refuses a short run and shows the actual sessions. |

**Red evidence (honest note).** The new pytest regressions first failed at collection, because `check_fold_periods` and the `calendars` argument didn't exist yet. The behavioural failures were observed by running the same scenarios against an export of `ee12160` (`git archive`):

- the old record's read failed with "stored content for eval-8bee2622… hashes to eval-be98ac10…";
- all four mismatched run periods were accepted.

**Interface change:** the `calendars` keyword argument on `EvaluationRunStore` and `render_research_report`. Contracts are updated in M2-11b and M2-12, and the format rule in M2-09 and M2-07. M2-11b's allowed files now list the fixture.

**For your judgement (non-blocking):**
- Calendars carry no version in M1. `calendars` therefore maps the declared version string to the calendar the caller asserts it is, and the check can't prove that the object matches the version.
- Reading a record now requires its declared calendar.

## Checks (at `cd20083`)

- **Git Bash full suite:** **2390 passed, 1 failed** (the baseline cache-location test), 4 skipped, 3 deselected, 99 subtests.
- **PowerShell full suite:** **2389 passed, 2 failed**, 4 skipped, 3 deselected. Both failures are recorded in the baseline: `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module` (cp1252) and `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`. **No new failures.**
- **`ruff check .`** passed; whitespace is clean.
- **Clean install:** fresh venv from the project's Python 3.11.9, `pip install` of the worktree. The outside-repository smoke check passed: the M2 modules load from site-packages, schemas 0001–0004 ship, a new database migrates to version 4, and the append-only guards hold.
- **Not run:** CI, other Python versions, live calls or downloads.

## Regenerated report

- **Output:** `C:/Users/LOQ/TradingAgents-proposals/m2-report/nvda-research-report.html`, built from code at `cd20083`, offline from the same verified recordings. `build_report.py` passes `calendars={calendar_version: CAL}`, and all 22 fold periods passed the new check.
- **Unchanged:** every metric. The summary differs from the `9f8ab57` build only in `code_version`, the two record ids and the HTML size and hash. The ids are now `eval-5a31a537e55a8cd…` (5 bps) and `eval-b55626a90a720d3…` (10 bps); they changed only because `code_version` names the commit.
- **HTML:** 376,352 bytes, SHA-256 `38fa8bc6369c79a900a5f45d36c40fce3286fc17431bf070144bd87d005a27e6`, equal to `summary.json`. Each fold now shows its run's sessions and its last-period sample: between 73 and 127 paired sessions per fold, 0 excluded.
