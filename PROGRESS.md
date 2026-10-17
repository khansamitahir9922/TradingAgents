# PROGRESS

The handoff log, shared by Claude Code, Codex and the owner. Update it at the end of every work session (AGENTS.md / CLAUDE.md, Section 8). The newest entry goes at the top of the session log.

---

## Current state (2026-10-17)

| | |
|---|---|
| **Milestone** | **M0 Architecture: complete (locally).** **M1 Market foundation: in progress, 15 of 18 tasks done** (M1-00 – M1-11, M1-14 – M1-16). M1-12, M1-13 and M1-17 have their **daily parts merged** and their hourly parts unfinished (batch 3b, blocked on A4 permissions). **M2 Quant + initial evaluation: done** (daily only; merged 2026-10-16), under the owner's 2026-10-14 scheduling amendment. **M3 Portfolio, policy, risk: all 15 tasks committed (checked) on `m3/milestone`; in review** (not merged). |
| **`main`** | Local `main` is at **`b7c5d2a`** (`docs: hand the R1 and R2 fixes back for a second re-review with checks and report`): the owner approved the fast-forward from `53c51bd` on 2026-10-16 after Codex's final M2 review passed (`docs/reviews/codex-m2-accepted-b7c5d2a.md`). It contains M1's merged scope and all of M2. **Nothing has been pushed** (`main` is 84 commits ahead of `origin/main`). |
| **Current work** | **M3: Codex's second re-review at `b716355` accepted R2 and left two R1 password cases (short; doubly escaped); both fixed and handed back** (`docs/reviews/claude-m3-rereview3-package.md`, range `b716355..` the closing commit). Batch checks passed: Git Bash 2861 passed, PowerShell 2860 passed, only baseline failures; clean install passed. Nothing merged or pushed; M4 not started. History: **M3: Codex's re-review at `776119c` left R1 (B8) and R2 (B2); both fixed and handed back for a second combined re-review** (`docs/reviews/claude-m3-rereview2-package.md`, range `776119c..` the closing commit). Batch checks passed: Git Bash 2854 passed, PowerShell 2853 passed, only baseline failures; clean install passed. Nothing merged or pushed; M4 not started. History: **M3: Codex's milestone review at `4102817` requested changes B1–B8; all fixed and handed back for one combined re-review** (`docs/reviews/claude-m3-rereview-package.md`, range `4102817..` the closing commit). Nothing merged or pushed; M4 not started. History: **M3 built and handed over for one combined review** (`docs/reviews/claude-m3-milestone-package.md`, range `6085fd9..` the closing commit). Batch checks passed: Git Bash 2816 passed, PowerShell 2815 passed, only baseline failures; clean install passed. Nothing is merged or pushed; M4 not started. History: **M3 in progress on `m3/milestone`** (worktree `C:/Users/LOQ/TradingAgents-m3`, from `docs/m3-specs` `6085fd9`): the owner approved D1–D18 as recommended and the whole milestone (15 tasks, 52 h) on 2026-10-16, after Codex accepted the specs. Then one combined Codex review. M2 is done (local `main` `b7c5d2a`, no push). M1's hourly parts remain blocked on A4. |
| **Package name** | **`investment_engine`**: OPEN-01 confirmed by the owner on 2026-10-09. It's the internal Python package name; public branding is decided separately. |
| **Other branches** | `m1/batch-2` (at `0661d46`), `m1/batch-1` (at `109a72d`), `m1/M1-01-clock` (at `a8f338b`), `m1/M1-00-skeleton` (at `f906841`), `docs/m0-closeout` (at `9486f05`), `m0-architecture` (at `906ae85`) and `fix/report-reliability-baseline` (at `559f8c2`) are kept. Nothing has been deleted. |
| **Runtime code** | `tradingagents/` and `cli/` unchanged. `investment_engine` on `main`: the M1-02 – M1-05 modules, `market/calendar/`, `market/availability.py`, `market/candles.py`, `market/corporate_actions.py`, `market/store/`, `market/importers/` (verified Yahoo daily bars and actions; hourly BLOCKED), `market/replay.py`, `market/resample.py`, `market/data_health.py` and the daily NVDA CLI (`python -m investment_engine`). M2 added `quant/`, `decision/`, `lineage/`, `evaluation/` and `reporting/` (merged). |
| **Runtime tests** | Compared against the recorded baseline (`docs/baselines/M1-00-baseline.md`). On `main` (`b7c5d2a`, M2's final head): Git Bash **2390 passed, 1 failed** (baseline `test_yfinance_keeps_its_cache_out_of_the_users_home`); PowerShell **2389 passed, 2 failed** (both baseline: also the cp1252 CLI test), 4 skipped, 3 deselected (Claude, 2026-10-16). Codex's independent runs: 2390 passed in both shells with only the cache-location failure. CI not yet run. |

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
**Working method (owner instruction, 2026-10-14).** Each milestone is approved once as a package and built in one go: tests first, one automatic local commit per task, the task checks, then the batch checks, a self-review and **one Codex review of the whole milestone**. Non-blocking items for Codex are collected and handed over with that review. Blocking problems (a new test failure, a file outside a spec, an ADR or architecture gap, a blocked checkpoint, a contract that can't be implemented safely) still stop the work. Merges, pushes, key use, downloads and purchases each need the owner's explicit word. Shared rules §4 in AGENTS.md and CLAUDE.md record this.

1. **M2: done** (merged into local `main` at `b7c5d2a`, 2026-10-16; not pushed). *History:* step 0 integrates the reviewed M2 specs with Codex's five package-review corrections (`docs/reviews/codex-m2-package-review-2026-10-14.md`). Then M2-00 – M2-12 (M2-11 split into 11a and 11b: 14 tasks), the batch checks, self-review and the NVDA HTML research report from the saved, verified daily recordings. Then one combined Codex review. The M2 merge needs its own owner approval.
2. **M1 hourly (batch 3b):** blocked on A4 (account terms and retention/publication permissions); see `docs/hourly-access-review`. Whether any route avoids a given permission is unverified. Key use, access checks, checkpoint R and downloads each need separate authorization. M1 completes only when 3b and M1-17's hourly part (5b) merge.
3. **Pending for Codex at the M2 review (non-blocking):** the M1 deferred review items in "Open issues"; the M1-08 contract allowing `received_at < end_time` for a CLOSED bar (M2 enforces its own completed-bar cutoff, see M2-00/M2-03); the M2-11 split.
4. **M3:** the draft pack (`docs/tasks/M3-README.md`, M3-00 – M3-14) (v0.3) and proposed decisions D1–D18 await Codex's re-review and the owner's choices. M3 code needs the owner's milestone approval; M3-00 also needs a local PostgreSQL (D16).

**Owner's conditions for batch 2 (2026-10-12):**
- complete **2019 – 2026** calendar coverage from **cited official exchange sources**, special closures included;
- verify the `pyarrow` and `duckdb` wheels as M1-10 requires;
- **corporate actions take explicit instrument context** to check currency and exchange-local dates; the choice is recorded rather than defaults assumed;
- check both the base installation and the `engine` extra.

**`.env.example`:** the owner reverted the local edit (Codex confirmed on 2026-10-12 that it matches the committed version). Every commit still stages named files only.

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
- **`tzdata`:** declared explicitly and unconditionally in M1-06 (`tzdata>=2026.5`, the installed version), as Codex accepted on 2026-10-12.

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
| **Hourly verification still blocks M1-12/M1-13 and M1 completion.** Recorded high/low differences: **169 sessions in vendor units**, **181 under raw reconstruction**, plus **35 missing expected hourly starts**. No comparable independent hourly reference yet. A proposed vendor must actually provide the needed historical, unadjusted data with matching bar/session/auction/late-trade coverage; an account alone does not establish access or settle the evidence. No additional provider integration or account purchase is authorized here. | Owner/source decision, then reviewed evidence | Hourly M1-12/M1-13 |
| ~~Q1-2021 exact reference close~~ **Resolved for the acceptance test:** owner approved option B, **2021-07-01 <= date < 2021-07-20**, including the independently cited July 19 close $751.19 and excluding the split date. Q1 recording remains the date-filtered-history counterexample; MarketWatch archives remain supporting material only. | Owner/Codex | M1-13 |
| Which independent sources count as anchors | **Accepted with conditions in the owner-approved daily scope:** independent vendors' dated publications of explicitly unadjusted values, dated financial articles with exact value/trading date, and company announcements for splits/dividends. Primary daily decisions use July/Massive and NVIDIA anchors; retained MarketWatch archives are supporting only. | M1-12 daily scope implemented |
| The per-field Yahoo determination results | Determined in M1-12 | M1-12 / M1-13 |
| **Deferred review items (Claude Code review of `0661d46..62118a2`, 2026-10-12)**, recorded, not scheduled:<br>• **One bad vendor row aborts a whole bar import** (NaN, negative volume, inconsistent OHLC; `yfinance_bars.py` and the writer's checks). Fails safe and is documented; rejecting the row with a reason may suit M1-17's report better. A spec decision.<br>• **`decide_daily_volume` ignores documentation when anchors exist**, and doesn't flag a disagreement; **`decide_prices` doesn't enforce one anchor per split epoch** (only a test asserts it).<br>• **`decide_hourly_volume(comparable=True)` is a caller's self-declaration**; when hourly evidence arrives, comparability should come from an evidence record.<br>• **`series_values` keeps unchecked entries from before the range, zeros included**, which could inflate the skipped count if a fetcher returned bar-response action columns.<br>• **yfinance dependency range:** tests no longer depend on it (fix 3), but `pyproject.toml` still allows `>=1.7.0`, so a fresh install may get a version the importers refuse until it is verified. No dependency change was approved.<br>• Several Codex session-log headings show a literal `?` where a dash was lost. Cosmetic. | Owner and Codex, at the next spec review | Before M1-17 |
| **Separate, M1-08:** the `Candle` contract accepts `received_at < end_time` for a `CLOSED` bar, which is why nothing caught B1. A contract check belongs to M1-08, in its own reviewed change | Owner and Codex | A later M1-08 follow-up |
| How far back yfinance hourly history reaches | Measured in M1-13 | M1-13 |
| `pyarrow` / `duckdb` versions with Python 3.11 – 3.14 wheels | Checked in M1-10 | M1-10 |
| **Time-zone data (found in M1-01). Done in M1-06:** `tzdata>=2026.5` is declared explicitly and unconditionally in `[project] dependencies`, as M1-06 permits and Codex accepted. | — | **Done** (batch 2) |
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
| **Batch 3 review fixes** (`m1/batch-3`, after `f2536fb`) | Importer tests (three files): **124 passed**, 2 deselected. **Git Bash** full suite: **1910 passed**, 1 failed (`test_yfinance_keeps_its_cache_out_of_the_users_home`, baseline), 4 skipped, 3 deselected. **PowerShell** full suite: **1909 passed**, 2 failed (`test_every_command_is_registered_when_run_as_a_module` and `test_yfinance_keeps_its_cache_out_of_the_users_home`, both baseline), 4 skipped, 3 deselected. **No new failures.** `ruff check .`: all checks passed. **Clean-install smoke (base install, fresh `py -3.11` venv):** passed from the repository root and, from outside it, the three importer modules loaded from site-packages. The `engine` extra wasn't reinstalled this round. Live Yahoo checks not run. | Session log, 2026-10-12, "batch 3 review fixes" |
| CI | **Not yet run** (nothing pushed) | — |

---

## Session log

### 2026-10-17: Claude Code (M3 third re-review package: Codex's remaining R1 password cases fixed)
- **Codex's second re-review at `b716355`** (`docs/reviews/codex-m3-rereview2-b716355.md`) accepted R2/B2 and the API docs, and kept B1 and B3–B7 accepted. It left R1: a password under four characters, and a quote-and-backslash password shown as repr of its libpq form, survived redaction. The owner forwarded it on 2026-10-17 with: "fix both remaining password cases together, add regression coverage, preserve the accepted fixes, and return one checked follow-up package. Do not merge, push or start M4."
- **Commit:** `9500b2c` (M3-00, test harness only). The red/green evidence and Codex's probes (15 passed) are in its entry below.
- **Batch checks:**
  - **PowerShell:** 2 failed, 2860 passed, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed in 767.97s (0:12:47). Both are PowerShell baseline failures; no new ones.
  - **Git Bash:** 1 failed, 2861 passed.
  - **Ruff:** passed.
  - **Clean install:** base and engine both passed.
- **Residual:** pytest's 240-character repr cut could split a password in a very long DSN. It is recorded in the package with two options, and not addressed.
- **Owner decision:** keep the `ie_dev` password.
- **Still open:** `listen_addresses = 'localhost'`.
- **Next:** Codex re-reviews `b716355..` the closing commit. CI not yet run.

### 2026-10-17: Claude Code (M3-00 follow-up, Codex M3 second re-review R1: short and doubly escaped passwords)
- **Finding (`codex-m3-rereview2-b716355.md`):** `_remember` skipped passwords under four characters. A password with a quote and a backslash, libpq-quoted by the guard and then shown by pytest's repr, survived as that composed spelling. Codex reproduced both with synthetic credentials in both shells.
- **Fix (`tests/engine/conftest.py`):**
  - Every nonempty password is remembered, of any length.
  - `_spellings` remembers the DSN and the password as written, and every composition of libpq quoting, Python repr and URL encoding up to three deep.
  - `_scrub` replaces them in one regex pass, longest first, so a password that also occurs in the marker ("red" in `<redacted>`) can't match inside an earlier replacement.
  - A short password redacts its every occurrence, wanted or not: an unreadable report is preferred to a leaked one.
- **Regressions (`test_postgres_harness.py`):**
  - The nested driver test now runs over three synthetic passwords (the canary, `q7X`, and `IE_quote'back\slash`) × the three traceback styles. Its fake driver parses the conninfo into locals, as Codex's probe does. It checks the five shown spellings, written out independently of the fixture.
  - New `test_the_scrubber_covers_composed_spellings_and_never_rescans_its_marker`.
  - **Before the fix** (old `conftest.py` restored temporarily): `[default-short]`, `[default-quoted]`, `[locals-short]` and `[locals-quoted]` failed, and the scrubber test failed on the composed spellings and the unremembered "red". **After the fix:** harness file 62 passed.
- **Codex's probes:** `test_codex_m3_password_variants.py` (SHA-256 `a4dc6ce8…f07025`, as recorded), `test_codex_m3_short_password_probe.py`, and the earlier follow-up and review probes all passed: 15 passed, 1 deselected (`database_created_before_equity_followup`, under S1). They ran from temporary copies that were then deleted.
- **Residual, recorded:** pytest 9.1.1 cuts the middle out of any repr over 240 characters (`saferepr`). A password inside a DSN longer than that could be split, leaving a fragment that no full spelling matches. The test DSNs are 70–100 characters. Not reproduced, and not addressed here.
- **Checks (Git Bash):** ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2861 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 795.10s (0:13:15) (only failure: the baseline cache-location test).

### 2026-10-17: Claude Code (M3 second re-review package: Codex's R1 and R2 fixed)
- **Codex's re-review at `776119c`** (`docs/reviews/codex-m3-rereview-776119c.md`) resolved B1, B3, B4, B5, B6 and B7, and left R1 (B8: the password in a failing connection setup's report) and R2 (B2: a lineage published between check and use). The owner forwarded it on 2026-10-17 with: "Fix R1/B8 and R2/B2 together, preserve the six accepted fixes, align the snapshot API documentation, and run the required checks. Return one combined re-review package with follow-up commits. Do not merge, push or start M4."
- **Commits:**
  - `66d9513` R1 (M3-00);
  - `5130b73` R2 (M3-12);
  - `dcf0176` the M3-06 and M3-07 contracts.
  - Each fix has a regression test observed failing without the fix and passing with it, plus its own full run. Codex's two probes pass, run from a temporary copy that was then deleted.
- **Six accepted fixes:** no file they changed was touched, except that `pipeline.py`'s lineage read moved; their tests pass in the runs below.
- **Batch checks:**
  - **PowerShell:** 2 failed, 2853 passed, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed in 719.75s (0:11:59). Both are PowerShell baseline failures (the cp1252 CLI test and the cache-location test); no new ones.
  - **Git Bash** (R2 run): 1 failed, 2854 passed.
  - **Ruff:** passed.
  - **Clean install:** base and engine both passed; the installed `_propose` is the R2 code.
- **Corrected wording (B4):** the 15% drawdown claim holds only for the chosen single-instrument fixture (see the docs entry below).
- **S1:** the condition is kept.
- **Owner decision:** keep the `ie_dev` password.
- **Still open:** `listen_addresses = 'localhost'`.
- **Next:** Codex re-reviews `776119c..` the closing commit. CI not yet run.

### 2026-10-17: Claude Code (M3-06 and M3-07 docs, Codex M3 re-review: snapshot and clear API documentation)
- `docs/tasks/M3-06.md`: the `LimitStore` contract shows `clear_halt(..., equity_now: Decimal, effective_at: datetime | None = None)` and the new `last_clear_at(account_id, at) -> Halt | None`, with a dated note (B4).
- `docs/tasks/M3-07.md`: `build_snapshot(..., last_clear: Halt | None, history, source: str)`, with a dated note that the accepted text had `halt: Halt | None` and no `source`.
- Both checked against `investment_engine/risk/limits.py:273-294` and `investment_engine/portfolio/snapshot.py:157-159`. Documentation only; no code or test changes.
- **Wording correction (re-review, B4 integration evidence):** the earlier package and the B4 PROGRESS entry said a BUY can't reach a 15% drawdown under the 10% position cap. That holds only for the chosen single-instrument fixture, not for accounts with other holdings. Those dated records are left as written, and this entry and `docs/reviews/claude-m3-rereview2-package.md` give the corrected statement.

### 2026-10-17: Claude Code (M3-12 follow-up, Codex M3 re-review R2: the view is bound to the lineage record actually used)
- **Finding:** `propose()` compared the view with the stored lineage, but `_propose()` read the record again. If the first read missed and a producer committed the genuine NEUTRAL record before the second read, the comparison was skipped and a forged BULLISH view became a BUY bound to that record.
- **Fix (`investment_engine/oms/pipeline.py`):** the lineage record is read once in `propose()`. That same object is checked by `_view_mismatch(view, view_lineage_id, stored)` and passed to `_propose()`, which no longer reads it. A record missing at that read stays a missing `view lineage` prerequisite for this proposal, even if it is published meanwhile. The B2 checks themselves (every field compared, no repair) are unchanged.
- **Regression (`test_intent_pipeline.py`):** `test_a_lineage_published_between_check_and_use_never_binds_an_unchecked_view`. The producer's record is captured before commit; the first lineage miss commits it through another connection and then raises. The forgery gets PREREQUISITE_MISSING (`("view lineage",)`), with 0 intents and 0 intent lineage records. A rerun after the record is visible is refused as "differs from the decision stored". Without the fix (old `pipeline.py` restored temporarily) it fails at the PREREQUISITE_MISSING assertion; with it, all 25 pipeline tests pass. Codex's probe `test_a_lineage_published_between_validation_and_use_does_not_bypass_view_binding` (and the R1 probe) pass, run from a temporary copy that was then deleted, together with `test_approvals.py` and `test_intents_cli.py` (29 passed).
- **Checks (Git Bash):** ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2854 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 667.19s (0:11:07) (only failure: the baseline cache-location test). The M3-06/M3-07 documentation changes were in the tree for this run; they change no code.

### 2026-10-17: Claude Code (M3-00 follow-up, Codex M3 re-review R1: no password in a failing connection setup's report)
- **Finding:** with a failing driver connection, pytest's default and long traceback styles showed the root guard's and psycopg's own arguments (the rebuilt conninfo text), which held the password. `SecretDsn` covers only the fixture's own values.
- **Fix (`tests/engine/conftest.py`):** the fixtures remember every DSN they read (maintenance and per-test), plus its password as written, as libpq quoting escapes it and as a repr shows it. A `pytest_runtest_makereport` hookwrapper replaces each one with `<redacted>` in the report's longrepr and captured sections, for setup, call and teardown alike. `SecretDsn` and the assertion hook stay.
- **Regression (`test_postgres_harness.py`):** `test_a_failing_connection_setup_never_prints_the_password` runs a nested pytest that loads the real `tests.conftest` and `tests.engine.conftest`, sets a fake canary DSN and makes the root `PG_REAL["sync"]` raise. Under the default, `-l --tb=long -rA` and `--tb=native -rA` styles it asserts 2 errors, the diagnostic shown, and no canary. Without the fix the default and long variants fail. The native variant passes either way, since native tracebacks print no arguments. Codex's probe `test_connection_setup_failure_does_not_expose_fake_password` passes, run from a temporary copy that was then deleted.
- **Checks (Git Bash):** harness file 55 passed; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2853 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 828.03s (0:13:48) (only failure: the baseline cache-location test).

### 2026-10-17: Claude Code (M3 re-review package: Codex's B1–B8 fixed)
- **Codex's review at `4102817`** (`docs/reviews/codex-m3-milestone-review-4102817.md`) requested changes B1–B8 and suggested S1–S4. The owner forwarded it on 2026-10-17 with "fix B1–B8 in one uninterrupted follow-up package, with regression tests, task commits and required checks; return one combined re-review package; do not merge, push or start M4."
- **Fix commits:** `67a333a` B8, `c366387` B1, `46fd8b0` B4, `0059303` B6, `b66c075` B3, `d528c90` B2, `c81cb08` B7, `0558667` B5, `23f9d0a` S2 (tests), `2d38b3b` S3 (docs). Each has a regression test observed failing without its fix and passing with it, plus its own full run.
- **Batch checks:**
  - **PowerShell:** 2 failed, 2849 passed, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed in 998.80s (0:16:38). Both are PowerShell baseline failures; no new ones.
  - **Git Bash** (at the S2 tree): 1 failed, 2850 passed.
  - **Ruff:** passed.
  - **Clean install:** base and engine both passed.
- **S1:** the disposable-database condition is kept explicit (no persistent M3 database exists).
- **Owner decision:** keep the current `ie_dev` password.
- **Still open:** `listen_addresses = 'localhost'`.
- **Next:** Codex re-reviews `4102817..` the closing commit.

### 2026-10-17: Claude Code (M3 docs, Codex M3 review S3: current labels and implemented signatures)
- `docs/tasks/M3-README.md`: the title, the "no M3 code" sentence and the "none accepted" decisions heading now give the current state (accepted; implemented on `m3/milestone`; B1–B8 fixed for re-review). The v0.3 wording is kept as dated history.
- `docs/tasks/README.md`: the M3 line says accepted and in review, with the draft history kept.
- `docs/tasks/M3-12.md`: the contract block shows the implemented signatures: `at: datetime | None` on `propose` and `expire_due` (PAPER supplies none), and the full `propose_over_replay` parameters. The accepted text is quoted as history.
- **Checks:** documents only; `git diff --check` clean.

### 2026-10-17: Claude Code (M3-07, M3-09 and M3-12 follow-up, Codex M3 review S2: tighter acceptance evidence, tests only)
- **M3-12 (`test_intent_pipeline.py`):** the failure-injection helper also intercepts writes sent through `fetchone`/`fetchall`, so the intent store's compare-and-set `UPDATE ... RETURNING` writes are injected too. The each-write test asserts that at least one of them was.
- **M3-09 (`test_intent_store.py`):**
  - The race helper's racers read the current aggregate version *before* the barrier, so both hold the same expected version and exactly one stale write is deterministic.
  - New `test_the_store_refuses_every_illegal_edge_and_writes_nothing`: from every reachable state, SUPERSEDED included, every illegal target goes through the store and raises IllegalTransition (OrdersNotBuilt for APPROVED -> CONVERTED). Versions, history and the audit count are unchanged.
- **M3-07:** `test_a_split_since_the_start_makes_a_held_snapshot_unavailable` (the held-action test had used a dividend). `test_the_reference_guard_itself_refuses_a_forming_decision_bar`: a knowledge port answering a FORMING bar, since the store never holds one.
- **Checks (Git Bash):** the four files passed (155, plus the 4 gated race tests). Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2850 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 941.74s (0:15:41) (only failure: the baseline cache-location test). The S3 document changes were in the tree for this run; they change no code.

### 2026-10-17: Claude Code (M3-14 follow-up, Codex M3 review B5: `intents propose --at T` proposes at T)
- **Finding:** `--at T` picked the latest view at or before T but proposed it at the view's own time, with the feed stopping there. Deadlines, controls, expiry and knowledge were evaluated at the wrong time. One minute after a deadline, the command still created a fresh AWAITING_APPROVAL proposal dated the day before.
- **Change (`intents_cli.py`):** a single-time research proposal replays with `proposal_delay = T - view time` and a feed through T, so it acts at T and knows everything delivered by T. The `--from/--to` range is unchanged: each view at its own time.
- **Regression (`test_intents_cli.py`):** `test_research_at_is_the_proposal_time_with_knowledge_through_it`, through the CLI. Every proposal is recorded at T:
  - one minute after the deadline: EXPIRED_ON_ARRIVAL;
  - exactly at the deadline: EXPIRED_ON_ARRIVAL;
  - one minute before: AWAITING_APPROVAL;
  - a correction of a volume-window bar delivered between the view and T: its revision 2 is in the intent's lineage;
  - Level 2 effective between the view and T: APPROVED.
  Observed failing without the fix (no proposal recorded at T), passing with it.
- **Checks (Git Bash):** `test_intents_cli.py` passed (9). Ruff passed after sorting an import block; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2840 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 782.68s (0:13:02) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-12 follow-up, Codex M3 review B7: a revision mismatch is a recorded prerequisite failure)
- **Finding:** M3-08 rule 4 says a holding valued from another bar revision than the view's decision bar is a prerequisite failure. The sizer correctly refused it, but the pipeline let that refusal escape as a `ValueError`. A valid offline replay with a late correction (view on revision 1, correction delivered before the proposal, holdings with coverage) stopped the whole run.
- **Change (`oms/pipeline.py`):** before sizing, if the snapshot holds the view's instrument valued from a different bar than the pinned reference, the pipeline records PREREQUISITE_MISSING ("reference") naming both revisions. It's a stored record like any other prerequisite, with no intent, checks or intent lineage; the snapshot is stored because it was built. Every other sizing error still raises, so programming errors aren't hidden as missing data.
- **Regression:**
  - `test_a_correction_between_view_and_proposal_is_a_missing_reference_not_an_error` (`test_intent_pipeline.py`): Codex's sequence, a store correction at view+1 min and a proposal at view+2 min.
  - `test_a_correction_delivered_before_the_proposal_is_recorded_and_the_replay_continues` (`test_intent_replay.py`): three replayed views; the first records the missing reference and the next two are AWAITING_APPROVAL. The replay test helper now passes coverage through.
  - Both observed failing without the fix (ValueError), passing with it.
- **Checks (Git Bash):** both files passed (31). Ruff passed. The whitespace check found blank lines my script left at the ends of the two test files; they were removed before the full run. No `postgres` test skipped.
  - full suite: 1 failed, 2839 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 641.94s (0:10:41) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-12 follow-up, Codex M3 review B2: a view must be the decision stored in its lineage)
- **Finding:** the pipeline loaded the view's `LineageRecord` but sized and checked the separately supplied `MarketView` without comparing the two. A stored NEUTRAL decision re-presented as BULLISH under the same lineage id became a BUY in AWAITING_APPROVAL, which can't be reconstructed from the record (Law 18).
- **Change (`oms/pipeline.py`):** before any mutation, the supplied view must equal the stored decision with exactly its lineage id as evidence, the form M2's `run_views` hands out. Nothing is replaced or repaired. A mismatch returns a PREREQUISITE_MISSING ("view lineage") diagnostic naming the differing fields, like an unknown account: nothing is stored, nothing expires, and the genuine view can still be proposed. A named but unstored lineage id keeps its ordinary stored record.
- **Regression (`test_intent_pipeline.py`):** `test_a_view_must_be_exactly_the_decision_stored_in_its_lineage` covers forged direction, health, validity, generation time, instrument, an extra evidence reference, a stronger BULLISH view, and another decision under this lineage id. All are refused with the field named; database counts are unchanged; a waiting intent isn't expired; the genuine view then proposes normally. Observed failing without the fix (the forged view was accepted), passing with it.
- **Test data corrected:** two tests had proposed a modified copy of a view (a shortened `valid_until`) under its original lineage. That is now refused, correctly. They store a genuine view with that validity instead, through a new `valid_until` parameter of `view_for`: `test_level_2_approval_never_outlives_the_view` (M3-12) and `test_the_view_validity_caps_the_expiry` (M3-13's `test_approvals.py`, test data only).
- **Checks (Git Bash):** the pipeline, replay, CLI and approvals files passed. Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2837 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 640.35s (0:10:40) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-09 follow-up, Codex M3 review B3: no unaudited metadata route)
- **Finding:** `IntentStore.set_fields` could change approval fields, decisions, deadlines and lineage with only an aggregate compare-and-set. It checked neither state nor latest version and wrote no transition or audit event, against M3-09 rules 3 and 5. Codex rewrote an approved intent's approver with it.
- **Change (`oms/intent_store.py`):** the unused mutator is removed (it had no callers). The store's only writers are `create`, `transition` and `supersede`, each atomic with its audit event. Material columns stay protected by the 0009 triggers.
- **Not done:** a SQL trigger refusing same-state updates of approval fields. It would mean editing `0009_intents.sql` in place again, which Codex accepted only for disposable databases (S1). It is left as possible later hardening.
- **Regression (`test_intent_store.py`):** `test_approval_evidence_and_history_change_only_through_audited_transitions`. The public writers are exactly create, transition and supersede. A second approval with other evidence raises IllegalTransition and writes nothing (record and audit count unchanged). A superseded version can't be moved. Observed failing before the change (`set_fields` was a public writer), passing after.
- **Checks (Git Bash):** `test_intent_store.py` passed (102). Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2836 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 636.30s (0:10:36) (only failure: the baseline cache-location test). The whitespace check then flagged a blank line at the end of the test file, which my script had added; it was removed before this commit.

### 2026-10-17: Claude Code (M3-08 and M3-11 follow-up, Codex M3 review B6: sizing and risk ignore the caller's decimal context)
- **Finding:** explicit `Context` methods covered some operations, but unqualified `quantize`, built-in `sum` and the reason formatting used the caller's ambient context. Under different rounding, identical inputs gave different recorded reasons (so different decisions); at precision 6 an ordinary approval raised `InvalidOperation`. Risk also kept one shared module context, not the fresh one M3-11 rule 4 asks for.
- **Change:**
  - **`risk/decisions.py` (helpers, M3-11):** `calculation_context()` is a fresh, fully specified context: precision 34, ROUND_HALF_EVEN, traps on InvalidOperation, DivisionByZero and Overflow. `exact` runs a function inside it and leaves the caller's context untouched.
  - **`risk/checks.py` (M3-11):** `check_risk`, `average_daily_value` and `reduced_version` are `exact`; the shared `CTX` is gone, and every operation, reasons included, uses the fresh context.
  - **`portfolio/sizer.py` (M3-08):** `size` is `exact`, so the limit price's `quantize` too.
- **Regression:**
  - `test_risk_results_ignore_the_callers_decimal_context`: five ambient contexts (precision 6/9/28/50; floor, ceiling, half-up, down, 05up; Inexact and Rounded trapped). It covers approve, a two-check reduction and its v2 and re-check, and a drawdown rejection with its halt request, by canonical JSON (quantities, decisions, reasons, identities). The caller's context is checked as unchanged.
  - `test_sizing_ignores_the_callers_decimal_context`: four contexts with Inexact trapped; BUY, SELL, and a large price.
  - All 9 observed failing before the fix; the restructured sizing test again failed without the sizer change, and passes with it.
- **Checks (Git Bash):** the risk, sizer and pipeline files passed. Ruff passed after sorting imports; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2835 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 630.88s (0:10:30) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-06, M3-07 and M3-12 follow-up, Codex M3 review B4: a clear records its equity, and the drawdown epoch is the latest clear)
- **Finding:** D3 restarts the high-water mark from the equity **at the clear**. `clear_halt` made that value optional, and the CLI never supplied it. The baseline also came from the latest halt event, so a re-halt after a clear fell back to the original start. In Codex's example (100,000, cleared at 85,000, then 60,000), the post-clear loss showed as no drawdown.
- **Change:**
  - **`risk/limits.py` (M3-06):** `clear_halt(..., equity_now)` is required: a finite Decimal, otherwise `TypeError` and nothing cleared. A cleared `Halt` can't be built without it, and a halt can't carry a baseline. New `last_clear_at(account, at)`: the latest clear, whatever happened since.
  - **`admin_cli.py` `limits clear-halt` (M3-06):** values the account at the clear time from its declared start (local data only; cash-only needs none) and records that equity. If the equity can't be established (no declared start, or holdings without established coverage), it refuses with the reason and clears nothing. RESEARCH needs `--effective-at`.
  - **`portfolio/snapshot.py` (M3-07):** `build_snapshot(..., last_clear=...)` replaces `halt=`. The epoch is the latest clear, with its equity as a floor, or else the declared start.
  - **`oms/pipeline.py` (M3-12):** the peak query and the snapshot use `last_clear_at`.
- **Tests:**
  - **Corrected:** the restored `test_peak_equity_and_the_drawdown_baseline` (M3-07) had encoded the old behaviour (a no-equity clear, and a return to the old peak after a halt). It now asserts the clearing equity as the floor and refuses a halt passed as a clear.
  - **New, M3-07:** `test_a_clear_always_records_its_equity`; `test_a_loss_after_a_clear_without_a_snapshot_is_measured_from_the_clearing_equity` (Codex's 100,000 / 85,000 / 60,000 case).
  - **New, M3-06:** `test_clearing_requires_the_equity_at_the_clear_and_its_epoch_survives_a_later_halt`; `test_the_cli_clears_a_halt_at_the_equity_valued_at_the_clear`.
  - **New, M3-12:** `test_the_drawdown_epoch_is_the_latest_clear_even_after_a_later_halt`. It runs through the pipeline: 100,000; 85,000 (halt); cleared at 85,000; 60,000 (29.4% below the clear, halt); 80,000. Every snapshot after the clear measures from 85,000. The halts are applied as the risk check requests them; the BUY-side halt rule itself is M3-11's tested behaviour, and a BUY can't reach a 15% drawdown under the 10% position cap.
  - Observed failing before the fix (3 of the new tests), passing after.
- **Checks (Git Bash):** the four affected files passed (70). Ruff then flagged a missing `Decimal` import for an annotation and a dict comprehension; both fixed, and the B4 tests passed again. Whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2826 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 635.33s (0:10:35) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-06 follow-up, Codex M3 review B1: restricted-list changes are serialized)
- **Finding:** `restrict`/`unrestrict` read the current rules before `publish_policy` took the account-control lock. Two concurrent changes could both build on the same stale list, so one change was silently lost, possibly a restriction an Admin had just added.
- **Change (`risk/limits.py`):** the read, the change and the publication run in one managed transaction under the account-control lock. The nested publish joins it, and the lock is re-entrant within the transaction.
- **Regression (`test_limits.py`):** `test_concurrent_restriction_changes_both_survive`, add/add and add/remove, 20 repetitions each. The racers wait at a barrier just before taking the lock. The test checks the final rules and that every published version differs from its predecessor by exactly one instrument (the audit chain, ordered by version). Observed failing without the fix (add/add kept only AMD; add/remove brought NVDA back), passing with it.
- **Checks (Git Bash):** `test_limits.py` passed (23). Ruff first flagged the new test's thread closure (unbound loop variables) and a `zip` without `strict`. I fixed both after the full run below; the file passed again and ruff passed. Whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2821 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 690.51s (0:11:30) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-00 follow-up, Codex M3 review B8: the test DSN never reaches failure output)
- **Finding:** pytest prints a failing test's fixture values, so `pg_database`'s plain DSN string, password included, appeared in any failing PostgreSQL test's report. `bd18615` had covered subprocess argv only.
- **Change (`tests/engine/conftest.py`):**
  - The fixture, `maintenance_dsn()` and `temporary_database` hand out a `SecretDsn`: a `str` subclass that libpq uses as before, with the repr `<test PostgreSQL DSN, redacted>`. That covers failure reports, `--showlocals` and `!r` formatting.
  - A `pytest_assertrepr_compare` hook withholds both sides of any failed comparison involving a DSN. pytest otherwise quotes the raw text, for example of `dsn not in output`.
  - The environment-only subprocess change (`bd18615`) stays.
- **Regression (`test_postgres_harness.py`):** a nested pytest run uses the real fixture with a fake canary password and no server. It covers a body failure with captured output, equality and containment failures, `!r` formatting, a setup error and a teardown error, under the default, `-l --tb=long -rA` and native tracebacks. The run must show exactly "4 failed, 1 passed, 2 errors" and never the canary or `password=`. It was observed failing before the change (the fixture had no redaction; the first containment hook still quoted the other side) and passes now. This is also the nested failure-output evidence that M3-00's deviation lacked.
- **Owner decision (2026-10-17):** the owner keeps the current `ie_dev` password. It was printed only locally: a redacted scratch log and this session's output.
- **Checks (Git Bash):** the harness file passed (52). Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2819 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 690.48s (0:11:30) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3 milestone close: batch checks, self-review and the review package)
- **All 15 tasks are committed (checked)** on `m3/milestone`, with follow-ups, in the range `6085fd9..` this commit. Package: `docs/reviews/claude-m3-milestone-package.md` (commits, where to look hardest, incidents, deviations, owner items).
- **Batch checks:**
  - **B1, PowerShell** (`& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfEs`, cwd the M3 worktree): 2 failed, 2815 passed, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed in 645.18s (0:10:45). Both failures are the PowerShell baseline (the cp1252 CLI test and the cache-location test). No new failures.
  - **B2, clean install:** passed in fresh `py -3.11` venvs. `pip install .` gave the CI import from the root, and `intents_cli` from outside without psycopg. `pip install ".[engine]"` gave the CI import, eleven M3 modules from site-packages, schemas `0001`–`0010`, the limits file, psycopg 3.3.6 binary and the new commands.
  - **Git Bash** (last task-level run at `bd18615`): 1 failed, 2816 passed (the baseline only). Ruff passed.
- **Self-review**, against the specs and laws with adversarial probes, produced:
  - two follow-ups: `c273a9b` (views without lineage) and `bd18615` (the test DSN was printed on a subprocess failure);
  - in-task fixes, recorded in their entries: the PAPER live-time check, lineage ids hashing provenance, stale per-version lineage values, `list` showing the current state, and read-only `list`/`show`.
- **Owner items:** set `listen_addresses = 'localhost'`; change the local `ie_dev` test password (the package's incident 3); merge and push need your word.
- **Not run:** CI; Python 3.12–3.13; any network call or market download.
- **Next:** the owner's complete milestone review and Codex's review of every commit in the range. Findings come back as follow-up commits.

### 2026-10-17: Claude Code (M3-04, M3-05, M3-06, M3-07 and M3-09 follow-up: the test DSN never goes on a command line)
- **Found:** five fresh-process tests passed the test database DSN to their subprocess as an argument. When one failed, pytest printed the `CompletedProcess` with its arguments, so the DSN, **password included**, appeared in a local scratch log (outside the repository) and in this session's tool output. It happened during the discounted M3-14 run, when Windows couldn't start processes. Nothing was committed or sent anywhere else.
- **Change:** the probes now read the DSN from an `IE_PROBE_DSN` environment variable given to the subprocess. The environment isn't part of `CompletedProcess`'s output. The files are each task's own test file: `test_audit.py` (M3-04), `test_accounts.py` (M3-05), `test_limits.py` (M3-06), `test_portfolio_snapshot.py` (M3-07) and `test_intent_store.py` (M3-09).
- **Owner action suggested:** change the local `ie_dev` test password and update `INVESTMENT_ENGINE_TEST_PG_DSN`. The role is local, loopback-only and not a superuser.
- **Checks (Git Bash):** the five tests passed. One full run covered this and the M3-12 follow-up together; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2816 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 625.84s (0:10:25) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-12 follow-up: a view without lineage is never stored)
- **Found in self-review:** proposal records are keyed by (account, view lineage id). A view naming no lineage record was stored under the empty id, so a second such view for the same account would have returned the first one's record.
- **Change:** such a view now gets a returned PREREQUISITE_MISSING diagnostic ("view lineage"), like an unknown account. Nothing is stored and nothing expires. A view naming a lineage id that isn't stored still gets an ordinary stored record.
- **Test:** `test_views_without_lineage_get_a_returned_diagnostic_and_never_share_a_record`. Observed failing without the fix (records stored), passing with it.
- **Checks (Git Bash):** one full run covered this and the DSN follow-up together. Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2816 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 625.84s (0:10:25) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-14: the CLI report of proposed intents with reasons)
- **Built:**
  - `investment_engine/intents_cli.py`: `views replay`, and `intents propose|list|show` on the Admin CLI's intents group.
  - `cli.py`: registration only (an import and `add_typer` for `views`).
- **The report:**
  - Every output starts with the safety header (account and kind, autonomy level, PAPER or RESEARCH mode, no orders, kill switch not built, declared starting state, limit and rule versions in force).
  - `show` prints every version with each policy and risk check, reductions as "v1 82 -> v2 10: <reason> (risk-1)", deadlines and expiries in UTC and exchange time, the approver and the lineage id.
  - `list` prints each proposal's outcome and reason and, for an intent, its current state ("now EXPIRED"). An intent that was AWAITING_APPROVAL when proposed may since have expired.
  - `list` and `show` open the database read-only (rule 5).
- **Tests first:** `tests/engine/test_intents_cli.py` was written first and failed (module missing). Eight tests:
  - every outcome and its reason;
  - the header;
  - deterministic output;
  - unavailable values never printed as 0;
  - a PAPER account rejected for promotion at live time;
  - `views replay` without local data writes nothing;
  - read-only `list`/`show`;
  - two end-to-end tests on a synthetic store with a late-delivered correction and an equal-time pair. The CLI-only setup and replay is byte-identical in two fresh databases set up on different days, and proposals before T0 are PREREQUISITE_MISSING. The CLI's proposals match `propose_over_replay` called directly with a feed over the whole store.
- **Notes for review:**
  - PAPER proposals take the live time (no time supplied).
  - `propose` passes no action coverage, so an account declared with holdings gets PREREQUISITE_MISSING ("no established coverage"). M3 accounts are cash-only by default (D14), so the demo is unaffected.
- **Checks (Git Bash):** the file passed (8). Ruff passed; whitespace clean; no `postgres` test skipped.
  - **First full run, not counted:** 11 failed (the baseline plus 10 fresh-process and subprocess tests) in 732.14s. Every new failure was a subprocess exit 3221225794 (0xC0000142, DLL initialisation failed), including the unrelated `cli.main backtest --help`. Windows couldn't start processes. That run probably overlapped the previous check, which I had stopped to add the read-only change. The failing files passed alone (43 passed).
  - **Rerun alone:** 1 failed, 2815 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 654.82s (0:10:54) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-13: approve, decline and expire at the Admin CLI)
- **Built:**
  - `oms/approvals.py`: `approve`, `decline`, `ApprovalRefused` and `record_refusal`.
  - The `intents approve|decline|expire` commands, added to `admin_cli.py`'s `GROUPS`.
  - Who may act is checked at the real command time; the deadline, autonomy setting (by `setting_id`), limits and rules versions and any halt are checked at the business time.
  - Both times are recorded; every refusal is audited in its own transaction.
  - The account-control lock serializes approvals with control changes.
- **Stale writes:** the command acts on the intent as read before the lock. If expiry or another approval changed it meanwhile, the aggregate-version check reports "intent changed meanwhile; nothing approved".
- **Tests first:** both spec test files were written before the code and failed (module missing; commands missing).
  - Refusals: wrong version, old version after a reduction, not awaiting, deadline (exactly at it too), earlier than the proposal, Viewer, inactive, unregistered, autonomy 1 -> 2 -> 1, new risk limits, new rules, halt. Each changes nothing and writes one refusal event.
  - Races on PostgreSQL: approve vs expire and two approvals (10 repetitions each); approve vs `set_autonomy` and vs `limits publish` (50 each). The racers wait at a gate just before the account-control lock, and the test records lock order, which is commit order.
  - CLI: an operator added today approves a 2021 intent; an inactive operator and a Viewer are refused with an earlier `--at`; PAPER refuses `--at`; expire changes one account only; `--paper` never touches RESEARCH; decline needs a reason.
- **Deviations to review:**
  1. The CLI checks `--version` and `--reason` itself instead of Typer's required options. Typer's usage-error box is not ASCII (rule 6), and a missing reason is now an audited refusal (rule 7).
  2. A PAPER `--at` is refused by the CLI even when it equals the live time; the refusal is audited through the new `record_refusal`. `approve`/`decline` themselves refuse a PAPER `at` different from `command_at`.
  3. A missing `--at` for RESEARCH is reported as a usage error, not audited (no time to act at).
- **Checks (Git Bash):** the two files passed (25, about 2 minutes). Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2807 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 586.44s (0:09:46) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-12: the intent pipeline, intent lineage and replay proposals)
- **Built:**
  - `oms/pipeline.py`: `propose`, `expire_due`, `expire_paper_due`, `propose_over_replay`, `ProposalRecord`/`ProposalStore` and `ControlStores`. It covers the outcome matrix (B3), BUY admission under the `buy-admission|account|session` lock (B5), legal-edge routing including EXPIRED_ON_ARRIVAL (S5), one managed transaction per (account, view), idempotent re-runs, and replay reads through the Knowledge port (S2).
  - `lineage/intent_lineage.py`: one append-only record per intent version.
  - `schema_pg/0010_intent_lineage.sql`; the registry lines.
- **Tests first:** the four spec test files were written before the modules and failed at import (observed). The draft was extended to cover every acceptance test:
  - a failure injected at each write in turn (every write of a successful run was tried);
  - the admission side cases (reduction, approval, rerun, decline, expiry, rollback, SELL);
  - replay delivery after availability, equal-time sequence order, a missing session, settings effective too late;
  - determinism across fresh databases and setup days;
  - the two research timelines, and PAPER live-time only.
- **Found and fixed while testing:**
  1. **PAPER time check:** the draft compared a supplied `at` with a second read of the live clock, which a real LiveClock never matches. PAPER calls now supply no time (`at=None`), and a supplied one is refused (spec rule 1: "a supplied replay time raises"). RESEARCH requires one. `expire_paper_due` takes the live clock, as the contract shows.
  2. **Lineage ids differed between setup days:** the id hashed the `AutonomySetting`, including its provenance (`recorded_at`, `set_by`). It now hashes the setting's deterministic `setting_id`; the full setting is still stored (S2).
  3. **Stale lineage values:** a version's lineage closure read whatever admission count and volume references were current when it was called, so a reduced v2 could inherit v1's. Both are now bound per version; a policy rejection records none, and a SELL records no admission count.
  4. **Idempotency inside the lock:** the existing-record check now runs under the account-control lock.
- **Test-data notes:** an account holding shares needs established action coverage to be snapshotted (Law 9), so those tests pass coverage. A volume gap is RISK_REJECTED (ADV unavailable, no older bar); a missing decision bar or valuation bar is PREREQUISITE_MISSING.
- **Lineage `final_state`** is the state the pipeline routed the version to. A later expiry or approval is in the intent's transition history.
- **Checks (Git Bash):** the four files passed (39, including the 50-repetition race, about 165 s). Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2782 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 598.08s (0:09:58) (only failure: the baseline cache-location test)
  - **The suite is now about 10 minutes**, mainly from the race test. Each proposal reads 20 Parquet files for its average daily value; flagged as a later optimisation.

### 2026-10-17: Claude Code (M3-07 follow-up: complete replay knowledge, and the drawdown peak query)
- **Why:** M3-12 proposes over a replay at the view's time, which comes after the last delivered bar. M2's `ReplayKnowledgeReader` refuses any time later than its last delivered event, because more events might still arrive. Separately, building each snapshot reloaded the account's whole snapshot history to find its drawdown peak, so a run of proposals slowed down quadratically.
- **Change, within M3-07's allowed files:**
  - `ReplayKnowledge` takes `complete_through`. The caller uses it to declare that every event delivered up to that time has been fed. Queries up to that time are then answered from what was delivered; anything later is still refused. `actions_between` clamps its query time to the last delivered event in the same case.
  - `portfolio_snapshots` gained an `equity NUMERIC NOT NULL` column. `SnapshotStore.peak(account_id, since=, at=)` returns the highest-equity snapshot in a range.
  - `0008_portfolio.sql` was **edited in place**, not given a new script: it is unmerged, and only per-test databases have used it. This is flagged for review.
- **Still reads M2 internals:** `ReplayKnowledge` reads the private `_check_at` and `_delivered_until` of `ReplayKnowledgeReader`. This is flagged for the milestone review.
- **Tests:** two added, `test_a_caller_that_fed_every_event_can_query_after_the_last_one` and `test_the_peak_query_returns_the_highest_equity_snapshot_in_range`. Both files passed (21).
- **Checks (Git Bash):** ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2743 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 345.53s (0:05:45) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-11: risk checks: approve, reject or reduce)
- **`risk/checks.py`:** `RiskInputs`, `HaltRequest`, `check_risk`, `reduced_version` and `average_daily_value`.
  - **Checks, in order, all reported:** `fresh_data`; `halt`; `drawdown` (D3; at the threshold a BUY is rejected and a HaltRequest returned unless already halted); `min_price` (D6); `position` (D1, BUY only); `cash` (D2, BUY only, gross exposure included); `liquidity` (D4, BUY and SELL); `daily_buys` (D5).
  - **Admission (S3):** `daily_buys` fails exactly when the intent isn't `already_admitted` and the count excluding itself is at the cap.
  - **Outcome:** failures of 1–4 or 8 reject. Failures of only 5–7 reduce to the smallest allowed whole quantity: partial SELLs (D18). Below `min_quantity` it rejects (D9), and a second reduction of a reduced version rejects with "reduction did not converge".
  - **`reduced_version`:** keeps the id and every material field except the quantity (Law 12).
  - **`average_daily_value`:** needs every one of the last N expected sessions; a missing one gives the reason, never an older bar (S2).
  - **Determinism:** Decimal only; nothing is read from a store or clock; exactly at a limit passes. Mismatched limit versions or snapshots raise.
- **Tests first:** `tests/engine/test_risk_checks.py` was written first and red at collection; 10 passed after the implementation. They cover:
  - approval and the check order;
  - exactly at the position cap;
  - each reducible check alone with hand-calculated quantities (82, 8, 41);
  - several reducible failures taking the minimum, and below one share rejecting;
  - the reduction as a new version that re-checks to APPROVE, and a forced second reduction rejecting;
  - halts rejecting BUYs but passing SELLs, and the drawdown threshold requesting a halt once;
  - stale, unhealthy or expired views, missing volume and a cheap stock rejecting;
  - the cap with admitted and unadmitted v2;
  - S6's $100,000 holding selling down to the volume limit;
  - determinism and inconsistent inputs.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2741 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 352.82s (0:05:52) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-10: policy checks)
- **`policy/checks.py`:** `check_policy(intent, *, account, autonomy, rules, instrument, snapshot, view_lineage, calendar, at)` runs every check, in order, each with a fixed-template reason:
  - `autonomy`: Level 0 fails;
  - `promotion`: every PAPER intent fails, "PROMOTION NOT ASSESSED", naming the strategy versions (D15, Law 19); RESEARCH passes;
  - `instrument`: must be ACTIVE and inside its dates on the target session;
  - `restricted`: the rules version's list (D8);
  - `long_only`: a SELL can't exceed the holding (D2);
  - `trading_window`: a regular session, DAY LIMIT and a D1 view (D7, D12).

  The decision passes only if all pass, with `decided_at = at`. No store, clock or external text is read. Inconsistent inputs raise rather than decide: another account's intent, snapshot or setting, another instrument, or a rules version other than the intent's.
- **Tests first:** `tests/engine/test_policy_checks.py` was written first and red at collection; 7 passed after the implementation. They cover:
  - each check failing alone with its exact reason, and all passing;
  - several failures reported together, and PAPER failing promotion at Levels 1 and 2;
  - long-only with an oversized SELL, and instruments outside their active dates;
  - rules versions applying exactly as published;
  - determinism and the inconsistent-input refusals.

  The package-wide no-system-clock test covers the new module.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2731 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 272.13s (0:04:32) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-09: intent store and the G2 state machine)
- **`oms/intent_states.py`:**
  - `ALLOWED` is exactly the frozen G2 table, and `FINAL` the six terminal states.
  - `check` raises `IllegalTransition` for a non-edge. For APPROVED -> CONVERTED it raises the separate `OrdersNotBuilt`: a legal G2 edge that M3 refuses until M4.
- **`oms/intent_store.py`:** `IntentStore` is PostgreSQL only and shares one port with audit and accounts.
  - **Compare-and-set:** one `aggregate_version` per intent id covers all versions. Each write moves it by exactly one in a single `UPDATE ... RETURNING`; a stale expected version gives `StaleWrite` and writes nothing.
  - **Writes:** `create` (v1, idempotent; different content under the id raises). `transition` checks G2 legality first, acts on the latest version only, and refuses SUPERSEDED, which only `supersede` writes. `supersede` marks the old version and creates v+1 in one compare-and-set step, changing only the quantity. `set_fields` records decisions or lineage without a state change.
  - **Logs and audit:** every move is logged append-only, with one audit event in the same transaction: command time from the clock, and `business_at` for RESEARCH accounts.
  - **Queries:** `due_for_expiry(account, at)` is per account (R3). `admitted_buys(..., excluding=)` counts distinct BUY intent ids that ever entered AWAITING_APPROVAL or APPROVED (D5), and `was_admitted` answers for one intent (S3).
- **`schema_pg/0009_intents.sql`:** `intents`, `intent_versions` and `intent_transitions`. Triggers refuse any update of material or reference columns or content (Law 12), refuse anything but a one-step forward move of the aggregate, refuse deletes and truncates, and keep the log append-only. The audit registry now also lists `oms.intents`, `policy.decisions`, `risk.decisions` and `oms.intent_store`.
- **Tests first:** `test_intent_store.py` was written first and red at collection. Fixes found by the tests:
  - **Code:** `supersede` had moved the aggregate twice (the trigger refused it), so the new latest version now goes in the same single step. `transition` now checks legality before its SUPERSEDED guard, so moves out of a final state always report `IllegalTransition`.
  - **Tests:** the race helper had kept every connection open and exhausted the server's slots, so each racer now closes its own; one expected aggregate version was off by one; events at the same command time order by id.

  101 passed. They cover:
  - the frozen table, and all 81 state pairs as allowed, guarded or illegal;
  - every allowed edge through the store, including the CONVERTED refusal;
  - final states, stale writes, and atomic supersede limited to the quantity;
  - SQL refusals of material updates, aggregate rewrites and log changes;
  - create idempotency, audit times, admission counting and per-account expiry;
  - fresh-process decoding;
  - four races, each from a state where both moves are legal (approve vs expire, approve vs decline, expire vs supersede, reject vs supersede), each run 50 times: exactly one winner, no lost update.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2724 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 272.38s (0:04:32) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-08: OrderIntent contract and position sizer)
- **`oms/intents.py`:**
  - `Side`; `IntentState`, with all nine G2 states (CONVERTED exists for M4's contract).
  - `intent_id_for`: `int-` + SHA-256 of the account, view lineage, instrument and sizer version.
  - `OrderIntent`: frozen, with the Part H fields plus the gate's inputs (reference bar, view validity, snapshot, policy and limit versions). It refuses fractional or non-positive quantities, floats, naive times, non-LIMIT or non-DAY orders, and a bad `supersedes`. `MATERIAL` lists the seven fields Law 12 freezes.
- **`policy/decisions.py`:** `CheckResult` (a reason is always set) and `PolicyDecision`, which passes exactly when all its checks pass.
- **`risk/decisions.py`:** `RiskOutcome`, `RiskDecision` (`reduced_quantity` exactly for REDUCE, whole shares), and `NotRun(stage, reason)` (B3). All are codec-registered; audit-registry entries come with M3-09, whose files include the registry.
- **`portfolio/sizer.py`:** `size(...)` with `SIZER_VERSION = "sizer-target-weight-1"`.
  - **Order of decisions:** ABSTAIN, then an expired view, then NEUTRAL each give no intent, with the reason.
  - **BULLISH:** targets 10% of equity. The limit is the reference + 1%, rounded down to the cent; the quantity is floored to whole shares.
  - **BEARISH:** sells everything held, at the reference - 1% rounded up; nothing when flat.
  - **No intent** when below one share or already at the target.
  - **Consistency:** the reference must come from the view's lineage (provider, instrument, bar) and match the holding's bar revision, or `size` raises (B1).
  - **The rest:** target session = the next regular session after T; `created_at = at`; no clock read.
- **File-name note:** both acceptance areas (intent contract and sizer) are in `tests/engine/test_sizer.py`; there is no separate `test_order_intent.py`.
- **Tests first:** written first and red at collection; 10 passed after the implementation. They cover:
  - the first BUY from the cash-only account (82 shares at 121.20 for 120.00 and $100,000);
  - hand-calculated sizes, including exactly one share;
  - below one share, at target, NEUTRAL, ABSTAIN and expired;
  - BEARISH with and without a holding, and both rounding directions;
  - reference and holding mismatches raising;
  - determinism, and the id depending on the sizer version;
  - value refusals and frozenness;
  - decision-contract round trips and refusals.
- **Checks (Git Bash):** see the result line below; whitespace clean; no `postgres` test skipped. Ruff first flagged a nested `if` in `risk/decisions.py`. I combined it while the suite was already running; ruff then passed at the end of the same check run, and the 10 task tests passed again on the fixed file.
  - full suite: 1 failed, 2623 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 237.84s (0:03:57) (only failure: the baseline cache-location test)

### 2026-10-17: Claude Code (M3-07: raw reference prices and PortfolioSnapshot)
- **`portfolio/reference.py` (Codex B1):**
  - **`RawReference`:** a raw Decimal close; floats are refused by type, so M2's adjusted `decision_close` can't enter.
  - **`decision_reference`:** finds exactly one decision bar in the view's lineage (the D1 bar of the snapshot's session, provider and instrument) and reads exactly that revision. A missing bar, two candidates, another provider, instrument, revision or session, a non-CLOSED bar or a currency mismatch gives `Unavailable` with the reason.
  - **The `Knowledge` port:** `StoreKnowledge` (live: available and received by T) and `ReplayKnowledge` over M2's `ReplayKnowledgeReader` (delivery time and equal-time `through_sequence`). Both answer `candle_revision`, `latest_closed` and `actions_between`.
- **`portfolio/snapshot.py`:**
  - **`StartingState`:** declared; its `state_id` excludes `recorded_at` and `declared_by`; whole shares; Decimal cash only.
  - **`PortfolioSnapshot`:** `held()` is 0 when nothing is held; DECLARED source only, LEDGER refused until M5.
  - **`build_snapshot` valuation:** held positions are valued at the raw close of the latest completed session's bar. A missing or not-yet-known bar is `Unavailable`; an older bar is never used (S2).
  - **`build_snapshot` actions:** missing or short action coverage, or a split or dividend since the start for a held instrument, is `Unavailable` ("ledger needed (M5)").
  - **`build_snapshot` drawdown baseline:** it restarts after a clear (D3, S6), with the clear's equity as a floor when recorded.
  - **`PortfolioSnapshotStore`:** `declare_start` is Admin-only, once per account, audited and serialized by the account-control lock; RESEARCH uses replay time and PAPER can't backdate. Snapshots are append-only (`get`, `latest`, `history`).
- **`schema_pg/0008_portfolio.sql`** adds `starting_states` and `portfolio_snapshots` (append-only). The audit registry lists `portfolio.reference` and `portfolio.snapshot`. The Admin CLI gains `accounts declare-start`.
- **Contract notes for Codex (non-blocking):**
  - **Extra parameters:** `build_snapshot` also takes `source` (whose bars value holdings), and the `Knowledge` port gains `actions_between` for rule 4.
  - **`ReplayKnowledge` reads M2's `ReplayKnowledgeReader` internals** (`_candles`, `_check_at`) for exact-revision lookups. `decision/pipeline.py` isn't in M3-07's files. A public `candle_revision` on the reader would be cleaner in a later reviewed change.
- **Tests first:** both test files were written first and failed at collection. Corrections to my tests:
  - test bars needed valid OHLC, and the store refuses FORMING bars by design;
  - the store never backdates a correction, so "available before T, delivered after" is tested in replay;
  - the rise-and-fall peak scenario got its own price series;
  - the float-cash check had been converting the value first.

  One code fix: snapshots were stored as their id-hash content and are now stored as the type-tagged record. 8 reference tests and 11 snapshot tests passed.
- **Process note:** a failed file write (an invalid newline argument) truncated the untracked `test_portfolio_snapshot.py`, and a retry appended to the empty file. I rebuilt it in full from this session's own text, with all corrections applied, before running anything; nothing in git was affected.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2613 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 243.77s (0:04:03) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-06: versioned risk limits, policy rules and halts)
- **`risk/limits.py` and `policy/rules.py`:**
  - **`RiskLimits` (D1–D9):** fractions are Decimals in (0, 1]; `long_only` must be true; counts are positive integers; `min_price` and `min_quantity` are positive Decimals, and `min_quantity` must be whole shares.
  - **`PolicyRules` (D7, D8, D12, D13):** `restricted` and `view_timeframes` are sorted, de-duplicated tuples (B2). The session, order type and time-in-force are fixed to the v1 values, and `H1` is refused (D12).
  - **`Halt`:** carries a `baseline_equity`.
  - **`load_limits_file`:** strict; floats (via `parse_float`) and unknown keys are refused.
  - **`LimitStore`:** PostgreSQL only, sharing one port with the audit store and account registry.
    - **Publishing:** `publish_risk` and `publish_policy` take the account-control lock, require an Admin at the real command time, number versions consecutively (`risk-<n>`, `policy-<n>`), and write one audit event each.
    - **Times:** RESEARCH needs `effective_at` and can't move back; PAPER can't backdate.
    - **Reads:** `risk_at` and `policy_at` raise `NoLimits` when nothing is effective.
    - **Restricted list:** `restrict` and `unrestrict` each publish a new policy version.
    - **Halts:** `set_halt` (Core Engine) latches a halt; `clear_halt` (Admin) clears it.
- **Contract deviations, both kept within the M3-06 rules:**
  - `clear_halt(..., equity_now=None, effective_at=None)`. `equity_now` is optional because snapshots arrive in M3-07: without it, the baseline restarts from the next snapshot, under M3-07 rule 5's `baseline_at`. `effective_at` was added for RESEARCH clears.
  - The proposed file's header records the owner's 2026-10-16 approval of D1–D9 and D13. It's still applied only by an explicit `limits publish`.
- **`schema_pg/0007_limits.sql`:** `risk_limit_versions`, `policy_rule_versions` and `halts`, all append-only. The audit registry lists `policy.rules` and `risk.limits`, and package data includes `risk/proposed_limits.json`.
- **Admin CLI (groups added through `GROUPS`; no change to `cli.py`):**
  - `limits publish ACCOUNT [--file]` (default: the packaged proposal), `limits show [--at]` and `limits clear-halt`;
  - `restricted add|remove`;
  - domain lookup errors such as `NoLimits` are printed plainly.
- **Tests first:** `tests/engine/test_limits.py` was written first and failed at collection. Two mistakes in my own tests:
  - `DELETE` on an empty table fires no row trigger, so it can't prove the guard; replaced with `TRUNCATE`;
  - events at the same command time are ordered by id, so the assertion now filters halt events.

  21 passed. They cover:
  - fail-closed lookups, and the packaged values equal to D1–D9 and D13;
  - effective-at-T versions; UPDATE, DELETE and TRUNCATE refused;
  - float and unknown-key file refusals, and nine validation refusals that publish nothing and write no event;
  - order-independent tuples; `H1` refused;
  - restricted add and remove as versions, with events, refused for a Trader;
  - a latched halt that a Trader can't clear, and an Admin clear that sets the baseline;
  - research replay-time versions and no paper backdate;
  - four concurrent publishes giving `risk-1` to `risk-4`;
  - fresh-process decoding of RiskLimits, PolicyRules (empty and non-empty) and Halt events;
  - CLI publish, show, restrict and refusals.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2594 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 298.24s (0:04:58) (only failure: the baseline cache-location test)
- **Clean install** (package data changed): a fresh `py -3.11` venv with `pip install ".[engine]"`. From outside the repository, `proposed_limits.json` loads (9 risk and 6 policy keys) and `schema_pg` 0005–0007 ship.

### 2026-10-16: Claude Code (M3-05 follow-up: the Admin CLI registers its own command groups)
- **Why:** M3-06, M3-13 and M3-14 add Admin CLI groups, but only M3-05's allowed files include `cli.py`. Editing the registration lines in a later task would leave that task's scope.
- **Change, within M3-05's allowed files:** `admin_cli.py` keeps a `GROUPS` map and a `register(app)` function; `cli.py` calls it once. Later tasks add their groups to `GROUPS` in `admin_cli.py` only. Commands and behaviour are unchanged.
- **Checks (Git Bash):** the CLI and admin tests passed (45). The full suite, with the M3-06 work stashed so only this change was in the tree, is below. Ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2573 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 276.83s (0:04:36) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-05: accounts, operators and autonomy levels)
- **`investment_engine/policy/accounts.py`:** `AccountKind` (RESEARCH, PAPER), `Role`, `Account`, `AutonomySetting` and `Operator`, plus `AccountRegistry`, which is PostgreSQL only and must share the audit store's port.
  - **Levels:** every account starts at Level 0. Levels 3 and 4 raise "disabled in v1"; anything else outside 0–2 is refused.
  - **Authorization:** every change needs an active ADMIN at the real command time (the injected clock). The role comes from the registry, never the actor's claim.
  - **Times:** RESEARCH changes require `effective_at` (replay time) and keep `recorded_at` beside it; a RESEARCH timeline can't move back. PAPER changes refuse `effective_at`, so they can't be backdated.
  - **Identity:** `setting_id` and `Account.identity` hash deterministic content only, leaving out `recorded_at`, `set_by` and the OS user (re-review S2, acceptance note 2).
  - **Locks and records:** every change takes the `account-control` lock, assigns the next `sequence` under it and writes an append-only row and one audit event in one managed transaction. Creating an account records the account and its default Level 0 setting in a single `account.create` event. `bootstrap_admin` takes the global `operators-bootstrap` lock and checks again inside it.
- **`schema_pg/0006_accounts.sql`:** `accounts`, `autonomy_settings` and `operators` tables, all append-only (UPDATE, DELETE and TRUNCATE refused). The audit registry now lists `policy.accounts`.
- **`investment_engine/admin_cli.py` (new; registered in `cli.py`):** `operators bootstrap-admin|add|deactivate|list` and `accounts create|set-autonomy|show|list`, with `--operator`, `--reason` and `--effective-at`. Output is plain ASCII and shows both times, labelling the effective time "(simulated)" for research accounts. Authorization refusals print "Not authorized: ... Nothing was changed."
- **Tests first:** both test files were written first and failed at collection. Two test-driven fixes:
  - account creation first wrote two events, so it now writes one;
  - my concurrency test gave the audit store a separate port; the registry now refuses that.

  Results: 10 passed in `test_accounts.py` and 4 in `test_admin_cli_accounts.py`. Coverage:
  - level rules; history with sequence order for equal times, where 1 -> 2 -> 1 gives three ids;
  - refusals for Trader, Viewer, inactive and unknown operators, a claimed role, and processes, with nothing written;
  - one audit event per change, which rolls back with it;
  - bootstrap once, and two concurrent bootstraps giving exactly one admin;
  - replay times vs no backdating;
  - authorization at command time: today's admin sets a 2019 setting, and an operator deactivated today is refused at any replay time;
  - identity without provenance across two fresh databases;
  - fresh-process decoding of account events;
  - CLI happy paths and refusals.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2573 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 327.18s (0:05:27) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-04: audit store)
- **`investment_engine/audit/events.py`:**
  - `Actor`: an OPERATOR with a role, or a PROCESS without one; `os_user` is attribution only.
  - `AuditEvent`: actor, dotted action, target, before and after, real command time `at`, replay `business_at` (Codex re-review R2), reason of at most 1,000 characters, correlation id and idempotency key. Its `event_id` is `aud-` + SHA-256 of the canonical content. `before` and `after` must be codec-registered values and are normalized, so round trips compare equal.
  - `AuditStore`: PostgreSQL only. `append` raises unless the port's managed transaction is open, so a change and its event commit or roll back together. An identical append is a no-op; different content under an id raises `AuditConflict`. `for_target` and the half-open `between` read events in `(at, event_id)` order and re-verify each id.
- **`audit/registry.py`:** the fixed module list `AuditStore` imports for fresh-process decoding; empty here, extended by later tasks.
- **`schema_pg/0005_audit.sql`:** a PostgreSQL-only table. UPDATE, DELETE and TRUNCATE are refused, and so is inserting an existing id, through `ie_refuse_change` and a BEFORE INSERT guard.
- **Tests first:** `tests/engine/test_audit.py` was written first and failed at collection. Three of my own test statements then named a column that doesn't exist (`reason`, which lives in the content); I corrected them to update `action`, and rewrote the conflict test to plant a different event under an id. 15 passed. They cover:
  - a rolled-back change leaving no event;
  - append outside a transaction refused;
  - an identical no-op and a planted conflict;
  - the UPDATE, DELETE, TRUNCATE and both ON CONFLICT routes refused;
  - field round trips and ordered queries;
  - refused bad values, actors and roles;
  - id hashing;
  - a DSN-shaped secret in the environment never reaching an event;
  - SQLite refused;
  - a fresh subprocess decoding a test-registered type through the registry;
  - the `57d4316` and lineage ids unchanged.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2559 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 244.49s (0:04:04) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-03 follow-up: copy and status tests follow the latest PostgreSQL script)
- **Change (`tests/engine/test_copy_sqlite.py` only):** the copy report's target schema and `db status` output are compared with `LATEST_PG`, the highest packaged script, instead of a written-in 4. This is for the same reason as the M3-01 follow-up above, and the checks are shared with it.
  - full suite: 1 failed, 2544 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 235.35s (0:03:55) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-01 follow-up: schema tests follow the latest PostgreSQL script)
- **Why:** M3-04 onwards add PostgreSQL-only scripts (0005 and up), which M3-01 rule 1 allows. Several M3-01 tests had version 4 written into them. Without this change they would fail, and fixing them inside a later task would leave that task's allowed files.
- **Change (`tests/engine/test_postgres_schema.py` only):**
  - `LATEST` is the highest packaged script number. Migration, re-apply, newer-schema refusal and failing-script rollback now assert against it.
  - The comparison with SQLite version 4 is limited to the five mirrored tables, and asserts that set exactly.
  - No assertion is weakened: every mirrored table, column, key and check is still compared.
  - Verified with a temporary `0005_probe_only.sql` present and then removed: 37 tests (this file and the M3-03 copy tests) passed both ways.
- **Checks (Git Bash), shared with the M3-03 follow-up:** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2544 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 235.35s (0:03:55) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-03: copy SQLite data into PostgreSQL and switch the CLI)
- **`storage/copy_sqlite.py`:** `copy_sqlite_to_postgres(path, target, *, calendars) -> CopyReport`.
  - The source opens read-only (`mode=ro`); source schemas 1–4 are accepted, and tables a schema doesn't have count zero.
  - The target is migrated first, then everything is copied in one managed transaction. Instruments and mappings go through the stores, so mapping overlap rules and locks apply. Record content is copied byte for byte with the same ids.
  - Every copied lineage and evaluation record is read back through its store and must hash to its id. Evaluation records are also checked against the supplied calendars (R1, R2). Identical rows count as present; a different row, a corrupted record or an unknown calendar version aborts with nothing written (`CopyConflict` or `ValueError`).
- **`config.py`:** `ENV_PG_DSN = "INVESTMENT_ENGINE_PG_DSN"`, and `operational_db_dsn()`, which raises `OperationalDatabaseNotConfigured` naming the variable and the setup guide, never a value. The docstrings of the module and of `operational_db_path` now say SQLite is only a copy source.
- **CLI:**
  - `init`, `report` and `import-yfinance` open PostgreSQL. Report and import connections are read-only (`default_transaction_read_only`), and without a schema they say to run `init`.
  - New `db status` (schema version and row counts) and `db copy-from-sqlite PATH`, which passes the calendar versions the code ships. Those are labelled as M2 labelled them: `us-equities-` plus 16 hex digits of SHA-256 over the packaged calendar files.
  - psycopg errors print a fixed message naming `INVESTMENT_ENGINE_PG_DSN` without its value. A missing driver gives the `.[engine]` instruction, and psycopg is imported only when a PostgreSQL command runs.
- **`docs/dev/postgresql.md`:** the CLI's own database (`investment_engine`) and DSN, and the copy command.
- **Tests first:** `tests/engine/test_copy_sqlite.py` was written first and failed at collection; after the implementation, 11 passed. They cover:
  - an exact copy of a full M2 database (byte-identical content, both evaluation formats, a re-run with everything present, an unchanged source hash);
  - schemas 1, 2 and 3; schema 5 refused;
  - an aborting conflict; an aborting corrupted record; an unsupported calendar named, with nothing written;
  - an unset DSN; `init`, `status` and copy on PostgreSQL, with output free of the password and of `dbname=`;
  - a base-install probe with psycopg blocked, where `--help` works and `db status` names `.[engine]`.
- **`tests/engine/test_cli.py`:** back-end set-up only. Tests are marked `postgres`, and the `app` fixture sets the DSN to a fresh test database. Direct checks use the port, and the stored `active_from` is compared as `date(1999, 1, 22)`. Two assertions were added so nothing is weakened now that the Operational Database isn't a file under the data directory:
  - the read-only report also leaves the instrument and mapping rows unchanged;
  - "report without init" also creates no table.

  `tests/test_cli_commands.py` needed no change.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2544 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 179.55s (0:02:59) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-02: existing stores on PostgreSQL through the database port)
- **`investment_engine/storage/database.py` (new): the port.**
  - **Adapters:** `SqliteDatabase` and `PostgresDatabase`. Both require autocommit connections, so a read never opens a hidden transaction.
  - **Statements:** constant SQL with named `:name` parameters. `translate_named` turns them into psycopg `%(name)s`, skipping `::` casts and quoted text and doubling literal `%`. A missing parameter raises `KeyError` on both backends.
  - **Transactions:** the port owns them. The outermost `transaction()` begins and commits or rolls back; nested scopes join it without a savepoint. A failure in a nested scope rolls back the outermost transaction even when the caller caught it (`TransactionAborted`). `in_transaction` reports the managed scope only.
  - **Errors:** driver errors become `AppendOnlyViolation` (M3-01's class) or `IntegrityViolation` (kind `unique`, `check`, `foreign_key` or `not_null`).
  - **Locks:** `lock(*names)` takes advisory locks in ascending key order on PostgreSQL; it's a no-op inside SQLite's `BEGIN IMMEDIATE`.
  - **Values:** SQLite gets ISO text exactly as M1–M2 stored it; `as_date` and `as_datetime` read both forms back.
- **Stores switched to the port, names kept:** `SqliteInstrumentRepository`, `SqliteSymbolResolver`, `LineageStore`, `EvaluationRunStore`.
  - **No compatibility shim:** a raw `sqlite3.Connection` raises `TypeError`, pointing to `SqliteDatabase`.
  - **Mapping inserts (B4):** they lock both conflict dimensions in key order, then check and insert.
  - **Lineage and evaluation appends:** the check and insert now run in one managed transaction.
- **Callers (rule 7; inventory re-run, matching Codex's 12 files):** `cli.py` wraps its SQLite connection (transitional until M3-03; the read-only connection is now opened in autocommit mode). Seven caller test files changed set-up only: `test_cli`, `test_data_health`, `test_feature_snapshot`, `test_view_pipeline`, `test_yfinance_actions`, `test_yfinance_bars` and `test_walk_forward`, plus `test_html_report`. The store tests now run on both backends through the new `backend`/`database` fixtures. SQLite-only tests (schema scripts, migrations, PRAGMA, SQLite's own replace routes) stay on raw SQLite. A scan finds no raw connection passed to a store constructor. The external M2 report script, outside the repository, will be wrapped the same way the next time it runs.
- **Tests first:**
  - `test_database_port.py` and `test_mapping_races.py` were written before the port and failed at collection.
  - **B4 regression evidence:** with the advisory locks disabled through a probe plugin, both race tests failed, with `assert 2 == 1`: both conflicting mappings committed. With the locks, both pass (50 repetitions each), and non-overlapping reuse and another provider still commit.
  - A new test reads the genuine `57d4316` record back under its original id on both backends.
- **Counts:** 47 store and port tests run on each backend (`[sqlite]` and `[postgresql]`); 123 `postgres` tests in the engine suite.
- **Checks (Git Bash):** see the result line below; ruff passed; whitespace clean. No `postgres` test skipped; the 3 extra skips are the SQLite variants of the PostgreSQL-only race tests.
  - full suite: 1 failed, 2533 passed, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed in 161.00s (0:02:40) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-01 follow-up: postgres.py importable without the driver)
- **Why:** M3-02's database port must raise M3-01's `AppendOnlyViolation` on the SQLite path too. Importing `storage.postgres` at module level imported `psycopg`, which a base install lacks (M3-03 rule 8), and `storage.sqlite`, which would form an import cycle with the port.
- **Change, within M3-01's allowed file:** `postgres.py` now imports `psycopg` only inside `open_operational_pg` (type hints via `TYPE_CHECKING`), and `SchemaVersionError` only inside `apply_pg_schema`. Behaviour is unchanged, and the class stays where the M3-01 contract puts it. A probe that blocks every `psycopg` import still imports the module and uses `AppendOnlyViolation` and `advisory_key`.
- **Scope note:** I first made this edit while working on M3-02, whose allowed files don't include `postgres.py`. I reverted it there and made it here instead, as M3-01's own follow-up, so M3-02 stays within its files.
- **Checks:** the same full-suite run as the M3-00 follow-up above; `test_postgres_schema.py` (26) passed within it.

### 2026-10-16: Claude Code (M3-00 follow-up: test-database teardown when autovacuum holds it)
- **Found in a full-suite run during M3-01's follow-up (not a new product failure):** a teardown error in `test_postgres_schema.py::test_instrument_checks_reject_the_same_rows_as_sqlite[row1]`. `DROP DATABASE ... WITH (FORCE)` raised `InsufficientPrivilege: permission denied to terminate process`. Something else, most likely an autovacuum worker, which runs as the superuser, had the fresh database open, and the non-superuser `ie_dev` role may not terminate it.
- **Fix (`tests/engine/conftest.py`):** `temporary_database` drops through `_drop`. A plain `DROP DATABASE` is retried, up to 20 times every 0.25 s, while it reports `ObjectInUse`; `WITH (FORCE)` is used only as the last resort. The database is still always dropped or the error is raised; nothing is left silently.
- **Checks (Git Bash), shared with the M3-01 follow-up commit, which was in the same working tree:** see the result line below; ruff passed; whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2466 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 122.47s (0:02:02) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M3-01: PostgreSQL schema and migrations)
- **`investment_engine/storage/postgres.py`:**
  - `open_operational_pg` opens connections in autocommit mode, with the session time zone UTC;
  - `apply_pg_schema` uses the same forward-only numbering as SQLite, one transaction per script together with its version row, and `SchemaVersionError` for a newer database;
  - `AppendOnlyViolation` is defined here for M3-02;
  - `advisory_key` gives a SHA-256-derived signed 64-bit key, and `advisory_keys` returns distinct keys in ascending order.
- **`storage/schema_pg/0001`–`0004`** mirror SQLite version 4 with native `DATE`, `TIMESTAMPTZ` and `BYTEA`. The append-only refusals:
  - one PL/pgSQL function (`ie_refuse_change`) behind row triggers refusing UPDATE and DELETE, and statement triggers refusing TRUNCATE;
  - BEFORE INSERT guards (0004) that refuse an existing id before conflict arbitration, which covers both `ON CONFLICT DO UPDATE` and `DO NOTHING`.

  Functions have a fixed `search_path`. Package data now includes `schema_pg/*.sql`.
- **Tests first:** `tests/engine/test_postgres_schema.py` was written first and failed at collection, because the module didn't exist yet. After the implementation: 26 passed, on the real local PostgreSQL. They cover:
  - migration to 4, idempotent re-apply, newer-schema refusal, and rollback of a failing script with no partial table or version row;
  - autocommit and UTC;
  - a column, nullability and key comparison with SQLite version 4, and the native types;
  - every replacement route refused with the original unchanged, for both tables (UPDATE, DELETE, TRUNCATE, both `ON CONFLICT` forms, a plain duplicate);
  - instrument checks rejecting the same seven bad rows as SQLite;
  - the advisory-key properties.
- **Checks (Git Bash):** the full suite below ran before a one-line lint fix in the new test file (a dict comprehension); after the fix, ruff passed and the file's 26 tests passed again. Whitespace clean; no `postgres` test skipped.
  - full suite: 1 failed, 2466 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 127.36s (0:02:07) (only failure: the baseline cache-location test)
- **Clean install** (package data changed): a fresh `py -3.11` venv with `pip install ".[engine]"`; from outside the repository, the four `schema_pg` scripts ship and load from site-packages.

### 2026-10-16: Claude Code (M3-00: PostgreSQL development and test setup)
- **Driver:** `psycopg[binary]>=3.3.6` added to the `dev` and `engine` extras (wheel evidence in the step-0 entry). Markers: `postgres` is registered in `pyproject.toml`.
- **Guard (`tests/conftest.py`, rule 4):** `_no_network` now also wraps `psycopg.connect`, `Connection.connect` and `AsyncConnection.connect`.
  - Unmarked tests can't connect.
  - In `postgres` tests every `PG*` variable is removed, at set-up and again at each connect, so values a test sets itself are neutralized too.
  - The effective parameters (`conninfo_to_dict` of the DSN plus keyword overrides) must use only the allowed keywords and one loopback host. `hostaddr` is pinned to the numeric loopback address.
  - Refusals name keywords, never values. The real functions are looked up through `PG_REAL`, so the probes use a recorder.
- **Fixture (`tests/engine/conftest.py`):**
  - `pg_database` gives each test an `ie_test_<hex>` database from `template0`, created through `INVESTMENT_ENGINE_TEST_PG_DSN`;
  - teardown is `temporary_database`, which drops the database `WITH (FORCE)` in a `finally`;
  - without the variable, tests skip with the documented reason.
- **Also:** a layering rule (psycopg only under `investment_engine/storage/`), a CI `postgres:17` service with a throwaway password, and `docs/dev/postgresql.md`.
- **Deviations, recorded honestly:**
  - **Tests-first not observed:** the guard and fixture were written before `test_postgres_harness.py`, so no red run exists.
  - **No nested pytest run:** "dropped even after a failing test" is tested through `temporary_database`, the fixture's own teardown, raising inside the block with an open connection, rather than a nested pytest run.
  - **Async probes run without an event loop:** they drive the coroutine directly, because Windows' event loop opens a socket pair that the existing socket guard refuses.
- **Task tests:** `tests/engine/test_postgres_harness.py`, 49 passed. Coverage:
  - 27 refusal probes (9 forms × 3 entry points);
  - 15 neutralization probes (5 variables × 3 entry points);
  - supported local forms, and the unmarked-test refusal for each entry point;
  - the skip reason;
  - two real-server tests: a fresh, empty, loopback database, and the drop after a failure.
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean. No `postgres` test skipped.
  - full suite: 1 failed, 2440 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 110.87s (0:01:50) (only failure: the baseline cache-location test)
- **Clean install** (dependencies changed), with a fresh `py -3.11` venv and `pip install ".[engine]"`:
  - the CI import from the repository root passed;
  - from outside the repository, `psycopg` 3.3.6 (binary) and `investment_engine` loaded from site-packages.

### 2026-10-16: Claude Code (M3 step 0: specs accepted, PostgreSQL checked, milestone started)
- **Approval (owner, 2026-10-16):** D1–D18 as recommended and the complete M3 milestone (15 tasks, the 52 h estimate and the 4 h task exception), built on `m3/milestone` from `docs/m3-specs`, with local task commits, all checks and one combined Codex review. Not authorized: merge, push, API keys, market-data downloads, M4.
- **Specs:** Codex accepted the pack at `6085fd9` (`docs/reviews/codex-m3-spec-accepted-6085fd9.md`, imported byte-for-byte, SHA-256 `e5d94318…`). Status rows now say accepted. Codex's three notes are folded in:
  - `command_at` in the M3-13 signatures;
  - identity vs provenance equality in M3-05;
  - the unknown-account diagnostic isn't persisted (M3-12).
- **PostgreSQL (D16) checked** without printing the DSN:
  - the PostgreSQL 17.11 service `postgresql-x64-17` is running;
  - `INVESTMENT_ENGINE_TEST_PG_DSN` is set, and logging in as `ie_dev` works (CREATEDB yes, superuser no);
  - `pg_hba.conf` allows only `127.0.0.1/32` and `::1/128`.
- **Open owner item:** `listen_addresses` is still `'*'`, so the server listens on all interfaces; remote logins are refused by `pg_hba.conf`. The owner should set it to `'localhost'` (the setup guide's Step 3). Not blocking: the tests pin loopback.
- **psycopg wheels verified (M3-00 rule 1):** `psycopg-binary` 3.3.6 has wheels for CPython 3.11, 3.12, 3.13 and 3.14 on `win_amd64` and `manylinux_2_17_x86_64` (downloaded with `pip download --only-binary=:all:` into the scratch folder). `psycopg[binary]==3.3.6` is installed in the project venv (binary implementation, libpq 18.0.4).
- **Checks:** documents only; `git diff --check` clean.

### 2026-10-16: Claude Code (M3 specification pack v0.3: Codex's re-review of `e7ec7e1` applied)
- **Codex accepted the B1–B6 fixes in v0.2; they're kept unchanged.** v0.3 fixes three integration blockers:
  - **R1:** M3-02 now lists every existing caller of the store constructors (the CLI and seven test files, re-inventoried), with set-up-only changes. The CLI stays on SQLite, wrapped, until M3-03, so M3-02 commits with the whole suite passing. The external M2 report script is updated outside the repository.
  - **R2:** privileged commands authorize the named operator at the real command time (LiveClock) and act at the business time (replay for RESEARCH). Audit events carry `at` and `business_at`; approvals store `approved_at` and `approval_recorded_at`. The operator registry is never backdated.
  - **R3:** expiry is per account: `expire_due(account_id, at)`, an account-scoped store query, account validation before any mutation, `intents expire --account` and a separate live-time `--paper` sweep.
- **Clarifications:**
  - S1: ambient `PG*` settings are neutralized and the connection is allowed with a pinned loopback; explicit unsupported parameters are refused.
  - S2: hashed identities exclude command provenance, so replay ids are reproducible from the same setup inputs.
  - S3: risk gets `admitted_buys_excluding_self` and `already_admitted`.
  - S4: D18 says the rest of a partial sell is not sold automatically.
- **Codex's re-review record** is imported byte-for-byte as `docs/reviews/codex-m3-spec-rereview-e7ec7e1.md`.
- **Checks:** documents only; `git diff --check` clean; estimates (52 h) and backward dependencies rechecked by script. No runtime tests (no code changed). CI not yet run.
- **Next:** Codex re-reviews `e7ec7e1..docs/m3-specs`; the owner answers D1–D18 and decides on M3 approval and the PostgreSQL install. Not authorized: M3 code, merge, push, keys, downloads.

### 2026-10-16: Claude Code (M3 specification pack v0.2: Codex's review of `1ce5250` applied)
- **Blocking findings:**
  - **B1:** an explicit RawReference for the decision bar, so the first BUY of a cash-only account has a raw Decimal price.
  - **B2:** sorted tuples instead of frozensets, so the codec is unchanged; an audit decoding registry.
  - **B3:** NotRun decisions, PREREQUISITE_MISSING kept apart from POLICY_REJECTED, an outcome matrix, and lineage per version.
  - **B4:** mapping advisory locks on both conflict dimensions.
  - **B5:** a per-account, per-session buy-admission lock, counting distinct intents.
  - **B6:** the PostgreSQL test guard checks effective libpq parameters, refuses ambient `PG*`, `hostaddr`, services and multi-host forms, and pins loopback.
- **Suggestions S1–S7 folded in:**
  - S1: managed transactions over autocommit connections;
  - S2: replay-time research setup without backdating paper, and delivery-aware reads;
  - S3: explicit calendars in the copy, schemas 1–4, lazy driver import;
  - S4: autonomy setting ids and sequences, and control and bootstrap locks;
  - S5: legal G2 paths for late proposals and legal race starts;
  - S6: buy-only position and cash checks, partial selling (new D18), and a halt clear that resets the baseline (D3);
  - S7: Codex's M2 acceptance and M3 review records imported byte-for-byte into `docs/reviews/`.
- **Decisions:** D1–D18 are consolidated in the README; all are proposed and none accepted.
- **Estimate:** revised to 52 h, with seven 4 h tasks as an explicit planning exception.
- The correction table is in `docs/reviews/claude-m3-spec-package.md`.
- **Checks:** documents only; `git diff --check` clean; estimates and backward dependencies checked by script. No runtime tests (no code changed). CI not yet run.
- **Next:** Codex re-reviews `1ce5250..docs/m3-specs`; the owner answers D1–D18 and decides on M3 approval. Not authorized: M3 code, merge, push, keys, downloads, PostgreSQL installation.

### 2026-10-16: Claude Code (M2 complete; M3 specification pack drafted for review)
- **M2 is done.** Codex's final review passed at `b7c5d2a` (`docs/reviews/codex-m2-accepted-b7c5d2a.md`, in the root checkout). With the owner's approval, local `main` was fast-forwarded from `53c51bd` to `b7c5d2a` in the `TradingAgents-main` worktree. Nothing was pushed; no branch was deleted. The M2 spec status rows now say Done.
- **M3 pack (draft v0.1, documents only):** `docs/tasks/M3-README.md` and M3-00 – M3-14 on `docs/m3-specs`, about 49 h.
  - A: PostgreSQL move (setup, schema, existing stores, copying SQLite data, CLI switch).
  - B: audit, accounts/operators/autonomy, versioned limits and halts.
  - C: PortfolioSnapshot, OrderIntent and sizer, intent store with G2 and compare-and-set.
  - D: policy and risk checks.
  - E: pipeline and intent lineage, Level 1 approval at the CLI, the intents report.
- **Owner decisions D1–D17** are listed in the pack's README with recommendations (OPEN-07 as D1–D9, OPEN-08 as D10–D12, plus order price, starting cash, promotion rule, local PostgreSQL and CLI approvers). Limits ship only as a proposed file; accounts without published limits reject everything.
- **Architecture unchanged.** No ADR is proposed. Two placements are flagged for Codex: account kinds and operators in the Policy module, and the dual-backend tests for the M1–M2 stores.
- **Checks:** documents only; `git diff --check` clean. No runtime test run (no code changed). CI not yet run.
- **Next:** Codex reviews the pack; the owner answers D1–D17 and decides on M3 approval. Not authorized: M3 code, merge, push, keys, downloads.

### 2026-10-16: Claude Code (M2 re-review fixes R1 and R2 complete; handed back for a second re-review)
- R1 and R2 are fixed in `cd20083` with regressions; the red evidence is described honestly in its entry. The table and results are in `docs/reviews/claude-m2-rereview2-package.md`.
- **Batch checks:**
  - Git Bash full suite: 2390 passed, 1 failed (baseline);
  - PowerShell: 2389 passed, 2 failed (both baseline);
  - ruff passed;
  - clean install with schemas 0001–0004: passed.
  - CI not yet run.
- **Report:** regenerated from `cd20083`. Every metric is unchanged; only `code_version`, the record ids and the HTML changed. 376,352 bytes, and the metadata matches the saved file.
- **Next:** Codex re-reviews `ee12160..m2/milestone`; then the owner decides on the M2 merge. Not authorized: push, M3, keys, downloads.

### 2026-10-16: Claude Code (M2-11b follow-up with M2-09, M2-07 and M2-12, Codex re-review R1 and R2)
- **R1 (P1): older saved evaluations stopped opening.** S3's new `DirectionEvaluation` fields changed the canonical encoding of records stored before it, so `EvaluationRunStore.get` rejected a genuine `57d4316` record after the schema-4 upgrade.
  - **Fix:** the three audit fields are now `None` when not recorded, and the codec omits fields a class lists in `LINEAGE_LATER_FIELDS` while they are `None`. An old record decodes with them `None` and re-encodes to its original payload and id, with the hash check unchanged. `evaluate_direction` always records them (an empty tuple is a recorded empty sample), and they must be set together. The report says "last-period sample not recorded in this record (earlier format)". Stored rows and ids are not rewritten, and lineage ids are unaffected because no lineage class uses the list.
  - **Upgrade fixture:** `tests/engine/fixtures/evaluation/record-57d4316.json` holds the zlib bytes that `57d4316`'s own `EvaluationRunStore.append` wrote for its `record()` fixture, generated by running that commit's code from a `git archive` export. Its id `eval-8bee2622…` matches the one Codex reproduced.
- **R2 (P2): a short run could be labelled as a complete six-month fold.**
  - **Fix:** `check_fold_periods(record, calendars)` requires each run's first session to open at its fold's `test_start` and the session after its last to open at `test_end`, on the calendar named by `record.calendar_version`. `EvaluationRunStore(conn, *, calendars)` applies it on append and on read, and `render_research_report(..., calendars=...)` applies it before rendering. Each fold now shows its run's actual sessions. An unfinished fold still requests its whole window and shows INCOMPLETE (B3). Partial-window evaluations are not supported.
  - **Fixture:** the report test's `computed_record` now simulates the whole fold (2021-01-04 to 2021-07-01) instead of ten sessions.
- **Regressions:**
  - **R1:** a genuine old record reads back after the upgrade with its id and payload intact, and re-appending it leaves the bytes unchanged; corruption is detected in both formats; current records round-trip with their audit sample; the audit fields must be set together; the report marks the sample as not recorded.
  - **R2:** truncated start, truncated end, start before the fold and end after it are refused by the store and by `check_fold_periods`, and nothing is stored; a complete fold and an unfinished fold are accepted; an undeclared calendar is refused; the genuine old record passes the period check; the report refuses a short run and shows the actual sessions.
- **Red evidence (honest note):** the new pytest regressions first failed at import, because `check_fold_periods` and `calendars` didn't exist yet. The behavioural failures were observed with the same scenarios run against an export of `ee12160`:
  - the old record's read failed with "stored content for eval-8bee2622… hashes to eval-be98ac10…";
  - all four mismatched run periods were accepted.

  After the fix: 99 passed in the affected files.
- **Interface change:** the store's constructor and the renderer each take a `calendars` keyword argument (contracts updated in M2-11b and M2-12; format rule in M2-09 and M2-07). The external `build_report.py` passes `{calendar_version: CAL}`.
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2390 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 116.96s (0:01:56) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M2 fixes for Codex's review complete; handed back for re-review)
- B1–B6, S2 and S3 are fixed in follow-up commits with regressions run first (each observed failing). S4 and the accepted final interfaces are documented; S1 is fixed in the external build script. The table and results are in `docs/reviews/claude-m2-rereview-package.md`.
- **Batch checks:**
  - Git Bash full suite: 2377 passed, 1 failed (baseline);
  - PowerShell: 2376 passed, 2 failed (both baseline);
  - ruff passed;
  - clean install with schemas 0001–0004: passed.
  - CI not yet run.
- **Report:** regenerated from `9f8ab57`. Byte metadata now matches the saved file. Results are unchanged apart from the Sharpe values (B4).
- **Next:** Codex re-reviews `57d4316..m2/milestone`; then the owner decides on the M2 merge. Not authorized: push, M3, keys, downloads.

### 2026-10-16: Claude Code (M2 re-review: S4 documents and accepted final interfaces)
- **Final interfaces:** Codex accepted the contract extensions in principle. The specs now record them in "Final interfaces" sections: M2-02 (RSI14 seed), M2-03 (`warmup`, `decision_close`), M2-07 (`run_views` signature, compressed lineage, 0004 guards), M2-09 (`PredictionView`, `calendar`, `trailing`, audit fields), M2-10 (`Benchmark`, extra `EvaluationRun` fields, B3/B4 rules), M2-11a (`walk_forward`, `FoldResult`, `WalkForwardResult`, `RevisionCache`, S2/B3 rules), M2-11b (`EvaluationRecord` and its store, B5) and M2-12 (`adjusted_closes`, B6 checks). M2-11a and M2-11b no longer claim the old contract applies "exactly".
- **S4:**
  - the M2 README's 2026-10-13 introduction is labelled as superseded history;
  - shared rules §4 in AGENTS.md and CLAUDE.md (blocks still identical) and `docs/tasks/README.md` record the owner-approved exception that a milestone may be built on the previous milestone's branch while that one is in review, merging only after it;
  - the M2-06 lint follow-up entry, inserted three times by failed commit attempts before my helper was hardened, now appears once. The correction itself is kept.
- **Process deviations stay recorded as they were:** unobserved red runs for M2-00 to M2-08, M2-07 code before tests, the `2a8c3ac` lint slip and the `7028523` message. None is presented as tests-first evidence.
- **Checks:** documents only. `git diff --check` clean; shared-rules blocks identical. No runtime change, so no test run for this commit.

### 2026-10-16: Claude Code (M2-09 and M2-11a follow-up, S2 and S3: fold guard and auditable last-period sample)
- **S2 (Codex suggestion):** `walk_forward` now validates the supplied fold collection. Test windows must be in order and may not repeat or overlap; otherwise it raises. `make_folds` already produced valid folds, so the report is unaffected. Regressions (run first, 3 failed): duplicate, overlapping and out-of-order folds.
- **S3 (Codex suggestion):** `DirectionEvaluation` now keeps `trailing_refs` (the trailing ReturnObservations actually used), `last_period_sample` (the paired prediction sessions) and `last_period_excluded` (scored sessions without a usable trailing return). They default to empty, so existing constructions stay valid, and they are stored with the record. Regression (run first, failed): the sample, exclusions and references for the hand-built table.
- After the changes: 52 passed (walk-forward, metrics and run-store files).
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2377 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 204.26s (0:03:24) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M2-12 follow-up, B6: the report checks its source and time labels)
- **Codex finding B6 (P2):** the renderer didn't compare each view's lineage provider with the declared report source, and it accepted data later than the report's generation time.
- **Fix (`reporting/html.py`):** rendering raises when a view's lineage snapshot comes from another provider than `source`, or when any view time, evaluation-record cutoff or price-series cutoff is later than `generated_at`. Historical views and the chart's separately labelled common basis are unaffected; extra health sources aren't prohibited.
- **Regressions, run first and observed failing (2 failed):**
  - a yfinance view rendered with `source="testvendor"` and no runs or prices;
  - a view, a record cutoff and a price series later than the report time.

  A mixed-historical-dates case also passes. 16 passed.
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2373 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 178.74s (0:02:58) (only failure: the baseline cache-location test)

### 2026-10-16: Claude Code (M2-11b follow-up, B5: evaluation records must agree with their folds)
- **Codex finding B5 (P1):** `EvaluationRecord` didn't check its outer configuration against its nested fold runs, so a 5 bps calculation could be stored and rendered as 10 bps. The report's stress test built exactly that.
- **Fix (`evaluation/run_store.py`):** construction now refuses a record unless:
  - each fold run's configuration, source, instrument and evaluation cutoff equal the outer record's;
  - each fold's walk-forward version and label configuration equal the walk-forward configuration;
  - each fold's direction metrics use the label version, basis and horizon;
  - the stitched summary matches the folds and their net returns;
  - promotion is `PROMOTION NOT ASSESSED: thresholds pending approval`.

  Contradictions raise and are listed; valid records serialize and append idempotently as before.
- **Regressions, run first and observed failing (9 failed):** mismatched cost, source, instrument, cutoff, label configuration, fold version, direction basis, stitched value and promotion status.
- **Tests corrected:**
  - the report fixture's two records are now computed by actually running `simulate_research` at 5 and at 10 bps on a small synthetic store (`computed_record`), not relabelled;
  - the old id-hash case that relabelled the cost was removed, because such a record is now refused.

  34 passed (run-store and report files).
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2370 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 148.15s (0:02:28) (only failure: the baseline cache-location test)

### 2026-10-15: Claude Code (M2-10 follow-up, B4: daily Sharpe includes the initial-cash boundary)
- **Codex finding B4 (P2):** the daily Sharpe used only adjacent closes, so it left out the return from initial cash to the first close: entry costs and the first session's move. Net return and drawdown already started from initial cash.
- **Fix (`evaluation/simulation.py`):** returns now run from the initial cash through every valued close, for the strategy and both benchmarks. The zero risk-free rate, sample deviation and ×√252 are stated in the module docstring.
- **Regressions, run first and observed failing (3 failed):**
  - the hand-calculated case now includes the 0% first return;
  - a flat-price run where the only change is the 5 bps entry cost now has an available, negative Sharpe;
  - a first-session drop from 100 to 90 is included, for both the strategy and buy-and-hold.

  After the fix: 35 passed (simulation and walk-forward files). The zero-variance case, with no trade, stays unavailable.
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2360 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 130.24s (0:02:10) (only failure: the baseline cache-location test)

### 2026-10-15: Claude Code (M2-10 and M2-11a follow-up, B3: windows past the cutoff are incomplete)
- **Codex finding B3 (P2):** `simulate_research` dropped requested sessions closing after the evaluation cutoff before its completeness check. So a window cut short at the cutoff reported `complete=True` and a full-window net return.
- **Fix (`evaluation/simulation.py`):** sessions after the cutoff are now listed in an incomplete-run limitation ("N requested sessions end after the evaluation cutoff …: first..last"). Full-window return metrics become unavailable with an "incomplete run" reason; the sessions that were valued stay visible. A window ending exactly at the cutoff stays complete.
- **Fix (`evaluation/walk_forward.py`):** test views are limited to those generated by the evaluation cutoff, so an unfinished fold yields an incomplete run (its stitched value unavailable) instead of a later-dated view error.
- **Regressions, run first and observed failing (3 failed, 3 passed):**
  - failing: cutoff before the last close; an entirely future window; walk-forward with an unfinished fold;
  - already passing: the window ending exactly at the cutoff.

  After the fix: 33 passed (simulation and walk-forward files).
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2358 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 117.06s (0:01:57) (only failure: the baseline cache-location test)

### 2026-10-15: Claude Code (M2-07 follow-up, B2: replay knowledge respects delivery time on re-query)
- **Codex finding B2 (P1):** `ReplayKnowledgeReader` kept only each payload's `available_from`. After later events were accepted, re-querying an earlier T returned revisions not yet delivered at that T (rev 2 available at E+3 and delivered at E+8 was visible at E+5). Actions had the same defect.
- **Fix (`decision/pipeline.py`):**
  - each revision keeps its delivery time and feed sequence; `accept` requires non-decreasing delivery and strictly increasing sequences;
  - a query at T sees a revision only if `available_from <= T` **and** it was delivered by T;
  - the optional `through_sequence` excludes equal-time events later in the feed sequence;
  - stored timestamps are unchanged and no store is added.

  M2-07's rule 5 and contract record this.
- **Regressions, run first and observed failing (3 failed):**
  - candles: accept both events, then query at E+5, E+7.999999, E+8 and E+4;
  - actions: the same re-query;
  - equal-time events: `through_sequence`, and a reused sequence is refused.

  After the fix the pipeline and walk-forward files pass (24); the earlier latency regression, including reversed reader rows, still passes.
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2354 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 128.77s (0:02:08) (only failure: the baseline cache-location test)

### 2026-10-15: Claude Code (M2-11b follow-up, B1: append-only insert guards)
- **Codex finding B1 (P1):** with recursive triggers off (the connection default), `INSERT OR REPLACE` / `REPLACE` overwrote an existing lineage or evaluation record without firing the DELETE triggers.
- **Owner-approved scope extension (2026-10-15):** `investment_engine/storage/schema/0004_append_only_insert_guards.sql`, recorded in M2-11b's allowed files (with B1 regressions in `tests/engine/test_lineage.py`). It adds BEFORE INSERT triggers on `lineage_records` and `evaluation_records` that refuse any insert of an existing id, before conflict resolution runs, so the replace, ignore and upsert forms all fail. New ids still insert, and the stores' identical-append no-op never reaches SQL. The migration is forward-only, so existing schema-3 databases gain the guards on upgrade.
- **Regressions, run first and observed failing (7 failed):**
  - for each table: `INSERT OR REPLACE`, `REPLACE INTO`, `INSERT OR IGNORE` with an existing id must raise "append-only" and leave the original bytes and the reconstructed record unchanged. The upsert form already failed through the UPDATE trigger and is kept as a regression;
  - a schema-3 database, where replacement still works, gains the guards on upgrade to schema 4; new ids still insert.

  After the fix: 66 passed across the lineage, run-store and SQLite files.
- **Side issue:** the SQL-portability test also scans comments, so the first comment, which named the forbidden statements, failed it. The comment was reworded; the test is unchanged.
- **Checks (Git Bash):** see the result line below; `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2351 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 111.19s (0:01:51) (only failure: the baseline cache-location test)

### 2026-10-14: Claude Code (M2 milestone complete on its branch: batch checks, self-review, report; handed to Codex)
- **State:** all 14 M2 tasks are committed and checked on `m2/milestone` (range `53c51bd..HEAD`). The combined review package is `docs/reviews/claude-m2-milestone-package.md`: commits, contract extensions, process notes, pending items and report results.
- **Batch checks (cwd `C:/Users/LOQ/TradingAgents-m2`):**
  - Git Bash full suite: **2341 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected.
  - PowerShell, `& C:\Users\LOQ\TradingAgents\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`: **2340 passed, 2 failed**, 4 skipped, 3 deselected. Both failures are recorded baseline failures (`test_every_command_is_registered_when_run_as_a_module`, cp1252; `test_yfinance_keeps_its_cache_out_of_the_users_home`). **No new failures.**
  - `ruff check .` passed.
  - **Clean install:**
    - `py -3.11 -m venv <scratch>/smoke-m2`, then `<scratch>/smoke-m2/Scripts/python.exe -m pip install ".[engine]"`: exit 0;
    - from the repository root, `-c "import tradingagents, cli.main, investment_engine"`: "clean-install import OK";
    - from outside the repository, `-I <scratch>/m2_smoke.py`: passed. It imports every M2 module from site-packages, finds schemas 0001–0003 packaged, migrates a new database to version 3, and confirms the lineage table refuses DELETE.
  - CI not yet run (nothing pushed).
- **Report:** `C:/Users/LOQ/TradingAgents-proposals/m2-report/nvda-research-report.html`, built by `build_report.py` there (outside the repository, no network).
  - **Inputs:** the saved verified recordings (2026-10-12, yfinance 1.7.0) through the M1 importers: 1954 daily bars and 33 actions.
  - **Views:** 1954 with lineage (1443 BULLISH, 219 BEARISH, 93 NEUTRAL, 199 ABSTAIN).
  - **Evaluation:** 11 complete 24/6/6 folds each at 5 bps (`eval-3d820ee92b21917…`) and at the 10 bps stress cost (`eval-b5724937986ffde…`); all 22 fold runs complete.
  - **Findings:** rules mostly match always-up; the information coefficient is negative wherever defined; returns trail buy-and-hold in rising folds and lose less in 2022-H1. No profitability or significance is claimed; promotion is not assessed.
- **Self-review (whole milestone):**
  - the package's "Where to look hardest" points were re-read against the specs and laws;
  - probes: empty report inputs give honest text; reverse and fractional split factors are exact (0.5 × 1.5 = 0.75); the real-data run shows the 2021 and 2024 splits with no fictitious loss (strategy equals buy-and-hold in single-trade folds across both splits).
  - Not found: any new blocking defect. Contract extensions and process deviations are listed in the package for Codex to accept or reject.
- **Honest corrections:**
  - the M2-00 and M2-01 entries say their tests "failed to import before the module existed": inferred, not observed. For M2-00 to M2-08 the tests were written first but not run before implementing;
  - M2-07's code was drafted before its tests;
  - `2a8c3ac` was committed with a lint failure; `7028523` has M2-11b's message by mistake.

  All four are recorded with their fixes.
- **This commit:** documents only. It adds the review package, the PROGRESS status and this entry, the M2 README status, and tidies the M2-02 status row (nested by my commit helper).
- **Next:** Codex reviews the complete milestone. Findings come back as follow-up commits. The M2 merge needs the owner's separate approval. Not authorized: push, keys, downloads, trading, hourly work. While the review runs, M3 planning (specs, OPEN-07/08) can be prepared, but M3 code waits for M2's merge and M3's approval.

### 2026-10-14: Claude Code (M2-12: NVDA HTML research report renderer, committed and checked; commit-message error recorded)
- **Process error, recorded:** commit `7028523` contains exactly the M2-12 files (`investment_engine/reporting/__init__.py`, `investment_engine/reporting/html.py`, `tests/engine/test_html_report.py`, the M2-12 status), but carries **M2-11b's commit message** and a duplicate of M2-11b's PROGRESS entry.
  - Cause: a check failure ended my command before the new entry and message files were written, so the M2-11b ones were reused.
  - Fixed forward in commit `M2-12 follow-up` (duplicate removed, this entry added), without rewriting history. The real M2-11b commit is `0b7db92`.
  - The commit helper now refuses an entry whose heading doesn't name the task being committed.
- **Added:** `investment_engine/reporting/__init__.py`, `investment_engine/reporting/html.py`, `tests/engine/test_html_report.py` (13 cases).
- **`render_research_report(views, runs, *, lineage_store, generated_at, source, instrument_id, adjusted_closes=())`:**
  - every view must carry its lineage id, the record must exist in the store, and the view must equal the stored decision (a tampered view is refused);
  - runs are `EvaluationRecord`s for the same source and instrument.
- **Sections:**
  - status chips: SIMULATED / REPLAY · historical research; PAPER EXECUTION NOT CONNECTED; AUTONOMY NOT CONFIGURED; TRADING STATUS CANNOT BE VERIFIED; PROMOTION NOT ASSESSED;
  - latest view: symbol and word for direction, strength as a 0–1 scale "not a probability", `valid_until` assessed at that historical T, DataHealth per source, abstain reason, rule explanations, BACKFILL_ASSUMED input counts;
  - inline-SVG chart with ▲▼●✕ markers; counts by direction; the last 40 views;
  - per evaluation record: configuration, costs, windows, versions, coverage and backfill assumptions, promotion status, per-fold counts, every direction metric (unavailable shows its reason, never 0), strategy vs buy-and-hold vs cash, trades, stitched summary with its label, limitations and disclosures.
- **Contract extension for the review: `adjusted_closes`.** Each view's decision close is adjusted as of its own T, so plotting those across 2024-06-10 would show a false 90% drop. The chart takes one supplied M2-00 series with a single basis and `as_of`, named in its caption; without it, the report says "No price series supplied".
- **Safety:** all supplied strings are escaped (a stored `<script>` reason renders as text); no remote `src`/`href`; deterministic output; nothing written; `probability_up` never shown.
- **Tests first, observed:** collection failed before the module existed. After implementing, one test failed because it edited a view without its stored lineage, and the renderer's lineage check refused it, as designed. The test now stores a record with the malicious text, and a separate test proves tampering is refused. 13 passed.
- **Checks (Git Bash):**
  - the first check run stopped on two ruff findings (a percent-format in the SVG builder, an unused test import); both were fixed and every check rerun;
  - full suite: **2341 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; whitespace clean.

### 2026-10-14: Claude Code (M2-11b: evaluation run records, committed and checked)
- **Added:**
  - code: `investment_engine/evaluation/run_store.py`, `investment_engine/storage/schema/0003_evaluation.sql`;
  - tests: `tests/engine/test_evaluation_run_store.py` (7 cases), plus one upgrade case in `tests/engine/test_sqlite_store.py` (the M2-07 migration case now also expects `evaluation_records`; no earlier assertion removed).
  - `docs/tasks/M2-11.md` status.
- **`EvaluationRecord`:** one complete walk-forward evaluation, holding:
  - the walk-forward and evaluation configurations (costs included);
  - the result: each fold's boundaries, purge counts, direction metrics with baseline samples and outcome references, the SIMULATED run with its decision lineage ids and realised input references, the stitched summary and the promotion status;
  - source, instrument, `as_of`, code and calendar versions, coverage evidence references and reason, and the backfill assumption.

  `record_id` is `eval-` + SHA-256 of tagged canonical content (registered with M2-07's codec), so every assumption changes it.
- **`EvaluationRunStore`:** an identical append is a no-op; a different record under an existing id raises `EvaluationRunConflict`; `get` rebuilds and re-verifies the record; `ids(instrument)`; no update or delete path. Migration 0003 adds `evaluation_records`, whose triggers refuse UPDATE and DELETE (SQLite syntax, to be rewritten for PostgreSQL in M3).
- **Naming note for the review:** M2-11's contract says `EvaluationRunStore.append(run: EvaluationRun)`. The stored unit is the whole walk-forward record, because rule 5 requires fold boundaries and versions in the stored run; the per-fold `EvaluationRun`s are inside it.
- **Acceptance covered:** exact reconstruction of configuration and references; append idempotence and conflicts; direct SQL immutability; the id covering every assumption; required versions and UTC time; upgrades from schema 1 and schema 2 with M1 data intact; the migration ships as package data (the installed check runs in the batch checks).
- **Tests first, observed:** collection failed before the module existed. One test I added had a broken multi-line string (my script's escaping) and was repaired before the run; 42 passed (run-store and sqlite files).
- **Checks (Git Bash):** `ruff check .` passed; whitespace clean.
  - full suite: 1 failed, 2328 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 494.51s (0:08:14) (only failure: the baseline cache-location test)

### 2026-10-14: Claude Code (M2-11a: walk-forward folds and leakage guards, committed and checked)
- **Added:** `investment_engine/evaluation/walk_forward.py` and `tests/engine/test_walk_forward.py` (12 cases).
- **Folds:**
  - `WalkForwardConfig` holds months as positive ints (not bool); a step shorter than the test window is refused because test windows would overlap.
  - `Fold` requires `train_start < train_cutoff < test_start < test_end`.
  - `make_folds` aligns calendar months to the first covered session (e.g. 2019-01-02; a test start on Saturday 2021-01-02 moves to Monday 2021-01-04). The cutoff is the close of the last session before the test start; test windows are half-open. Only complete test windows count: 11 folds for 2019-01-01..2026-10-09 at 24/6/6.
- **`walk_forward(folds, *, views, reader, calendar, source, instrument_id, coverage_evidence, coverage_first, coverage_last, coverage_reason, evaluation_config, at, fit_steps=(), impute_required_sources=False)`:**
  - fit steps and required-source imputation raise `UnsupportedFitStep`;
  - test decisions are the replay's own `PredictionView`s filtered by window;
  - training labels are computed at each cutoff and counted eligible or purged (`training_eligible`);
  - test outcomes are read at the evaluation time;
  - trailing (last-period) returns are read at each view's T;
  - coverage is established at each of those times from the evidence;
  - each fold has `DirectionEvaluation` plus a fresh-cash `simulate_research` run;
  - warm-up and abstain counts are reported;
  - the stitched summary is labelled "Normalized stitched fold returns … not a continuous portfolio's dollar P&L";
  - `promotion` is "PROMOTION NOT ASSESSED: thresholds pending approval"; no output promotes anything.
- **`RevisionCache`:** an in-memory, read-only projection of one provider's and instrument's stored revisions with the store's `visible_at` semantics. With the plain store reader the test file took 288 s (thousands of DuckDB reads); with the cache it takes 15 s. A test checks that the cache's answers equal the store reader's for many times and ranges.
- **Acceptance covered:**
  - fold edges and alignment; non-overlapping half-open tests;
  - purging of labels ending after the cutoff;
  - a correction arriving after the cutoff changes neither training-label counts nor test metrics;
  - fit-step and imputation rejection; determinism;
  - terminal outcomes unavailable; warm-up/stitched/promotion disclosures;
  - views outside every fold are never test observations.
- **Tests first, observed:** collection failed before the module existed. Before implementing I removed a meaningless test, extended the synthetic history to 2 July 2024 so a fourth fold is complete, and moved coverage to evidence form. All passed on the first implemented run; the cache was added after that run for speed.
- **Checks (Git Bash):**
  - full suite: see the next line;
  - `ruff check .` passed; whitespace clean.
  - full-suite result line: 1 failed, 2319 passed, 4 skipped, 3 deselected, 20 warnings, 99 subtests passed in 151.35s (0:02:31)

### 2026-10-14: Claude Code (M2-10: cost-inclusive SIMULATED research, committed and checked)
- **Added:** `investment_engine/evaluation/simulation.py` and `tests/engine/test_research_simulation.py` (17 cases).
- **`simulate_research(views, *, reader, calendar, source, instrument_id, first, last, at, coverage, config)`:**
  - **Inputs:** replayed MarketViews, each with exactly its lineage id. SPLIT and DIVIDEND coverage is required; otherwise it raises `AdjustmentUnavailable`.
  - **Decisions:** each view trades at the next regular open strictly after `generated_at`, if `valid_until` ≥ that open; the latest valid decision for one open wins. BULLISH → long; BEARISH/NEUTRAL → cash; ABSTAIN keeps exposure; unchanged exposure doesn't trade.
  - **Prices and actions:** raw prices. Splits multiply shares and dividends pay cash per post-split share before an ex-date's open (an ex-date cash research assumption, disclosed).
  - **Buys:** the most whole shares the cash covers with costs (bps per side, quantized to 0.0001); cash is never negative.
  - **Benchmarks:** buy-and-hold enters at the same first eligible open with the same cash, costs and actions; cash earns zero interest.
  - **Metrics:** net return; max drawdown (from the initial cash); daily Sharpe (zero risk-free, ×√252, sample deviation; unavailable for fewer than 2 returns or zero variance); trades, entries, round trips, abstains, expired decisions and decisions outside the window.
  - **Incomplete runs:** a session without a completed bar, or an unsupported action, makes the run incomplete (`complete=False`, a limitation listing the dates); return metrics become unavailable rather than zero-priced.
- **`EvaluationRun`:** the contract fields plus `source`, `instrument_id`, `first`, `last`, `as_of`, `cash_curve`, `ending_shares` and `complete`. `run_id` is `run-` + SHA-256 of canonical content, using M2-07's codec (the new dataclasses are registered there for M2-11b). Decision lineage ids and realised-input revisions (bars plus actions read at `as_of`) are both kept.
- **Acceptance covered:**
  - next open; same-open exclusion; expiry; the latest of conflicting decisions; repeated exposure; ABSTAIN;
  - exact 5 and 10 bps arithmetic;
  - split and dividend value preservation; buy-and-hold alignment;
  - missing bar → incomplete;
  - hand-computed net return, drawdown and Sharpe; zero-variance Sharpe unavailable;
  - a late correction changes realised revisions and the run id but not the decision lineage;
  - determinism; no broker/OMS/ledger/execution/clock imports.
- **Tests first, observed:** collection failed before the module existed (`1 error`). Before implementing I also removed a placeholder test that asserted nothing, and made a test use the run's `cash_curve` field instead of an invented method. All 17 passed on the first run after implementing.
- **Checks (Git Bash):**
  - full suite: **2307 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; whitespace clean.

### 2026-10-14: Claude Code (M2-09: honest direction metrics and matched baselines, committed and checked)
- **Added:** `investment_engine/evaluation/metrics.py` and `tests/engine/test_evaluation_metrics.py` (14 cases).
- **Inputs:**
  - `PredictionView(source, prediction_session, view)` supplies the provider and session a MarketView doesn't carry; the walk-forward builds them from lineage snapshots;
  - `evaluate_direction(views, outcomes, *, config, calendar, trailing=())` joins by provider, instrument and prediction session, checking basis and the exact h-session horizon on the calendar;
  - a duplicate view, outcome or trailing return, a mismatched horizon, provider or basis, or a view without its outcome all raise.
- **Metrics** (`MetricValue`: key, value, n, reason):
  - `direction_accuracy`: BULLISH/BEARISH views with available non-zero outcomes;
  - `always_up_accuracy_matched` (same scored dates) and `paired_accuracy_difference`;
  - `always_up_accuracy_full` (all available non-zero outcomes, so selective abstention is visible);
  - `positive_base_rate`;
  - `zero_outcome_exclusions`;
  - last-period direction: the sign of the same-basis h-session return ending at the prediction close, which must be complete and available, and computed, by the view's T. Its matched accuracy, the model's accuracy on that paired sample, their difference, and `last_period_unavailable`;
  - `information_coefficient`: tie-aware Spearman of the signed strength vs the realised return, zeros included; None with a reason for fewer than 3 or constant samples.
- **`DirectionEvaluation`:** the counts (eligible, directional, neutral, abstain, unavailable outcomes), the outcome references, and `disclosures` (strength isn't a probability; no significance claimed; overlapping horizons when h > 1).
- **Tests first, observed:** running the new test file before the module existed failed at collection (`1 error`). After implementing, 13 passed and 1 failed: my test's directional-view count was wrong (5 instead of the table's 6) and was corrected. 14 passed.
- **Checks (Git Bash):**
  - full suite: **2290 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; whitespace clean, new files included.

### 2026-10-14: Claude Code (M2-06 follow-up: unused test imports; check script hardened)
- **Process deviation, recorded:** `2a8c3ac` was committed with two unused imports in `tests/engine/test_market_view.py` (ruff F401). My task-check script printed ruff's failure but still exited 0, so the commit step continued.
- **Fix:** removed the imports (`ruff check --fix`). The check script now exits nonzero on any test failure other than the baseline, a missing result line, a ruff error or a whitespace error, and the commit only runs after it succeeds. Every earlier task commit's ruff run printed "All checks passed".
- **Checks (Git Bash):** full suite **2232 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected; `ruff check .` passed; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-06: MarketView and decision policy 0.1.0, committed and checked)
- **Added:** `investment_engine/decision/__init__.py`, `investment_engine/decision/market_view.py`, `tests/engine/test_market_view.py` (32 cases).
- **`MarketView`** has the Part H fields. Its constructor enforces:
  - a finite float strength in [0, 1], zero for ABSTAIN and NEUTRAL;
  - `probability_up` is always None;
  - an abstain reason exactly when ABSTAIN;
  - `valid_until > generated_at`.
- **`decide(...)`:**
  - one signal slot per strategy, in order and matching identity and version; the strategy set is non-empty and distinct; the snapshot's health must match its T and instrument;
  - **Law 9:** not applicable, a missing health entry for any declared required source, or any non-OK status (DEGRADED included) gives ABSTAIN naming each source and status;
  - an unavailable snapshot or unestablished required-action coverage abstains; established coverage with no actions doesn't;
  - warm-up abstains.
- **Combination:**
  - A1 (first strategy) sets the regime;
  - a same-direction signal takes the maximum strength;
  - an opposing signal gives a consistency NEUTRAL with its reason visible;
  - A1 NEUTRAL stays NEUTRAL;
  - A1 alone gives A1's direction.
- **Other fields:** `valid_until` is the next session's close (Friday→Monday and the Juneteenth holiday are tested); `horizon` is "5 sessions"; `regime` is A1's direction; reasons combine every signal's reasons.
- **Checks (Git Bash):**
  - task tests: 32 passed;
  - full suite: **2232 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-05: the two daily rule strategies, committed and checked)
- **Added:** `investment_engine/quant/strategies/trend.py`, `investment_engine/quant/strategies/pullback.py`, `tests/engine/test_first_strategies.py` (31 cases).
- **A1 `daily-trend` 0.1.0** (SMA50, SMA200, dist_sma200):
  - BULLISH when the close is above SMA200 and SMA50 > SMA200;
  - BEARISH when the close is below SMA200 and SMA50 < SMA200;
  - otherwise NEUTRAL, equalities included.
  - Strength `min(1, |dist|/0.10)`.
- **A2 `daily-pullback` 0.1.0** (rsi14, dist_sma200):
  - BULLISH when the close is above SMA200 and RSI ≤ 30;
  - BEARISH when the close is below SMA200 and RSI ≥ 70;
  - otherwise NEUTRAL.
  - Strength `min(1, |RSI-50|/50)`.
- **Shared:**
  - "close vs SMA200" is the sign of `dist_sma200`;
  - both strategies read only their declared features through `declared_snapshot`;
  - each documents `strength_scale` as "not a probability";
  - required sources `(yfinance, D1)` and actions `(SPLIT,)`;
  - reasons name the rule and values, e.g. "close 4.2% above SMA200; SMA50 above SMA200";
  - any declared feature in warm-up gives `None`.
- **Acceptance:** every table row, both equality cases, inclusive RSI 30/70, strength scales, warm-up, declared sources/actions/features and determinism.
- **Non-blocking note for the milestone review:** `FeatureDefinition` (M2-01) is unhashable because its parameters are a `MappingProxyType`; tests compare keys instead. Adding a key-based `__hash__` is a small M2-01 follow-up if Codex wants it.
- **Checks (Git Bash):**
  - task tests: 31 passed;
  - full suite: **2200 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-04: rule-strategy interface, committed and checked)
- **Added:** `investment_engine/quant/strategies/__init__.py`, `investment_engine/quant/strategies/base.py`, `tests/engine/test_strategy_interface.py` (21 cases).
- **Contract:**
  - `Direction` (BULLISH, BEARISH, NEUTRAL; ABSTAIN is the policy's);
  - `StrategySignal` validates a non-empty name, a semantic version, the direction, a finite **float** strength in [0, 1] (bool, int and Decimal refused; documented as a scale, not a probability), non-empty reason strings, and non-empty feature keys;
  - `RuleStrategy` is a runtime-checkable Protocol with required sources, required actions and features.
- **`declared_snapshot(snapshot, definitions)`:** returns an immutable copy whose values mapping exposes only the declared keys. Any other key, including through `.get`, raises `UndeclaredFeature`. Declared definitions must exist in the snapshot with the same version and input basis; a different version or parameters, or a mismatched recorded version, raise.
- **Checks (Git Bash):**
  - task tests: 21 passed;
  - full suite: **2169 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-03: FeatureSnapshot, committed and checked)
- **Added:** `investment_engine/quant/snapshot.py` and `tests/engine/test_feature_snapshot.py` (13 cases).
- **`build_snapshot(instrument_id, source, features, *, at, reader, calendar, health, coverage)`:**
  - one T for bars, actions, features and DataHealth; a `health.as_of` or instrument mismatch raises;
  - the decision bar is the latest session closed at or before T (`decision_session`); a session still open at T is never used;
  - the window is the consecutive calendar sessions ending there, as long as the longest declared warm-up (200), never before the coverage's first date (the verified history boundary).
- **Snapshot fields:** the contract fields plus `warmup` (the feature keys still warming up from the history boundary) and `decision_close` (the decision bar's adjusted close).
- **Unavailable snapshots** carry a reason and no feature values, in these cases:
  - a missing health entry for `source D1`, naming the source;
  - unestablished coverage (only `AdjustmentUnavailable` is caught; other errors propagate);
  - a missing decision bar (yesterday's values are never recycled);
  - any hole in the window, even one older than M1's 20-session health lookback.

  Warm-up from the boundary is labelled separately and isn't a hole.
- **References:** `input_refs` are exactly the bars the valued features used (the last 200 for the four definitions; 50 for SMA50 alone). When the snapshot is unavailable, they are the bars examined. Mappings are read-only.
- **Self-review:** dropped a draft field that fetched the raw decision close through an optional reader method (a hack); raw prices stay with M2-10's simulation.
- **Checks (Git Bash):**
  - task tests: 13 passed;
  - full suite: **2148 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-02 follow-up: RSI14 declares its seeding window)
- **Gap found while planning M2-03.** M2-02 rule 2 asks for RSI's seeding window "stated in the code"; the first commit didn't declare one, so RSI depended on all history since the boundary. That would make every view's inputs (and lineage) about 2,000 bars, and adding earlier history would change RSI.
- **Fix:** `RSI14` is now `rsi` v1.0.0 with `{"seed_sessions": 200, "window": 14}` and warm-up 200 (the same window as SMA200); `evaluate` computes it over exactly the last 200 closes, and refuses a seed shorter than `window + 1`. The `rsi()` function and its 15-close minimum are unchanged. This happened before any later task used the definition.
- **Tests:** a new case proves earlier history never changes RSI14 and that it equals `rsi(last 200, 14)`; the registration expectation now shows warm-up 200. 26 passed.
- **Checks (Git Bash):** full suite **2135 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected; `ruff check .` passed; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-02: indicators, committed and checked)
- **Added:** `investment_engine/quant/indicators.py` and `tests/engine/test_indicators.py` (25 cases).
- **Indicators:**
  - `sma`; `rsi` (Wilder: seeded by the simple averages of the first `window` gains/losses, then `(prev*(n-1)+current)/n`; 100 with only gains, 0 with only losses, 50 when flat); `distance_from`;
  - all take float64 through `float_inputs`; non-positive prices or averages, invalid windows and non-finite results raise.
  - The seed and recurrence are documented in the module.
- **Definitions:** `SMA50`, `SMA200`, `RSI14` (warm-up 15), `DIST_SMA200`, all on `SPLIT_ADJUSTED_AS_OF`, plus their parameter schemas and `registry()`. `evaluate(definition, closes)` gives `None` until exactly the declared warm-up and never a partial window.
- **Acceptance covered:**
  - hand-computed SMA/RSI, including gains-only, losses-only, flat, the post-seed recurrence and a 17-close series against an independent recurrence;
  - warm-up boundaries; no look-ahead;
  - across a synthetic 10-for-1 split through the M2-00 view (about 265 stored sessions): the raw closes drop about 90% while the adjusted ones stay continuous, and SMA(200) equals a manually adjusted reference;
  - registration with warm-ups.
- **Tests first / self-review:**
  - the module was missing before implementation;
  - one test used definitions as dict keys, which they can't be (their parameter mapping is read-only and unhashable). Changing `features.py` is outside M2-02's allowed files, so the test uses pairs instead;
  - a probe found `sma([1e308, 1e308], 2)` returned `inf`; outputs are now checked, with tests.
- **Checks (Git Bash, cwd `C:/Users/LOQ/TradingAgents-m2`):**
  - task tests: 25 passed;
  - full suite: **2134 passed, 1 failed** (baseline cache-location test), 4 skipped, 3 deselected;
  - `ruff check .` passed; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-01: versioned feature definitions and the float64 boundary, committed and checked)
- **Added:** `investment_engine/quant/features.py` and `tests/engine/test_features.py` (33 cases).
- **`FeatureDefinition`:**
  - validates a lowercase identifier name, a semantic version, finite int/float parameters with identifier names (booleans, Decimal, strings and lists refused), the `AdjustedBasis`, and a positive integer warm-up;
  - parameters are copied into a sorted `MappingProxyType`;
  - `key` is canonical JSON of name, version, parameters and input basis (order-independent, not a Python repr).
- **`FeatureRegistry(schemas)`:**
  - checks each definition against its feature's declared `ParamSpec`s: exact parameter names, int vs float, minimum; an undeclared feature name raises;
  - identical re-registration is a no-op; a different definition under an existing key raises.
- **`float_inputs`** is the explicit boundary: only finite floats pass. Decimal, int, bool and non-finite values are refused.
- **Tests first:** the test file failed to import before the module existed; all 33 pass after implementation.
- **Checks (Git Bash, cwd `C:/Users/LOQ/TradingAgents-m2`):**
  - task tests: 33 passed;
  - full suite: **2109 passed, 1 failed** (baseline `test_yfinance_keeps_its_cache_out_of_the_users_home`), 4 skipped, 3 deselected;
  - `ruff check .` passed after import sorting; `git diff --check` clean.

### 2026-10-14: Claude Code (M2-00: point-in-time split-adjusted daily view, committed and checked)
- **Added:** `investment_engine/quant/__init__.py`, `investment_engine/quant/adjusted.py`, `tests/engine/test_adjusted_view.py` (41 cases).
- **Contract:**
  - `adjusted_daily(reader, source, instrument_id, first, last, *, at, calendar, coverage)` returns `AdjustedBar`s (float64; never stored, not a Candle) with the exact Decimal `factor`, full `BarRef` and the `ActionRef`s of every split used;
  - the factor counts SPLIT revisions visible at T and effective by T's exchange date, for bars before their ex-date;
  - prices are divided and volume multiplied in a fresh 60-digit Decimal context per value, then converted once through `money.to_float64`.
- **Coverage evidence:**
  - `VerificationEvidence` is a structured, canonical reference: provider, instrument, action type, verified range, request bounds, verification version, status;
  - `establish_coverage` establishes coverage only from COMPLETE evidence covering every type over the whole range;
  - `adjusted_daily` re-parses the references through `require_coverage`, so forged established coverage, PARTIAL/FAILED verification, another provider/instrument/type/T or a short range all raise `AdjustmentUnavailable`. Established coverage with zero splits succeeds, and its references survive for lineage.
- **Completed bars (correction 5):** `completed_daily_bars` refuses FORMING bars, bars off the session boundaries, bars ending or available after T, `received_at < end_time`, foreign identities, duplicates and mixed currencies; split rows from another identity or available after T are refused. It and `visible_actions` are shared with later M2 readers.
- **Tests first:** the test file failed to import before the module existed. After implementing, two failures came from my code: a shared Decimal context left an Inexact flag, and a filter skipped the query for sessions still open at T, which hid a bar ending after T. Both fixed; no test changed to pass.
- **Checks (Git Bash, cwd `C:/Users/LOQ/TradingAgents-m2`):**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_adjusted_view.py tests/engine/test_layering.py tests/engine/test_no_system_clock.py`: **94 passed**;
  - full suite `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`: **2076 passed, 1 failed, 4 skipped, 3 deselected**; the failure is the baseline `test_yfinance_keeps_its_cache_out_of_the_users_home`;
  - `ruff check .` passed after sorting the test's imports; `git diff --check` clean.
  (Root `.venv` Python used from this worktree; the package imports from the worktree.)

### 2026-10-14: Claude Code (M2 milestone, step 0: documentation integration)
- **Owner approval (2026-10-14, relayed with Codex's package review):** fast-forward local `main` to the reviewed `53c51bd` (no push), then build the whole M2 milestone on its own branch from verified daily NVDA data. Apply Codex's corrections first, use the proposed settings as provisional research assumptions, and complete all 14 tasks with tests, task commits and checks. Return the HTML report and one combined package for Codex. Excluded: M1 hourly work, the M2 merge, pushes, keys, market-data downloads, trading.
- **Merge done:** in the clean `C:/Users/LOQ/TradingAgents-main`, heads rechecked (`0661d46` → `53c51bd`, ancestry verified), then `git merge --ff-only 53c51bd782f9ebc901254e2b74ed48ced75f3195`. Not pushed. M1 now stands at 15 of 18 tasks done.
- **Branch and worktree:** `m2/milestone` from `main`, in `C:/Users/LOQ/TradingAgents-m2`. Every other branch, worktree and the root's uncommitted files are untouched.
- **Integration:**
  - the reviewed M2 spec commits `bb86480`, `6df10da` and `71133c1` were cherry-picked unchanged (as `0b2afae`, `54b9297`, `75ce29e`; the spec files are byte-identical to `71133c1`); their PROGRESS conflicts were left for this commit;
  - PROGRESS.md is a three-way merge (base `cc62dbf`): `53c51bd`'s log, the root working copy's newer handoff entries, and the M2-spec branch's own entries, all kept; status rows and next steps rewritten for the current state;
  - AGENTS.md, CLAUDE.md and `docs/tasks/README.md` take the root's role-restoration records; the temporary Copilot assignment is marked ended; shared rules §4 records the milestone-package workflow (shared blocks checked identical);
  - `docs/reviews/` (handoff, Copilot review queue, acceleration plan, Claude's package proposal, Codex's package review) is committed as the record behind these decisions; `.github/copilot-instructions.md` stays out.
- **Codex's five corrections applied:**
  1. the daily-only prerequisite amendment is in every controlling text: roadmap overview and §5, `docs/tasks/README.md`, the M2 README, M2-00 and M2-08 (the two specs that required a complete M1); M1's hourly criteria are unchanged;
  2. integration happens on `m2/milestone`, not on `main`;
  3. M2-11 is split mechanically: M2-11 keeps the full contract plus a mapping table; M2-11a (folds and leakage guards: rules 1–4 and 6) and M2-11b (run records: rule 5) give files, interfaces, dependencies and acceptance-case mapping; M2-12 depends on both;
  4. blocking gaps stop the work (recorded in shared rules §4 and here); only non-blocking items wait for the milestone review;
  5. completed-bar cutoff: M2-00 rule 7 and M2-03 rule 6 require CLOSED bars with `end_time <= T`, availability and replay delivery by T, and refuse `received_at < end_time`, with acceptance cases.
- **Configuration:** the M2 README records the provisional research settings (OPEN-08 next-session-close validity; 5-session split-adjusted horizon; 5 bps per side and a 10 bps stress run; 24/6/6-month windows; promotion thresholds not accepted). M2-06 and M2-10 note them as resolved for M2.
- **Also corrected:** Claude's package document no longer claims the internal-only hourly route avoids redistribution permission (Codex review); A4 must establish it.
- **Checks (documentation only):** `git diff --check` clean; shared-rules blocks identical. No runtime change, so no test run for this commit.

### 2026-10-14: Codex (reviewed Claude's whole-M2 proposal; consolidated authorization prepared)

- Owner relayed Claude's D1–D5 list and said they want a whole milestone completed and reviewed, without reading the technical list. Reviewed the actual uncommitted next-package document, current source heads, frozen laws/contracts/milestone/change rules and M2 specs. Created a concrete planning review note instead of reopening completed R-07 work.
- Corrected the earlier dependency interpretation: full M1-before-M2 is currently a roadmap/spec rule; frozen Part K doesn't impose that sequencing. Daily-only M2 can proceed under an explicitly approved planning amendment, with verified daily prerequisites merged, M1 kept incomplete and H1 blocked. No laws, process/domain boundaries or execution authority change; no architecture ADR for the scheduling exception alone.
- Required integration corrections: update all controlling prerequisite text (not only roadmap), integrate docs on `m2/milestone` rather than directly into main, preserve the reviewed contracts/tests when splitting M2-11, defer only nonblocking suggestions, and validate CLOSED inputs/end-time/availability/replay-delivery cutoffs independently of the old M1 receipt contract issue. D3 remains provisional simulation/research config, no trading/promotion. D5 remains unapproved; internal-only data handling alone doesn't establish all applicable disclosure permissions.
- Prepared a short consolidated owner instruction for Claude covering the precise local reviewed merge and M2 package while excluding keys/downloads/purchases and the final M2 merge. This planning review itself supplies no owner git permission. No runtime changes, tests/CI/downloads, commit, merge or push. Main still `0661d46`; target `53c51bd`; M2 specs `71133c1`. Files remain unstaged; whitespace checked.

### 2026-10-14: Codex (end-of-month target; acceleration proposal for Claude)

- Owner said the workflow is taking too long and all milestones need completion this month. Recorded **October 31, 2026** as the requested planning target, without promising feasibility or altering frozen scope. M10 live is outside v1. The roadmap overview's M2–M9 ranges sum about 340–450 provisional effort hours, excluding remaining M1/external waiting; these are not measured AI elapsed times.
- Prepared `docs/reviews/october-acceleration-plan.md`: one clearly approved milestone-sized package, uninterrupted task implementation with automatic task commits/checks, one combined independent review, productive independent planning during review, and consolidated owner decisions before each package. Existing check cadence/stop rules/merge permissions remain unchanged.
- Listed the actual critical gates: prepared reviewed M1 merge, hourly A4/access/R/evidence, M2 OPEN-08/09/configuration, later risk and ledger/broker/hosting ADR decisions. The full M2 draft pack is already reviewed; do not rewrite it or implement before its prerequisites are met. No earlier milestone reorder or scope reduction adopted.
- Updated Claude handoff to point to the proposal. Files remain unstaged, no commit/merge/push/runtime edits/keys/downloads. Main stays `0661d46`; count remains 12/18 M1 done. Runtime tests/CI not run (documents only); whitespace checked. Claude implements and Codex reviews again.

### 2026-10-14: Claude Code (returned as implementation lead; state verified, next package proposed)
- **Read:** CLAUDE.md, this file and `docs/reviews/claude-return-handoff.md`. The recorded state is verified:
  - every head matches the handoff;
  - `main` and every accepted commit are ancestors of `53c51bd` (a fast-forward is possible);
  - `7ef63f6` is not an ancestor, but its runtime, spec and test files are byte-identical in `53c51bd`;
  - all five worktrees are clean.
- **Fresh check at `53c51bd`.** Claude ran these in a new detached worktree, `C:/Users/LOQ/TradingAgents-reviews/claude-53c51bd`; Codex's checkouts weren't touched.
  - `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` (Git Bash): **2035 passed, 1 failed, 4 skipped, 3 deselected**. The only failure is the baseline `test_yfinance_keeps_its_cache_out_of_the_users_home`.
  - `ruff check .`: passed.
  - PowerShell and the clean install were not rerun. CI not yet run.
- **Proposal written (uncommitted):** `docs/reviews/claude-next-package-2026-10-14.md`. It covers:
  - owner decisions D1 to D4: the M1 fast-forward; whether M2 daily work may start before hourly M1 completes (a roadmap change, not an architecture change); M2's provisional configuration; the hourly gate actions;
  - an M1 hardening package (H-1 to H-4, from the deferred review items);
  - a `docs/m2-integration` branch (a simulated merge conflicts only in PROGRESS.md).
- **No source changes.** No merge, push, commit, keys or downloads. M2 code is still blocked.
- **Next:** the owner's answers to D1 to D3 and approval of the package; Codex reviews the proposal.
- **Later the same day, the owner set the working method:** each milestone is completed in one go, with automatic task commits under one package approval, and Codex reviews the whole milestone. Pending items wait for that review.
  - The proposal was rewritten to match. It now holds: blockers B1 to B4, owner decisions D1 to D5, the complete M2 package (steps 0 to 14, about 33–42 h estimated), the list of items pending for Codex, and an honest October 31 forecast.
  - Unchanged: merges, pushes, key use and downloads still need their own explicit approval.

### 2026-10-14: Codex (Claude returned; implementation/review roles restored)

- Owner explicitly reported Claude Code is back and asked for a complete handoff and faster, longer work packages. Restored Claude-as-implementer/Codex-as-reviewer now, based on the actual return rather than waiting for a calendar reset date. Copilot assignment ended; completed R-07 acceptance remains valid at exact heads.
- Wrote `docs/reviews/claude-return-handoff.md`: work done, branches/worktrees/heads, checks and limitations, prepared merge, hourly blockers, M2 draft state, and one combined-review/longer-work-package workflow. Updated AGENTS/CLAUDE role notices (outside identical shared-rule sections), task README, historical Copilot instructions/queue and this root handoff. All remain unstaged; no runtime changes or commit.
- Verified main remains `0661d46`, daily target `53c51bd`, and prepared main checkout is clean. Source worktrees remain clean and existing root changes are preserved. No merge approval was recorded in the owner's handoff request; the prepared exact fast-forward remains the next approval-dependent action.
- Runtime tests/CI not rerun (documents only). Whitespace and shared-rule equality checked. No keys, data downloads, push, merge, branch deletion or M2 runtime. **12/18 M1 tasks done** remains current; the approved future merge would make 15/18 while hourly work remains unfinished.

### 2026-10-14: Codex (R-07 accepted; local merge prepared, not performed)

- Owner relayed `d6b46fb0-ae95-45a5-aa10-fcf5cf4dc134/Pasted text.txt`. Copilot reviewed exact standalone `cc62dbf..7ef63f6`, dependent `db826f2..53c51bd`, and docs `6df10da..71133c1`: **no blocking findings in any part**. It reports **147** standalone and **178** combined targeted cases passed, changed-file Ruff passed, snapshot whitespace clean. Earlier CLI count corrected to 79. Full suites/install/CI/live/hourly/authenticated checks were not run by Copilot in this review; previous implementer evidence remains separate.
- Codex verified all branch heads still match the reviewed commits and all three source worktrees are clean. Rechecked snapshot whitespace and exact ported resample/runtime/spec/test equality between `7ef63f6` and `53c51bd`. No new source change or runtime test rerun in this step; no need to repeat previously passing checks on identical code.
- Reviewed proposed main diff: **22 existing commits, 37 changed paths**, accepted daily 3a/protocol/schedule plus batch 4/fixes and partial daily CLI. No upstream runtime, architecture/SVG, CI, env-example, secrets or `.claude/` changes. Main `0661d46` is an ancestor of exact target `53c51bd782f9ebc901254e2b74ed48ced75f3195`; `git merge --ff-only` is possible. Standalone `7ef63f6` is not merged separately because its fix already exists exactly in the dependent head.
- Prepared `C:/Users/LOQ/TradingAgents-main` with `git worktree add C:/Users/LOQ/TradingAgents-main main`: clean, at unchanged main `0661d46d5222955c57309d3cd0b9fd3b6efdfa5c`. Root's branch/dirty role-setup documents and all other worktrees/branches remain preserved. This is reversible checkout preparation, **not a merge**.
- Updated this root handoff and review queue, left unstaged. No commit, merge, push, key use, market-data download or M2 runtime. M2 documentation `71133c1` remains on its separate branch. Main still has **12/18 M1 tasks done**; proposed approved merge would make 15/18 while hourly M1-12/13/17 stays unfinished.
- **Next:** obtain the owner's explicit approval for this concrete fast-forward, as AGENTS.md §4/§5 requires; then recheck main/target/checkout, merge only the exact reviewed target, and report final state. Do not interpret the reviewer report as owner merge permission.

### 2026-10-13: Codex (Copilot review received; all follow-ups implemented and checked)

- Review attachment `7494f4c6-771a-4fa3-9c06-38ede792ade0/Pasted text.txt`: **R-01 changes required**, one reproducible point-in-time blocker in `compare_daily`; **R-06 no blockers**, provider-label suggestion; **R-02 no blockers**, now supplied zero-split evidence wording; **R-04/R-05 no blockers**; **R-03 no documentation blocker identified but source/permission verification incomplete**. All acceptance is limited to the reviewed snapshots; no merge authorized.
- **Standalone R-01 fix:** `7ef63f64f9a5fa7928c0a785dfe8ce937fd775f5`, branch `m1/batch-4-review-fix`, worktree `C:/Users/LOQ/TradingAgents-batch4-review-fix`, base `cc62dbf`. Seven regression cases failed before the fix; inclusive-boundary case passed. Future/naive/inconsistent availability is now rejected and derived availability must match the latest input. **147 target tests passed**; full Git Bash and PowerShell each **2009 passed, 1 baseline failure**; Ruff and fresh installed cutoff smoke passed. Four allowed M1-15 files only.
- **Dependent CLI follow-up:** `53c51bd782f9ebc901254e2b74ed48ced75f3195`, branch `m1/M1-17-daily`, worktree `C:/Users/LOQ/TradingAgents-daily-cli`, base `db826f2`. Exact resample/test/spec contents from the standalone fix were ported without merge or history rewrite. Added actual provider to the RESEARCH DATA label; two existing output assertions failed first. **178 combined target tests passed**; full Git Bash and PowerShell each **2035 passed, 1 baseline failure**; Ruff and installed base/engine CLI+cutoff smoke passed. Fresh installation environment was created for this review session, with own Python and isolated installed-code checks; project editable installation unchanged.
- **Only full-suite failure in every run:** `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, recorded in baseline. No new failures. Historical PowerShell CLI failure did not reproduce and was not altered/skipped. Exact commands/output paths are committed in the respective PROGRESS.md files. CI, live providers, keys/downloads/hourly gates not run.
- **M2 suggestion:** documentation commit `71133c197949a0d6acbb267db0fc3b7ae5c156d2`, `docs/m2-specs`, base `6df10da`, only M2-00 plus handoff. Zero-split evidence must identify completed exhaustive verification for exact provider/instrument/type/range/as-of, request bounds and version; incomplete/failed queries cannot establish absence. Added future acceptance cases. Whitespace clean; no runtime tests needed/run for this documentation change. M2 remains draft and OPEN-08/09 unresolved.
- **Review record clarification:** Copilot's summary lists 139 tests for its CLI/layering/system-clock selection; Codex independently reran that selection and observed **79** (same 26 CLI cases). Queue asks for a count correction; no raw output was invented and this is not treated as a code blocker.
- **Preserved:** root's uncommitted reviewer-setup files remain unstaged. Root and detached original review snapshot stay `cc62dbf`; main stays `0661d46`; all existing branches/worktrees kept. No merge, push, secrets or architecture changes. **12/18 M1 tasks done** remains accurate. Copilot re-review of all three follow-ups is **R-07**, pending.

### 2026-10-13: Codex (daily CLI implemented alongside Copilot review)

- Separate worktree `C:/Users/LOQ/TradingAgents-daily-cli`, branch `m1/M1-17-daily`, base `cc62dbf`, scope commit `6c5e35e`, code/checks commit **`db826f20c4f9076e8b53b3b2cc943dc9233b7eb5`**. The owner's instruction was to work on the next task while Copilot reviews; Codex stated the daily-scope assumption before implementation. Checked dependencies remain unmerged in branch ancestry; this is not a passed independent review.
- Real task delivered: `python -m investment_engine init`, offline provider-specific D1 report, and explicit daily-only import wiring. Exact Decimal values, revisions/corrections, ET/UTC, source/availability/precision labels, corporate actions and DataHealth are shown. Hourly remains BLOCKED/UNAVAILABLE; default full import fails honestly. Tests use existing recordings and synthetic observations under the network guard. No live data or keys.
- **26 new CLI tests**, **48 CLI/layering/clock tests passed**. Final full suites ran sequentially: Git Bash and PowerShell each **2027 passed, 1 failed, 4 skipped, 3 deselected**. Only failure: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, recorded in baseline. No new failures. Ruff and fresh base/engine installed smoke checks passed. CI not run.
- Self-review fixed revision currency labels with a regression test first. Actual code/check commands, installation paths and limitations are recorded in the daily branch's PROGRESS.md. This root entry is a cross-worktree handoff, not another commit.
- Copilot packet **R-06** appended, independently pending. Root role-setup edits and all previous worktrees preserved; root code remains `cc62dbf`, main `0661d46`. No merge/push. **12/18 M1 tasks done** remains accurate; partial unmerged work does not increase that count.

### 2026-10-13: Codex - received Copilot's first partial review

Read the owner's entire Copilot transcript attachment and closing summary (`ae50c017-6198-4e5f-9d10-3f31c6ff3ae9/Pasted text.txt`). Confirmed that the named snapshots still resolve to batch 4 `cc62dbf`, M2 drafts `6df10da`, hourly assessment `699f9fa`; no branch or source changed during that review.

**Actual independent review result:** R-02 reported no blocking findings for exact `5984997..6df10da`. Copilot mentioned a lineage/evidence-reference documentation suggestion but didn't include its location, failure scenario or proposed wording. No change was guessed from that summary. This result is a review of draft documents, not M2 implementation authorization or acceptance of OPEN-08/09.

**Still incomplete:** Copilot explicitly didn't claim R-01's full code review passed. It inspected the proposal/setup/public-assessment documents but didn't return full per-job verdicts. Its public source fetches failed, so R-03 source verification remains limited and **A4 remains unresolved**. Missing permission is a pre-existing gate, not a reported implementation bug. No independent runtime checks were reported. The transcript lists activity/commands without full results, so only its stated conclusions are recorded as received evidence.

**Handoff improved:** updated the queue with per-job received status, a focused continuation prompt and absolute paths. Copilot initially opened the older `codex-claude-extension-integration` checkout, which lacks the new queue/instructions. The prompt points to current workflow files in `C:/Users/LOQ/TradingAgents` and the isolated R-01 review snapshot. Corrected navigation hints for the actual ADR-005 filename and the M1-12 assessment location. No reviewer result, test pass, permission or owner scope approval is fabricated.

**Checks this turn:** attachment read; exact git refs and working-tree status checked; `git diff --check` clean; shared-role instructions left unchanged. Runtime tests/Ruff/CI/fresh install not rerun because only review-tracking documentation changed. No actionable code finding was supplied and no runtime was modified. These tracking/setup edits remain unstaged and uncommitted. Main is still `0661d46`, M1 done count 12/18; no merge/push, keys or downloads. Next: Copilot completes R-01 and remaining verdicts; owner separately decides the prepared daily-first scope change before its implementation.


### 2026-10-13: Codex - GitHub Copilot temporary independent reviewer

The owner opened GitHub Copilot on the same project and explicitly assigned it independent reviewing while Codex implements, until Claude returns after its October 15 reset. Recorded the temporary exception in AGENTS.md and CLAUDE.md, kept their shared-rule sections identical, added `.github/copilot-instructions.md`, noted the assignment in the task README and prepared `docs/reviews/copilot-review-queue.md`. This is an administrative workflow change; frozen laws/authority, accepted task scopes, verification and git approvals are unchanged.

**Concrete handoff prepared:** R-01 reviews all eight batch 4 commits at exact `cc62dbf`; R-02 the M2 draft pack at `6df10da`; R-03 public A4 assessment at `699f9fa`; R-04 the unapplied daily-first CLI scope proposal; R-05 these uncommitted reviewer instructions. Copilot reports findings in chat; Codex records them and handles code fixes. No Copilot review result exists yet. The queued status isn't acceptance.

Created an isolated detached review worktree with `git worktree add --detach C:/Users/LOQ/TradingAgents-reviews/copilot-batch4-cc62dbf cc62dbf23e04db27cbecfbd6a1d462ecdd4c3d1c`. The reviewer must not edit implementation files, switch the shared branch, mutate shared handoff documents or modify the project venv. Its review can inspect that stable snapshot while implementation continues elsewhere. Use a separate test environment; full suites in the shared environment must not run concurrently because upstream caches interfere.

**Communication limit:** inspected the available tools and shell; no callable Copilot/IDE chat bridge and no `copilot` CLI command were found. No install, window control, message sending or background monitor was attempted. The owner must paste the prepared starter prompt and relay the response. Future completion messages include the next packet/prompt; direct delivery is never claimed.

**Scope still pending:** the earlier daily-first M1-17 proposal hasn't been approved by this role-change request. Hourly evidence/A4 remain unresolved, M1-17 full task still depends on 3b and 4, and M2 runtime is not authorized. Reviewer acceptance cannot authorize these scope changes, merges, pushes, keys or market-data downloads. Restore the normal Claude implementation/Codex review roles when Claude actually returns and record it here.

**Checks:** exact queue hashes and commit ancestry verified; shared rules identical; documentation links/fences/whitespace checked. `git diff --check` clean. Runtime tests, CI and fresh installation not rerun for this documentation-only setup; latest code evidence remains the 139 targeted passes, both full suites 2001 passes with the sole baseline cache-location failure, Ruff and fresh-install checks recorded above. These workflow documents are **unstaged and uncommitted** for review; no runtime changed, no merge/push or secret staging. Main remains `0661d46` and M1 done count 12/18.

### 2026-10-13: Codex (Copilot R-02 coverage-evidence suggestion)

- Copilot's relayed review of `5984997..6df10da` reported no blockers; its omitted suggestion was supplied in attachment `7494f4c6-771a-4fa3-9c06-38ede792ade0/Pasted text.txt`.
- Updated only M2-00 and this handoff. Zero-split coverage now explicitly requires references to completed, exhaustive verification for the exact provider/instrument/SPLIT/range/as-of, request bounds and verification version. Empty local queries and incomplete/failed responses cannot prove absence. Added the corresponding future acceptance cases and retained references into M2-07 lineage.
- This is a spec clarification, not an implemented coverage system, architecture change or accepted OPEN-08/09 configuration. No M2 runtime, merge, push, keys or downloads.
- Checks: `git diff --check` clean; reviewed the clarification against M2-07's evidence references. Runtime tests and CI not run (documents only). Follow-up awaits Copilot review; the rest of the previously reviewed pack was unchanged.

### 2026-10-13: Codex - owner-authorized self-review, M2 contract clarifications

The owner instructed Codex to self-review and continue without waiting for Claude's October 15 reset. This changes who performs this review; it does **not** authorize merges/pushes, keys/downloads, bypassing the hourly checkpoint or declaring incomplete M1 done. Self-review is labelled honestly; Claude can audit the changes later.

Read every M2 spec and the pack index again. Clarified three draft inconsistencies: FeatureDefinition's key annotation now includes input basis as its canonical-key rule requires; a missing required health entry creates an unavailable snapshot that reaches the ABSTAIN policy instead of raising beforehand; last-period-direction baseline is explicitly the already-completed same-horizon window ending at prediction session close, avoiding an unfinished forward label.

No M2 runtime was implemented. OPEN-08/09 choices and action-coverage/total-return acceptance remain unresolved; complete M1 is still an implementation prerequisite. The read-only pack check (`& 'C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe' 'C:/Users/LOQ/TradingAgents-proposals/m2-pack-check-codex.py'`) and whitespace checks passed. M2 runtime tests and CI not run (documentation only). The separate batch 4 branch contains ongoing DataHealth boundary fixes; public A4 evidence is on `docs/hourly-access-review`. A prepared, unapplied daily-CLI split proposal is outside the repo at `C:/Users/LOQ/TradingAgents-proposals/daily-cli-unblock.patch`; it needs an owner scope decision before implementation.


### 2026-10-13: Codex - completed M2 planning pack, documentation only

The owner authorized M2 specification drafting on a separate branch, OPEN-06 option A research scope, with OPEN-09 assumptions provisional, during the longer batch 4 work package. **No M2 code, merge, push, key use or market-data download.** Existing `docs/m2-specs` worktree was preserved at `C:\Users\LOQ\TradingAgents-m2-specs`, based on scheduling commit `5984997`. Claude's untracked M2-00 – M2-07 drafts were continued, not discarded.

**Documents prepared:** M2-00 – M2-12; `docs/tasks/M2-README.md`; a link from the task README; replacement of roadmap's provisional M2 work-package rows with the draft task/batch graph. Each spec has goal, dependencies, allowed files, contracts, choices, acceptance checks and out-of-scope boundaries. Proposed M2-A/B/C/D groups allow longer combined sessions on approval while retaining task commits/checks and milestone prerequisites.

**Codex revised the initial drafts:**

- Full provider/instrument/revision/import/time/basis references and explicit established action coverage, including a verified-empty case.
- Split-adjusted price view before indicators; a separate labelled total-return/label task instead of an insufficient generic dividend-adjusted OHLC formula. Raw execution/accounting values remain raw.
- Flat-RSI edge, exact RSI threshold boundaries, finite-value validation and guarded feature access. Feature-window holes and stale decision bars cannot pass just because the 20-session health window is OK.
- MarketView input checks, a non-circular evidence-reference/hash flow, complete append-only lineage with SQL mutation guards and full DataHealth/configuration.
- Replay knowledge projection: only revisions already delivered by the feed may enter features/health. The E / E+3 correction with five-second latency is an explicit pipeline acceptance test; unrestricted PIT store reads at delivery T would leak that correction.

**Codex drafted M2-08 – M2-12:** separately labelled price/total returns and completed labels; matched directional base-rate/IC metrics; Decimal raw-price cost-inclusive SIMULATED long/cash research; fold purging, fit isolation and immutable EvaluationRun records; honest static HTML reporting. No numeric-return models or calibrated probabilities in M2. No actual ledger cash, execution replay, broker, Order, OrderIntent, new process or outbox is introduced.

**Decisions still pending:** independent acceptance of all draft contracts, action-coverage evidence and total-return convention; OPEN-08 validity; OPEN-09 horizon/costs/folds/exposure/ABSTAIN assumptions and promotion thresholds. The proposed numerical promotion thresholds remain unaccepted and cannot authorize execution. M2-11 may need a further reviewed split if its fold/storage implementation estimate exceeds three hours. These are draft refinements within the existing Quant/Evaluation/Lineage boundaries, not accepted architecture changes.

**Checks:** from this worktree, `& 'C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe' 'C:/Users/LOQ/TradingAgents-proposals/m2-pack-check-codex.py'` passed: 13 complete numbered specs, required sections, balanced fences, local links, whitespace and an acyclic dependency graph. The read-only helper stays outside the repository. `git diff --check` and `git diff --cached --check` passed. Runtime tests/CI/live checks **not run in this worktree**, because only documents changed. Batch 4's separate code checks: 134 task/clock checks; full Git Bash and PowerShell each 1996 passed with only the recorded cache-location baseline failure; Ruff and fresh installed synthetic replay/resample/health passed. Consult `m1/batch-4`'s PROGRESS for exact commands; this is a cross-branch summary, not an M2 runtime result.

**Handoff for Claude:** independently review Codex's drafts and the batch 4 follow-up commit before treating them as accepted. Resume implementation-lead/reviewer division when Claude is available. The owner authorized local task/follow-up commits during takeover; merges/pushes remain forbidden for this package. Main stays `0661d46`, 12/18 M1 tasks done. Hourly evidence and M1-17 are still blocked by their existing gates.

### 2026-10-13: Codex (Copilot R-01/R-06 follow-ups in the daily CLI branch)

- **Review received:** attachment `7494f4c6-771a-4fa3-9c06-38ede792ade0/Pasted text.txt`. Copilot independently reviewed `cc62dbf..db826f2` with no blocking findings. Suggested label alignment: put the actual provider in `RESEARCH DATA (<provider>)`. Its R-01 review of the preceding batch found a separate cutoff-lineage blocker, which this dependent branch must carry a fix for before any merge.
- **Tests first for the label:** augmented the existing exact-output and provider-isolation assertions; `& C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q tests/engine/test_cli.py -k 'has_exact_values or only_the_named'`: **2 failed, 24 deselected** before the one-line label fix. Both now pass, including `testvendor`; the number of CLI cases remains 26.
- **Dependency repair:** exact runtime/test/spec contents from standalone fix **`7ef63f64f9a5fa7928c0a785dfe8ce937fd775f5`**, branch `m1/batch-4-review-fix`, were applied as a scoped patch, without merge/rebase/cherry-pick or altering existing review snapshots. Normalized text of resample.py, test_resample.py and M1-15.md was compared and matched that checked fix. It validates UTC availability against `at` and the maximum input availability; eight tests include Copilot's counterexample and the valid inclusive boundary. Their tests-first/full/installed checks are in the standalone fix's PROGRESS.md.
- **Scope:** this follow-up changes only M1-15's allowed runtime/spec/test paths and M1-17's label/test/spec plus shared handoff. It enforces existing contracts; architecture, processes, source providers, CI, dependencies, upstream runtime and existing upstream tests are unchanged. M2-00's separate coverage-evidence suggestion is documentation commit `71133c1`, still a draft; no M2 code.
- **Combined target checks (Git Bash, cwd `C:/Users/LOQ/TradingAgents-daily-cli`):** `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q tests/engine/test_replay.py tests/engine/test_resample.py tests/engine/test_data_health.py tests/engine/test_cli.py tests/engine/test_layering.py tests/engine/test_no_system_clock.py`: **178 passed**. Earlier CLI/layering/system-clock selection alone: **79 passed**, matching the current test selection. Copilot's relayed summary reported 139 for that CLI selection; the queue requests correction of that apparent transcription error rather than inventing missing output. Its batch-4 selection was 139 before the eight new regressions.
- **Full suites, sequential:** Git Bash `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q` and PowerShell `& C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q`, cwd the daily worktree: each **2035 passed, 1 failed, 4 skipped, 3 deselected**, 99 subtests passed. Outputs `C:/Users/LOQ/TradingAgents-proposals/r06-followup-bash.txt` and `r06-followup-powershell.txt`. Only failure: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in baseline**; no new failures. Historical PowerShell CLI failure did not reproduce and was not changed/skipped.
- **Ruff:** `& C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m ruff check .`: **All checks passed**. `git diff --check`: clean.
- **Installed verification:** used the fresh isolated Python 3.11 environment created for this review-fix session, `C:/Users/LOQ/TradingAgents-proposals/review-fixes-smoke-20261013`. After its standalone batch-4 base install passed, updated it from this worktree with its own Python `-m pip install --force-reinstall --no-deps .`. No project venv/editable mapping was changed. Repository-root CI import command with this fresh Python, `-c "import tradingagents, cli.main, investment_engine; print('clean-install import OK')"`: passed. From outside repo, the same Python `-I C:/Users/LOQ/TradingAgents-proposals/daily-cli-installed-smoke.py base` and `-I C:/Users/LOQ/TradingAgents-proposals/review-fixes-installed-cutoff-smoke.py`: both passed, with neither pyarrow nor duckdb present.
- **Engine-extra smoke:** from this worktree the same isolated Python `-m pip install ".[engine]"`: passed. From outside repo, `-I C:/Users/LOQ/TradingAgents-proposals/daily-cli-installed-smoke.py engine` and `-I C:/Users/LOQ/TradingAgents-proposals/review-fixes-installed-cutoff-smoke.py --with-engine`: passed. Installed code loads the seed, preserves synthetic correction timing, blocks H1 and rejects invalid cutoff lineage. These scripts are local artifacts outside the repository; no market fetch occurred.
- **Not run:** CI, other Python versions, live provider calls, authenticated/hourly gates, keys or market-data downloads. No merge, push or branch deletion. `.env` and `.claude/` excluded. Main remains `0661d46`, **12/18 M1 tasks done**. The new code is checked, not yet independently accepted.

**Next:** Copilot reviews the new dependency fix and label follow-up plus M2's documentation clarification. Original R-06 acceptance remains valid for `db826f2` only; it does not approve these subsequent changes or any merge. Full hourly work and M1 completion remain blocked.

### 2026-10-13: Codex (M1-17 daily CLI delivery; independent Copilot review pending)

- **Owner scope:** the owner instructed Codex to work on the next task while Copilot reviews. Codex stated in commentary that it was taking this as authorization for the already prepared daily-only delivery. The scheduling exception uses committed/checked 3a and 4 dependencies in branch ancestry, not an unrecorded merge or a passed independent review. Scope documentation is a separate commit, `6c5e35e`. Allowed runtime paths are exactly those in M1-17; roadmap/README edits document the delivery split. Root workflow setup changes were preserved in the other worktree.
- **Location:** `C:/Users/LOQ/TradingAgents-daily-cli`, branch `m1/M1-17-daily`, base `cc62dbf`. Main remains `0661d46`; every pre-existing branch/worktree is preserved. M1 remains **12/18 done**: M1-17's daily part is checked, not done or merged.
- **Implemented:** Typer/Rich `python -m investment_engine` commands; idempotent `init` with a packaged, primary-source-cited NVDA seed; offline provider-specific D1 replay report with exact Decimal OHLCV, ET/UTC, availability/provenance and observation/replay times; correction comparisons with the previous stored revision; corporate actions; separately labelled stored-visible-at DataHealth. Empty, missing, stale/degraded and inactive cases stay honest. Trading status is explicitly unverified and autonomy unconfigured. H1 health/comparison are unavailable; H1 reports fail before storage reads. `import-yfinance --daily-only` wires the verified action/D1 importers; default full import exits nonzero after reporting H1 blocked, without making any H1 fetch.
- **Packaging:** only the permitted `investment_engine` package-data list changed, adding `reference/*.json`. No dependencies, CI, `tradingagents/`, upstream `cli/`, architecture, diagrams or existing tests changed.
- **Tests first:** the initial 22 CLI cases produced 21 missing-CLI import errors and one missing-module-entry failure before implementation. Additional offline/adversarial checks cover real importers using existing recordings, no database creation by report, seed conflicts and revision currency changes. The currency regression failed before its renderer fix: old USD values had incorrectly inherited the new EUR label. The renderer now retains each revision's units and reports prior bases. Test-fixture authoring mistakes (filename and column list) were corrected; they were not application regressions or changes to existing tests.
- **Self-review:** checked replay cutoffs/latency, correction-only windows, provider isolation, read-only file hashes, seed idempotence/conflicts, nullable action fields, honest basis/precision labels, packaged resources and optional-engine errors. This is implementer self-review, **not** independent acceptance. Corporate-action BACKFILL labels refer to actual displayed availability, without inventing the original publication time. Code does not read the system clock directly.

**Observed checks on the final runtime code** (root project Python is used deliberately in this separate worktree; its editable install was not changed):

- Git Bash, cwd `C:/Users/LOQ/TradingAgents-daily-cli`: `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q tests/engine/test_cli.py tests/engine/test_layering.py tests/engine/test_clock.py`: **48 passed**, including **26 new CLI cases**.
- Git Bash, same cwd: `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q`: **2027 passed, 1 failed, 4 skipped, 3 deselected**, 99 subtests passed. Output: `C:/Users/LOQ/TradingAgents-proposals/daily-cli-final-bash.txt`.
- PowerShell, same cwd: `& C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q`: **2027 passed, 1 failed, 4 skipped, 3 deselected**, 99 subtests passed. Output: `C:/Users/LOQ/TradingAgents-proposals/daily-cli-final-powershell.txt`.
- **Only failure in both shells:** `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in baseline**. No new failures. The other historical PowerShell baseline failure, `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module`, did not reproduce; it was not modified or skipped. Earlier full runs before the added currency regression had 2026 passed with the same single baseline failure.
- PowerShell: `& C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m ruff check .`: **All checks passed**. `git diff --check`: clean. No repository-wide formatting.
- **Fresh base install:** `py -3.11 -m venv C:/Users/LOQ/TradingAgents-proposals/daily-cli-smoke-20261013`; from the task worktree, `& C:/Users/LOQ/TradingAgents-proposals/daily-cli-smoke-20261013/Scripts/python.exe -m pip install .`: passed. After the final renderer fix, `.../Scripts/python.exe -m pip install --force-reinstall --no-deps .`: passed. Same fresh Python from repository root: `-c "import tradingagents, cli.main, investment_engine; print('clean-install import OK')"`: passed.
- **Outside-repository base smoke:** cwd `C:/Users/LOQ/TradingAgents-proposals`, `& C:/Users/LOQ/TradingAgents-proposals/daily-cli-smoke-20261013/Scripts/python.exe -I C:/Users/LOQ/TradingAgents-proposals/daily-cli-installed-smoke.py base`: passed. Checks installed site-packages, module help, two init calls and friendly missing-engine report failure. Neither pyarrow nor duckdb was installed in the base environment.
- **Fresh engine smoke:** from the task worktree, the same fresh Python `-m pip install ".[engine]"`: passed. From outside the repository, the same Python `-I C:/Users/LOQ/TradingAgents-proposals/daily-cli-installed-smoke.py engine`: passed. Installed code writes synthetic original/correction observations, shows correction only after arrival, loads the packaged seed, and refuses H1. Fresh installed versions: yfinance **1.7.0**, pyarrow **26.0.0**, duckdb **1.5.6**. The smoke script is a local verification artifact outside the repository.
- **Not run:** CI, other Python versions, live imports, authenticated requests, keys, market-data downloads or hourly protocol gates. No market data was downloaded; saved fixtures and synthetic observations only. No merge/push. `.env` and `.claude/` are excluded from all staged paths.

**Next:** independent Copilot review of these two exact commits, plus completion of its batch-4 review. The hourly/full portion retains every original acceptance requirement and still waits for 3b. No M2 code or M1-complete declaration is authorized.

### 2026-10-13: Codex - continued under owner-authorized self-review

The owner said to review on our own and continue rather than wait for Claude. Reviewed `6618c47` and `e43b309` against their task contracts and the combined branch. This is **self-review**, never described as independent approval. The instruction doesn't merge anything, waive missing hourly evidence, accept OPEN-08/09 assumptions or authorize keys/downloads.

**Implemented M1-16 follow-up:**
- A health query on 2019-01-01 (covered, but a holiday with no earlier covered session) previously raised CalendarRangeError. T's date is now validated outside the range-exhaustion handler; looking backwards past coverage returns an empty lookback, giving honest MISSING when no bars exist. Truly uncovered dates still raise.
- `lookback_sessions=True` previously became 1 because bool subclasses int, silently reducing the checked history. Booleans are now refused, consistent with the existing explicit-integer threshold rule.
- Three regression cases written first all failed on `e43b309`; all now pass. Only the task's allowed module/test/spec and this log changed.

**Exact final commands/results:**
- `.venv/Scripts/python.exe -m pytest -q tests/engine/test_data_health.py -k 'boolean_cannot or first_covered_holiday'`: 3 intentional new regression cases failed before implementation.
- `.venv/Scripts/python.exe -m pytest -q tests/engine/test_replay.py tests/engine/test_resample.py tests/engine/test_data_health.py tests/engine/test_no_system_clock.py`: **139 passed**.
- `.venv/Scripts/python.exe -m ruff check .`: passed.
- `& 'C:/Program Files/Git/bin/bash.exe' -lc '.venv/Scripts/python.exe -m pytest -q'`: **2001 passed, 1 failed**, 4 skipped, 3 deselected, 99 subtests passed.
- `& .venv/Scripts/python.exe -m pytest -q` (PowerShell): **2001 passed, 1 failed**, same skips/deselection/subtests.
- Both suites' sole failure: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in baseline**. The PowerShell CLI baseline failure did not reproduce; no new passing-baseline test failed.
- `git diff --check` and `git diff --cached --check`: clean.

**Fresh installed B2:** `py -3.11 -m venv <scratch>`; `<scratch>/Scripts/python.exe -m pip install '.[engine]'`, where scratch is `C:/Users/LOQ/AppData/Local/Temp/codex-health-review-b7833549af5947708a356aa2d6336bb0`; passed (install log retained there). Repository-root `<scratch>/Scripts/python.exe -c "import tradingagents, cli.main, investment_engine; print('review clean-install import OK')"` passed. From scratch, `& ./Scripts/python.exe -I 'C:/Users/LOQ/AppData/Local/Temp/codex-batch4-smoke-3dda18c4eff646308845dd5a578dbf0a/batch4_smoke.py'` passed. A subsequent isolated installed-copy check asserted `_lookback(calendar, datetime(2019,1,1,15,tzinfo=UTC),20) == []` and `HealthThresholds(lookback_sessions=True)` raises ValueError; passed. No dependencies or packaging changed.

**Additional progress:** re-read all 13 M2 specs and corrected draft key/ABSTAIN/baseline consistency on the separate branch (`6df10da`); no M2 runtime. Investigated public Alpaca/exchange terms and prepared a source-linked A4 assessment on separate `docs/hourly-access-review` worktree, keeping protocol execution rules unchanged. A4 remains unresolved; no secret or data access. Prepared a concrete, **unapplied** daily-first M1-17 split in `C:/Users/LOQ/TradingAgents-proposals/daily-cli-unblock.md` and `.patch`; `git apply --check C:/Users/LOQ/TradingAgents-proposals/daily-cli-unblock.patch` passed. It preserves full hourly acceptance cases and the M1 completion gate. Its scope decision is necessary because the existing roadmap explicitly schedules batch 5 only after 3b and 4, independent of who reviews.

**Next:** owner decides the daily-first split or resolves A4's account/publication permissions. On daily-first authorization, apply the prepared scheduling/spec patch, implement the whole partial task with tests first and all checks, then self-review. Don't stop after each already-authorized substep. No merge/push, branch deletion, M2 code, keys or market downloads occurred. Main stays `0661d46`, M1 done count 12/18. CI/live checks/other-Python matrix not run.


### 2026-10-13: Codex - final batch 4 checks and combined M2 handoff

**Completed the approved uninterrupted work package.** Claude had already committed the protocol (`f03ea74`), correct scheduling (`5984997`) and the three batch 4 tasks before its limit. Codex reviewed those actual changes, fixed remaining input-validation gaps in `6618c47`, and finished M2-00 – M2-12 plus the pack index on the separate `docs/m2-specs` worktree, committed as **`bb86480`** (documentation only, independent review pending). **Main is still `0661d46`; nothing merged or pushed; no keys or market-data downloads.**

**Self-review correction to Codex's own `6618c47`:** requiring identical field-basis labels in `compare_daily` was too strict. All permitted Candle bases describe raw as-traded values; daily volume may need split reconstruction while hourly volume is already raw. They remain comparable. The final follow-up removes only that comparison restriction, keeps currency/identity/session/cutoff checks, and retains the original single-basis requirement within each hourly aggregation. Two regression cases (price/volume provenance) failed on `6618c47`, then passed after the fix. No earlier acceptance test was weakened.

**Final exact checks, after that correction:**

| Command | Observed result |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q tests/engine/test_resample.py -k reconstruction_provenance` before correction | 2 intentional new regression cases failed, reproducing Codex's overly strict check |
| `.venv/Scripts/python.exe -m pytest -q tests/engine/test_replay.py tests/engine/test_resample.py tests/engine/test_data_health.py tests/engine/test_no_system_clock.py` | **136 passed** |
| `.venv/Scripts/python.exe -m ruff check .` | All checks passed |
| `& 'C:/Program Files/Git/bin/bash.exe' -lc '.venv/Scripts/python.exe -m pytest -q'` | **1998 passed, 1 failed**, 4 skipped, 3 deselected, 99 subtests passed |
| `& .venv/Scripts/python.exe -m pytest -q` (PowerShell) | **1998 passed, 1 failed**, 4 skipped, 3 deselected, 99 subtests passed |
| `git diff --check`; `git diff --cached --check` | Clean |

Both full suites' only failure is **`tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`**, recorded in the M1-00 baseline. The PowerShell CLI baseline failure did not reproduce. **No new passing-baseline test failed.**

**Final B2, fresh venv:** `C:/Users/LOQ/AppData/Local/Temp/codex-batch4-final-ad691f646f7940efafae889b66bd7290` (`<final-scratch>`). `py -3.11 -m venv <final-scratch>`; `<final-scratch>/Scripts/python.exe -m pip install '.[engine]'` passed (install output retained in `<final-scratch>/install.log`). From repository root, `<final-scratch>/Scripts/python.exe -c "import tradingagents, cli.main, investment_engine; print('final clean-install import OK')"` passed. From `<final-scratch>`, `& ./Scripts/python.exe -I 'C:/Users/LOQ/AppData/Local/Temp/codex-batch4-smoke-3dda18c4eff646308845dd5a578dbf0a/batch4_smoke.py'` passed: installed synthetic replay [1, 2], OHLCV resampling/comparison, OK health and unchanged store hashes. The earlier base-only fresh install proved the new modules import without optional engines. No dependency, packaging or CI file changed.

**Review handoff:**

- Claude's batch 4 commits, reviewed by Codex: `5984997..b394fbb` (`e8d4eab`, `3cb6344`, `4a98c3b`, `cacf899`, `b394fbb`). Codex's original findings are fixed; no additional blocking finding remains in that reviewed code. The M1-14 log omission remains a recorded, repaired process deviation.
- **Claude/owner independently reviews Codex's code:** `b394fbb..m1/batch-4`, including `6618c47` and this final correction/check commit. Codex self-review isn't independent approval.
- **Claude/owner independently reviews M2 drafts:** `5984997..bb86480`, all 13 specs plus roadmap/README/handoff. Keep OPEN-08/09 provisional and M2 runtime blocked. Proposed A/B and C/D combined runs support longer work sessions once accepted and approved; task checks/commits, milestone dependencies and review/merge gates still apply.
- Only local commits were authorized here. The next merge, push, authenticated hourly gate or M2 implementation needs its own owner instruction. Batch 5 (M1-17) waits for **3b and 4**. M1 remains **12/18 done**; checked/unmerged work isn't counted done.

**Prompt when Claude returns:**
> Read CLAUDE.md and PROGRESS.md in both existing worktrees. Codex continued the approved package while you were unavailable. Independently review every Codex commit in `b394fbb..m1/batch-4`, then `5984997..bb86480` on `docs/m2-specs`, against the task specs, laws and data-honesty rules. Report blocking findings with file:line, failure scenario and fix separately from suggestions. The final task/clock checks were 136 passed; both full suites had 1998 passes and only the recorded cache-location failure; fresh installs passed. Resume implementation lead after this independent review; Codex resumes reviewing your later changes. Keep hourly blocked and OPEN-08/09 provisional. Do not merge, push, use keys, download market data or implement M2 without the owner's next explicit instruction.

**Not run:** CI, other-Python matrix, live/provider checks or M2 runtime tests. Frozen architecture/SVG, TradingAgents/CLI, dependencies and CI were preserved. AGENTS.md/CLAUDE.md shared rules still match; neither `.env` nor `.claude/` is tracked or staged by this work.


### 2026-10-13: Codex takeover - batch 4 review and regression fixes

The owner authorized the whole batch 4, local follow-up commits, all checks and M2 drafting on a separate branch while Claude's weekly limit is exhausted. **No merge, push, M2 implementation, key use or market-data download.** Actual checkout already contained Claude's finished task commits: `e8d4eab` / `3cb6344` (M1-14 and its missing-log follow-up), `4a98c3b` (M1-15), `cacf899` (M1-16), `b394fbb` (Claude self-review fixes). Protocol/scheduling were already committed as `f03ea74` and `5984997`; the latter correctly makes batch 5 wait for **3b and 4**. Nothing was repeated or rebased.

**Review:** inspected each commit's changed files and task contracts, then the combined replay/resampling/health code and acceptance tests. All changed paths remain inside the tasks' allowed files; architecture, upstream runtime, dependencies and CI are unchanged. M1-14's missing PROGRESS entry is an explicitly recorded process deviation repaired by `3cb6344`, without rewriting history.

**Codex implemented these follow-up fixes (independent review still needed):**

- `resample.py`: reject a reader row for another requested instrument/provider/timeframe; compare only resampled inputs of the requested identity; reject duplicate sessions and incompatible vendor identity, currency, field bases or session boundaries before making numeric comparisons. A caller could previously pass MSFT's resampled bars to an NVDA comparison and receive apparently valid numbers.
- `data_health.py`: validate the requested identity and exact completed calendar start/end pair, CLOSED state and availability. A stored daily candle ending one minute before the expected close could previously be reported OK with the default tolerance. Invalid input now raises rather than inventing a health status. No Candle/store contract was changed.
- Added **11 regression cases** in the two task test files. The new cases all failed on Claude's original code before the fix, with `DID NOT RAISE`; intentional tests-first failures, not regressions in an existing passing test. Original 123 task/clock checks passed before modification; 134 pass after it.

**Exact check commands and observed results (code unchanged between checks):**

| Check | Command | Result |
|---|---|---|
| Original task/clock checks | `.venv/Scripts/python.exe -m pytest -q tests/engine/test_replay.py tests/engine/test_resample.py tests/engine/test_data_health.py tests/engine/test_no_system_clock.py` | 123 passed before fixes |
| Regression reproduction | `.venv/Scripts/python.exe -m pytest -q tests/engine/test_resample.py tests/engine/test_data_health.py -k 'another_instrument or cannot_be_compared or duplicate_resampled or wrong_session_end or another_identity'` | 11 expected new regression-test failures before implementation |
| Fixed task/clock checks | `.venv/Scripts/python.exe -m pytest -q tests/engine/test_replay.py tests/engine/test_resample.py tests/engine/test_data_health.py tests/engine/test_no_system_clock.py` | **134 passed** |
| Full Git Bash suite | `& 'C:/Program Files/Git/bin/bash.exe' -lc '.venv/Scripts/python.exe -m pytest -q'` (launched from PowerShell at repository root) | **1996 passed, 1 failed**, 4 skipped, 3 deselected, 99 subtests passed |
| Full PowerShell suite | `& .venv/Scripts/python.exe -m pytest -q` | **1996 passed, 1 failed**, 4 skipped, 3 deselected, 99 subtests passed |
| Ruff | `.venv/Scripts/python.exe -m ruff check .` | All checks passed |
| Whitespace | `git diff --check` | Clean |

**Only failure in both suites:** `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, recorded in the M1-00 baseline. The other PowerShell baseline failure, `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module`, **did not reproduce in this run**. No new passing-baseline test failed. An initial tool attempt to select Git Bash through its shell argument did not start pytest (`.venv` not recognized); the explicit Git Bash invocation above then ran successfully.

**Batch B2 fresh installation:** scratch venv `C:/Users/LOQ/AppData/Local/Temp/codex-batch4-smoke-3dda18c4eff646308845dd5a578dbf0a` (abbreviated `<scratch>` below). Commands:

1. `py -3.11 -m venv <scratch>`; `<scratch>/Scripts/python.exe -m pip install .` - passed. Package downloads occurred; **no market data or authenticated API requests** occurred.
2. From repository root: `<scratch>/Scripts/python.exe -c "import tradingagents, cli.main, investment_engine; print('clean-install import OK')"` - passed.
3. `<scratch>/Scripts/python.exe -I -c "import importlib.util, sys; from investment_engine.market import replay, resample, data_health; from investment_engine.market.calendar.us_equities import load_us_equities_calendar; assert importlib.util.find_spec('pyarrow') is None; assert importlib.util.find_spec('duckdb') is None; assert 'pyarrow' not in sys.modules and 'duckdb' not in sys.modules; assert 'site-packages' in replay.__file__; assert len(load_us_equities_calendar().sessions_between(__import__('datetime').date(2024,1,1),__import__('datetime').date(2024,12,31))) == 252; print('installed batch 4 base modules OK; optional engines absent')"` - passed; isolated interpreter imports the installed copy.
4. `<scratch>/Scripts/python.exe -m pip install '.[engine]'` - passed; installed pyarrow 26.0.0 / DuckDB 1.5.6 without dev extras.
5. From `<scratch>`: `& ./Scripts/python.exe -I ./batch4_smoke.py` - passed. The scratch script writes synthetic hourly/daily bars and a correction, replays revisions [1, 2], resamples/compares daily OHLCV, evaluates OK health, verifies installed module paths and unchanged store hashes at `market[x]`. Script stays outside the repository.

**Not run:** CI, Python 3.12-3.14 matrix, live Yahoo/Alpaca checks, authenticated protocol gates, M2 runtime tests (no M2 code). The previously accepted v0.3.10 offline runner was not re-run this session. Hourly remains BLOCKED; M1 done count remains **12/18** until later owner-approved merges. Codex's self-review is not independent approval of Codex's own fixes.


### 2026-10-13: Claude Code (batch 4: self-review fixes)
I self-reviewed M1-14 – M1-16 against their specs and the laws, with adversarial probes (scratch script, outside the repository). **Two gaps** were found, on paths the spec tests don't reach:
1. **Replay trusted the reader's identity.** A reader returning another provider's revision for a `yfinance` request was passed straight through as a `testvendor` event, and the same held for another instrument or timeframe. **Fix:** every payload must match the requested provider, instrument and timeframe, or replay raises. Providers never mix even with a misbehaving reader.
2. **DataHealth outside the calendar's coverage** (e.g. 2030, or 2018) reported `MISSING` over "0 sessions". **Fix:** a time outside the coverage raises `CalendarRangeError`, because the expected bars can't be established, so no status is reported. Inside the coverage, a lookback shortened where the coverage begins is still evaluated.

**Tests (written first; 5 failed before the fix):** `test_a_revision_for_another_identity_than_requested_is_refused` (provider, instrument, timeframe) and `test_a_time_outside_the_calendars_coverage_raises_instead_of_reporting` (after, before).

**Probed and found sound:**
- reader order;
- latency at the window edges;
- forming and half-day sessions;
- the cutoff on direct inputs;
- `compare_daily` with no closed bars;
- duplicate stored revisions (refused).

**Checks:**
- the replay and DataHealth tests → 49 passed;
- `.venv/Scripts/python.exe -m pytest -q` (Git Bash) → **1985 passed, 1 failed** (the same baseline failure), 4 skipped, 3 deselected;
- `ruff check .` → All checks passed.

### 2026-10-13: Claude Code (batch 4: M1-16 DataHealth, committed and checked)
**M1-16** (`investment_engine/market/data_health.py`, `tests/engine/test_data_health.py`):
- `evaluate_health` reports per provider and timeframe, at T = the injected clock's time, using **only** OK, STALE, MISSING and DEGRADED.
- **Applicability** is a separate field. An inactive instrument gives no source statuses, with `required_sources_ok = False` and a reason ("not active before …" or "not active on or after …").
- **MISSING:** no symbol mapping at T (detail "no symbol mapping for <provider> on <date>"), or no bar visible in the lookback.
- **STALE:** expected bars behind > the timeframe's threshold. Expected bars come from the calendar, so nights, weekends and holidays never count.
- **DEGRADED:** holes up to the latest visible bar.
- Reads use `candles_visible_at(T)` per provider only. Nothing is persisted.
- The spec's implicit choices are recorded in M1-16 ("batch 4"): behind against missing; the lookback bounded by the calendar; the input checks.

**Tests (written first):** 17, covering every acceptance case in the spec:
- OK; one bar behind still OK; STALE with `bars_behind`, and a relaxed threshold;
- a weekend and a holiday not counted;
- DEGRADED listing the removed session;
- MISSING with no bars, and with no mapping;
- hourly bars, counting ended hours;
- inactive and delisted instruments, which aren't applicable;
- **every path reaching exactly the four statuses** (`detail` empty iff OK);
- two providers, independent, and `testvendor` never filling a `yfinance` gap;
- a bar first observed after T, and a correction after T, both unused;
- the injected clock; the required-set and threshold checks.

**Corrected in my own tests before the first green run:** a series starting 3 June would rightly show May as holes under a 20-session lookback, so the series now starts 1 May; the hourly test uses a 2-session lookback; and one expected count (9 sessions behind on 30 June, not 6).

**Checks:**
- `.venv/Scripts/python.exe -m pytest -q tests/engine/test_data_health.py` → 17 passed.
- `tests/engine/test_no_system_clock.py` and `test_layering.py` → 53 passed (the clock scan covers the new modules).
- `.venv/Scripts/python.exe -m pytest -q` (Git Bash) → **1980 passed, 1 failed** (the same baseline failure), 4 skipped, 3 deselected.
- `ruff check .` → All checks passed.

### 2026-10-13: Claude Code (batch 4: M1-15 resampler, committed and checked)
**M1-15** (`investment_engine/market/resample.py`, `tests/engine/test_resample.py`):
- `resample_daily` reads one provider's H1 bars with `candles_visible_at(at)`, groups them into calendar sessions, and returns a `ResampledBar` (CLOSED or FORMING) or a `SessionGap` per session.
- `aggregate_session` is pure, and it validates (it raises on any of these):
  - a bar ending after `at`, or unavailable at `at`;
  - mixed provider, instrument, currency or basis;
  - a duplicate start, an off-grid bar, or a non-H1 or FORMING input.
- **Aggregation** is in Decimal (first open, max high, min low, last close, summed volume). Every input is a complete `InputRef`, and the availability basis is BACKFILL_ASSUMED if any input is.
- `compare_daily` reads the same provider's D1 bars at the same cutoff and reports field differences, `missing_vendor` and `missing_resampled`.
- The spec's implicit edge cases are resolved conservatively and recorded in M1-15 ("batch 4"): a forming day needs every ended hour; no output before the open; gaps for empty sessions; the grid check; and the optional session range for `compare_daily`.

**Tests (written first):** 26, covering every acceptance case in the spec:
- a full regular day field by field, the half-day grid, and a full half-day;
- the missing middle hour (a gap);
- FORMING built only from ended bars, and a forming day with an earlier hour missing (a gap);
- the cutoff: a bar ending after `at` raises; an unavailable input raises; the correction is revision 1 before its availability and revision 2 after;
- mixed providers raise, and five kinds of inconsistent input;
- duplicates and off-grid bars;
- `compare_daily` per provider, identical, a different close, missing on either side, a vendor bar not yet available, FORMING not compared, and the same-cutoff rule;
- complete lineage.

My first run had two failures, neither in the logic: the cutoff check order (fixed, and recorded) and an invalid test bar (close above high, which the Candle contract rejects).

**Checks:**
- `.venv/Scripts/python.exe -m pytest -q tests/engine/test_resample.py` → 26 passed.
- `.venv/Scripts/python.exe -m pytest -q` (Git Bash) → **1963 passed, 1 failed** (the same baseline failure), 4 skipped, 3 deselected.
- `ruff check .` → All checks passed, after one simplification ruff suggested (`list(...)`).

### 2026-10-13: Claude Code (batch 4: M1-14 replay feed, committed `e8d4eab` and checked)
`m1/batch-4` was created from the scheduling commit `5984997`. The M2 spec drafts are in a separate worktree, `C:\Users\LOQ\TradingAgents-m2-specs`, on `docs/m2-specs`.

**M1-14** (`investment_engine/market/replay.py`, `tests/engine/test_replay.py`):
- `ReplayFeed` delivers each stored revision as exactly one `ReplayEvent`: revision 1 is `BAR_CLOSED`, a later revision is `CANDLE_REVISED`, and any action revision is `CORPORATE_ACTION`.
- **Times:** `event_time = available_from`; `received_at = processed_at = event_time + latency`.
- **Window:** delivered iff `start <= received_at < end`. Candidates are read per provider with `*_revisions_available_between(…, start - latency, end - latency)`.
- **Order:** spec rule 6's identity key, so it doesn't depend on reader order. A repeated stored revision raises.
- **Clock:** advanced to each `received_at` and never backwards.
- **Rejected:** a FORMING bar raises. Negative latency, an empty or backwards window, naive times, and duplicate or empty sources, instruments or timeframes are refused.
- Replay never writes.

**Tests (written first):** 27, covering every acceptance case in the spec:
- the four Friday-correction windows;
- the latency leak (`BAR_CLOSED` at E + 5 s carrying revision 1, `CANDLE_REVISED` at E + 8 s);
- late first observation, and the window edge;
- corporate actions, including actions before bars at equal times;
- two providers;
- the original, reversed and 20 seeded shuffles of reader output;
- determinism, the clock, invalid arguments, FORMING, an unchanged store (hashes), labels, and the timeframe order.

Two of my test set-ups first wrote a correction "received" before its original, which the writer correctly refuses; they were fixed.

**Checks (before `e8d4eab`):**
- `.venv/Scripts/python.exe -m pytest -q tests/engine/test_replay.py` → 27 passed.
- `.venv/Scripts/python.exe -m pytest -q` (Git Bash) → **1937 passed, 1 failed** (`tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in the baseline**), 4 skipped, 3 deselected.
- `ruff check .` → All checks passed. Ruff first flagged import order in the new test file; it was sorted, then rechecked.

**Process deviation, recorded:** this entry and M1-14's spec status line were meant to be in `e8d4eab`. A shell script failed, and the commit went ahead without them. They follow in a separate docs commit; the history wasn't rewritten.

### 2026-10-13: Claude Code (scheduling change applied: batches 3a, 3b, 4, 5; owner-approved)
**Codex's review of v0.3.10:** the protocol and the offline runner pass (94 tests, ruff, 13 hashes; the 200 requests-per-minute figure matches Alpaca's published Basic-plan limit). Codex made **one scheduling correction**: batch 5 (M1-17) must depend on **3b and 4**, because M1-17 needs M1-12 and M1-13, which are done only when 3b merges.

**The owner approved** (2026-10-13):
- locally committing the v0.3.10 documents: `f03ea74`;
- applying the corrected scheduling change as a separate commit: **this commit**;
- **batch 4** as one uninterrupted package;
- M2 specification drafts on a separate branch, with OPEN-06 option A as the proposed baseline and OPEN-09 provisional.

Not authorized: merges, pushes, M2 implementation, key use or market-data downloads.

**Applied** (the reviewed patch, plus Codex's correction):
- `docs/roadmap.md` §4.3: rows 3a, 3b, 4 and 5, where batch 5 needs **3b and 4**, and a dated decision note;
- `docs/tasks/README.md`: a split task is done when its last batch merges;
- `docs/data-provenance/yfinance.md`: "batch 3" becomes "batch 3b".

**Codex's notes for M2, carried into the spec drafts:**
- Option A strategies are starting baselines, not proven profitable.
- OPEN-09 costs, the 5-day horizon and the walk-forward windows are **draft assumptions**. The specs must define entry and exit rules, overlapping signals, warm-up data, and the **removal of training examples whose 5-day outcome crosses into the test period**.
- The promotion thresholds (Sharpe 0.5, 30 trades, 60% of windows, 3 months of shadow) are **provisional**, not established as sufficient. **Passing never enables trading automatically.**
- Strategy and benchmark returns are compared on the same basis: dividends and costs treated consistently.

### 2026-10-13: Claude Code (snapshot check after Codex's review; no changes)
Codex's latest review describes the **v0.3.9** snapshot: 79 tests, `E` in the tape-C profile, no time estimate in checkpoint R, and the stale runner sentence. All three items are already fixed in **v0.3.10** (entry below). Re-verified 2026-10-13 on the current files:
- `MANIFEST.sha256` SHA-256 `2ad88c803a63c241c8fb16d452d6559b60d4491aad8772af9690c0a1c360a343`; `sha256sum -c` gives 13 OK;
- **94 passed**; ruff: All checks passed!;
- no `E` entry in `ALPACA_MINUTE_TAPE_C`, and other tapes are unmapped;
- `resource_estimate` has `REQUESTS_PER_MINUTE = 200`, `estimated_minimum_minutes`, and "estimates, not bounds" (no `upper_bound` keys);
- the stale sentence is absent from M1-12;
- the roadmap patch (SHA-256 `c6747e66…a8047d`) still passes `git apply --check`.

**Review this snapshot: v0.3.10, manifest `2ad88c80…`.** No files changed in this check.

### 2026-10-13: Claude Code (protocol v0.3.10 package: Codex's v0.3.9 review, roadmap patch, work package, OPEN-06/09 proposals; uncommitted)
Codex reviewed v0.3.9 and independently confirmed:
- 79 tests passed and ruff passed;
- empty and malformed responses are rejected;
- partial results can't establish verification;
- auction volume respects combined restrictions;
- the runner connects the checks.

**One fix and two cleanups remained.** The owner approved one offline finishing run. Limits: no keys, market-data downloads, commits, merges, pushes, or starting the proposed batches.

**Fixes:**
1. **Checkpoint R** (`hv/run.py`, `resource_estimate`):
   - It now states the **request-rate assumption**: Alpaca's Basic plan, 200 historical calls per minute ("About Market Data API", retrieved 2026-10-12).
   - It gives the **estimated minimum time**: requests ÷ 200, rounded up; retries, latency and processing add to it.
   - Sizes are labelled **"projected from calibration date …; estimates, not bounds"**, and the "upper bound" keys are gone.
   - **Test:** `test_checkpoint_r_states_the_rate_assumption_and_minimum_time`.
2. **Stale sentence** about an unfinished entry point: removed from M1-12.
3. **A3's public part, with tape applicability.** I read Alpaca's aggregation table row by row with its tape column (through a fetch of the page's coloured markers, not a byte-exact copy). NVDA is tape C.
   - Both profiles are now **tape-C tables**: the vendor profile is exactly the minute rows whose tape includes C.
   - **Unmapped on tape C:**
     - **E** (tapes A/B only, Codex's example);
     - the **blank** regular-sale code (A/B only);
     - S, 1, 2, 3 and 8;
     - a trade with **no** codes;
     - **any other tape**.
   - Alpaca's daily rows agree with the UTP matrix on G, P, Z, 4, 9 and T.
   - **Tests:** the vendor table equals the documented rows code by code; the daily rows agree; unmapped codes and tapes; and a trade on another tape can't build a bar.
   - **Still pending at A3:** Alpaca's tape-C condition endpoint (needs keys, after A4).

**Exact commands and results** (Git Bash, in `C:\Users\LOQ\hourly-verification`, frozen snapshot):
- `sha256sum -c MANIFEST.sha256`: 13 files OK. `MANIFEST.sha256` itself: `2ad88c803a63c241c8fb16d452d6559b60d4491aad8772af9690c0a1c360a343`.
- `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests`: **94 passed**.
- `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m ruff check --no-cache .`: **All checks passed!**

Repository: only `docs/tasks/M1-12.md` (v0.3.10) and `PROGRESS.md` changed, uncommitted; `git diff --check` clean. Repository tests weren't run (no repository code changed). No keys, no market data, CI not run.

**1. Roadmap patch (prepared, not applied).**
- **File:** `C:\Users\LOQ\TradingAgents-proposals\roadmap-batch-split.patch`, outside the repository, SHA-256 `c6747e6645496295b4a20d4d596d25a1a5952d5b3a68abdc13ed744207a8047d`.
- **Check:** `git apply --check -p1` against the current tree passes (exit 0); nothing was applied.
- **Changes:**
  - `docs/roadmap.md` §4.3: rows 3 and 4 become **3a** (daily, reviewed; hourly fields BLOCKED), **3b** (the hourly protocol run, unblocking and the hourly import; M1-12/M1-13 done only when 3b merges), **4** (M1-14 – M1-16; needs batches 1 and 2 only) and **5** (M1-17; needs 3a and 4, and 3b for the hourly section). A note records the owner's decision (date to fill in) and that only the grouping changed, not task dependencies.
  - `docs/tasks/README.md`: "a task split across two batches is done only when its last batch merges".
  - `docs/data-provenance/yfinance.md`: "batch 3" becomes "batch 3b".
- **Unchanged:** the dependency phases, §4.5 (M1 completion) and the architecture. No ADR is needed.
- **When approved,** it would go in as its own docs commit, before batch 4 starts.

**2. The combined work package (proposed; starts only after the patch is approved and applied).**

| Track | Branch | Order and contents | Est. | Checkpoints |
|---|---|---|---|---|
| **Batch 4 (code)** | `m1/batch-4` from `main` | M1-14 replay → M1-15 resampler → M1-16 DataHealth. Each task: spec re-read, tests first, implementation, task checks (its tests, full suite in Git Bash, ruff), PROGRESS entry, one commit. Then batch checks (PowerShell suite, clean-install smoke), self-review with adversarial probes | 8 – 9 h | Stop rules unchanged; Codex reviews every commit; merge needs approval |
| **M2 spec pack (docs)** | `docs/m2-specs` from `main` | Draft 1 – 3 h task specs: (1) the point-in-time **split-adjusted view** and leakage protections, then (2) versioned features, (3) indicators for the chosen strategies, (4) `FeatureSnapshot`, (5) the rule-strategy interface and first strategies, (6) `MarketView` with Law 9 `ABSTAIN`, (7) `LineageRecord`, (8) the initial evaluation (cost model, next-bar fills), (9) walk-forward, (10) the HTML report; plus roadmap §5's M2 table and batch plan | 4 – 6 h | Codex reviews the specs; **no M2 code until they are accepted and M1's prerequisites hold** |

Run as **one session** (about 12 – 15 h of work). Code and docs live on separate branches with separate commits and reviews. A blocker in one track doesn't stop the other, except a stop rule, which stops the session and is reported.

**3. OPEN-06 and OPEN-09: proposed choices (owner decisions; not evidence-based thresholds).**

*OPEN-06, first rule strategies and required sources:*
- **Option A (recommended):** two daily strategies on NVDA, computed on the point-in-time split-adjusted daily view.
  - **(A1) Trend:** close against the 200-day SMA, with the 50/200 SMA state, gives BULLISH, BEARISH or NEUTRAL. Strength is the normalised distance from the 200-day SMA.
  - **(A2) Pullback within the trend:** RSI(14) ≤ 30 above the 200-day SMA gives BULLISH; RSI ≥ 70 below it gives BEARISH; otherwise NEUTRAL.
  - **Required sources (Law 9):** yfinance **D1** bars (verified daily fields) with DataHealth `OK`, and yfinance **SPLIT** actions (for the adjusted view). Missing either means `ABSTAIN`.
  - Hourly isn't required (it's blocked). Dividends aren't required (price return; total return is labelled separately).
- **Option B:** the trend strategy only. Fastest; the least to evaluate.
- **Option C:** add an hourly strategy. Not possible until 3b resolves.

*OPEN-09, evaluation and promotion thresholds* (starting points to confirm; one instrument only, see OPEN-05):
- **Initial evaluation (M2):**
  - daily bars 2019 – 2026;
  - **next-bar-open fills**;
  - stated costs of **5 bps per side** (commission assumed 0, slippage 5 bps), with a sensitivity run at 10 bps;
  - benchmarks: buy-and-hold NVDA, and cash;
  - metrics: return after costs (total and annualised), Sharpe, Sortino, maximum drawdown, hit rate against the base rate, the information coefficient, trade count, exposure and turnover.
- **Horizon:** views are evaluated over **5 trading days** (swing).
- **Walk-forward:** rolling **2-year training and 6-month test windows**, stepped by 6 months; only out-of-sample windows count.
- **Shadow promotion (before M4):** across the out-of-sample windows, after costs:
  - Sharpe ≥ **0.5**;
  - maximum drawdown no worse than buy-and-hold over the same windows;
  - at least **30** trades;
  - a positive result in at least **60%** of windows.

  A stricter alternative: Sharpe ≥ 0.8 and at least 50 trades.
- **Level 1 and Level 2:** set before M4. Proposal: Level 1 after at least **3 months** in shadow with results tracking the backtest within a stated band; Level 2 decided later.

### 2026-10-12: Claude Code (protocol v0.3.9 package: Codex's four findings, complete runner, roadmap proposal; uncommitted)
Codex reviewed the v0.3.7 package. **Its correction:** the historical `u` field is confirmed by Alpaca staff, so that objection is resolved. **Four blocking findings remained.** The owner approved one uninterrupted offline package. Limits: no keys, market-data downloads, purchases, commits, merges, pushes or batch 4; hourly stays blocked.

**Codex's note on snapshots:** the scratch files changed during its review (62 tests at first, then a snapshot with three collection errors). That version isn't approved. This package is **frozen**: `MANIFEST.sha256` in the scripts folder lists all 13 files, and every result below is for that snapshot.

**Findings and fixes:**
1. **The daily check could give a false explanation**: only matching minutes were fetched.
   - v0.3.8 already pulled whole dates. v0.3.9 makes that the only path: `run_protocol` pulls the full trading date for every difference and agreement session, and D-OFFICIAL always uses all of it.
   - **Regression tests:** Codex's case end to end (an eligible trade elsewhere in the date, so "unexplained" and P-H undetermined), plus the unit-level case.
2. **Empty or malformed responses could pass.**
   - Pages must carry the records key, `symbol` equal to the requested one, and object records. A token-only page, a missing or other symbol, or non-object records are malformed: retried, then incomplete.
   - Calibration fails with no trades, or with any regular-session minute lacking a vendor bar.
   - **Tests:** four malformed-page cases, an explicit null list, an empty market, and one missing minute.
3. **The final decision didn't enforce complete coverage.**
   - `p_h_decision` now requires results for **exactly** the expected (session, extreme, bar) identities: 196 for the saved fixtures.
   - **The runner is complete** (`run_protocol`):
     - calibration;
     - checkpoint R as an owner callback;
     - full-date and capture-window pulls;
     - all eight combinations;
     - exact coverage;
     - all 60 agreement bars, each checked, plus the daily extremes;
     - E1 over every pre-split bar in full-date sessions;
     - V-H over all 1004 anchors under both closing-cross hypotheses;
     - the final decisions.
   - Two fitting rules are reported and never chosen.
   - **Tests:** a single result against the expected set; duplicate and unexpected results; and a synthetic two-session market where exactly H-MIN/CC-TS is right and is selected. Separately: checkpoint R declined; access refused mid-run; a paging failure; flag evidence; a missing expected target.
4. **Closing-auction rules.**
   - CC-TS and CC-LAST are separate hypotheses for prices and volume, with the capture boundary `[close, 24:00 New York)` always pulled completely.
   - Closing-cross volume counts only valid prints whose **combined** conditions allow volume under the ALPACA profile.
   - **Tests:** Codex's 500-share case (`6` + `9`, adds nothing), and an `incorrect` print.

**Cited:** Alpaca staff on the historical `u` field. The Alpaca community forum, "Persistent IONQ SIP trade/bar mismatch", reply of 2026-07-16: canceled and incorrect trades "are not included in bar calculations however, they do show up as trades". The protocol's validity rule matches Alpaca's bar rule.

**Self-review fixes, within scope.**
- Volume now uses the vendor's minute bars wherever paging is complete, the same rule for full-date and volume-only sessions, with reconciliation recorded alongside.
- A permission error mid-run stops cleanly.
- The agreement count comes from the target set (60 for the fixtures).
- The protocol states E1's exact bar set, the page validation and the runner's manual pre-conditions (A4, A3).
- One test expectation of mine was wrong: an in-range cancelled trade makes two rules fit, and the runner correctly declines to choose. It's now a test of that behaviour.

**Exact commands and results** (Git Bash, in `C:\Users\LOQ\hourly-verification`, frozen snapshot):
- `sha256sum -c MANIFEST.sha256`: 13 files OK.
- `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests`: **79 passed**.
- `/c/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -m ruff check --no-cache .`: **All checks passed!**

Repository: only `docs/tasks/M1-12.md` (v0.3.9) and `PROGRESS.md` changed, uncommitted; `git diff --check` clean. Repository tests weren't run (no repository code changed). No keys, no market data, CI not run.

**Proposed roadmap change (not applied; it needs the owner's approval and Codex's review).** In `docs/roadmap.md` §4.3, replace the batch 3 and 4 rows with:

| Batch | Tasks | Purpose | Task order inside the batch | Needs merged first | Notes |
|---|---|---|---|---|---|
| **3a** | M1-12 – M1-13, **daily part** | Yahoo daily verification, corporate actions, daily bars | 12, then 13 (done: `0661d46..4f594bf`, accepted by Codex) | Batches 1 and 2 | **Firm checkpoint passed for daily fields.** `H1_PRICE`/`H1_VOLUME` stay BLOCKED in `YAHOO_VERIFICATION`. Merging doesn't complete M1-12 or M1-13. |
| **3b** | M1-12 – M1-13, **hourly part** | Hourly verification protocol run; then, separately, unblocking and the hourly import | Protocol gates A4 → A3 → A1 + A2 → R → full run → evidence review; then the unblocking commit; then the M1-13 hourly path | 3a | **Firm checkpoint.** M1-12 and M1-13 are **done only when 3b merges.** |
| **4** | M1-14 – M1-16 | Replay, resampling, data health | 14, 15, 16 | Batches 1 and 2 (M1-01, M1-05, M1-07 – M1-11) | Doesn't depend on Yahoo verification; can run while 3b waits on evidence |
| **5** | M1-17 | NVDA report | — | 3a and 4; 3b for the hourly section | Package data: smoke check within the task. Until 3b, the report's hourly section shows BLOCKED. **M1 completes only when no field is blocked** (§4.5). |

Also in §4.3:
- Under the table, add: "Batches 3a/3b split the daily and hourly work (owner decision, date). Batch 4 no longer waits for batch 3, because M1-14 – M1-16 don't use M1-12 or M1-13."
- The dependency **phases** table is unchanged; it already places M1-13 – M1-16 in phase G.

Elsewhere:
- `docs/tasks/README.md` (Workflow): add one line, "a task split across two batches is done when its last batch merges".
- `PROGRESS.md`'s task count stays at 12 of 18 until 3b merges.
- No architecture or ADR change; roadmap §4.5 (M1 completion) is unchanged.

### 2026-10-12: Claude Code (protocol v0.3.8 package: Codex's four findings, sources, offline harness, batch proposal; uncommitted)
Codex reviewed v0.3.7: four blocking findings. The owner approved fixing all four and completing the offline preparation package in one run. Limits: no keys, market-data downloads, purchases, commits, merges, pushes or batch 4 work; hourly stays blocked; repository changes only in M1-12.md and PROGRESS.md.

**1. Cancellation handling (finding 1).**
- **Researched:** Alpaca's historical-trades reference documents an optional `u` field (`canceled` / `incorrect` / `corrected`). Alpaca's official Python `Trade` model has no such field, and its real-time feed sends cancellations (`x`) and corrections (`c`) as separate messages. On Alpaca's forum, staff say corrections are applied in end-of-day batches and bars are regenerated for a few days, and that (symbol, date, exchange, trade ID) identifies a historical trade.
- **Protocol:** flag presence is now **A2 evidence** (fields present per trade object; counts of each flag value). **H-UNCANCELLED is untestable** unless the pulled data contains flagged `canceled`/`incorrect` records, and untestable never counts as explained. Even when testable, an explanation needs the specific trade to carry the flag.
- **Harness:** flag counts, fields seen, and an "untestable" outcome. A test shows H-MIN and H-UNCANCELLED are identical without flags.

**2. Separate vendor and official rules (finding 2).**
- **ALPACA profile:** reproduces Alpaca's bars, and defines the H-MIN, H-ODD and H-UNCANCELLED rules. It is cited to Alpaca's FAQ, including its statement that it "simply" uses first-only or always-update in place of the specifications' more complicated rules.
- **UTP profile** (§3.14.2, four versions cited): D-OFFICIAL and H-DAY only.
- **The field-update algorithm is exact:**
  - open/close stay unset if no trade sets them;
  - the "first" reading is fixed per rule ("first trade" in Alpaca's wording, which never arises in minute bars; "no open yet" from the UTP wording, for H-DAY);
  - a bar exists only with every field set and volume > 0;
  - D-OFFICIAL evaluates only high/low and volume.

**3. Closing auction (finding 3).** Reconciliation assigns minutes **by timestamp truncation only**, so a closing-cross print at 16:00:00.2 is in the 16:00 minute. Placement in the last hourly bar is a **separate Yahoo hypothesis (CC-LAST, against CC-TS)**, giving eight rule combinations. Its window is the rest of the trading date, so every same-date report is captured; reports dated later are a recorded limitation.

**4. Full-session coverage (finding 4).** Every session D-OFFICIAL checks is pulled for its **full trading date** (00:00 – 24:00 New York): the 181 difference sessions **and** the agreement-sample sessions. A test shows a more extreme eligible trade elsewhere in the date defeating a local explanation. Volume-only sessions pull from the close to the end of the date, for CC-LAST.

**Completeness, per Codex's note.** Paging integrity (hard failure) and reconciliation (recorded differences) are kept apart:
- any paging failure makes the session's coverage missing;
- any unresolved reconciliation difference makes the session's differences unexplained, and it is resolved only by a reviewed written explanation;
- the limitation is stated: matching summaries don't prove every trade was delivered.

A new checkpoint **R** has the owner approve a resource estimate, extrapolated from A2's per-date pages and bytes, before the full run.

**Harness** (`C:\Users\LOQ\hourly-verification`, outside any repository): **73 passed** offline (`.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests` there), and `ruff check` (default rules) clean.
- **Coverage:**
  - paging, retries, malformed pages and repeated tokens;
  - duplicate conflicts under the (date, exchange, ID) key;
  - update flags present or absent;
  - corrections and cancellations, and missing cancellation evidence;
  - timestamp minutes and closing-cross placement;
  - full-date coverage;
  - paging failures recorded apart from reconciliation differences;
  - calibration failing closed;
  - every classification outcome;
  - the real fixture targets and pull list: 181 + up to 60 sessions.
- **Still manual or unwired:** the agreement-sample comparison, E1 and the volume decision are tested functions, not yet one command. A2's `corrected`-timestamp check is by inspection.

**Self-review fixes, within scope.**
- My earlier design calibrated a "first" reading that minute bars can't reveal (Alpaca's minute column has no first-only codes). The reading is now fixed per rule and justified by the sources.
- Calibration pulled the date twice; it now pulls once.
- The duplicate key followed Alpaca's documented identity.
- Trade-object fields are now recorded as A2 evidence.
- Two of my test set-ups were corrected, and lint findings were fixed.

**Validation:** harness 73 passed, offline. Repository: `git diff --check` clean. Only `docs/tasks/M1-12.md` and `PROGRESS.md` changed, uncommitted. Repository tests weren't run, since no repository code changed. No keys used, no market data downloaded, CI not run.

**Concrete batch proposal (replaces the earlier table; nothing started).** Estimates are from roadmap §4.2 and §5.

| Batch | Tasks (order) | Est. | Needs first | Checkpoints |
|---|---|---|---|---|
| **3a** | Merge the daily part of M1-12/M1-13 (`0661d46..4f594bf`), hourly fields explicitly BLOCKED | merge only | **Your decision to split batch 3**; Codex agrees | Merge approval. M1 stays incomplete |
| **3b** | Hourly protocol run: A4, then A3 and A1 + A2, then R, then the full run and evidence review; afterwards, separately, unblock and the M1-13 hourly path | depends on R | v0.3.8 accepted; A4 passes; your approval at R | Every protocol gate; Codex reviews the evidence; separate unblocking commit |
| **4** | **M1-14** replay, **M1-15** resampler, **M1-16** DataHealth | 8 – 9 h | Only tasks in `main` (M1-01, 05, 07 – 11) | One commit per task; task and batch checks; Codex reviews every commit; merge approval |
| **M2 spec pack** (docs) | Split M2's work packages into 1 – 3 h task specs: adjusted-price view and leakage protections first, then features and indicators, `FeatureSnapshot`, the strategy interface, `MarketView` (Law 9 `ABSTAIN`), `LineageRecord`, evaluation, walk-forward and the report; plus the roadmap §4.3 batch update | 4 – 6 h drafting | Your **OPEN-06** (first strategies and sources) and initial **OPEN-09** (metrics) | Codex reviews; no M2 code before acceptance |
| **5** | **M1-17** NVDA CLI (daily complete; hourly section shows BLOCKED) | 3 h | 3a and 4 merged | M1 completes only when no field is blocked (roadmap §4.5) |
| **6** | M2: adjusted view, feature definitions, indicators, `FeatureSnapshot` | 12 – 17 h | M2 specs accepted; M1 merged (or your explicit choice to start before hourly resolves) | Per-task commits; no look-ahead tests |
| **7** | M2: strategy interface and first strategies, `MarketView`, `LineageRecord` | 9 – 12 h | Batch 6 | Law 9 abstention tests; replay-identical views |
| **8** | M2: initial evaluation, walk-forward, HTML report (design principles §2 – 5) | 14 – 20 h | Batch 7 | Walk-forward before any paper run (M4) |

**Suggested long runs:**
1. Batch 4 together with the M2 spec pack: about 12 – 15 h; code and docs in separate commits and reviews.
2. Batch 5 with 3a's merge follow-ups.
3. Batches 6 and 7 together.

Cross-milestone pulls such as an early PostgreSQL move (M3, ADR-008) are **not** proposed: ADR-008 times it at M3, and moving it would need a reviewed plan change.

### 2026-10-12: Claude Code (protocol v0.3.7 work package: rules researched, offline scripts, batch proposal; uncommitted)
The owner approved one uninterrupted work package with a single report. Its limits: changes only in M1-12.md and PROGRESS.md, left uncommitted; scripts outside the repository; no authenticated requests, market-data downloads or purchases; hourly stays blocked; no merge, push or batch 4.

**1. Protocol findings.** Codex's three blocking findings and A4's pass/fail rule were addressed in v0.3.6 (entry below) and carried into v0.3.7.

**2. Official rules researched and cited (M1-12 v0.3.7, step 3).**
- **Sources:** the UTP Data Feed Services Specification's sale-condition matrix (§3.14.2), versions 4.1 (September 2026), 3.0a (November 2025), 2.1a (June 2025) and binary 1.2d (undated). All four were downloaded from utpplan.com, and their SHA-256 checksums are recorded.
- **Agreement across versions:** the consolidated rows are identical for every code that affects high/low or volume. Only v1.2d adds codes 2 and 3, and the reserved code N changes.
- **Key fact:** the UTP Plan defines **only consolidated (daily) rules**.
  - G, P, Z and 4 set daily high/low, and last only if first. Odd lots (I) and Form T are volume only.
  - **There is no official minute profile.** Alpaca's minute rules are a vendor convention, now cited as such and to be confirmed verbatim at A3. My transcription came from a summary.
- **Also added to the protocol:**
  - A1/A2 now cover the full session and calibrate the trade-count definition; if neither definition works, A2 fails;
  - how the daily extreme is located (minute bars, else every trade of the trading date);
  - the last-bar pull runs one minute past the close for the closing cross;
  - closing-cross volume is added from trades;
  - E and N: Alpaca maps them, but the UTP matrix marks them "TBD", so they can't be judged officially;
  - if more than one rule explains everything, the owner and Codex decide.

**3. Scripts, outside the repository** (`C:\Users\LOQ\hourly-verification`, not a git repository), tested **offline only**: **62 passed** (`.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests` run there); ruff (pyflakes, bugbear, import order) clean. A socket guard fails any connection attempt. The real transport refuses to run without `HV_ALLOW_NETWORK=yes`.
- **Coverage:** paging, including short pages with a token; retries and incomplete responses; malformed pages; repeated tokens; duplicates and conflicts; corrections and cancellations; auctions; inclusive-end widening and half-open bars; half-days; every classification outcome, including Codex's "$100 / $110" case; calibration; unmapped codes; results kept outside the repository.
- **Real-fixture check:** `hv/targets.py` reproduces, read-only from the saved fixtures, 181 sessions, 28 pre-split, 187 in-range and 9 outside-range extremes, 35 missing bar starts, and 730 sessions in coverage (728 with hourly bars).
- **Not yet wired into one command:** the agreement sample, E1, volume and the decisions are tested functions.

**4. Self-review fixes, within scope.**
- An unmapped condition would have crashed the run. Now it fails the calibration closed, or makes only the dependent differences unexplained.
- A code Alpaca maps but UTP marks "TBD" is handled.
- A daily-extreme trade outside the session's bars is a named boundary reason.
- A single hourly rule is required for the P-H decision.
- The minute alignment is epoch-based.
- The missing-bar count includes whole missing days.
- One wrong checksum abbreviation was replaced by the full checksums.
- Three of my own test set-ups were corrected.

**Not done:** no authenticated request, no market data, no fixture change. The UTP PDFs (public specifications) were downloaded to a scratch folder, and `pypdf` was installed in a scratch venv to read them; the project venv is unchanged. No repository tests run (no repository code changed). Nothing committed.

**5. Batch proposal (for the owner's decision; nothing started).**

| Batch | Contents | Can start | Checkpoints kept |
|---|---|---|---|
| **3a** | M1-12 and M1-13, **daily part**, as accepted by Codex (`0661d46..4f594bf`). Merge with `H1_PRICE`/`H1_VOLUME` explicitly BLOCKED | On the owner's merge approval. That **changes the plan**: batch 3 is currently "incomplete, don't merge", so splitting it needs the owner's and Codex's agreement | Merge approval; hourly stays blocked; M1 stays incomplete |
| **3b** | The hourly protocol run: A4 terms, then A3, A1 and A2, then the full run; evidence review; then, separately, unblocking and the M1-13 hourly path | On approval of v0.3.7 and of the A4 step (no keys before A4 passes) | Every protocol gate; Codex reviews the evidence; separate unblocking commit |
| **4 (larger)** | **M1-14 replay, M1-15 resampler and M1-16 DataHealth.** Each depends only on tasks already in `main` (M1-01, M1-05, M1-07 – M1-11), not on the Yahoo checkpoint. Tested on synthetic candles; M1-15 handles hourly input generically | **Now**, from `main`, on approval, in parallel with 3b | One commit per task, task checks, batch checks, Codex reviews every commit, merge approval |
| **5** | **M1-17** NVDA CLI (`init`, `import-yfinance`, `report`). The daily sections are complete; the hourly section reports BLOCKED until 3b resolves | After 3a and 4 are merged | M1 is complete only when no field is blocked (roadmap §4.5) |
| **Docs track (cross-milestone)** | **M2 spec pack:** split M2's work packages into 1–3 h task specs, including the agreed adjusted-price view and leakage protections, and the roadmap §4.3 batch update | Drafted alongside batch 4, as documentation for review. It needs the owner's **OPEN-06** (first strategies and sources) and initial **OPEN-09** (metrics) | Codex reviews the specs; no M2 code until they're accepted |
| **6 – 8** | M2 implementation in about three batches: features, indicators and the adjusted view; strategies, MarketView and lineage; evaluation, walk-forward and the HTML report | After the M2 specs are accepted and M1 is complete, or by the owner's explicit choice to start M2 before hourly is resolved | Law 9 abstention, no look-ahead, walk-forward before any paper run |

This plan uses longer runs: batch 4 and the M2 spec drafting could be one approved session of about 10–14 hours of work, with per-task commits and the usual review gates.

### 2026-10-12: Claude Code (hourly protocol revised to v0.3.6; uncommitted, for Codex review)
Codex reviewed v0.3.5: the six earlier corrections are present, but three gaps block a download, plus a pass/fail rule for A4. The owner approved revising the protocol only: no key use, downloads, purchases, unblocking, merge, push or batch 4.

1. **"Explained" now needs both values and the reason.** A difference counts as explained only if:
   - the selected hourly rule reproduces Yahoo's hourly extreme, and the trade(s) setting it are identified;
   - **D-OFFICIAL** reproduces Yahoo's daily extreme, with its trade(s) identified the same way;
   - the specific rule clause that admits those trades on one side and excludes them on the other is named; or the daily extreme falls in a documented missing hourly bar.

   If minute bars can't locate the daily extreme, the session's full trades are searched. Anything not reproduced is unexplained.
2. **Exact trade rules, fixed in advance.**
   - Minute and daily effect profiles (open/close, high/low, volume; all, none or first-only), with the strictest condition winning. The documented differences are listed, e.g. P, Z, 4 and G set the daily high/low only. The UTP matrix governs.
   - Hourly rules: H-MIN; H-ODD (overrides **only** the odd-lot restriction); H-DAY; H-UNCANCELLED.
   - Cancellation, correction, auction and closing-cross boundary handling are all defined.
3. **Complete downloads.** Windows are widened by one minute because the API's `end` is inclusive, and trades are assigned locally to half-open bars. Every page token is followed; failures are retried, then the interval is marked incomplete; duplicates are keyed. Every minute must reproduce the vendor's own SIP minute bar exactly, and a difference relying on incomplete data is unexplained.
4. **A4 pass/fail.** Terms are checked **first**, before any key use. A4 passes only if local storage, committing the derived outputs (given the repository's visibility) and any individual values are all permitted. Unresolved means no key use or download.

**Checks:** documentation only; `git diff --check` clean. Alpaca's aggregation FAQ and trades reference were read for the definitions. No data downloaded, no tests run, nothing committed.

### 2026-10-12: Claude Code (hourly verification protocol drafted; uncommitted, for Codex review)
Codex accepted the review fixes `62118a2..4f594bf`: no blocking findings; 124 importer tests, the full suite in both shells and fresh installs, base and `engine` extra, passed in its run. It then corrected Claude Code's hourly plan in six points. The owner approved drafting the protocol only: no purchase, no download, no fixture change, hourly stays blocked, no merge, push or batch 4.

**Draft: M1-12 v0.3.5, "Hourly verification protocol"** (uncommitted), with Codex's corrections:
1. **Alpaca first, explicit `feed=sip` only.** Access checks A1 (minute bars) and A2 (trades) on a pre-split session must succeed with SIP. IEX is never substituted. A3: the vendor's condition table and the UTP Plan's sale-condition matrix. A4: the data terms.
2. **Trades are required** for the price rules. Three pre-registered rules: R-ELIG (official eligibility), R-ODD (odd lots may set high/low) and R-ALL. Minute bars serve volume and cross-checks only.
3. **Complete coverage:** all **181 sessions** in as-traded units (28 pre-split, 153 post-split; 187 in-range and **9 outside-range extremes, including 2023-12-26 09:30**, reproduced). Each difference ends as explained by a rule, explained by a missing bar, or unexplained; any unexplained one keeps hourly prices blocked. A seeded 60-bar agreement sample is a check only.
4. **Factors:** pre-split × 10 is decisive; post-split × 1 is a control only.
5. **Massive Starter** is listed as a partial fallback only (minute aggregates, no trades).
6. **No claim** that the fixture is the only remaining Yahoo copy; current availability is unchecked.

Volume: all 1004 pre-split bars are decisive anchors under the 3% / 50% rule. Raw vendor data stays outside the repository; only reviewed derived results enter it. Unblocking would be a separate commit, with the owner's approval.

**Checks:** documentation only; `git diff --check` clean. No data downloaded, no tests run, nothing committed.

### 2026-10-12: Claude Code (batch 3 review fixes, approved by the owner)
Claude Code independently reviewed `0661d46..62118a2`: one blocking finding (B1) and seven suggestions. Codex reproduced B1. The owner approved four follow-up fixes, each with regression tests first and its own commit; no merge, push, batch-3 completion or batch 4.

**Fix 1 (B1): forming daily bars are decided by the download's `received_at`.** `yfinance_bars.py` compared the session close with `clock.now()` at processing time, so a bar downloaded at 15:59:58 ET and processed after 16:00 was stored `CLOSED`, `BACKFILL_ASSUMED`, available from the close, with partial-day prices.
- **Fix:** drop a bar when `session.close > received_at` of the download that delivered it. M1-13 v0.2.4 updates the report field, step 9 and the acceptance tests.
- **Tests (written first; the crossing case failed before the fix):** `test_forming_is_decided_by_the_downloads_receipt_time`, received before the close, before the close with processing crossing it, exactly at it, and after it.
- **Checks:** `.venv/Scripts/python.exe -m pytest -q tests/engine/test_yfinance_bars.py` → 35 passed, 1 deselected. `.venv/Scripts/python.exe -m pytest -q` (Git Bash) → **1894 passed, 1 failed, 4 skipped, 3 deselected**; the only failure is `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in the baseline**. `ruff check .` → All checks passed.

**Fix 2: `factor_from_history` enforces the verified range.** It was a public helper with no range check; both importers used it.
- **Fix:** it now takes the verification record as a **required** argument, refuses `d < verified_from`, any split entry before `verified_from`, duplicate ex-dates and non-date inputs. Both importers pass their own record. M1-12 v0.3.4 records the contract.
- **Tests (written first; 13 failed before the fix):** equality with `split_factor` on six dates; the record is required; pre-range date and entry refused; the given record's range is the one applied; duplicates and datetimes refused; spies confirm both importers pass their record (31 dividend and 12 bar calls).
- **Checks:** the three importer test files → 121 passed, 2 deselected. Full suite (Git Bash) → **1907 passed, 1 failed** (the same baseline failure), 4 skipped, 3 deselected. `ruff check .` → All checks passed.

**Fix 3: the recorded-data tests no longer depend on the installed yfinance.** The importers read the installed version (`importlib.metadata.version`), and the tests assumed 1.7.0, while `pyproject.toml` allows `>=1.7.0`.
- **Before the fix:** running the two importer test files with the version lookup reporting `1.7.1` (scratch runner) → **16 failed, 4 passed, 36 errors**.
- **Fix:** each importer test file has an autouse fixture that makes the lookup report `YAHOO_VERIFICATION.yfinance_version`. The importers' real check is unchanged, and **dependency requirements are unchanged**.
- **New tests:** an unverified installed version (`1.7.1`) is refused with `VersionMismatch` **before any fetch**, with nothing written, for both importers; and the importers still use the real `importlib.metadata.version`.
- **After the fix:** the same scratch runner with `1.7.1` → **59 passed**.
- **Checks:** the three importer test files → 124 passed, 2 deselected. Full suite (Git Bash) → **1910 passed, 1 failed** (the same baseline failure), 4 skipped, 3 deselected. Ruff then flagged import order in the two edited test files; `ruff check --select I001 --fix` sorted them (import order only), after which `ruff check .` → All checks passed and the two files → 59 passed.

**Fix 4: an unsupported claim is removed from `docs/data-provenance/yfinance.md`.** The sentence "typical quoted historical price increments are about 0.001 …" had no source. The measured errors ($0.0029 after quantization; about $0.00291343 before) and the rounding explanation (`F × u`) stay.
- **Checks:** `tests/engine/test_yahoo_semantics.py` (which checks that the document mirrors the record) → 65 passed. Documentation only; the full suite runs in the batch checks below.

**Batch checks (after `f2536fb`):**
- B1, PowerShell: `& .venv\Scripts\python.exe -m pytest -q` → **1909 passed, 2 failed** (`tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module`, `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`; both **recorded in the baseline**), 4 skipped, 3 deselected. No new failures.
- B2, clean install: `py -3.11 -m venv <scratch>/smoke`; `<scratch>/smoke/Scripts/python.exe -m pip install -q .`; from the repository root `import tradingagents, cli.main, investment_engine` → OK; from outside it, the three importer modules → loaded from the fresh venv's site-packages. The `engine` extra wasn't reinstalled this round.
- CI not yet run. Live Yahoo checks not run.

**Remaining suggestions, deferred** (Open issues): bad vendor rows abort whole imports; documentation ignored when volume anchors exist; no per-epoch anchor check in `decide_prices`; self-declared hourly comparability; unchecked pre-range entries in `series_values`; the yfinance dependency range. **Kept separate:** the M1-08 `Candle` check for `received_at < end_time`. **Hourly evidence is unresolved.**

**Next:** Codex reviews these commits. No merge, push, batch-3 completion or batch 4.

### 2026-10-12: Codex ? final daily-only batch 3 handoff for Claude review
**Approved implementation finished.** Code commits: **`fcd8457`** (M1-12 partial: verified daily semantics and actions), **`d93e47e`** (M1-13 partial: daily bars), **`f1ebc7b`** (self-review Boolean fix). This documentation commit records final checks/handoff. Review range starts at **`0661d46`**. `main` remains **`0661d46`**; nothing merged or pushed, no branches deleted, batch 4 not started. The 12 merged tasks remain the done count; these partial tasks are **committed (checked), awaiting independent review**, not done.

**Final checks on `f1ebc7b`:**
- Git Bash: `.venv/Scripts/python.exe -m pytest -q tests/engine/test_yahoo_semantics.py tests/engine/test_yfinance_actions.py tests/engine/test_yfinance_bars.py` ? **104 passed, 2 deselected** (the two new live integration checks were not run).
- Git Bash: `.venv/Scripts/python.exe -m pytest -q` ? **1890 passed, 1 failed, 4 skipped, 3 deselected**, 99 subtests passed; output `%TEMP%/codex-b3-followup-full.txt`.
- PowerShell: `& .venv/Scripts/python.exe -m pytest -q` ? **1890 passed, 1 failed, 4 skipped, 3 deselected**, 99 subtests passed; output `%TEMP%/codex-b3-powershell-final.txt`.
- **Only observed failure in both shells:** `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` ? **recorded in baseline**. **No new failures.** The second historically recorded PowerShell failure (`tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module`) did not reproduce in Codex's environment; its assertion was not changed or skipped.
- `.venv/Scripts/python.exe -m ruff check .` ? **All checks passed**; `git diff --check` and staged whitespace check ? clean.
- **Fresh base/engine install: passed**, Python 3.11, no dev extras. Actual commands and saved artifacts below. Base installation imports all three importer modules **from site-packages outside the repo**, with neither `pyarrow` nor `duckdb` installed/loaded; installed final Boolean guard rejects True. The repository-root CI-style import (`tradingagents, cli.main, investment_engine`) succeeds with that fresh Python.
- After installing the engine extra in the same fresh environment, an **outside-repo installed-copy synthetic check** applies schema version 1, imports actions, reconstructs the July close **751.1900**, verifies repeat import writes nothing, writes one observed correction to **751.5900**, proves an earlier visible-at read still returns original revision 1, and confirms hourly import is blocked. The store path includes `[x]`; no network was called.
- **CI, live Yahoo checks and Python 3.12?3.14 runs: not run.** No push.

**Fresh install command/artifact record:**
`<scratch> = C:/Users/LOQ/AppData/Local/Temp/codex-b3-smoke-3cd36c230dd742dc89c13eb2c4cfb0d8` (created new for this check).
1. `py -3.11 -m venv <scratch>`.
2. `<scratch>/Scripts/python.exe -m pip install .` (repository root). After the self-review fix, ran the same command again so the installed copy contains the final code. Logs: `install-base.txt`, `install-base-final.txt` under scratch.
3. From repository root: `<scratch>/Scripts/python.exe -c "import tradingagents, cli.main, investment_engine; print('clean-install import OK')"` ? passed.
4. From scratch (outside repository), exact command: `<scratch>/Scripts/python.exe -c "import importlib, importlib.util, sys; from pathlib import Path; names=('investment_engine.market.importers.yahoo_semantics','investment_engine.market.importers.yfinance_actions','investment_engine.market.importers.yfinance_bars'); mods=[importlib.import_module(n) for n in names]; assert all(Path(m.__file__).is_relative_to(Path(sys.prefix)/'Lib'/'site-packages') for m in mods); assert all(importlib.util.find_spec(n) is None for n in ('pyarrow','duckdb')); print('installed importer paths verified; storage extra neither installed nor loaded'); from investment_engine.market.importers.yahoo_semantics import decimal_value; rejected=False; exec('try:\n decimal_value(True)\nexcept TypeError:\n rejected=True'); assert rejected; print('installed final boolean guard OK')"` ? passed. Equivalent assertions are preserved in `<scratch>/smoke_base.py` for reproduction **before** installing the extra; that script itself was not the command run. Item 4 passed before item 5 installed storage libraries.
5. `<scratch>/Scripts/python.exe -m pip install ".[engine]"` (repository root) ? passed; `install-engine.txt`.
6. From scratch: `<scratch>/Scripts/python.exe <scratch>/smoke_engine.py` ? **installed-copy synthetic actions/daily reconstruction/idempotence/PIT correction/hourly guard OK**. Script is retained outside the repository. It uses synthetic data; it is not additional historical evidence.

**Self-review:** exact current split citations, range guards, pre-range exclusion, end-exclusive dates, provider/Decimal/Clock boundaries, out-of-request/non-session/forming handling, revised-action availability, no duplicate files, schema/package imports and blocked hourly paths checked. Evidence IDs are defined; source counts/precision and actual error are explicit. Each commit changes only its task's allowed files; no runtime `tradingagents/`/`cli/`, existing tests, architecture, SVG, dependencies or CI changed. `.env` stays ignored; `.claude/` is the only untracked item and never staged.

**Not completed:** independent review; any merge/push; hourly evidence, hourly ingestion or its remaining acceptance cases; M1 completion; batch 4. Existing hourly fixture differences remain unexplained. No fabricated bars or prices were introduced.

**Claude review prompt:**
> Read CLAUDE.md, PROGRESS.md, docs/tasks/README.md and M1-12/M1-13. Codex implemented the approved daily-only work while you were unavailable. Independently review EVERY commit from 0661d46 to the current m1/batch-3 head and the combined change against the specs/laws. Report blocking findings with file:line, failure scenario and fix, separate from suggestions. Keep hourly blocked. Do not merge, push or start batch 4. Coordinate fixes on this branch; Codex resumes reviewing your later implementations.

**Owner workflow preference:** use longer uninterrupted runs for clearly approved related tasks, while preserving separate task tests/commits, explicit stop rules and independent reviews. Future milestone groupings are planning proposals, not authorization to combine M1?M4 into one unreviewed implementation or begin new work.

### 2026-10-12: Codex ? numeric-boundary self-review follow-up
After the two task commits, adversarial self-review found that the generic `__index__` fallback accepted Python/NumPy booleans as financial numbers. Two Python-boolean tests failed first (no TypeError); the fix restricts integer conversion to non-boolean `numbers.Integral` and removes the permissive fallback. Tests now cover both Python booleans, both NumPy booleans, valid NumPy int64 and float64 reconstruction. This preserves the explicit M1-02 conversion boundary.

Changed only M1-12's allowed semantics module/test and PROGRESS. **Task checks:**
- Git Bash: `.venv/Scripts/python.exe -m pytest -q tests/engine/test_yahoo_semantics.py tests/engine/test_yfinance_actions.py tests/engine/test_yfinance_bars.py` ? **104 passed, 2 deselected**.
- Git Bash: `.venv/Scripts/python.exe -m pytest -q` ? **1890 passed, 1 failed, 4 skipped, 3 deselected**. Only failure: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in baseline**; no new failures. Output `%TEMP%/codex-b3-followup-full.txt`.
- `.venv/Scripts/python.exe -m ruff check .` ? all checks passed; `git diff --check` ? clean.

Final PowerShell and installed engine smoke checks are being recorded in the handoff entry. Base installed-copy imports already pass from outside the repository; neither storage library is installed/loaded and the final boolean guard is present. No dependency/architecture changes. Live checks and CI not run.

### 2026-10-12: Codex ? M1-13 daily implementation, before task commit
M1-12's partial implementation is committed as **`fcd8457`** with its own task checks; M1-13 builds on that checked commit, under the owner-approved takeover. Tests were written first and failed to collect because `yfinance_bars.py` did not exist. **Hourly is not implemented**: the real record blocks both fields before fetch; synthetic verification cannot enable the paused hourly implementation either.

The daily importer uses explicit instrument context, exact pinned-version/field guards, before/after full-history fetches per symbol segment, cited and stored split equality over the same range, later-split reconstruction, per-field bases and calendar UTC sessions. `end` is exclusive. The approved July window imports **12 sessions** with factor 40 and the independently cited **$751.1900** July 19 close, excluding July 20. The Q1 counterexample remains separate. Required response columns/timestamps/values are validated before writing, forming rows counted, rejected dates reported, and corrections never backdated.

Self-review added tests proving an uncited split fails even when storage agrees, missing/changed stored splits fail, historical corrections preserve visible-at views, a hypothetical reviewed later split creates no false revisions, dated symbol changes split requests and a mapping ending on the excluded date is sufficient. **Two tests first failed** on calendar-closed symbol segments: weekend-only segments incorrectly fetched empty bars. The importer now skips segments with no sessions, reports no coverage for an entirely closed window, and retains explicit errors for an empty response on a segment with sessions.

**M1-13 task checks (Codex):**
- Git Bash: `.venv/Scripts/python.exe -m pytest -q tests/engine/test_yfinance_bars.py` ? **31 passed, 1 deselected** (live check excluded).
- Git Bash: `.venv/Scripts/python.exe -m pytest -q` ? **1885 passed, 1 failed, 4 skipped, 3 deselected**. Only failure: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in baseline**. **No new failures.** Output: `%TEMP%/codex-b3-m113-full.txt`.
- `.venv/Scripts/python.exe -m ruff check .` ? **All checks passed**.
- `git diff --check` ? clean. Only M1-13 allowed files changed (new importer/test, its own spec, Bars provenance section, PROGRESS).
- No dependency/packaging settings changed; fresh-install validation follows as a batch check. CI/live integration **not run**.

**Pending before review handoff:** PowerShell full suite and fresh base/engine install checks. Existing source, architecture, CI and dependencies remain unchanged. Task remains partial; hourly boundaries and live hourly evidence are pending, and batch 3 must not be declared complete.

### 2026-10-12: Codex takeover ? approved daily-only batch 3 work
The owner asked Codex to implement while Claude Code is unavailable (usage limit), then return to independent reviewing when Claude can work again. Approval covers the exact `ActionImportReport`/reporting corrections, the July 1?20 **end-exclusive** window, M1-12 and verified daily M1-13, separate local task commits and required checks. **No merge, push or batch 4.** Claude independently reviews these Codex implementations before any merge.

Claude had updated M1-12 v0.3.3 / M1-13 v0.2.3 and the fixtures README, and started `test_yahoo_semantics.py`; no implementation or commits existed. Codex continued those files. The initial tests failed to collect because the importers did not exist (expected tests-first red stage). Existing price assertions were corrected to the spec's $0.01 tolerance: the cited daily high differs by $0.0029, so exact equality and a zero maximum error would misstate the evidence. The primary decision uses the independently cited July/Massive anchors; retained MarketWatch archives are supporting only.

M1-12 implements version/instrument/range checks, exact in-range cited split equality, before/after stability, field-specific transformations, Decimal reconstruction and action import reporting. The fixture imports **33 actions** (2 splits, 31 dividends), excludes **29** (4 splits, 25 dividends), is idempotent, and corrections become OBSERVED revisions without backdating. Hourly fields are explicitly BLOCKED. Default vendor/storage imports are lazy.

Self-review regression: at UTC midnight, symbol lookup must use the exchange-local date. A new test failed (NEW instead of OLD), then passed after the fix. Tests also cover invalid dividends, empty responses, naive timestamps, unsupported instruments, all four cited-history mismatches and blocked fields. No other source modules or existing tests changed.

**M1-12 task checks, final code (Codex):**
- Git Bash: `.venv/Scripts/python.exe -m pytest -q tests/engine/test_yahoo_semantics.py tests/engine/test_yfinance_actions.py` ? **68 passed, 1 deselected** (live integration excluded).
- Git Bash: `.venv/Scripts/python.exe -m pytest -q` ? **1854 passed, 1 failed, 4 skipped, 2 deselected**. Only failure: `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`, **recorded in baseline**. **No new failures.** Output: `%TEMP%/codex-b3-m112-full.txt`.
- `.venv/Scripts/python.exe -m ruff check .` ? **All checks passed** (after import-order cleanup).
- `git diff --check` ? clean. Named-file staging excludes `.env`, `.claude/`, and M1-13's still-uncommitted spec.
- Fresh-install task check not required: no dependencies/packaging settings changed. Batch PowerShell and fresh-install checks will run after the daily M1-13 work.
- CI and live integration checks **not run**. M1-12 remains **partial** overall because hourly verification is blocked; this task commit delivers verified actions and daily decisions, not batch completion.

### 2026-10-12: Claude Code (batch 3 checkpoint, round 3: Codex's latest findings; uncommitted, for re-review)
The owner approved documentation and evidence corrections only, including M1-13. No importer code, no architecture or SVG changes, nothing committed.

**1. Split scope made consistent (M1-12 v0.3.2, M1-13 v0.2.2).**
- "Complete split history" now means complete **over the verified date range** (`ex_date >= verified_from`, equal to `cited_splits`) in both specs.
- `split_factor` itself raises for `d < verified_from` or for any split before it. Dividends before the range are counted, never stored.
- M1-13's re-import test contradicted the new-split rule (it expected `unchanged` for an uncited split). It now puts the split in a test record's `cited_splits`; without that, the import aborts.
- **New acceptance tests:** `split_factor` raises for 2018-12-31 and for a passed 2007 split; a pre-range dividend isn't stored.

**2. Hourly prices: investigated, still pending. Hourly volume: still blocked.** From the saved fixtures (details in `tests/engine/fixtures/yfinance/README.md`):
- auction prints explain 7 of the 173 inside extremes, and missing bars explain 7 sessions; **about 150 sessions are unexplained**;
- the 8 outside extremes are isolated single-bar spikes, none on a gap day;
- **2026-02-09 14:30** (high 198.725 against 193.660): no independent intraday source found. The Internet Archive has no post-close quote page for that session, and news search found no dated range.

**3. Q1-2021 anchor found.** MarketWatch's NVDA quote page, archived by the Internet Archive on the weekend after each session, gives official closes published before the 2021 split:
- 2021-02-19 **$597.06**, 2021-02-26 **$548.58**, 2021-03-05 **$498.46**;
- recorded first, then compared: Yahoo daily close × 40 equals all three **exactly** ($0.0000);
- added to `nvda_reference.json` with archive URLs and content digests. M1-13's test now uses them, and the option to move the window is withdrawn.

**4. Source count.** The reference file had **14** sources at round 2 (the earlier "15" was wrong); with the three archive sources it now has **17**. The 35 missing hourly bar starts remain documented in the fixtures README.

**Files changed, uncommitted:** `docs/tasks/M1-12.md`, `docs/tasks/M1-13.md`, `tests/engine/fixtures/reference/nvda_reference.json`, `tests/engine/fixtures/yfinance/README.md`, `PROGRESS.md`.

**Checks:** none run; nothing executable changed. The reference JSON was parsed to confirm it's valid (17 sources, 9 price anchors). CI not yet run.

### 2026-10-12: Claude Code (batch 3 checkpoint, round 2: Codex's three findings addressed; uncommitted, for re-review)
**Codex's re-review of round 1:** the daily evidence passes the proposed checks; Codex recalculated daily volume at 1.14% and 1.69%, and the decisive dividends match. Implementation is **not** approved yet. Three blocking findings, plus two non-blocking corrections. The owner approved correcting the evidence and the draft specs, **including M1-13** so that its split contract agrees with M1-12, all **uncommitted** with the importer paused.

**1. The split-scope rules conflicted.** M1-12 skipped the unverifiable 2001 split, while M1-13 still compared the whole history, so every bar import would have aborted.
- **Fix:** one enforced **verified date range**, defined in M1-12 v0.3.1 and used by M1-13 v0.2.1.
  - `YAHOO_VERIFICATION` gains `verified_from` (2019-01-01) and `cited_splits`.
  - A request with `start < verified_from` is refused **before any fetch**.
  - The vendor's in-range splits must equal `cited_splits` exactly, including splits after the requested window and any **new** split since verification.
  - Pre-range splits are never used, compared or stored.
  - `F(d)` keeps every later in-range split.
  - Storage agreement compares the range on both sides.
- **Acceptance tests are added to both specs:**
  - the refusal happens before any fetch;
  - pre-range splits are ignored, including the 2001 date;
  - an extra, missing, re-dated or new in-range split aborts;
  - a later split is applied outside the window.

**2. Hourly-price verification was incomplete.** One matching high around the 2024 split doesn't satisfy P-H's rule.
- **P-H is now pending.** v0.3.1 requires both of P-H's checks, and every difference must be investigated before a decision.
- **Recorded** in `tests/engine/fixtures/yfinance/README.md`, all 728 overlapping sessions:
  - hourly highs and lows differ from daily on **169** sessions;
  - on **164** of them an hourly extreme falls **inside** the daily range (173 extremes; median $0.050, 90th percentile $0.66, largest $3.86);
  - on **8** an extreme falls **outside** it. Each is a single bar whose high or low stands far from its own open and close. The largest is **2026-02-09 14:30, high 198.725 against a daily high of 193.660** (+$5.065).
  - Open and close differences (454 and 530 sessions) are also recorded; these are expected, since the daily values are official prices.
- The cause isn't established without an independent hourly source.

**3. The Q1-2021 reference close was missing.** I searched financial press, Nasdaq and exchange material, and NVIDIA's filings.
- No exact, independently cited NVDA close inside 2021-01-04 – 2021-03-30 was found. Free price tables are split-adjusted, and the Motley Fool's 2021-02-25 article gives percentages only.
- **Nothing was calculated from Yahoo.**
- M1-13's test now records this as open, with two options for review:
  - (a) an independent vendor's unadjusted bar for that window;
  - (b) move the window to 2021-07-01 – 2021-07-19, which has the same purpose (no split events in the response, `F = 40`) and a cited close of $751.19.

**Non-blocking corrections:**
- **The reference file has 14 sources, not 15.** Corrected in the round-1 entry.
- **The 35 missing hourly bar starts** (Codex's count reproduced) are documented in the fixtures README; the downloaded values are unchanged. They are:
  - the 12:30 closing bar on every one of the 7 half-days;
  - partial days on 2026-01-30 and 2026-02-02;
  - 2026-07-10 from 11:30;
  - all of 2026-07-13 and 2026-07-14.

**State:**
- **Daily:** prices, volume, dividends and in-range splits are provisionally established.
- **Hourly:** volume is blocked and prices are pending, with no comparable independent hourly source.
- **One owner action would address the hourly evidence and the Q1-2021 anchor together:** a one-off pull of an independent vendor's unadjusted bars. It's recorded in Open issues.

**Files changed, uncommitted:**
- `docs/tasks/M1-12.md` (v0.3.1);
- `docs/tasks/M1-13.md` (v0.2.1, owner-approved for this round);
- `tests/engine/fixtures/yfinance/README.md` (new);
- `PROGRESS.md`.

No code was written and no test suite was run, since nothing executable changed. The analysis read only the saved fixtures and the cited calendar.

### 2026-10-12: Claude Code (batch 3 checkpoint: M1-12 evidence saved, v0.3.1 rules drafted; uncommitted, for Codex review)
**Approval.** The owner approved batch 3 (M1-12, M1-13) on `m1/batch-3` from `0661d46`. Before any code, the Yahoo evidence was checked, and **the checkpoint stopped the batch**: under the v0.3 rule (volume anchors within 0.5%), daily volume met **neither** interpretation.

**Codex's ruling (2026-10-12):**
- Stopping was right.
- The proposed source types are accepted, with conditions.
- The volume rule must be corrected, with **daily and hourly volume decided separately**.
- Hourly volume stays **blocked** until there are comparable independent references or explicit provider documentation.
- No ADR is needed.

The owner then approved saving the fixtures, gathering citations, drafting v0.3.1 and updating this file, **all uncommitted**, with the importer paused.

**Saved, uncommitted, for review:**
- **`tests/engine/fixtures/yfinance/`:** seven JSON files, each with metadata (call, parameters, request and receipt times in UTC, yfinance 1.7.0, pandas and Python versions). Floats are written with `repr`, so they round-trip exactly. Recorded 2026-10-12 08:25 UTC by a scratch script; in implementation it becomes the `integration` recorder.

  | File | Contents |
  |---|---|
  | `nvda_splits_before` / `nvda_splits_after` | `Ticker.splits`, fetched before and after the bar downloads. **Identical: 6 splits.** |
  | `nvda_dividends` | `Ticker.dividends`: 56 |
  | `nvda_actions_max` | `history(period="max", actions=True)`, action rows only |
  | `nvda_1d_2019_2026` | Daily bars, 2019-01-02 – 2026-10-09: 1954 rows |
  | `nvda_1h_730d` | Hourly bars, 2023-11-10 – 2026-10-09: 5054 rows, 653 KB. Includes the bars from before the 2024 split, which will eventually drop out of Yahoo's rolling window. |
  | `nvda_1d_2021q1_with_actions` | A 2021-Q1 window with `actions=True`: **0 split events**, so a date-filtered call must never be the split history. |

  All bar calls use `auto_adjust=False, actions=False, repair=False, back_adjust=False, prepost=False`.
- **`tests/engine/fixtures/reference/nvda_reference.json`:** **14** cited sources (corrected from "15" after Codex's re-review), each with its URL, publication date, retrieval date and quote.
- **`docs/tasks/M1-12.md`, draft v0.3.1:**
  - a daily volume rule (3%, every decisive anchor must pass, the wrong interpretation at least 50% off, `F = 1` sessions as controls only);
  - a separate hourly volume rule (comparable hourly references with the same bar boundaries, or explicit documentation; hourly sums are supporting only);
  - split evidence scoped to the covered range.

**Evidence and provisional determinations (not decisions until review):**

| Field | Evidence | Provisional result |
|---|---|---|
| **S** split ratio | NVIDIA 8-Ks: 2021-07-20 4:1 and 2024-06-10 10:1 equal Yahoo's. 2006 and 2007 match the company and exchange records. **2001:** Yahoo's 2001-09-12 was a market-closure day (9/11); the 10-K gives distribution on 2001-09-17, and the actual ex-date isn't established. The 2000 split is cited only through a secondary copy of the proxy. | Established for the covered range. Before 2019: under the v0.3.1 scope rule, 2001 is skipped and reported. |
| **P-D** daily prices | Fool: $751.19 on 2021-07-19 = Yahoo 18.779751 × 40. Massive: 2024-06-06 1209.98 and 06-07 1208.88 = Yahoo × 10; 06-10 121.79 and 06-11 120.91 = Yahoo × 1. **All exact to $0.01**, one anchor per split epoch. | `SPLIT_ADJUSTED_AS_OF_DOWNLOAD`, so reconstruction |
| **V-D** daily volume | Decisive (Massive, F = 10): 2024-06-06 and 06-07. Yahoo ÷ 10 is **+1.14% and +1.69%**; Yahoo as-is is +911% and +917%. Controls (F = 1): 2024-06-10 +2.07%, 06-11 +1.63%. | `SPLIT_ADJUSTED_AS_OF_DOWNLOAD` under the v0.3.1 daily rule (all decisive anchors within 3%, the wrong one at least 50% off) |
| **P-H** hourly prices | The 2024 split is inside hourly coverage. 2024-06-07's hourly high, 121.691711 × 10, equals Massive's high of 1216.9171. There is no ~10× step at the ex-date. | ~~`SPLIT_ADJUSTED_AS_OF_DOWNLOAD`~~ **Pending** (corrected after Codex's re-review): hourly highs and lows differ from daily on 169 of 728 sessions; see the next entry |
| **V-H** hourly volume | Hourly sum ÷ Massive daily: 0.967 and 0.954 before the split, 0.962 and 0.941 after. Hourly sum ÷ Yahoo daily: 0.096 and 0.094 before, 0.943 and 0.926 after. This suggests **unadjusted**, unlike daily volume, but under v0.3.1 these sums are **supporting only**. No comparable hourly reference or documentation was found. Yahoo Help SLN28256 doesn't mention volume. | **`UNDETERMINED`, blocked** |
| **D** dividends | NVIDIA 8-Ks: $0.16 (ex 2021-06-09) = Yahoo 0.004 × 40, and $0.04 (ex 2024-03-05) = Yahoo 0.004 × 10, both **exact**. Not decisive (F = 1): $0.01 (2024-06-11) and $0.25 (2026-06-04, 10-Q). | `SPLIT_ADJUSTED_AS_OF_DOWNLOAD`, so reconstruction |

**Consequence if review confirms:** M1-12's action import and M1-13's **daily** bars can proceed. M1-13's **hourly** bars, and so M1 completion, stay blocked until hourly volume has evidence. That's recorded as an open issue, with options.

**Not done:** no code, tests or provenance document (`docs/data-provenance/yfinance.md`); those are implementation. No commit, and no checks run, since nothing executable changed. Primary SEC copies of the 2000, 2001 and 2006 split filings still need re-reading in full.

### 2026-10-12: Claude Code (batch 2: fix for Codex's re-review; ready for re-review)
**Codex re-reviewed `a10bd73` to `30353a1`.** The four original findings are addressed, and Codex confirmed that DuckDB still expands an explicit file list, so files are opened directly. **One new blocking finding:** `a10bd73` validated *every* observation as a first import. That refused a genuine correction because of a backfill time the correction never uses, which contradicts M1-10 ("Any backfill time supplied is ignored").

**Fix (`c637a75`, M1-10):**
- An identity **already stored** is validated in full as the **`OBSERVED` next revision** it would become, at its own receipt time. That one record is used both for the unchanged check and as the correction written. Its backfill time is ignored.
- A **first-seen** identity keeps the first-import checks, backfill time included.
- **Duplicate validation is kept:** an invalid duplicate is still refused, and a valid one still writes nothing.

**Regression tests first:** 3 of 4 new tests failed before the fix.
- A candle correction with a backfill time before the bar's end is **accepted** as revision 2, `OBSERVED` at receipt.
- A dividend correction with a backfill time that isn't the ex-date start is likewise accepted as revision 2, `OBSERVED` at receipt.
- A duplicate carrying such a backfill time is **unchanged**, and nothing is written.
- The same bad backfill times are **still refused on a first import** (passed before and after).

**One existing test case changed, to follow the spec:** in `test_an_invalid_duplicate_action_is_refused_not_counted_unchanged`, the case "backfill not at the ex-date start" became "naive `processed_at`". A duplicate also ignores the backfill time, so that case no longer describes an invalid duplicate. The other three cases are unchanged.

**Checks on `c637a75`:**
- Task checks:
  - `.venv/Scripts/python.exe -m pytest -q tests/engine`: **527 passed**;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1786 passed**, 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.
- **B1, PowerShell:** `& .venv\Scripts\python.exe -m pytest -q`: 2 failed, **1785 passed**, 4 skipped, 1 deselected. The failing set equals the PowerShell baseline.
- **B2, clean install, both variants:** both passed on `c637a75`, each in a fresh Python 3.11 venv using that venv's own Python, run from outside the repo and from its root.
  - **Base:** the package loads from `site-packages`, and the installed calendar gives 2025-01-09 closed and 252 sessions in 2024. `pyarrow` and `duckdb` are neither installed nor loaded.
  - **`engine` extra:** both libraries are installed but not loaded on import. A write-then-read in a store at `market[x]`, with a decoy `marketx` beside it, returns only its own closes; revision [1] is visible before the correction and [2] after.
- **CI:** not yet run.

**Files changed:** `market/store/writer.py`, `tests/engine/test_store_write.py` (M1-10 allowed files) and `PROGRESS.md`.

### 2026-10-12: Claude Code (batch 2: fixes for Codex's review; ready for re-review)
**Codex reviewed all eight batch-2 commits. Verdict: fixes needed, four findings, no ADR needed.** All four are fixed in follow-up commits. Regression tests came first: 17 of the new tests failed on the unfixed code.

| Commit | What |
|---|---|
| `a10bd73` | Findings 1–3, plus the M1-10 two-provider correction test (part of finding 4) |
| `3eafd38` | Finding 4: exact sessions per year (M1-07) |
| (this commit) | This record and the batch checks |

**1. The reader could return another folder's data (M1-11).** A store at `market[x]` read the files of `marketx`, because DuckDB treated `[x]` as a pattern.
- **Codex's suggested fix was not enough.** I tested it: DuckDB **still expands `[x]` inside an explicit list of paths**. With both folders populated, reading `m[x]/…/import=a.parquet` returned `mx`'s value.
- **Fix:** pathlib lists the partition's files (the folder is taken literally), and pyarrow reads each from an **open file object**. DuckDB queries the resulting Arrow table, registered as `records`, and **never sees a path**. The path-inside-root check is kept.
- **Tests:** candles and actions, through `latest` and `revisions_available_between`, empty and populated. A matching writer test passed before the fix (the writer's reads were already literal) and stays as a guard.
- **This resolves the batch-2 known limit** "a store root path containing glob characters isn't supported".

**2. Duplicates skipped validation (M1-10).** Values matching the stored record returned "unchanged" before the observation was checked.
- **Fix:** each observation is first built in full as the record it would be if first seen, which runs every contract check. Only then is it compared, as a validated record, with the stored one.
- **Tests:** a duplicate with `FORMING`, a float price, or a naive `received_at` or `processed_at` is refused. A dividend duplicate with the wrong currency, a bad time zone, a naive time, or a backfill time other than the ex-date start is refused. In every case no file changes. **A valid duplicate still writes no file.**
- **Behaviour note:** a correction's backfill time was ignored before; now it must be valid, though it's still never used, so corrections are never backdated.

**3. Bad arguments passed when the store was empty (M1-11).** Every method now checks its times, dates, timeframe and action types before looking at the store. **Tests:** 14 bad calls covering all ten methods, each run on an empty and a populated store (28 cases).

**4. Two acceptance checks were incomplete.**
- **M1-07:** each year's session count is now asserted exactly: 2019 252, 2020 253, 2021 252, 2022 251, 2023 250, **2024 252**, 2025 250, 2026 251. These are worked by hand from the cited schedules (weekdays less weekday closures) and recorded in a table in the test. A second test ties that table to the data file, so a missing or extra closure fails.
- **M1-10:** correcting `testvendor`'s dividend creates only its revision 2. `yfinance`'s files are byte-for-byte unchanged.

**Checks on `3eafd38`:**
- Task checks:
  - `.venv/Scripts/python.exe -m pytest -q tests/engine`: **523 passed** (+48);
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1782 passed**, 4 skipped, 1 deselected; failing set = baseline (`tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`);
  - `ruff check .`: all checks passed.
- **B1, PowerShell:** `& .venv\Scripts\python.exe -m pytest -q`: 2 failed, **1781 passed**, 4 skipped, 1 deselected. The failing set equals the PowerShell baseline. Codex's run didn't reproduce `tests/test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module`; it does fail here, most likely because of the console encoding.
- **B2, clean install, both variants**, each with its fresh venv's own Python: both passed on `3eafd38`. Fresh Python 3.11 venvs; the smoke script ran with `-I` from outside the repo, and an import was also checked from the repo root.
  - **Base** (`pip install .`): the package loads from `site-packages`, and the installed calendar gives 2025-01-09 closed and 252 sessions in 2024. `pyarrow` and `duckdb` are **neither installed nor loaded**, and importing `investment_engine.market.store` loads neither.
  - **`engine` extra:** the same checks pass, and both libraries are installed but not loaded on import. A write-then-read in a store at **`market[x]`**, with a decoy `marketx` beside it, returns only its own closes (`1150.0000`, `1151.0000`): revision [1] is visible before the correction and [2] after.
- **CI:** not yet run.

**Files changed:** `market/store/reader.py`, `market/store/writer.py` and their tests (M1-10, M1-11 allowed files), `tests/engine/test_calendar_holidays.py` (M1-07), and `PROGRESS.md`. No architecture, SVG, TradingAgents code, existing non-engine tests, `pyproject.toml` or CI changed.

### 2026-10-12: Claude Code (batch 2: batch checks and self-review; ready for Codex review)
**Commits on `m1/batch-2`, after `109a72d`:**

| Commit | What |
|---|---|
| `c3feff5` | M1-06 calendar 1, plus `tzdata`, the batch-2 start in PROGRESS and the M1-02 wording exception |
| `cafa373` | M1-07 cited holidays 2019 – 2026 |
| `a641add` | M1-08 Candle contract |
| `5be0c18` | M1-09 CorporateAction contract (explicit instrument context) |
| `a1772bc` | M1-10 append-only writer and the `engine` extra |
| `f77f94e` | M1-11 point-in-time reader |
| `52e875a` | Self-review fix: store path safety and correction receipt order |
| (this commit) | Batch record |

**Batch checks on the final code state, `52e875a`:**
- **B1, PowerShell:** `& .venv\Scripts\python.exe -m pytest -q`: 2 failed, **1733 passed**, 4 skipped, 1 deselected. The failing set equals the PowerShell baseline.
- **B2, clean install, both variants,** each with its fresh venv's own Python: both passed. Fresh Python 3.11 venvs, cached downloads.
  - **Base** (`pip install .`): install, imports and the calendar loaded from the installed copy (2019-01-01 to 2026-12-31; 2025-01-09 closed) all pass. `pyarrow` and `duckdb` are **neither installed nor loaded**.
  - **`engine` extra** (`pip install ".[engine]"`): the same checks pass, both libraries are installed, and importing the package still loads neither. A write-then-read through the **installed** copy shows the revision visible before a correction as [1] and after it as [2].
- **Latest Git Bash run (`52e875a`):** 1 failed, **1734 passed**; failing set = baseline. `ruff check .`: all checks passed. **475 engine tests.**
- **CI:** not yet run. Python 3.12 – 3.14 and the `TZ=America/New_York` job are unverified.

**Self-review (Claude Code), against the specs, the laws and adversarial probes:**
- **One real defect found and fixed:** **path traversal**. A crafted `instrument_id` wrote a Parquet file outside the store. Contracts now require well-formed instrument IDs (kept identical to `Instrument` by a test), and the writer and reader refuse folders outside the root. Also hardened: corrections must be received after what they correct.
- **Caught in my own tests during the batch:**
  - a meaningless assertion line (removed before the first run);
  - a calendar test assuming an unsupplied holiday;
  - unrealistic store-test data, twice (backfills received before their ex-date; corrections received two years before what they corrected).

  In each case the code was right and the test was fixed.
- **Probed and fine:** DST around both 2024 changes; half-day closes in EDT and EST; the special closure shifting next and previous sessions; the base install neither installing nor loading `pyarrow` or `duckdb`; exact decimals through Parquet and DuckDB; a backfilled split invisible a microsecond before its ex-date start; same-day split-before-dividend ordering whichever was written first; no partial writes when one record in a batch is bad; no overwrite of an existing file.
- **Known limits, accepted and noted:**
  - calendar data **after 2026-10-12 is the published schedule**, so a later unscheduled closure needs a data update;
  - a candle's duration isn't checked against its timeframe in the contract (M1-13 maps vendor bars to calendar sessions);
  - a multi-partition write isn't atomic across partitions if the process dies midway (each file is complete or absent, and a rerun refuses to overwrite);
  - one writer process at a time;
  - ~~a store root path containing glob characters isn't supported~~ (fixed after Codex's review, `a10bd73`);
  - a first-seen action received **before** its ex-date but labelled backfill becomes available only from the ex-date start: conservative, never early.
- **Recorded deviations and choices for Codex's judgement** (each detailed in its task entry):
  - M1-09 adds `currency` and `exchange_timezone` (explicit context) and adapts rule 4 for actions, recorded in the spec (v0.2.1);
  - M1-10 takes `import_id` from the write call, stores ratios to 12 decimal places, and links files into place with a hard link;
  - M1-11 fetches results as Arrow to avoid DuckDB's `pytz` dependency;
  - M1-08 means "UTC" as a zero offset, and allows a FORMING bar's `event_time` to precede its `end_time`;
  - M1-07 records the sessions per year without asserting them, since the sources give no counts.
- **Scope:** every commit changed only its task's allowed files, plus the owner-approved documentation exception (M1-02). `pyproject.toml` changed only in `[project] dependencies` (M1-06), `[tool.setuptools.package-data]` (M1-07) and `[project.optional-dependencies]` (M1-10). No architecture, TradingAgents code, existing tests or CI changed. **No stop rule was triggered.**
- **Not committed:** the owner's local `.env.example` edit, which is never staged.

### 2026-10-12: Claude Code (batch 2 self-review fix: store path safety and observation order; M1-08 to M1-11 files)
- **Found by the batch self-review (adversarial probe): a path-traversal bug.** The candle and action contracts checked `instrument_id` only for "non-empty, no surrounding spaces", and the store builds folder paths from it. Reproduced: an observation with `instrument_id='../../../../../ESCAPED'` made the writer create a Parquet file **outside** the store's root (`store/ESCAPED/…` beside `store/market`). Real data comes from SymbolMapping, so this wasn't reachable through normal use, but a store must not trust paths built from data.
- **Also hardened:** the writer accepted a correction **received before** the revision it corrects, which would put a record's history out of time order.
- **Regression tests first,** 25 tests; all failed before the fix:
  - `test_candles.py` (5) and `test_corporate_actions.py` (3): malformed instrument IDs refused;
  - `test_availability.py` (9): **the contracts' instrument-ID check agrees exactly with `Instrument`'s** (M1-03) on valid and invalid IDs;
  - `test_store_write.py`: three crafted IDs write **no file anywhere**; an out-of-order correction is refused, leaving revision 1 only;
  - `test_store_read.py` (4): crafted providers or IDs are refused by reads.
- **Fix:**
  - `availability.py` adds `INSTRUMENT_ID_PATTERN` and `check_instrument_id` (the same rule as `Instrument`), used by `Candle` and `CorporateAction`;
  - the writer and reader validate the provider and instrument ID **and** refuse any folder that resolves outside the store's root (defence in depth);
  - the writer refuses a correction whose `received_at` is earlier than the stored revision's.
- **Existing tests adjusted for the new rule:** nine `test_store_write.py` tests had "corrections" received in 2024 for backfills received in 2026, which is unrealistic data. The correction time is now `LATER` (2026-10-11), after the backfill. No assertion about behaviour changed.
- **Probe after the fix:** the original attack is refused, and no file is written.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine`: 475 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1734 passed** (+25), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.
- **Files changed,** all within batch-2 tasks' allowed files:
  - M1-08: `availability.py`, `candles.py` and their tests;
  - M1-09: `corporate_actions.py` and its tests;
  - M1-10: `writer.py`, `test_store_write.py`;
  - M1-11: `reader.py`, `test_store_read.py`;
  - `PROGRESS.md`.

### 2026-10-12: Claude Code (batch 2, M1-11: market-data store, point-in-time reads)
- **Tests first.** `tests/engine/test_store_read.py` has 23 tests, with data written through the real `MarketDataWriter`:
  - **the Friday correction:** `visible_at` returns revision 1 at Monday's close and on Thursday, revision 2 from Friday 21:00 UTC, and no bar before Monday's close. Also `latest`, the full history, and `revisions_available_between` (Friday → revision 2, Monday → revision 1, in between → none);
  - **observation vs availability:** a backfill imported on 2026-10-10 isn't in `recorded_by(2024-06-04)` but is in `visible_at(2024-06-04)` as BACKFILL_ASSUMED; `recorded_by` follows each revision's receipt;
  - half-open, sorted bar ranges; exact contract objects back (Decimal exponent, UTC tzinfo, enums); an empty store gives empty lists; naive times refused; **no default view method exists**;
  - **two providers** read independently, with independent histories;
  - **corporate actions:** all five views; a backfilled split visible from its ex-date start and not a microsecond before; the `types` filter; **a same-day split and dividend come back split first whichever was written first**, in `latest`, the history and the availability window (M1-11 v0.3 ordering).

  Before the implementation, collection failed on the missing module. One test of mine used unrealistic data: a backfill received *before* its ex-date, corrected before the ex-date. The reader was right; the test now models a real historical download and a later correction.
- **Implementation:** `investment_engine/market/store/reader.py` (`MarketDataReader`):
  - every method takes the provider first, and DuckDB reads **only that provider's partition** (`read_parquet` over `import=*.parquet`, with Hive partitioning off), filtering on the identity columns as well;
  - the one-per-record views use `row_number()` over the identity, by revision descending;
  - **total sort keys** from the spec's table; the action-type rank is a `CASE` in `ActionType` declaration order, never a string comparison;
  - results are fetched **as Arrow** and converted with the writer's own `schema` functions. That avoids DuckDB's timezone conversion, which needs `pytz` (not declared by the `engine` extra), and keeps a single conversion path.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_store_read.py`: 23 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1709 passed** (+23), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.

  No dependency or packaging change.

### 2026-10-12: Claude Code (batch 2, M1-10: market-data store, append-only writes)
- **Wheels verified before any dependency change** (the spec's stop condition). Checked with pip's resolver (`pip install --dry-run --only-binary=:all: --no-deps --python-version <v> --platform <p>`) for Python 3.11, 3.12, 3.13 and 3.14, each on `win_amd64` and `manylinux_2_28_x86_64`. **All 16 combinations have wheels:** `pyarrow` 26.0.0 and `duckdb` 1.5.6. These are now the floors.
- **`pyproject.toml`, only the sections M1-10 allows:**
  - a new `[project.optional-dependencies] engine = ["pyarrow>=26.0.0", "duckdb>=1.5.6"]`;
  - the same two packages added to `dev`, so the CI test job installs them.
- **Tests first.** 29 tests:
  - `tests/engine/test_optional_imports.py`: in a subprocess, importing the package and every non-store module (including `market.store` itself) loads **neither** `pyarrow` nor `duckdb`; only the writer loads `pyarrow`;
  - `tests/engine/test_store_write.py`:
    - backfill revision 1 at the given time; live revision 1 observed;
    - the provider-first file layout;
    - an identical rewrite changes nothing (byte and modification-time check);
    - **a changed value is revision 2, OBSERVED, available exactly at receipt, even though the observation carried a backfill time**, with revision 1 and its file untouched;
    - revision 3; volume and basis changes count as corrections;
    - **two providers never correct each other**;
    - a bad record anywhere in a batch writes **nothing**;
    - FORMING, unquantized and non-provider records refused;
    - exact decimal round trip;
    - **an existing file is never overwritten** (`FileExistsError`, no leftover temporary file);
    - unsafe import IDs refused;
    - two observations of one bar in one batch get ordered revisions;
    - dividend backfill from the ex-date start, its correction, identical rewrite, and provider separation;
    - split ratios round-trip, and excess precision is refused.

  Before the implementation, collection failed on the missing modules.
- **Implementation:**
  - `investment_engine/market/store/__init__.py` (no heavy imports);
  - `store/schema.py`: Parquet schemas with exact types (prices and amounts `decimal128(18,4)`, volume `decimal128(20,0)`, ratios `decimal128(28,12)`, UTC microsecond timestamps), record conversion, and `to_table`, which refuses values that don't fit exactly;
  - `store/writer.py`: `CandleObservation`, `ActionObservation`, `WriteResult` and `MarketDataWriter`. Revisions are assigned per identity. The whole batch and every target are validated before any write. Each file is written under a temporary name, then **hard-linked** into place (`os.link` refuses an existing target, so nothing is replaced), and the temporary name is removed.
- **Choices not stated in the spec, recorded for review:**
  - the **`import_id` comes from the write call**, not from each observation, so a batch can't mix import IDs; it must be a safe file name;
  - a split ratio is stored to **12 decimal places**, and more is refused;
  - a multi-partition write isn't atomic across partitions if the process dies midway, but each file is complete or absent, and a rerun with the same import ID refuses to overwrite.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_store_write.py tests/engine/test_optional_imports.py`: 29 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1686 passed** (+29), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed;
  - **smoke, both installs** (a dependency change): two fresh `py -3.11` venvs, run with each venv's own Python.
    - **Base** (`pip install .`): the CI import is OK; from outside the repository, `pyarrow` and `duckdb` are **not installed** and not loaded, and the non-store modules work.
    - **With the extra** (`pip install ".[engine]"`): the CI import is OK; both libraries are installed but **not loaded** by the package import; the installed writer wrote `import=smoke-1.parquet` (one new record).

### 2026-10-12: Claude Code (batch 2, M1-09: CorporateAction contract)
- **The owner's condition, as implemented:** explicit instrument context. Each action stores the instrument's **`currency`** and **`exchange_timezone`** as required fields with **no defaults**:
  - a dividend must be in that currency;
  - a `BACKFILL_ASSUMED` action must be available exactly at **00:00 of its ex-date in exchange time** (`ex_date_start()`; e.g. 2024-06-10 → 04:00 UTC in EDT, 2024-01-10 → 05:00 UTC in EST);
  - `check_context(instrument)` confirms the record matches its `Instrument` (ID, currency, time zone), and importers must call it.

  This is **recorded in the spec** (`docs/tasks/M1-09.md` v0.2.1), with the reason: storing the context keeps every stored record self-checking without the store looking up reference data.
- **Rule 4 adapted for actions,** also recorded in the spec: actions are announced before their ex-date, so an `OBSERVED` action may be available **before** the ex-date start. Rules 5 – 7 are the shared M1-08 checks, unchanged.
- **Tests first.** `tests/engine/test_corporate_actions.py` has 49 tests:
  - a valid action of each type;
  - ten wrong field combinations refused;
  - split ratio positive and not 1 (reverse and fractional splits allowed; Decimal only);
  - dividend positive, in the instrument's currency, at `PRICE_QUANTUM`, as `Money`;
  - `ex_date_start` in EDT and EST; backfill pinned to it, with midnight UTC refused;
  - an observed action may precede its ex-date;
  - the time zone must be an exact IANA name (trailing space, lowercase and nonsense refused); currency shape;
  - `check_context` matches and three mismatches;
  - a backdated correction refused; BACKFILL only at revision 1; OBSERVED available exactly when received; naive times refused;
  - two-provider identities, the source pattern, `ex_date` a date, enum strings, immutability.

  Before the implementation, collection failed on the missing module.
- **Implementation:** `investment_engine/market/corporate_actions.py`: `ActionType`, `AmountBasis`, `ex_date_start`, and the frozen `CorporateAction` (type-specific field rules, shared availability checks, `check_context`, `identity`).
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_corporate_actions.py`: 49 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1657 passed** (+49), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.

  No dependency or packaging change.

### 2026-10-12: Claude Code (batch 2, M1-08: Candle contract)
- **Correction to the M1-07 entry below:** the data file has **77 closures** (2019 – 2026: 9, 9, 9, 9, 10, 10, 11, 10), not 80. The data and tests were unaffected; only the count in the entry was wrong.
- **Tests first,** 58 tests:
  - `tests/engine/test_availability.py`: the two bases, and provider IDs that do and don't match;
  - `tests/engine/test_candles.py`: **a passing and a failing case for each of the nine rules**:
    - 1: every datetime aware, UTC rather than merely aware, start before end;
    - 2: OHLC order, positive prices, non-negative volume, Decimal only;
    - 3: extra precision refused, not rounded; fractional volume refused; fewer decimals fine;
    - 4: `available_from` not before the event;
    - 5: OBSERVED is available exactly when received;
    - 6: a correction must be OBSERVED and not available before it was received;
    - 7: BACKFILL_ASSUMED only at revision 1; revision a positive int;
    - 8: CLOSED means `event_time == end_time`, and a FORMING bar may be observed earlier;
    - 9: `resampled:yfinance` and other non-provider sources refused;
  - plus two-provider identities, enum strings converted, other fields validated, immutability.

  Before the implementation, collection failed on the missing modules.
- **Implementation:**
  - `investment_engine/market/availability.py`: `AvailabilityBasis`, `PROVIDER_ID_PATTERN`, and the shared checks `check_utc`, `check_provider`, `check_name`, `check_revision` and `check_availability` (rules 4 – 7), so candles and corporate actions apply identical availability rules;
  - `investment_engine/market/candles.py`: `Timeframe`, `BarState`, `PriceBasis`, `VolumeBasis` and the frozen `Candle` with `identity`.
- **Choices not stated in the spec, recorded for review:**
  - "aware UTC" means a **zero UTC offset**: a New York time is refused rather than converted;
  - a FORMING bar's `event_time` may precede its `end_time`;
  - enum values given as strings are converted.
- **Task checks** (run while M1-09's uncommitted test file was on disk, so it was excluded with `--ignore`):
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_candles.py tests/engine/test_availability.py`: 58 passed;
  - `.venv/Scripts/python.exe -m pytest -q --ignore=tests/engine/test_corporate_actions.py` (Git Bash): 1 failed, **1608 passed** (+58), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check` on the task's files: all checks passed.

  No dependency or packaging change.

### 2026-10-12: Claude Code (batch 2, M1-07: trading calendar 2, cited holidays)
- **Data from official sources only, never from memory.** `investment_engine/market/calendar/data/us_equities.json` covers **2019-01-01 – 2026-12-31**: 77 closures (corrected from 80; see the M1-08 entry), including **one special closure**, and 17 early closes at 13:00 ET. Every entry cites one of six sources, all retrieved on 2026-10-12:
  - NYSE Group calendar press releases on ICE's investor site: 2019 – 2021 (published 2018-12-04); 2021 – 2023 (2020-12-28, a cross-check: no Juneteenth closure in 2021); 2022 – 2024 (2021-12-27: Juneteenth from 2022, no New Year's closure in 2022); 2025 – 2027 (2024-11-08);
  - the NYSE release closing the markets on **2025-01-09** for President Carter's national day of mourning (2024-12-30);
  - NYSE's live Holidays & Trading Hours page, a 2026 cross-check.
  - Archived copies of the NYSE page couldn't be fetched (the Wayback Machine is blocked for this tool), so the official press releases are the sources.
  - **No other special closure in 2019 – 2026 was found** in official NYSE or ICE sources.
  - **Dates after 2026-10-12 are the published schedule.** An unscheduled closure announced later would need a data update; the file's `note` says so.
- **Tests first.** `tests/engine/test_calendar_holidays.py` has 31 tests:
  - coverage and out-of-range;
  - every listed closure isn't a session, and every early close ends at its stated time;
  - **cited spot checks, each naming its source ID**: Good Fridays, Juneteenth (its 2022 first year and 2024), Thanksgiving, Independence Day observed on a Friday or Monday, Christmas observed on Friday 2021-12-24 (a full closure), the 2025-01-09 special closure, early closes (13:00 EST = 18:00 UTC; 13:00 EDT = 17:00 UTC);
  - cited **regular** sessions: 2021-12-31 (New Year's 2022 not observed), 2021-06-18 (no Juneteenth in 2021), 2021-12-23;
  - the special closure shifts next and previous sessions;
  - file consistency: unique dates, in coverage, weekdays, reasons and known sources, 13:00 closes, the stated regular hours;
  - per-year completeness: 8 – 11 closures, Thanksgiving on the fourth Thursday, the early close the day after.

  Before the implementation, collection failed on the missing loader.
- **Sessions per year, computed and recorded for review, not asserted against a source** (the sources give dates, not counts): 2019 **252**, 2020 **253**, 2021 **252**, 2022 **251**, 2023 **250**, 2024 **252**, 2025 **250**, 2026 **251**. The test asserts only a 245 – 254 sanity band.
- **Implementation:** `load_us_equities_calendar()` in `us_equities.py`. It reads the packaged file with `importlib.resources`, refuses data for another time zone or other regular hours, and refuses entries citing an unknown source. `pyproject.toml` `[tool.setuptools.package-data]` adds `market/calendar/data/*.json` to the `investment_engine` entry.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_calendar_holidays.py`: 31 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1550 passed** (+31), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed;
  - **smoke** (a packaging change): fresh venv, `pip install .`, the CI import OK; from outside the repository, the installed loader gave coverage 2019-01-01 – 2026-12-31, with 2025-01-09 closed.

### 2026-10-12: Claude Code (batch 2, M1-06: trading calendar 1, plus the batch-2 start)
- **Batch 1 is merged** (Codex's review of every commit passed; `main` at `109a72d`; 6 of 18 tasks done). **The owner approved batch 2**, and `m1/batch-2` was created from `109a72d`.
- **Documentation-only exception approved by the owner:** `docs/tasks/M1-02.md` is clarified (v0.1.1). Ordering comparisons reject mixed currencies or units, and equality returns `False`. The contract comments and acceptance wording are made consistent, as Codex suggested.
- **Tests first.** `tests/engine/test_calendar_sessions.py` has 23 tests:
  - the port is satisfied;
  - opens and closes around both 2024 DST changes, including the Friday before the November change;
  - weekends;
  - inclusive `sessions_between` (weekend skipped, a weekend-only range is empty, a reversed range refused);
  - `next_session` and `previous_session` across the weekend, strictly after or before;
  - every method refuses out-of-range dates, and `next`/`previous` never guess past coverage;
  - supplied holidays and half-days are honoured (half-day close 13:00 EDT = 17:00 UTC);
  - inconsistent closures refused (outside coverage, weekends, half-day close outside regular hours, a date both closed and half-day);
  - coverage validation; dates, not datetimes; immutable sessions.

  Before the implementation, collection failed on the missing package. One test of mine assumed a holiday the test calendar hadn't been given; fixed in the test.
- **Implementation:**
  - `investment_engine/market/calendar/base.py`: `Session`, `CalendarRangeError(LookupError)` and a `runtime_checkable` `TradingCalendar` protocol;
  - `us_equities.py`: `UsEquitiesCalendar` (09:30 – 16:00 `America/New_York` via `zoneinfo`; holidays and half-days supplied by the caller, validated);
  - `__init__.py`.
- **Dependency:** `pyproject.toml` `[project] dependencies` gains **`tzdata>=2026.5`** (the installed version), unconditional, as M1-06 permits and Codex accepted.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_calendar_sessions.py`: 23 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1519 passed** (+23), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed;
  - **smoke** (a dependency change): fresh `py -3.11` venv, `<scratch>/Scripts/python.exe -m pip install .`, **`tzdata` 2026.5 installed**, the CI import OK; from outside the repository, the installed calendar gave the 2024-03-11 session as 13:30 – 20:00 UTC.

### 2026-10-12: Claude Code (batch 1: batch checks and self-review; ready for Codex review)
**Commits on `m1/batch-1`, after `f4313cb`:**

| Commit | What |
|---|---|
| `b4c3ee2` | M1-02 Decimal boundary |
| `ef32f14` | M1-03 Instrument |
| `bb2feaa` | M1-04 SymbolMapping |
| `a5c1636` | M1-05 SQLite store and config |
| `5fbf486` | Self-review fix (M1-02): numpy `float64` |
| `6ef26f2` | Self-review fix (M1-03): exact time-zone names |
| (this commit) | Batch record |

**Batch checks on the final code state, `6ef26f2`:**
- **B1, PowerShell:** `& .venv\Scripts\python.exe -m pytest -q`: 2 failed, **1495 passed**, 4 skipped, 1 deselected. The failing set equals the PowerShell baseline.
- **B2, clean-install smoke:** `py -3.11 -m venv <scratch>/smoke-b1-6ef26f2`; `<scratch>/smoke-b1-6ef26f2/Scripts/python.exe -m pip install .`; from the repository root, `<scratch>/…/python.exe -c "import tradingagents, cli.main, investment_engine; …"`: OK. From outside the repository, with the same fresh Python, the installed package:
  - applied **schema version 1** (from `site-packages`);
  - added NVDA and resolved `yfinance:NVDA` → `EQ_US_NVDA`;
  - converted `np.float64(1208.88)` → `1208.8800`;
  - **refused** `"America/New_York "`.
- **Latest task-level run (Git Bash, `6ef26f2`):** 1 failed, **1496 passed**; failing set = baseline. `ruff check .`: all checks passed.
- **CI:** not yet run. Python 3.12 – 3.14 and the `TZ=America/New_York` job are unverified.

**Self-review (Claude Code)**, against the specs, the laws and adversarial probes:
- **Two real defects found and fixed** in follow-up commits, each with a regression test written first:
  1. `from_float64` crashed on numpy `float64` (pandas data);
  2. time-zone validation depended on Windows file lookup.
- **Probed and fine:** equal `Money` amounts hash alike; ordering against plain numbers and non-finite amounts (including `sNaN`) are refused; both resolvers refuse a string date the same way; `update_lifecycle` accepts status strings; no transaction is left open after errors; re-applying the schema to a populated database is a no-op; the SQLite contract class is collected and runs all 13 M1-04 cases.
- **Known limits, accepted and noted:**
  - `quantize` of a value beyond Decimal's 28-digit context raises `decimal.InvalidOperation` rather than `ValueError`; it's unreachable for real prices;
  - a **relative** `INVESTMENT_ENGINE_DATA_DIR` is used as given (relative to the working directory);
  - time-zone data on Windows still comes **transitively** via pandas until M1-06 declares `tzdata` (decided); M1-03's validation already relies on it at runtime.
- **Choices outside the specs,** each recorded in its task entry: equality across currencies is `False` while ordering raises; `datetime` is refused for dates; enum strings are converted; SUSPENDED is allowed with or without an end date; an identical overlapping mapping is refused; an empty data-directory variable counts as unset; the "not under home" test is adapted to this machine.
- **Scope:** every commit changed only its spec's allowed files. No architecture, runtime TradingAgents code, existing tests or CI changed. `pyproject.toml` changed only in `[tool.setuptools.package-data]` (M1-05). **No stop rule was triggered.**

### 2026-10-12: Claude Code (batch 1 self-review: M1-03 follow-up fix)
- **Found by the batch self-review (adversarial probe).** `Instrument` accepted the time zone `"America/New_York "` (a trailing space). It validated with `ZoneInfo()`, whose file lookup on Windows ignores trailing spaces, and can ignore case. Linux would refuse the same name, so an instrument stored on Windows could fail on Linux.
- **Regression test first:** `test_a_timezone_must_be_an_exact_canonical_name` (a trailing space, lowercase and uppercase). The trailing-space case failed before the fix.
- **Fix:** time zones are checked against `zoneinfo.available_timezones()`, the exact case-sensitive IANA keys, computed once per process with `functools.cache` (598 names, about 27 ms on the first call). The behaviour is the same on every platform.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_instruments.py`: 44 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1496 passed** (+3), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.

### 2026-10-12: Claude Code (batch 1 self-review: M1-02 follow-up fix)
- **Found by the batch self-review (adversarial probe).** `from_float64` built the Decimal from `repr(value)`. **numpy 2's `float64`**, which is what pandas hands over and what the M1-13 importer will receive, is a `float` subclass whose `repr` is `"np.float64(0.1)"`. So `from_float64(np.float64(0.1), …)` **crashed** with `decimal.InvalidOperation`. Reproduced on numpy 2.4.6 before the fix.
- **Regression test first:** `test_from_float64_accepts_numpy_float64` (numpy sums, a price, and NaN refused). It failed before the fix.
- **Fix:** `from_float64` now uses `float.__repr__(value)`, the plain shortest float representation, whatever the subclass. The docstring explains why.
- **Task checks:**
  - `.venv/Scripts/python.exe -m pytest -q tests/engine/test_money.py`: 57 passed;
  - `.venv/Scripts/python.exe -m pytest -q` (Git Bash): 1 failed, **1493 passed** (+1), 4 skipped, 1 deselected; failing set = baseline;
  - `ruff check .`: all checks passed.

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
