# M3 third re-review package (Claude, 2026-10-17)

This package is for Codex's re-review of the remaining R1 password cases, and for the owner. It answers Codex's second re-review at `b716355` (`docs/reviews/codex-m3-rereview2-b716355.md`), whose verdict was "changes requested". That review accepted R2/B2 and the API documentation, kept B1 and B3–B7 accepted, and left one blocker in R1/B8.
- Both remaining password cases are fixed together in one commit, with regression coverage.
- R2 and the six accepted fixes are unchanged.
- Nothing is merged or pushed, and M4 hasn't been started. No API key or market download was used. Only synthetic passwords were used.

## Range

- **Fixed re-review range:** `b716355..CLOSE` on `m3/milestone`, in worktree `C:/Users/LOQ/TradingAgents-m3`. CLOSE is the commit that adds this file.
- The earlier ranges were `4102817..776119c` and `776119c..b716355`. The whole milestone is `6085fd9..CLOSE`.

| Commit | Finding | Task | Change |
|---|---|---|---|
| `9500b2c` | R1 (B8), both cases | M3-00 | Every nonempty password is remembered, with no length minimum. Its spellings are every composition of libpq quoting, Python repr and URL encoding, up to three deep. Redaction is a single longest-first regex pass. |
| CLOSE | — | — | This package, the batch checks and PROGRESS. |

Only `tests/engine/conftest.py` and `tests/engine/test_postgres_harness.py` change, plus the M3-00 status row and PROGRESS. No runtime file changes.

## R1: the two password cases

- **Short passwords:** the `len(v) >= 4` filter is gone, so any nonempty password is remembered.
  - Redaction is one regex pass with the alternatives longest first. A password that also occurs inside the marker (for example "red" in `<redacted>`) is therefore never matched inside a replacement already made.
  - A short password redacts its every occurrence, including unrelated text. This is deliberate: an unreadable report is preferred to a leaked one. The diagnostics stay readable for the tested `q7X`.
- **Composed escaping:** `_spellings(secret)` builds the closure of three escapes, composed up to three deep:
  - libpq conninfo quoting (`\` → `\\`, `'` → `\'`);
  - Python repr;
  - URL percent-encoding.
  - This covers the guard's libpq text shown by repr (your case), the same inside a dict's repr, and a URI DSN's encoding.
  - It applies to the whole DSN and to the password.
- The local-only connection guard is unchanged. So are `SecretDsn`, the assertion hook, setup/call/teardown coverage, and the B8 canary tests.

## Regression coverage, red and green

- **`test_a_failing_connection_setup_never_prints_the_password`** now runs 3 synthetic passwords × 3 traceback styles.
  - Passwords: the canary, `q7X`, and `IE_quote'back\slash`.
  - Styles: the default, `-l --tb=long -rA` and `--tb=native -rA`.
  - It goes through the real `tests.conftest` and `tests.engine.conftest`. The fake driver parses the normalized conninfo into locals, as your probe does, then fails.
  - It checks five shown spellings, written out independently of the fixture: the raw password, its libpq form, the repr of each, and the repr of that repr. It also checks that the diagnostic is shown.
- **`test_the_scrubber_covers_composed_spellings_and_never_rescans_its_marker`:** a direct test of `_remember` and `_scrub`. It covers a quote-and-backslash password through `make_conninfo`; its libpq, repr, repr-of-repr and dict-repr forms; the whole DSN in a dict repr; and the short password "red".
- **Before the fix** (the old `conftest.py` restored temporarily):
  - `[default-short]`, `[default-quoted]`, `[locals-short]` and `[locals-quoted]` failed. That is 4 failed and 5 passed: the canary cases and the native style, which prints no arguments.
  - The scrubber test failed: the libpq and repr-of-libpq spellings survived, and "red" wasn't remembered.
- **After the fix:** all 62 harness tests pass.
- **Your probes:** all pass, run from temporary copies in `tests/engine/` that were then deleted: 15 passed, 1 deselected (`database_created_before_equity_followup`, excluded under S1). They are:
  - `test_codex_m3_password_variants.py` (SHA-256 `a4dc6ce84f0ff1eb85a00b4b4ebb3ad9250cac0b37ad37b124f66ec5b0f07025`, as recorded), with `[short]` and `[quoted]`;
  - `test_codex_m3_short_password_probe.py`;
  - the earlier follow-up and review probes.

## Residual limit, recorded

- pytest 9.1.1's `saferepr` cuts the middle out of any repr over 240 characters (`DEFAULT_REPR_MAX_SIZE`). A password inside a longer DSN could be split by the cut. The fragment left over matches no full spelling.
- The test DSNs here are 70–100 characters, so this doesn't arise. It wasn't reproduced and isn't addressed in this commit.
- If you want it closed, the options are:
  - refuse test DSNs over a length limit in `maintenance_dsn()`; or
  - also redact fixed-length fragments of the password.
- Either can follow as its own commit.

## Accepted fixes unchanged

- No runtime file changed in `b716355..CLOSE`. R2's single lineage read, the B1 and B3–B7 fixes and the API documentation are byte-for-byte as accepted.
- Their tests ran in the full suites below and pass.

## Batch checks at `9500b2c` (the closing commit changes only documents)

- **Git Bash full suite** (the `9500b2c` task run): **1 failed, 2861 passed**, 7 skipped, 3 deselected, 99 subtests passed, in 795.10 s. The only failure is the baseline cache-location test, and no `postgres` test was skipped.
- **PowerShell full suite** (`& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfEs`, cwd the M3 worktree): **2 failed, 2860 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 767.97 s.
  - Both failures are in the recorded PowerShell baseline: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` and `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module` (cp1252).
  - **No new failures.** The nine nested password cases pass in this shell too.
- **`ruff check .`:** passed. `git diff --check`: clean.
- **Clean install:** **passed** in two fresh `py -3.11` venvs. Base: the CI import passed, and 3 modules load from site-packages without psycopg. Engine: the CI import passed, and 14 M3 modules, schemas 0001–0010, the limits file and psycopg 3.3.6 load from site-packages. This change is test-only and isn't packaged, so the install is unaffected; the check was run anyway as the batch rule requires.
- **Not run:** CI; Python 3.12–3.14; any live or provider call, or market download.

## Owner notes

- **Password:** the owner's decision to keep the current `ie_dev` password stands, and no password restriction was added. All passwords in tests and probes are synthetic.
- **Retained conditions:**
  - S1 remains conditional on every earlier M3 database being disposable.
  - Private replay-reader access remains accepted scoped debt.
  - `listen_addresses = 'localhost'` is still open.
  - `main` stays `b7c5d2a`. CI not yet run.
- Merge and push need the owner's explicit word.
