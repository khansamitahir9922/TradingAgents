# PROGRESS

The handoff log, shared by Claude Code, Codex and the owner. Update it at the end of every work session (AGENTS.md / CLAUDE.md, Section 8). The newest entry goes at the top of the session log.

---

## Current state (2026-10-12)

| | |
|---|---|
| **Milestone** | **M0 Architecture: complete (locally).** **M1 Market foundation: in progress.** **2 of 18 tasks done** (M1-00, M1-01). |
| **`main`** | Local `main` is at **`a8f338b`** (`test: give comprehensions their own scope in the system-clock scan`). **M1-01 passed Codex review** (no blocking findings at `a8f338b`) and was **fast-forwarded into `main`** with the owner's approval on 2026-10-12. `main` is 7 commits ahead of `origin/main`. **Nothing has been pushed.** |
| **Current work** | **Batch 1** (M1-02 – M1-05) on **`m1/batch-1`**, approved by the owner. **M1-02 – M1-05 committed (checked)**; the batch self-review is in progress. No Codex review yet. |
| **Package name** | **`investment_engine`**: OPEN-01 confirmed by the owner on 2026-10-09. It's the internal Python package name; public branding is decided separately. |
| **Other branches** | `m1/M1-01-clock` (at `a8f338b`), `m1/M1-00-skeleton` (at `f906841`), `docs/m0-closeout` (at `9486f05`), `m0-architecture` (at `906ae85`) and `fix/report-reliability-baseline` (at `559f8c2`) are kept. Nothing has been deleted. |
| **Runtime code** | `tradingagents/` and `cli/` unchanged. `investment_engine` has `__init__.py` (M1-00) and `clock.py` (M1-01). |
| **Runtime tests** | **Run for M1-00 and M1-01**, and compared against the recorded baseline (`docs/baselines/M1-00-baseline.md`); see "Last check results". |

### M0 work items (all complete)
| ID | Item | State |
|---|---|---|
| M0-01 – M0-08 | Architecture, diagrams and guide; PRD; design principles; ADR-001 – 009; roadmap; M1 task specs; AGENTS.md / CLAUDE.md; PROGRESS.md | Reviewed by Codex; committed in `906ae85` |
| M0-09 | Commit, with the owner's approval | Done (2026-10-09): `906ae85` |
| M0-10 | Codex review of the commit | **Passed** (2026-10-09); no blocking findings |
| M0-11 | Owner-approved merge into `main` | **Done** (2026-10-09): fast-forward to `906ae85`; **not pushed** |

**Never stage:** `.env`, `.claude/`.

---

## Next steps
1. **Codex quick-reviews the workflow documentation commits** on `m1/batch-1`: `d9ab307`, then the follow-up fixing Codex's two findings (the smoke-check commands must use the fresh environment's Python; the outdated `tzdata` alternatives are removed).
2. **Batch 1 (M1-02 – M1-05)** on the same branch, once the documentation commit has passed review. Coding starts only then. The owner's batch approval covers implementing and locally committing the four tasks. Then the batch checks, Claude Code's self-review, Codex's review of every commit, and **one owner-approved merge** of the whole branch.

**Batch workflow (adopted 2026-10-12, documented in this commit):** `AGENTS.md`/`CLAUDE.md` shared rules §4 and §6, `docs/tasks/README.md` (Workflow, Checks) and `docs/roadmap.md` (§1.1, §4.3).
- **One-month goal:** finish **M1**. **M2 is a stretch goal**, and still needs reviewed specs (including the agreed adjusted-price view and leakage protections).
- **Batches:**
  - 1: M1-02 – M1-05;
  - 2: M1-06 – M1-11;
  - 3: M1-12 – M1-13 (Yahoo verification; **a firm checkpoint**);
  - 4: M1-14 – M1-17.
- **Per task:** its own tests, task checks (task tests, full suite in Git Bash, ruff; plus the smoke check if dependencies or packaging change), `PROGRESS.md` entry and commit. Within a batch, a committed and checked earlier task can satisfy a dependency.
- **Per batch:** the PowerShell full suite, the clean-install smoke check, Claude Code's self-review, Codex's review of **every commit**, then one owner-approved merge.
- **Stop rules:** a new test failure; a file change outside a spec's allowed files; a spec gap needing an architecture or ADR change; a blocked verification checkpoint.
- **`tzdata`:** M1-06's allowed files permit adding it to `[project] dependencies`. **Codex accepted the unconditional, explicit declaration** (2026-10-12). It's added only when M1-06 is implemented, in batch 2.

**Known stale labels, left for a later update.** The status lines in `docs/design-principles.md` and the ADR records (`architecture/adr/`) still say "awaiting review of the M0 commit and merge". They describe the state before M0's merge on 2026-10-09. The AGENTS.md, CLAUDE.md, task README and roadmap labels were fixed in the batch-1 documentation commit. This file is the current record.

---

## Reviewed ML proposals: future planning, not part of M1
**Origin.** The owner reviewed an applied-ML creator's techniques (mar_antaya: an NVDA weekly-return model, F1 XGBoost models, leakage guards). Claude Code assessed them, and Codex reviewed the proposal on 2026-10-09.

**Status.** Agreed direction. **Not yet in the roadmap**: the roadmap's provisional M2, M8 and M9 work packages will be updated in a separate, reviewed change, and must be reviewed before any M2 price-indicator work. **M1 is unchanged. No ADR is needed**, because these fit the existing Quant, Evaluation and ML modules and follow ADR-009 (raw history kept, adjustments derived).

**Key conclusions:**

**1. Adjusted view first (M2), the most important finding.**
- Indicators and return series need a **point-in-time split-adjusted price view** derived from stored CorporateActions. Without it, a split such as NVDA's 10-for-1 on 2024-06-10 would look like a ~90% crash.
- **Dividend-inclusive (total) returns** are defined and labelled separately.
- Each strategy or model states which series it uses.

**2. Raw prices stay authoritative** for execution reference prices, fills and accounting.

**3. Point in time.**
- For a prediction at T, an action applies only if its revision is available by T (`available_from <= T`), and it takes effect by its ex-date.
- A correction observed after T never changes the inputs of a prediction made at T.
- Providers stay separate.

**4. Missing data still means ABSTAIN.** Filling gaps (imputation) during research never bypasses Law 9: when required data is missing, the MarketView is `ABSTAIN`.

**5. Strategy outputs.** M2 rule strategies produce **direction and strength** (the MarketView contract). Numeric-return models (linear, gradient-boosted) belong in **M9**, and each task spec fixes the target (split-adjusted or total return) and the horizon.

**6. Leakage.**
- Inputs must be available before the prediction time.
- Cleaning, feature selection, tuning and calibration learn only from each walk-forward fold's training period.
- A training example is used only after its outcome is complete (the label horizon is purged).
- Chronological order alone isn't enough.

**7. Benchmarks matched to the question:**
- always-up for direction;
- zero return for numeric forecasts;
- buy-and-hold for investment performance.

Report directional accuracy against the base rate, and the information coefficient where relevant. Always state costs, sample sizes and the abstain rate.

**8. Calibration.** A model score becomes `probability_up` only after calibration is tested on separate, appropriately timed data.

**9. Precise claims.** A result is significant only when evaluation shows it. A summary alone establishes neither significance nor the lack of it (e.g. the creator's F1 result).

**10. Dashboard (M8).** A metric registry: key, label, unit, preferred direction and formatter.

**11. Not adopted:**
- a single train/test split as proof;
- shuffled splits on time-ordered data;
- narrative features without walk-forward evidence;
- choosing instruments by hindsight.

---

## Open issues and decisions
| Item | Owner | Needed by |
|---|---|---|
| ~~OPEN-01: package name~~ **Resolved:** `investment_engine`, confirmed by the owner on 2026-10-09 | Owner | Done |
| Which independent sources count as anchors for as-traded prices, volumes and dividends | Codex and owner, at spec review | M1-12 |
| The per-field Yahoo determination results | Determined in M1-12 | M1-12 / M1-13 |
| How far back yfinance hourly history reaches | Measured in M1-13 | M1-13 |
| `pyarrow` / `duckdb` versions with Python 3.11 – 3.14 wheels | Checked in M1-10 | M1-10 |
| **Time-zone data (found in M1-01). Decided:** `tzdata` is declared **explicitly and unconditionally** (for all platforms) in `[project] dependencies` when M1-06 is implemented. The M1-06 spec permits exactly that one entry, and **Codex accepted the unconditional declaration** (2026-10-12). Background: `zoneinfo` needs `tzdata` wherever there's no system time-zone database (Windows, some slim containers); until M1-06 it's present only transitively, via pandas on Windows. | Codex and owner | **Decided**; implemented in M1-06 (batch 2) |
| NVDA's listing date for the seed record | Checked in M1-17 | M1-17 |
| Whether DataHealth snapshots are persisted for lineage | Decided with lineage | M2 |
| OPEN-16: proposed order-lifecycle extensions. **Unaccepted**; they need a reviewed, accepted follow-up ADR. | Owner and Codex | Before M4 |
| All other product decisions: PRD Section 10 (OPEN-01 – OPEN-17) | Owner | Per PRD |

---

## Last check results
| Check | Result | Evidence |
|---|---|---|
| Runtime test suite | **Not run** for the M0 documentation work (no runtime changes) | — |
| **M1-00 baseline** (`main` at `9486f05`, before any change) | **Git Bash:** 1 failed, 1259 passed, 4 skipped, 1 deselected. **PowerShell:** 2 failed, 1258 passed, 4 skipped, 1 deselected. `ruff check .` passed. Clean-install smoke passed. Both earlier-reported failures are now **established, with saved output**:<br>• `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` fails in **both shells** (the temp folder is inside the home folder);<br>• `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module` fails in **PowerShell only** (a cp1252 `UnicodeDecodeError` in the subprocess output). | `docs/baselines/M1-00-baseline.md` and the raw `M1-00-*.txt` outputs |
| **M1-00 after the change** (`m1/M1-00-skeleton`) | New tests: `tests/engine/test_layering.py`, **5 passed**. **Git Bash:** 1 failed, **1264 passed** (+5), 4 skipped, 1 deselected; the failing set is identical to the baseline. **PowerShell:** 2 failed, **1263 passed** (+5), 4 skipped, 1 deselected; the failing set is identical. **No new failures.** `ruff check .` passed. Clean-install smoke, with the extended import `tradingagents, cli.main, investment_engine`, passed from the repository root as in CI. From outside the repository, `investment_engine` imports from the venv's `site-packages`, which proves it's packaged. | `docs/baselines/M1-00-after-*.txt` |
| Not reproducible locally | Python 3.12 and 3.13; the CI `TZ=America/New_York` job. The optional Python 3.14 run wasn't done. | Recorded in the baseline |
| Documentation checks (2026-10-08 / 09) | No trailing whitespace in `docs/`, `architecture/adr/`, `AGENTS.md`, `CLAUDE.md` or `PROGRESS.md`. Every M1 spec has the required sections. The shared-rules blocks in AGENTS.md and CLAUDE.md are identical. The staged architecture files are unchanged. | Script checks by Claude Code, 2026-10-08 |
| Codex document review | **Passed (2026-10-09).** No blocking issues in the reviewed M0 documents. Codex verified the volume-evidence and replay-ordering fixes, the document structure, dependencies, whitespace, the unchanged SVG and runtime files, and that `.env` and `.claude/` weren't staged. Runtime tests weren't run. | Codex review, relayed by the owner |
| Pre-commit checks | The staged file list matches the owner-approved set; `git diff --cached --check` is clean | Claude Code, 2026-10-09 |
| Codex review of commit `906ae85` | **Passed (2026-10-09).** All 38 committed files are the approved documentation; the SVG, runtime code, tests and CI files are unchanged; `.env` and `.claude/` are excluded; the shared rules match. It noted one non-blocking item, the PRD's "review draft" wording, which is fixed on `docs/m0-closeout` (Codex review passed, 2026-10-09). | Codex review, relayed by the owner |
| Codex review of `docs/m0-closeout` | **Passed (2026-10-09).** Only the two approved files changed; the architecture, SVG, roadmap, M1 specs and runtime files are unchanged; whitespace checks pass. Runtime tests weren't run. | Codex review, relayed by the owner |
| **M1-01** (`m1/M1-01-clock`), after the second Codex fix | **Engine tests: 70 passed.** That's 5 from M1-00, plus 65 for M1-01: the original 29; then, for the first finding, 4 regression cases, 1 safe-rebinding case and 6 scoping cases; then, for the second finding, 4 comprehension-variable regressions, 12 reads-still-caught cases (element, condition and first iterable, across list, set, dict and generator), 4 own-scope shadowing cases and 5 more scoping cases.<br>**Git Bash:** 1 failed, **1329 passed**, 4 skipped, 1 deselected; failing set = baseline (`test_yfinance_keeps_its_cache_out_of_the_users_home`).<br>**PowerShell:** 2 failed, **1328 passed**, 4 skipped, 1 deselected; failing set = baseline (also `test_every_command_is_registered_when_run_as_a_module`).<br>**No new failures.** `ruff check .`: all checks passed.<br>**Clean-install smoke: passed (the CI import succeeded from the repository root; from outside it, investment_engine.clock loaded from site-packages and LiveClock().now() was UTC).** Earlier M1-01 commits had also passed: `8c36fb4` with 1293 / 1292 passed and `dec5070` with 1304 / 1303 passed, the same failing sets each time.<br><br>**Exact commands**, from the repository root:<br>1. `.venv/Scripts/python.exe -m pytest -q tests/engine` (Git Bash)<br>2. `.venv/Scripts/python.exe -m pytest -q` (Git Bash)<br>3. `& .venv\Scripts\python.exe -m pytest -q \| Out-File -Encoding utf8 <scratch>\m101c-powershell.txt` (PowerShell)<br>4. `.venv/Scripts/python.exe -m ruff check .` (Git Bash)<br>5. Smoke: `py -3.11 -m venv <scratch>/smoke-m101c`; `<scratch>/smoke-m101c/Scripts/python.exe -m pip install -q .`; then, from the repository root, `<scratch>/smoke-m101c/Scripts/python.exe -c "import tradingagents, cli.main, investment_engine; print('clean-install import OK')"`; then, from outside the repository, `<scratch>/smoke-m101c/Scripts/python.exe -c "import investment_engine.clock as c; print(c.LiveClock().now().tzinfo, c.__file__)"` | Full outputs kept in Claude Code's scratch folder, outside the repository (the spec doesn't allow new output files) |
| CI | **Not yet run** (nothing pushed) | — |

---

## Session log

### 2026-10-12: Claude Code (batch 1, M1-05: SQLite operational store and data-directory config)
- **Tests first.** 37 tests:
  - `tests/engine/conftest.py`: an autouse fixture gives every engine test its own data directory;
  - `tests/engine/test_config.py`: the environment variable is honoured; deleted and blank fall back to `~/.investment_engine`; the variable is read at call time; engine tests use their own directory; reading the config creates nothing;
  - `tests/engine/test_sqlite_store.py`: the parent folder is created and foreign keys enforced; the schema is idempotent and versioned; a newer database is refused; scripts are numbered without gaps; a **portable-SQL grep** (no `INSERT OR REPLACE/IGNORE`, `REPLACE INTO`, `AUTOINCREMENT`, `WITHOUT ROWID`, `PRAGMA`, `ATTACH`, `GLOB`, or SQLite date and time functions); instrument round trip; persistence across connections; sorted `list()`; duplicate refused; unknown is `KeyError`; `update_lifecycle` changes only the lifecycle and enforces its rules; the schema `CHECK` refuses an invalid lifecycle written directly; no delete methods.
  - **M1-04's `SymbolResolverContract` runs against SQLite** (13 cases, `TestSqliteSymbolResolver`). Also: a refused mapping leaves no rows and no open transaction; an unknown instrument is refused (foreign key); mappings persist; no delete methods.

  Before the implementation, collection failed on the missing modules.
- **Implementation:**
  - `investment_engine/config.py`;
  - `investment_engine/storage/__init__.py`;
  - `investment_engine/storage/schema/0001_reference_data.sql`: `schema_version`, `instruments` and `symbol_mappings` with `CHECK`, `PRIMARY KEY` and `FOREIGN KEY` constraints;
  - `investment_engine/storage/sqlite.py`: `open_operational_db` (autocommit; foreign keys on), `apply_schema` (each script applied atomically with its version row; `SchemaVersionError` when the database is newer), `SqliteInstrumentRepository` and `SqliteSymbolResolver`, which **reuses M1-04's `conflict` and `covers`** inside a `BEGIN IMMEDIATE` transaction;
  - `pyproject.toml`: **only** `[tool.setuptools.package-data]`, adding `investment_engine = ["storage/schema/*.sql"]`.
- **Choices not stated in the spec, recorded for review:**
  - an **empty** `INVESTMENT_ENGINE_DATA_DIR` counts as unset;
  - the "out of the home folder" test checks for **the temporary folder, not the real default**, because on this machine the temp folder itself is inside the home folder (see the baseline);
  - the `BEGIN IMMEDIATE` and `PRAGMA` statements are in Python code, not in the schema scripts (the portability rule covers the scripts);
  - the database integrity errors are translated: a duplicate ID becomes "already registered", any other cause is reported as itself.
- **Self-review fix before this commit:** an early draft reported every integrity error as "already registered". It's now precise.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_config.py tests/engine/test_sqlite_store.py`: 37 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1492 passed** (+37), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed;
  - **smoke** (a packaging change): a fresh `py -3.11` venv, `<scratch>/Scripts/python.exe -m pip install .`, the CI import OK from the repository root, and from outside it the installed `investment_engine.storage.sqlite` applied **schema version 1**. That proves the `.sql` script is packaged.

### 2026-10-12: Claude Code (batch 1, M1-04: SymbolMapping)
- **Tests first.** `tests/engine/test_symbols.py` has 29 tests. The resolver behaviour is written once, as **`SymbolResolverContract`**, and run here by `TestInMemorySymbolResolver`. M1-05 subclasses the same contract for SQLite, which satisfies its "same test cases" requirement without editing this file. The contract covers:
  - half-open validity (before, start, inside, exclusive end, after);
  - open-ended mappings;
  - a reused symbol (`ABC` → `EQ_US_ABC`, then `EQ_US_ABC_2`, with a gap);
  - the FB → META ticker change (`EQ_US_FB` keeps its mnemonic) on both sides and in both directions;
  - provider independence;
  - exact (case-sensitive) matching;
  - every unknown lookup raising `UnknownSymbol`;
  - `datetime` refused;
  - both overlap rules, with the state unchanged after a refusal;
  - an identical overlapping mapping refused;
  - touching intervals allowed.

  Record validation: provider shape, symbol and ID shape, `valid_to > valid_from`, dates not datetimes, immutability. Before the implementation, collection failed on the missing module.
- **Implementation:** `investment_engine/market/symbols.py`:
  - `PROVIDER_YFINANCE`, a frozen `SymbolMapping` and `UnknownSymbol(LookupError)`;
  - the **module-level rule functions** `covers`, `overlaps` and `conflict`, so the M1-05 SQLite resolver reuses exactly the same rules, as its spec requires;
  - the in-memory `SymbolResolver` (add, resolve, symbol_for).
- **Choices not stated in the spec, recorded for review:**
  - an **identical** overlapping mapping (same instrument, symbol and provider) is refused as well as the two specified conflicts, because it would make the same claim twice;
  - the provider must match `[a-z][a-z0-9_]*`, the same shape M1-08 uses for provider IDs.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_symbols.py`: 29 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1455 passed** (+29), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.

  No dependency or packaging change.

### 2026-10-12: Claude Code (batch 1, M1-03: Instrument)
- **Tests first.** `tests/engine/test_instruments.py` has 41 tests:
  - a valid `EQ_US_NVDA`;
  - five valid ID shapes, including the `_2` suffix and `ETF_` prefix;
  - eight malformed IDs;
  - the prefix matching the asset class;
  - `CRYPTO` refused;
  - enum values given as strings accepted;
  - invalid time zones, currencies and MIC exchange codes refused;
  - each lifecycle rule (ACTIVE has no end date, DELISTED needs one, the end follows the start, SUSPENDED may have either form);
  - `datetime` refused where a `date` is expected;
  - half-open `is_active_on` at both boundaries;
  - immutability;
  - the registry's get, duplicate refusal and absence of any removal method.

  Before the implementation, collection failed on the missing module.
- **Implementation:**
  - `investment_engine/market/__init__.py` (docstring only);
  - `investment_engine/market/instruments.py`: `AssetClass` (EQUITY, ETF), `InstrumentStatus`, a frozen `Instrument` with full validation, and `InstrumentRegistry` (add, get; no removal).
- **Choices not stated in the spec, recorded for review:**
  - **`datetime` is refused** where a lifecycle `date` is expected (Python's `datetime` is a subclass of `date`, which would blur boundaries);
  - **enum values given as plain strings are converted** (needed for the M1-05 SQLite round trip);
  - **SUSPENDED is allowed with or without `active_to`** (the spec constrains only ACTIVE and DELISTED);
  - the exchange is validated as an **ISO 10383 MIC shape** (four characters `[A-Z0-9]`).
- **Portability:** the invalid-timezone test cases avoid names whose validity could differ between the `tzdata` package and a system time-zone database.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_instruments.py`: 41 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1426 passed** (+41), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.

  No dependency or packaging change.

### 2026-10-12: Claude Code (batch 1, M1-02: Decimal boundary)
- **The owner approved batch 1** (M1-02 – M1-05) on `m1/batch-1` at `f4313cb`, after Codex's review of the workflow documentation passed.
- **Tests first.** `tests/engine/test_money.py` has 56 tests:
  - every acceptance item;
  - non-finite amounts refused;
  - the currency-code shape;
  - mixed currencies or units refused in `+`, `-` and ordering;
  - equality across currencies is simply `False`;
  - `*` only by a `Decimal`;
  - `Money` and `Quantity` never mix;
  - more half-even cases, including a negative tie;
  - the quantum exponent kept;
  - converter type checks;
  - a float round trip at `PRICE_QUANTUM`.

  Before the implementation, collection failed on the missing module.
- **Implementation:** `investment_engine/money.py`:
  - `Money` and `Quantity`: frozen dataclasses, Decimal-only and finite amounts, an ISO 4217 currency or a non-empty unit;
  - mixing currencies or units raises `ValueError`; combining with another type raises `TypeError`;
  - `PRICE_QUANTUM`, `SHARE_QUANTUM` and `ROUNDING = ROUND_HALF_EVEN`;
  - `quantize`;
  - `from_float64` (float only, finite, via `repr`, then explicit quantization);
  - `to_float64` (finite Decimal only).
- **Choice not stated in the spec:** ordering comparisons across currencies **raise**, but equality returns `False`. Raising on `==` would break hashing and containers.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_money.py`: 56 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1385 passed** (+56), 4 skipped, 1 deselected; failing set = baseline;
  - `.venv/Scripts/python.exe -m ruff check .`: all checks passed.

  No dependency or packaging change, so no smoke check within the task.

### 2026-10-12: Claude Code (workflow documentation follow-up)
- **Codex reviewed `d9ab307`.** The shared rules match, and runtime code is unchanged. It found two documentation issues:
  1. `docs/tasks/README.md`: the clean-install check used plain `python`, which could test the project venv instead of the fresh install. **Fixed:** both import checks now explicitly use `<scratch>/Scripts/python.exe`, including the one run outside the repository.
  2. `PROGRESS.md`: an outdated paragraph still offered "Windows-only" or "transitive dependency" alternatives for `tzdata`. **Fixed:** they're removed, and the entry records that **Codex accepted the explicit, unconditional `tzdata` dependency** that M1-06 permits.
- Only `docs/tasks/README.md` and `PROGRESS.md` changed. No batch task started.


### 2026-10-12: Claude Code (M1-01 merge; batch workflow documentation)
- **M1-01 merged.** Codex's review passed at `a8f338b` with no blocking findings; the lambda false-alarm limit was accepted. With the owner's approval, `main` was fast-forwarded from `f906841` to `a8f338b` (nothing pushed, no branches deleted). **2 of 18 M1 tasks are done.**
- **Branch `m1/batch-1`, from `main` at `a8f338b`.** The batch workflow is documented in the six owner-approved files:
  - `AGENTS.md` and `CLAUDE.md`: shared rules §4 (batches, approvals, one commit per task, dependencies within a batch, self-review, review of every commit, stop rules) and §6 (task checks and batch checks). The shared blocks are still identical, and AGENTS.md's review role now says to review every commit;
  - `docs/tasks/README.md`: workflow, dependencies, and per-task and per-batch check tables;
  - `docs/roadmap.md`: §1.1 rewritten for batches, the owner's one-month window (the goal is M1; M2 a stretch), a §4.3 batch table with the order inside each batch and the merges needed first, the phase table kept, and the M0 section marked complete;
  - `docs/tasks/M1-06.md`: `tzdata` permitted in `[project] dependencies`, with an unconditional declaration proposed, the reasoning, and a smoke check within the task;
  - this file.
- **Also fixed:** the stale "awaiting review/merge" status labels in AGENTS.md, CLAUDE.md, the task README and the roadmap. **Still stale:** the labels in the design principles and ADR records, which are outside this commit's allowed files.
- **Not changed:** runtime code, tests, `pyproject.toml`, CI, the frozen architecture and SVG, and the other M1 specs.


### 2026-10-11: Claude Code (M1-01, second fix: comprehension scopes)
- **Codex finding (blocking).** A comprehension's loop variable was treated as belonging to the whole function, so `[dt.isoformat() for dt in values]` hid a module-level `from datetime import datetime as dt`, and a later `dt.now()` went unreported. Codex reproduced it for list, set and dict comprehensions and generator expressions.
- **Regression tests first,** across all four comprehension kinds:
  - the loop variable can't hide the enclosing import (Codex's example);
  - reads inside a comprehension are still caught: in the element, in a condition, and in the **first iterable**, which Python evaluates in the enclosing scope, so even `[dt for dt in [dt.now()]]` is caught;
  - inside its own scope, the loop variable does shadow the import.

  Before the fix, 8 failed (Codex's example ×4, first iterable ×4).
- **Fix.** Each comprehension is its own scope. The first iterable is analysed in the enclosing scope, everything else in the comprehension's scope. A `:=` (walrus) binds in the enclosing function, as in Python.
- **Probed before committing.** Nine more edge cases: nested comprehensions both ways, a later `for` clause seeing earlier variables, walrus, a comprehension in a class body, and lambdas. Five became permanent scoping tests.
- **Known conservative limit.** Lambdas aren't modelled as scopes. A lambda parameter that shares an import's name (`lambda dt: dt.now()`) is **flagged**: a possible false alarm, never a miss.
- **Codex's answers on planning** are recorded under "Next steps" (batches, rules, `tzdata`, the one-month goal).


### 2026-10-11: Claude Code (M1-01 fix for Codex's finding)
- **Codex finding (blocking).** The system-clock scan used one alias table for the whole file, so an import in one function could hide a forbidden read in another. Codex reproduced two cases.
- **Regression tests first.** Two parametrized tests, each in both orders:
  - Codex's `bad()` / `format_timestamp()` example;
  - a module-level `from datetime import datetime` read in one function, while another function does a local `import datetime`.

  Before the fix, 3 of the 4 cases failed on the old scanner. The fourth passed only by accident of ordering.
- **Fix.** The scanner is now scope-aware:
  - one binding table per module, function and class scope;
  - names are resolved as Python does: local, then enclosing, then module, with class bodies not visible from methods;
  - `global` declarations are honoured;
  - decorators, default arguments and base classes are evaluated in the enclosing scope;
  - when a scope binds a name more than once, every import candidate is checked, so the scan errs towards flagging.
- **Bug in my own fix, caught before committing.** An ad-hoc probe of six scoping edge cases showed that a function body directly inside another scope (a method, a nested function) was being analysed in the outer scope. I restructured the walk, and the six probes are now permanent tests (`test_the_scan_follows_python_scoping`), plus a safe-rebinding test.
- **Kept:** all 8 forbidden-function planted cases and the safe-use test.
- **Checks:** see "Last check results", with the exact commands. No new failures.
- **Time-zone note** stays deferred to M1-06, as Codex agreed.


### 2026-10-10: Claude Code (M1-01: Clock)
- **M1-00** passed Codex review. With the owner's approval, `main` was fast-forwarded to `f906841` (nothing pushed, no branches deleted).
- **Owner decision.** When the owner pastes a Codex message with suggested approval text, it counts as the owner's approval for exactly that step. Pushes still need an explicit instruction.
- **Codex correction on provider notes.** Rejecting Public under Law 1 was premature: Law 1 governs how *our* system places orders, not what features a provider offers. All provider recommendations stay as unverified candidates for later review (OPEN-02/03/04, ADR-011).
- **M1-01, tests first.**
  - `tests/engine/test_clock.py`:
    - `LiveClock` returns aware UTC;
    - `ReplayClock` start, UTC storage, naive-start rejection, forward and same-time `advance_to`, backward and naive-target rejection, `advance_by` including zero and negative rejection;
    - `ensure_utc` across the New York DST changes, including both folds of the repeated hour, a fixed offset and UTC, plus naive rejection.
  - `tests/engine/test_no_system_clock.py`: an AST scan that **resolves imports and aliases** (e.g. `from datetime import datetime as dt; dt.now()`) and fails on any reference to the eight system-clock functions outside `clock.py`. Its own tests:
    - a coverage guard;
    - a check that `clock.py` really is the sanctioned reader;
    - eight planted-read cases in a temporary package;
    - a safe-use case (constructing datetimes and `time.sleep` aren't flagged).
  - Before the implementation, the clock tests failed on the missing module and the scan's coverage tests failed on the missing `clock.py`.
- **Implementation:** `investment_engine/clock.py` with `ensure_utc`, the `Clock` protocol, `LiveClock` and a monotonic `ReplayClock`, as specified.
- **Checks:** see "Last check results". No new failures.
- **Found:** Windows time-zone data is only a transitive dependency (via pandas). It's raised under "Open issues" for M1-06's review.


### 2026-10-09: Claude Code (M1-00: package skeleton and baseline)
- **The owner confirmed OPEN-01 (`investment_engine`) and approved M1-00**, including its local task commit.
- **Baseline first,** on `main` at `9486f05`, before any change: environment, dev install, pytest in Git Bash and PowerShell, ruff and the clean-install smoke check, all saved in `docs/baselines/`. Both earlier-reported Windows failures were reproduced and are now established, environment-specific failures. They're **not fixed** in this task (out of scope); each would need its own owner-approved task.
- **Tests first.** `tests/engine/test_layering.py` has 5 tests:
  - the scan finds the package (so the rules can't pass vacuously);
  - no `tradingagents` or `cli` imports;
  - `yfinance` only under `market/importers/`;
  - `pyarrow` and `duckdb` only under `market/store/`;
  - the package imports, with `__version__ == "0.0.0"`.

  Before the implementation, the coverage and version tests failed for the right reason.
- **Implementation:**
  - `investment_engine/__init__.py`, with `__version__` only;
  - `pyproject.toml` packages `include` extended with `investment_engine*`;
  - the CI smoke import extended with `investment_engine`.

  The package name is recorded in `docs/tasks/M1-00.md`.
- **Checks:** all rerun; no new failures (see "Last check results"). One transient network retry during the smoke install was logged; the install succeeded.
- **Unresolved:** the two baseline failures above. CI not yet run.


### 2026-10-09: Claude Code (M0 merge and close-out documentation)
- **M0-10 and M0-11.** Codex's review of `906ae85` passed. With the owner's approval, local `main` was fast-forwarded to `906ae85` (no new commit, nothing pushed, no branches deleted). M0 is complete.
- **Branch `docs/m0-closeout`, from `main`.** Per the owner's scope, it changes **only `PROGRESS.md` and `docs/PRD.md`**:
  - this status update;
  - the reviewed ML proposals recorded above, so they're in the shared record and not only in a tool's private memory;
  - the PRD's two "review draft" references fixed (PRD v0.1.1).
- **Not changed:** the architecture, SVG, M1 specs and runtime code. Other documents' stale status labels are noted above.
- **Scope note.** A broader draft (labels across 15 more files, plus the roadmap's ML work packages) was prepared first, then narrowed to the two approved files. That draft wasn't committed; the roadmap update will be redone as its own reviewed change.

### 2026-10-09: Claude Code (M0 commit)
- Codex's review passed with no blocking issues, and the owner approved committing the reviewed M0 documents.
- Updated the status labels consistently:
  - documents: "Reviewed vX: Codex document review passed; committed with the owner's approval; awaiting review of the M0 commit and merge";
  - M1 specs: "Reviewed spec: implementation starts only after M0 is merged";
  - ADR records: review passed;
  - the roadmap's M0 table.
- Committed only the owner-approved paths on `m0-architecture`. Not pushed, not merged, M1 not started.

### 2026-10-08: Claude Code (M0 documentation, final spec corrections)
**Codex's review of the previous round.**
- Confirmed consistent: provider separation, replay timing, DataHealth states, and the handoff documents (AGENTS.md, CLAUDE.md, PROGRESS.md).
- Its checks passed: document structure, the dependency check, the identical shared-rules blocks, and whitespace. The SVG and tracked runtime files are unchanged, and `.env` and `.claude/` are unstaged.
- Codex did not run runtime tests.
- Two corrections remained before it would recommend the M0 commit.

**Fixed:**
1. **M1-12 volume evidence.**
   - Daily and hourly volume semantics are now established **only by primary evidence**: independently cited as-traded volume anchors, or explicit provider documentation (quoted, with link and date).
   - Dollar-volume continuity is **supporting evidence only** and never decides.
   - Without primary evidence, the field is `UNDETERMINED` and `BLOCKED`. The `F == 1` identity exception also needs primary evidence.
   - The spec now includes Codex's counterexample: a 4:1 split, as-traded prices 40 → 10, true volumes 1,000 → 16,000, vendor volumes 4,000 → 16,000. Continuity rates identity as perfectly continuous (160,000 = 160,000) while the truth is 1,000. Its acceptance test requires `BLOCKED` with continuity alone, and correct determinations when a cited anchor is added.
2. **M1-14 deterministic ordering.**
   - The replay ordering key now contains the full payload identity plus revision. For corporate actions that includes `action_type_rank` (declaration order: SPLIT 0, DIVIDEND 1, SYMBOL_CHANGE 2, DELISTING 3).
   - M1-11 now has an explicit total sort key for every read method, using the same rank.
   - New tests: a same-day split and dividend with identical provider, instrument, availability, ex-date and revision. The reader returns them in their original order, reversed, and in 20 seeded permutations, and replay output and sequence numbers must be identical (M1-14). Both write orders give the same query order (M1-11).

Documents only. **No runtime tests were run**, and no runtime or test code changed.

### 2026-10-08: Claude Code (M0 documentation, review round on M1 specs)
Applied Codex's M1 spec review:
1. **Complete split history** (M1-12 / M1-13). `F(d)` now includes splits after the requested window. The history comes from a full-history call, bracketed before and after the download, and must agree with the stored actions, read via M1-11 (new dependency of M1-13).
2. **Per-field verification from evidence.** Daily and hourly prices, daily and hourly volume, dividends and split ratios are each determined separately. Precision limits are documented. A blocked field blocks the affected tasks and M1 completion, and a proposed ADR alone unblocks nothing.
3. **Replay** (M1-14). There are three timestamps: `event_time` = `available_from`, `received_at` = `event_time + latency`, `processed_at`. There's one event per stored revision, and `BAR_CLOSED` always carries revision 1, so corrections can't arrive early. The window is half-open by delivery time. M1-11 gains revision-history and available-between queries.
4. **Providers** in identity, revisions, partitions, reads, replay, resampling and health, with two-provider tests.
5. **Resampler** (M1-15): an enforced `at` cutoff, mixed providers rejected, complete `InputRef` lineage.
6. **DataHealth** (M1-16): only the four frozen statuses; applicability reported separately.

Also updated roadmap v0.3 and the task README. Drafted `AGENTS.md`, `CLAUDE.md` and this file.

Earlier M0 rounds (2026-10-07 / 08):
- Architecture v1.0 frozen, and diagrams exported and synced.
- PRD drafted and corrected.
- Design principles v0.1 → v0.3.
- ADR-001 – 009 drafted and corrected (follow-up ADRs for changes; outbox in M4; retrospective alternatives labelled).
- Roadmap v0.1 → v0.2 (workflow, baseline, Yahoo verification, availability).
- M1 specs v0.1.

Every Codex finding so far has been accepted and applied.
