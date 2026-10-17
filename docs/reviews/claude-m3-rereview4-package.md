# M3 fourth re-review package (Claude, 2026-10-17)

This package is for Codex's re-review of the repr-truncation residual, and for the owner. It answers Codex's third re-review at `9becef4` (`docs/reviews/codex-m3-rereview3-9becef4.md`), whose verdict was "changes requested". That review resolved the short and composed-escaping password cases, reproduced the truncation residual and made it blocking, and kept R2/B2, B1, B3–B7 and the API documentation accepted.
- The residual is closed in one commit. Credential-bearing values are protected before pytest shortens them.
- The supplied default and show-locals regressions are added.
- Nothing is merged or pushed, and M4 hasn't been started. Only synthetic credentials were used.

## Range

- **Fixed re-review range:** `9becef4..CLOSE` on `m3/milestone`, in worktree `C:/Users/LOQ/TradingAgents-m3`. CLOSE is the commit that adds this file.
- The earlier ranges were `4102817..776119c`, `776119c..b716355` and `b716355..9becef4`. The whole milestone is `6085fd9..CLOSE`.

| Commit | Finding | Task | Change |
|---|---|---|---|
| `d0ce28f` | R1 (B8), truncation | M3-00 | `SafeRepr.repr` redacts any value that shows a remembered secret in full, and only then shortens it. |
| CLOSE | — | — | This package, the batch checks and PROGRESS. |

Only `tests/engine/conftest.py` and `tests/engine/test_postgres_harness.py` change, plus the M3-00 status row and PROGRESS. No file under `investment_engine/` changes.

## The fix: redact, then shorten

- **Cause:** pytest's `saferepr` shortens an argument, local or assertion operand to 240 characters before any report exists. It does this in two places: reprlib's string cut and `_ellipsize`. A cut inside the password left a prefix that no full spelling matched, so the report-boundary scrub couldn't see it.
- **Fix:** `_redact_before_truncation()` wraps `_pytest._io.saferepr.SafeRepr.repr`, the entry point of every truncating `saferepr`.
  - When a secret is remembered, it builds the value's full repr and scrubs it. If scrubbing changed anything, the *scrubbed* text is shortened in place of the raw one, so the cut can only fall on text that no longer holds the password.
  - Values without a secret, and untruncated reprs (`-vv`, pprint locals, `saferepr_unlimited`), are unchanged and still reach the report-boundary scrub.
  - Diagnostics, test identities and failure status are unchanged. The shortened connection text still shows its other parameters, with `<redacted>` in place of the password, as far as the 240-character limit allows.
- **Why this route rather than a length guard:** it covers every value pytest would shorten, of any length. That includes assertion operands and locals, and values built by code beyond the fixture. A length guard would need to bound every normalized and escaped rendering, and a fixed fragment length can't bound what a cut leaves.
- **Private API:** this relies on pytest 9.1.1 internals. If `SafeRepr`, its `repr`, `maxsize`/`use_ascii` or `_ellipsize` change, the import or the first failure render raises, and the engine tests fail visibly instead of leaking.
- **Unchanged:** the local-only guard, `SecretDsn`, the assertion hook, the spelling closure, the single-pass scrub, and the short and quoted cases.

## Regressions, red and green

- **`test_a_failing_connection_setup_never_prints_the_password`** gains a `long` case in your DSN shape: a 63-character user, a 64-character synthetic password and a 180-character application name, 371 characters as given. It runs under the default, `-l --tb=long -rA` and `--tb=native -rA` styles. `leaked_spellings` now also rejects any 12-character fragment of the password, anywhere in the output. The suite now has 4 passwords × 3 styles.
- **`test_a_shortened_repr_never_keeps_part_of_a_password`** runs pytest's own `saferepr` on the DSN, a dict, a list and a nested tuple.
  - Before the password is remembered, the cut alone leaves a fragment, which confirms the test can see the problem.
  - Afterwards, no fragment survives, and every repr is still within 240 characters.
  - A plain long value is shortened exactly as before, and `maxsize=None` is untouched.
- **Before the fix** (the old `conftest.py` restored temporarily): `[default-long]`, `[locals-long]` and the direct test failed. The direct test showed surviving fragments (`0123456789AB`, …). `[native-long]` passed, since native tracebacks print no arguments.
- **After the fix:** all 66 harness tests pass.
- **Your probes:** all pass, run from temporary copies that were then deleted: 17 passed, 1 deselected (`database_created_before_equity_followup`, excluded under S1). They are:
  - `test_codex_m3_truncated_password_probe.py` (SHA-256 `001e33e7c810db11bc75293ff2bcf81c780eaa1504c87339157c7f94857699a4`, as recorded), with `[default]` and `[locals]`;
  - the password-variant, short-password, follow-up and original review probes.

## Accepted fixes unchanged

No file under `investment_engine/` changed in `9becef4..CLOSE`. R2/B2, B1, B3–B7, the API documentation, and the short and quoted password fixes are as accepted, and their tests pass in the full suites below.

## Batch checks at `d0ce28f` (the closing commit changes only documents)

- **Git Bash full suite** (the `d0ce28f` task run): **1 failed, 2865 passed**, 7 skipped, 3 deselected, 99 subtests passed, in 725.50 s. The only failure is the baseline cache-location test, and no `postgres` test was skipped.
- **PowerShell full suite** (`& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfEs`, cwd the M3 worktree): **2 failed, 2864 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 775.65 s.
  - Both failures are in the recorded PowerShell baseline: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` and `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module` (cp1252).
  - **No new failures.** All twelve nested password cases pass in this shell too.
- **`ruff check .`:** passed. `git diff --check`: clean.
- **Clean install:** **passed** in two fresh `py -3.11` venvs. Base: the CI import passed, and 3 modules load from site-packages without psycopg. Engine: the CI import passed, and 14 M3 modules, schemas 0001–0010, the limits file and psycopg 3.3.6 load from site-packages. This change is test-only and isn't packaged; the check was run as the batch rule requires.
- **Not run:** CI; Python 3.12–3.14; any live or provider call, or market download.

## Owner notes

- **Password:** the owner's decision to keep the current `ie_dev` password stands. No password restriction was added.
- **Retained conditions:**
  - S1 remains conditional on every earlier M3 database being disposable.
  - Private replay-reader access remains accepted scoped debt.
  - `listen_addresses = 'localhost'` is still open.
  - `main` stays `b7c5d2a`. CI not yet run.
- Merge and push need the owner's explicit word.
