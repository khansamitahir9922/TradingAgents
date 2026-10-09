# M1-00 test baseline

Recorded **before any M1 change**, on `main` at the M0 close-out commit, following `docs/tasks/M1-00.md` ("Baseline procedure"). Every later task compares its check results against this record.

## Environment
| | |
|---|---|
| **Commit** | `9486f05c554b9a544b15fecc7d9bb0f2d58cb2d6` (`main`) |
| **OS** | Microsoft Windows [Version 10.0.26200.9457] |
| **Python (venv)** | 3.11.9 (tags/v3.11.9:de54cf5, Apr 2 2024), MSC v.1938, 64-bit |
| **pip** | 26.2.1 |
| **Recorded at** | 2026-10-09T06:04:32Z |
| **Raw outputs** | `M1-00-environment.txt`, `M1-00-install.txt`, `M1-00-pytest-gitbash.txt`, `M1-00-pytest-powershell.txt`, `M1-00-ruff.txt`, `M1-00-smoke.txt` |

## Results
| Name | Command (run from the repository root) | Result |
|---|---|---|
| `install` | `.venv/Scripts/python.exe -m pip install -e ".[dev]"` | Exit 0. Installed `ruff-0.16.10`; reinstalled `tradingagents-0.6.0` (editable). |
| `pytest-gitbash` | Git Bash: `.venv/Scripts/python.exe -m pytest -q` | Exit 1. **1 failed, 1259 passed, 4 skipped, 1 deselected**, 20 warnings, 99 subtests passed (46.47 s) |
| `pytest-powershell` | PowerShell: `& .venv\Scripts\python.exe -m pytest -q \| Out-File -Encoding utf8 docs\baselines\M1-00-pytest-powershell.txt` | Exit 1. **2 failed, 1258 passed, 4 skipped, 1 deselected**, 21 warnings, 99 subtests passed (29.84 s) |
| `ruff` | `.venv/Scripts/python.exe -m ruff check .` | Exit 0. `All checks passed!` |
| `smoke` | Fresh venv `py -3.11 -m venv <scratch>`; `<scratch>/Scripts/python.exe -m pip install .`; then `python -c "import tradingagents, cli.main; print('clean-install import OK')"`, run from the repository root as CI does | Exit 0. `clean-install import OK` |
| `pytest-py314` *(optional)* | — | **Not run.** Python 3.14 is available locally (`py -3.14`) but wasn't used for this baseline. |

**Skipped in both shells (4):**
- `tests/test_api_key_env.py:159`, `:173` and `:183`: "POSIX file modes";
- `tests/test_bedrock_provider.py:74`: "could not import 'langchain_aws'" (the optional `bedrock` extra isn't installed).

**Deselected (1):** the `integration` marker is excluded by `pyproject.toml`'s `addopts`.

## Failing tests (by ID)
| Test ID | Git Bash | PowerShell | First error line | Cause shown in the output |
|---|---|---|---|---|
| `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` | **Fails** | **Fails** | `AssertionError: assert not True` (the yfinance cache path `C:\Users\LOQ\AppData\Local\Temp\tradingagents-tests-yf-…` `is_relative_to(C:\Users\LOQ)`) | On this machine the system temp folder is inside the home folder, so a temp-folder cache counts as "in the home" |
| `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module` | Passes | **Fails** | `TypeError: expected string or bytes-like object, got 'NoneType'` (`out.stdout` is `None` at `tests\test_cli_commands.py:95`) | The subprocess output reader raised `UnicodeDecodeError: 'charmap' codec can't decode byte 0x90` (cp1252), so the captured stdout was `None` |

## The two earlier-reported failures
| Test | Status |
|---|---|
| `test_yfinance_keeps_its_cache_out_of_the_users_home` | **Reproduced** in **Git Bash and PowerShell** |
| `test_every_command_is_registered_when_run_as_a_module` | **Reproduced in PowerShell only.** Not reproduced in Git Bash, where it passes. |

Both now have saved output, so they're **established, environment-specific failures**. They aren't fixed in M1-00 (spec: out of scope); fixing either is a separate task needing the owner's approval.

## Not reproducible locally
- **Python 3.12 and 3.13:** not installed on this machine. The CI matrix covers them.
- **The CI `TZ=America/New_York` job:** Windows doesn't apply `TZ` the way Linux does, so it's verified only when CI runs.
- **CI itself:** runs only when the owner pushes or opens a pull request.

## How later tasks use this baseline
- **Git Bash:** the expected failing set is exactly `{test_yfinance_keeps_its_cache_out_of_the_users_home}`.
- **PowerShell:** the expected failing set is exactly `{test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module, test_yfinance_keeps_its_cache_out_of_the_users_home}`.
- Every other collected test must pass (or stay skipped or deselected for the reasons above). **Any other failure is new and blocks the task.**

## Note on the raw outputs
The raw `.txt` files are verbatim command output, except that **trailing spaces were stripped** from the four pytest outputs, so the repository's whitespace check (`git diff --check`) passes. No other content was changed. The `M1-00-after-*.txt` files hold the same commands rerun after the M1-00 change. That comparison is recorded in `PROGRESS.md`.
