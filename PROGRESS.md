# PROGRESS

The handoff log, shared by Claude Code, Codex and the owner. Update it at the end of every work session (AGENTS.md / CLAUDE.md, Section 8). The newest entry goes at the top of the session log.

---

## Current state (2026-10-12)

| | |
|---|---|
| **Milestone** | **M0 Architecture: complete (locally).** **M1 Market foundation: in progress.** **12 of 18 tasks done** (M1-00 – M1-11). |
| **`main`** | Local `main` is at **`0661d46`** (`docs: record the batch 2 re-review fix and checks`). **Batch 2 passed Codex's review** (after two rounds of follow-up fixes) and was **fast-forwarded into `main`** with the owner's approval on 2026-10-12; batch 1 (`109a72d`) before it. `main` is 29 commits ahead of `origin/main`. **Nothing has been pushed.** |
| **Current work** | **Batches re-planned (owner decision, 2026-10-13):** 3a (M1-12/M1-13 daily part, reviewed, awaiting merge approval), 3b (hourly; protocol v0.3.10 reviewed, waiting on A4 and keys), 4 (M1-14 – M1-16, **approved, in progress** on `m1/batch-4`), 5 (M1-17, after 3b and 4). M2 specs are being drafted on `docs/m2-specs`. Hourly fields stay BLOCKED. |
| **Package name** | **`investment_engine`**: OPEN-01 confirmed by the owner on 2026-10-09. It's the internal Python package name; public branding is decided separately. |
| **Other branches** | `m1/batch-2` (at `0661d46`), `m1/batch-1` (at `109a72d`), `m1/M1-01-clock` (at `a8f338b`), `m1/M1-00-skeleton` (at `f906841`), `docs/m0-closeout` (at `9486f05`), `m0-architecture` (at `906ae85`) and `fix/report-reliability-baseline` (at `559f8c2`) are kept. Nothing has been deleted. |
| **Runtime code** | `tradingagents/` and `cli/` unchanged. `investment_engine` on `main`: the M1-02 – M1-05 modules plus `market/calendar/` (US equities, cited 2019 – 2026 data), `market/availability.py`, `market/candles.py`, `market/corporate_actions.py` and `market/store/` (schema, append-only writer, point-in-time reader). The `engine` extra adds `pyarrow` and `duckdb`. |
| **Runtime tests** | Run for every task and batch, and compared against the recorded baseline (`docs/baselines/M1-00-baseline.md`). On `main` (`0661d46`): **527 engine tests**; Git Bash **1786 passed**, PowerShell **1785 passed**, failing sets = baseline. Codex independently reran the engine tests, the full suite and ruff for batch 2. CI not yet run. |

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
1. **Batch 4 (M1-14, M1-15, M1-16)**, approved by the owner on 2026-10-13: one uninterrupted package on `m1/batch-4`, built on this scheduling commit. Tests first, one commit per task, task and batch checks, self-review. Then Codex reviews every commit.
2. **M2 specification drafts** on `docs/m2-specs`, alongside batch 4, for review. OPEN-06 option A is the proposed baseline; OPEN-09 assumptions and thresholds are **provisional**. No M2 code.
3. **Batch 3a merge** needs the owner's approval. **Merge order:** `m1/batch-4` is built on top of `m1/batch-3`, so that every merge stays a fast-forward. 3a (this branch) merges first, then batch 4. Merging batch 4 first would need a rebase, with approval.
4. **Batch 3b (hourly):** A4 (Alpaca's terms) first; then, with the owner's paper-account keys, A3, A1 + A2 and checkpoint R, per M1-12 v0.3.10.
5. Merges, pushes, M2 implementation, key use and market-data downloads all need explicit approval.

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
