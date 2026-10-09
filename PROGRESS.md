# PROGRESS

The handoff log, shared by Claude Code, Codex and the owner. Update it at the end of every work session (AGENTS.md / CLAUDE.md, Section 8). The newest entry goes at the top of the session log.

---

## Current state (2026-10-09)

| | |
|---|---|
| **Milestone** | **M0 Architecture: complete (locally).** **M1 Market foundation: in progress**, starting with M1-00. |
| **`main`** | Local `main` is at **`9486f05`** (`docs: update M0 handoff and record future ML proposals`): the M0 commit `906ae85` plus the reviewed close-out commit, fast-forwarded with the owner's approval. It's 3 commits ahead of `origin/main`. **Nothing has been pushed.** |
| **Current task** | **M1-00**: package skeleton, layering tests and recorded test baseline. Branch `m1/M1-00-skeleton`, from `main` at `9486f05`. **Implemented and checked; committed with the owner's approval; awaiting Codex review of the commit**, then the owner-approved merge. |
| **Package name** | **`investment_engine`**: OPEN-01 confirmed by the owner on 2026-10-09. It's the internal Python package name; public branding is decided separately. |
| **Other branches** | `docs/m0-closeout` (at `9486f05`), `m0-architecture` (at `906ae85`) and `fix/report-reliability-baseline` (at `559f8c2`) are kept. Nothing has been deleted. |
| **Runtime code** | `tradingagents/` and `cli/` unchanged. M1-00 adds only the empty `investment_engine` package, its tests, the packaging line and the CI smoke-import line. |
| **Runtime tests** | **Run for M1-00.** The baseline was recorded and compared; see "Last check results" and `docs/baselines/M1-00-baseline.md`. |

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
1. **Codex reviews the M1-00 commit** on `m1/M1-00-skeleton`, then the owner approves the merge into `main`. Push only if the owner asks.
2. Then **M1-01 (Clock)**, after M1-00 is merged. It isn't started.

**Known stale labels, left for a later update.** AGENTS.md, CLAUDE.md, the design principles, the task README, the ADR records and the roadmap's M0 table still say "awaiting review of the M0 commit and merge". They describe the state before M0-10 and M0-11. This file is the current record.

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
| CI | **Not yet run** (nothing pushed) | — |

---

## Session log

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
