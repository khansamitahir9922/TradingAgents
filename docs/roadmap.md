# Roadmap

| | |
|---|---|
| **Document status** | **v0.4, for review.** v0.3: Codex review passed; merged into `main` with the owner's approval (M0, `906ae85`, 2026-10-09). v0.4 adopts the **batch workflow** (§1.1, §4.3), records the owner's one-month window, and updates M0's completed status. Earlier notes:<br>v0.2 applied Codex's first roadmap review: workflow, baseline, Yahoo verification, availability.<br>v0.3 applies the M1 spec review: complete split history, per-field verification, replay timing, provider separation, the resampler cutoff, the frozen DataHealth states, and blocking on failed verification. |
| **Date** | 2026-10-08 |
| **Sources** | `architecture/architecture-v1.0.md` Part K (milestones and promotion gates; v1.0 FROZEN), `docs/PRD.md` (milestone table, OPEN-01 – OPEN-17), `architecture/adr/`. Where this roadmap and the architecture disagree, the architecture wins. |
| **Estimates** | **M1 is detailed**. M2 is **done** (merged into local `main` at `b7c5d2a`, 2026-10-16). M3 is **done** (merged into local `main` at `84494f2`, 2026-10-17). M4 has a **draft specification pack** (M4-00 – M4-13, ≈ 73 h; v0.3), awaiting Codex's review and the owner's decisions D19–D34. M5 – M10 remain provisional work packages, split into reviewed 1–3 hour tasks before implementation. |

This roadmap splits the frozen milestones into **tasks of about 1–3 hours** each. A task is small enough to build, test and review in one sitting, and to hand over between Claude Code and Codex using only the repository's documents.

---

## 1. How work proceeds

### 1.1 Life of a task: tasks in reviewed batches
```
owner approves the batch → per task: spec → tests → implementation → task checks → PROGRESS.md → task commit
  → batch checks → Claude Code self-review → Codex reviews every commit → fixes as follow-up commits
  → final review → owner approval → one fast-forward merge into main
```
Adopted on 2026-10-12 (Codex agreed, owner approved), replacing review-and-merge per task. **The safeguards are unchanged**; there are fewer round trips.

1. **Batch approval.** The owner approves a batch (§4.3). That covers implementing and locally committing its tasks on one branch, `m1/batch-<N>`, from `main`.
2. **Per task:**
   - the spec (`docs/tasks/<ID>.md`, already reviewed);
   - acceptance tests written first, failing for the right reason;
   - the implementation, in allowed files only;
   - the **task checks** (`docs/tasks/README.md`);
   - a `PROGRESS.md` entry;
   - **one commit per task.**

   A task may build on an earlier task **in the same batch branch** once that task is committed and checked. Dependencies outside the batch must be merged.
3. **Batch checks:** the PowerShell full suite and the clean-install smoke check. The smoke check also runs inside any task that changes dependencies or packaging.
4. **Self-review.** Claude Code reviews the whole batch against the specs and laws, including adversarial edge-case probes.
5. **Codex review of every commit**, and of the batch as a whole.
6. **Fixes** as follow-up commits, or a written justification where a finding is declined. Then a **final review.**
7. **Owner approval** and **one fast-forward merge** into `main`. **Nothing is pushed** without the owner's explicit instruction.

**Stop rules:** a batch stops and is reported to the owner on:
- a new test failure;
- a needed file change outside a spec's allowed files;
- a spec gap needing an architecture or ADR change;
- a blocked verification checkpoint (Yahoo field verification in M1-12 is a firm checkpoint).

A task counts as **done only when its batch is merged**.

### 1.2 Rules that apply to every task
- **No architecture change without an accepted ADR** (Part P). If a task finds it needs one, it stops, a proposed ADR is written, and nothing is adopted until the ADR is reviewed and accepted.
- **`tradingagents/` and `cli/` stay unchanged** unless a task spec lists the exact change. The one planned upstream change is in M6 (Part I).
- New platform code lives in its **own package beside `tradingagents/`** (name: OPEN-01, confirmed in M1-00; the specs use the proposed `investment_engine`).
- Until M6, the new package **doesn't import `tradingagents`**. Research data in M1 comes straight from yfinance, which is research-only (Part D).
- **Files a task may change** are listed in its spec. Across M1, they're limited to:
  - the new package and its package data;
  - new tests under `tests/engine/`, including recorded fixtures;
  - task documents under `docs/tasks/`, and `PROGRESS.md`;
  - `docs/baselines/` (M1-00) and `docs/data-provenance/` (M1-12, M1-13);
  - `pyproject.toml`, only in the sections a spec names;
  - `.github/workflows/ci.yml`, only the smoke-import line (M1-00).

  Existing tests, `tradingagents/`, `cli/` and `architecture/` aren't changed in M1.

### 1.3 Existing conventions to preserve
These are in force today (`pyproject.toml`, `.github/workflows/ci.yml`) and new code follows them:

| Area | Convention |
|---|---|
| Tests | `pytest`, with `testpaths = ["tests"]` and `--strict-markers`. Markers: `unit`, `integration`, `smoke`. **`integration` tests are excluded by default** and run only with `-m integration`. Anything that needs the network (e.g. live yfinance) is `integration`; unit tests use recorded fixtures. |
| Lint | `ruff check .` over the **whole repo**, strict select `E, W, F, I, B, UP, C4, SIM`; line length 100; target `py311`. `ruff format` is **not** adopted repo-wide (deferred upstream), so tasks don't reformat existing files. |
| CI | Tests run on Python **3.11, 3.12, 3.13 and 3.14**, plus one run with `TZ=America/New_York` (so time code that only works in UTC fails). A **clean-install smoke** job installs without dev extras and imports the packages, which catches undeclared dependencies. |
| Python | `requires-python = ">=3.11"`. The local `.venv` uses 3.11.9. |
| Install | `pip install -e ".[dev]"` |

**Test baseline.** Two existing tests were **reported** in an earlier session to fail on this Windows machine:
- `test_yfinance_keeps_its_cache_out_of_the_users_home` (reported cause: the temp folder is under the home folder);
- `test_every_command_is_registered_when_run_as_a_module` (reported to fail only from PowerShell: cp1252 decoding).

**No saved output supports this, and Codex hasn't reproduced it.** Until M1-00 records the baseline, they're treated as **reported, not established**. M1-00 runs the exact baseline commands, saves their output under `docs/baselines/`, and records every failure by test ID. From then on, every task reports:
- its new acceptance tests: all must pass;
- the existing tests: every test that passed in the recorded baseline must still pass;
- any failure, listed by test ID, as either "recorded in the baseline" or "new". A new failure blocks the task.

The CI workflow must stay green. CI only runs when the owner pushes or opens a pull request, so until then each task reports **"CI not yet run"** rather than claiming a CI result. Two CI conditions can't be reproduced on this Windows machine: Python 3.12–3.13, and the `TZ=America/New_York` run. Those stay unverified until CI runs.

---

## 2. Milestone overview

| Milestone | Depends on | Must be decided first | Visible result (Part K) | Estimate |
|---|---|---|---|---|
| **M0** Architecture | — | — | v1.0 frozen, diagrams, PRD, ADR-001 – 009, roadmap, M1 task specs, agent guides; **closed by its reviewed, owner-approved merge into `main`** | documents only |
| **M1** Market foundation | M0 **merged into `main`** | OPEN-01 (package name) | CLI: replay NVDA → clean daily/hourly candles + health report | **≈ 42–49 h** (detailed) |
| **M2** Quant + initial evaluation | M1 **daily scope** (owner amendment, 2026-10-14; see §5) | OPEN-06; OPEN-09 (initial) | HTML report: NVDA chart with MarketViews + an honest evaluation | ≈ 35–45 h *(provisional)* |
| **M3** Portfolio, policy, risk | M2 | OPEN-07, OPEN-08 | CLI: proposed intents with approve/reject/reduce reasons | ≈ 35–45 h *(provisional)* |
| **M4** OMS + Execution Worker (simulated) | M3 | OPEN-16 settled (adopted by ADR or explicitly left out); OPEN-09 thresholds; walk-forward in place | Simulated paper run + order log + crash tests on both processes | ≈ 55–70 h *(provisional)* |
| **M5** Ledger + reconciliation | M4 | **ADR-010** securities ledger model; OPEN-12 | P&L + reconciliation reports | ≈ 35–45 h *(provisional)* |
| **M6** TradingAgents adapter | M1 (data), M2 (MarketView) | OPEN-10, OPEN-11 | Research shown alongside the MarketView | ≈ 30–40 h *(provisional)* |
| **M7** Paper broker + hosting | M4, M5 (M6 recommended) | **ADR-011**, **ADR-012**; OPEN-02, 03, 04, 11, 14 | Real paper orders on the broker's paper account | ≈ 40–55 h *(provisional)* |
| **M8** API + dashboard | M5, M6, M7 | OPEN-13, OPEN-15, OPEN-17 | Web dashboard | ≈ 60–80 h *(provisional)* |
| **M9** ML | M2 evaluation, M8 recommended | Dataset and model-registry design (ADR if it touches boundaries) | Champion/challenger report | ≈ 50–70 h *(provisional)* |
| **M10** Live | Long paper validation + governance | Jurisdiction, regulation, governance | — | **not planned in v1** |

Strictly, M6 needs only M1 and M2, so it could run earlier. The roadmap keeps the frozen order and doesn't reorder milestones; reordering is the owner's call.

---

## 3. M0 — Architecture (complete)

| ID | Work | State |
|---|---|---|
| M0-01 | Architecture v1.0 frozen; diagrams exported; guide synced | Reviewed; committed (M0-09) |
| M0-02 | `docs/PRD.md` | Reviewed; committed (M0-09) |
| M0-03 | `docs/design-principles.md` | Reviewed; committed (M0-09) |
| M0-04 | `architecture/adr/` ADR-001 – ADR-009 + index | Reviewed; committed (M0-09) |
| M0-05 | `docs/roadmap.md` (this file) | Reviewed v0.3; committed (M0-09) |
| M0-06 | `docs/tasks/README.md` and `M1-00.md` … `M1-17.md` | Reviewed; committed (M0-09) |
| M0-07 | `AGENTS.md` (Codex) and `CLAUDE.md` (Claude Code): the same rules for both tools | Reviewed; committed (M0-09) |
| M0-08 | `PROGRESS.md`: the handoff log | Reviewed; committed (M0-09) |
| M0-09 | **Commit** the M0 set on `m0-architecture`, with the owner's go-ahead (excluding `.env` and `.claude/`) | Done, with the owner's approval (2026-10-09): commit `docs: record Architecture v1.0 and M0 working documents` |
| M0-10 | **Codex review** of the commit; fixes recommitted; **final review** | **Passed** (2026-10-09) |
| M0-11 | **Owner approval** and **merge** of `m0-architecture` into `main`. Pushing is a separate step, only on the owner's instruction. | **Done** (2026-10-09): `906ae85`, followed by the close-out commit `9486f05`. Not pushed. |

**M0 closed on 2026-10-09** with its reviewed, owner-approved merge into `main`.

---

## 4. M1 — Market foundation (detailed)

**Goal (Part K):** Instrument + SymbolMapping, Clock, Calendar, Candle, CorporateAction, revisions, replay feed, resampler, DataHealth, on SQLite.
**Visible result:** a CLI command that replays **NVDA** (the frozen M1 baseline, PRD OPEN-05) and prints clean daily and hourly candles plus a data-health report.
**Not in M1:** indicators, MarketView, orders, outbox infrastructure (M4; ADR-005), PostgreSQL (M3; ADR-008), live market data (M7).

**Owner's time window (2026-10-11):** one month. **The goal is to finish M1.** M2 is a **stretch goal**, and it still needs reviewed specs, including the agreed adjusted-price view and leakage protections.

### 4.1 Rules that shape M1

**1. Raw values must be verified, not assumed.**
Part H stores prices raw (unadjusted). Yahoo describes its historical Close as adjusted for splits ("Adj Close" is adjusted for splits and dividends), and yfinance's `auto_adjust=False` proves nothing. So M1-12 **determines from evidence** what each field means, **separately** for:
- daily prices, daily volume, hourly prices and hourly volume;
- dividend amounts and split ratios.

Each field's transformation (identity, split reconstruction, or identity only where no later split exists) is **chosen from that evidence**. It isn't required that every initial expectation holds: if volume turns out to be unadjusted, identity is correct. Precision limits are documented. Reconstructed values meet the "unadjusted" requirement when the reconstruction is independently verified (accepted in Codex review). They're stored with an explicit basis per field (`price_basis`, `volume_basis`, `amount_basis`).

**2. Split reconstruction uses the complete split history.**
`F(d)` multiplies **every** split after `d` up to the download date, including splits **after the requested window**. yfinance filters split events in a date-ranged request to that range, so the split history always comes from a full-history request. It's fetched in the same run as the data (before and after, and the run aborts if they differ), and must agree with the stored split actions, read via M1-11.

**3. Failed verification blocks.**
A field that can't be established is investigated first; a failed initial hypothesis isn't, by itself, a reason to change the architecture. While a field stays blocked:
- **every task that writes it is blocked** (parts of M1-12, M1-13 and M1-17);
- and **M1 can't be completed**.

Only if this source can't meet the requirement is a proposed ADR written. **A proposal alone neither unblocks the work nor completes M1.** The work resumes only after the ADR is accepted, the architecture and specs are updated, and the change is implemented.

**4. Replay can't know the future.**
Every stored revision of a candle or corporate action keeps two kinds of time apart:
- **observation** (`received_at`, never changed);
- **availability** (`available_from` with `availability_basis`).

The rules:
- A record first seen in a historical download is `BACKFILL_ASSUMED`: available from its bar end (candles) or from the start of its ex-date (actions). It's labelled as an assumption, because its original publication time can't be established.
- **Any later revision is `OBSERVED`**, available only from its own observation time, and **never backdated**.

**Replay events** (M1-14) carry three timestamps:
- `event_time` = the delivered revision's `available_from`;
- `received_at` = `event_time + latency` (exactly Law 5);
- `processed_at` = `received_at`.

They're computed in replay and never stored. **Each event carries exactly one stored revision.** A bar's first event always carries revision 1, and each correction arrives only in its own later event, so no latency setting can deliver a correction early.

**5. Providers never mix.**
The provider (`source`) is part of every record's identity:
- revisions are numbered per provider;
- every read takes a provider;
- replay, resampling and DataHealth work per provider.

One provider's value is never treated as another's correction.

**6. DataHealth keeps the four frozen states.**
`OK`, `STALE`, `MISSING` and `DEGRADED` are the only statuses. Whether health checks apply at all (e.g. an instrument not yet active) is reported **separately**.

Section 4.4 lists the decisions still open.

### 4.2 Tasks

| ID | Task | Est. | Depends on |
|---|---|---|---|
| **M1-00** | Package skeleton, layering tests, and the **recorded test baseline** | 2–3 h | M0 merged |
| **M1-01** | Clock: `LiveClock`, `ReplayClock`, UTC-only; no system-clock reads in business code | 2 h | M1-00 |
| **M1-02** | Decimal boundary: `Money`, `Quantity`, explicit float64 converters and quanta | 2–3 h | M1-00 |
| **M1-03** | Instrument with lifecycle and ID format | 1–2 h | M1-00 |
| **M1-04** | SymbolMapping with dated lookup | 2 h | M1-03 |
| **M1-05** | SQLite operational store for instruments and mappings; data-directory config | 2–3 h | M1-03, M1-04 |
| **M1-06** | Trading calendar 1: port, regular US sessions, DST | 2 h | M1-01 |
| **M1-07** | Trading calendar 2: holidays, half-days, special closures (cited data) | 2–3 h | M1-06 |
| **M1-08** | Candle contract: provider identity, price and volume bases, availability | 2–3 h | M1-01, M1-02, M1-03 |
| **M1-09** | CorporateAction contract: provider identity, amount basis, availability | 2 h | M1-02, M1-03, M1-08 |
| **M1-10** | Market-data store: append-only Parquet writes; per-provider revisions; never-backdate rule | 3 h | M1-08, M1-09 |
| **M1-11** | Market-data store: per-provider DuckDB reads (`latest`, `visible_at(T)`, `recorded_by(T)`) and revision histories | 3 h | M1-10 |
| **M1-12** | **Yahoo field-semantics verification** (per field, from evidence) + corporate-action importer, using the complete split history | 3 h | M1-02, M1-05, M1-09, M1-10 |
| **M1-13** | yfinance bar importer: daily and hourly, per-field verified transformations, complete split history | 3 h | M1-05, M1-07, M1-08, M1-10, **M1-11**, M1-12 |
| **M1-14** | Replay feed: one event per stored revision, three Law 5 timestamps, half-open window, sequence tie-breaks | 3 h | M1-01, M1-09, M1-11 |
| **M1-15** | Resampler: hourly → daily per provider, with an enforced time cutoff and full input references; comparison with vendor daily | 3 h | M1-07, M1-08, M1-11 |
| **M1-16** | DataHealth: the four frozen statuses per provider and timeframe; applicability reported separately | 2–3 h | M1-01, M1-05, M1-07, M1-11 |
| **M1-17** | NVDA CLI: `init`, `import-yfinance`, `report` | 3 h | M1-05, M1-11, M1-12, M1-13, M1-14, M1-15, M1-16 |

**Total ≈ 42–49 hours** (18 tasks). Each task's spec gives its allowed files, contracts, choices and acceptance tests.

**Changes since roadmap v0.1:**
- **v0.2:**
  - M1-12 and M1-13 swapped content, so corporate actions come first;
  - sequence numbers moved to replay (M1-14);
  - M1-17 and M1-16 now depend on M1-05.
- **v0.3:** M1-13 now depends on M1-11, which provides the stored split history. The phases are unchanged.

### 4.3 Order of work and batches
**Batches** (agreed with Codex on 2026-10-11). Each batch is one branch, reviewed commit by commit, and merged once:

| Batch | Tasks | Purpose | Task order inside the batch | Needs merged first | Notes |
|---|---|---|---|---|---|
| — | M1-00, M1-01 | Skeleton, baseline, Clock | — | — | **Done** (merged task by task: `f906841`, `a8f338b`) |
| **1** | M1-02 – M1-05 | Money types, instruments, symbol mappings, SQLite | 02, 03, then 04 (uses 03), then 05 (uses 03 and 04) | M1-00 | M1-05 adds package data: run the smoke check within the task |
| **2** | M1-06 – M1-11 | Calendars, candles, corporate actions, storage | 06, 07 (uses 06), 08, 09 (uses 08), 10 (uses 08, 09), 11 (uses 10) | M1-01, M1-02, M1-03 (batch 1) | M1-06 adds `tzdata`, M1-07 calendar data and M1-10 optional dependencies: smoke checks within those tasks |
| **3a** | M1-12 – M1-13, **daily part** | Yahoo daily verification, corporate actions, daily bars | 12, then 13 | Batches 1 and 2 | **Firm checkpoint passed for the daily fields** (Codex review, 2026-10-12). `H1_PRICE` and `H1_VOLUME` stay BLOCKED in `YAHOO_VERIFICATION`. Merging 3a doesn't complete M1-12 or M1-13. |
| **3b** | M1-12 – M1-13, **hourly part** | Hourly verification (M1-12 protocol), then unblocking and the hourly import | Protocol gates A4 → A3 → A1 + A2 → R → full run → evidence review; then the unblocking commit; then the M1-13 hourly path | 3a | **Firm checkpoint** (§4.1, rule 3). M1-12 and M1-13 are **done only when 3b merges**. |
| **4** | M1-14 – M1-16 | Replay, resampling, data health | 14, 15, 16 | Batches 1 and 2 (M1-01, M1-05, M1-07 – M1-11) | Doesn't use M1-12 or M1-13, so it doesn't wait for batch 3; it can run while 3b waits for evidence. |
| **5a (in progress, review pending)** | M1-17 daily part | Offline daily report, init and daily-import wiring | 17 daily part on its own branch, based on `cc62dbf` | Continuation exception: 3a daily work and 4 committed/checked in branch ancestry | H1 BLOCKED; independent review and merge still pending; no market downloads |
| **5b (not started)** | M1-17 remaining hourly/full part | Full original report/import acceptance cases | 17 remaining part | **3b and 4** | M1-17 done only after 5b merges; M1 completion criteria unchanged |

**Milestone packages (owner, 2026-10-14).** From M2 on, a whole milestone is approved once, built in one go with automatic local task commits and reviewed by Codex as a whole (shared rules §4).

**Daily continuation (2026-10-13).** The owner told Codex to continue implementation while Copilot reviews. Codex stated that it was taking this as authorization for the proposed daily-only delivery, using checked dependencies in branch ancestry. This permits useful partial work while hourly verification waits; it does not claim that batch 4 passed independent review, authorize a merge, or complete M1-17.

**Batch split (owner decision, 2026-10-13; reviewed by Codex).** Batch 3 was split into 3a (daily, reviewed) and 3b (hourly, waiting on the verification protocol), and the old batch 4 into 4 (M1-14 – M1-16) and 5 (M1-17, after 3b and 4). Each task's dependencies are unchanged; only the batch grouping changed.

The dependency **phases** below still hold, and every batch's order follows them. Each phase needs only tasks from earlier phases:

| Phase | Tasks |
|---|---|
| A | M1-00 |
| B | M1-01 · M1-02 · M1-03 |
| C | M1-04 · M1-06 · M1-08 |
| D | M1-05 · M1-07 · M1-09 |
| E | M1-10 |
| F | M1-11 · M1-12 |
| G | M1-13 · M1-14 · M1-15 · M1-16 |
| H | M1-17 |

### 4.4 Decisions still open in M1
Most implementation choices are **resolved in the task specs**. These remain genuinely open:

| Decision | Owner | Where |
|---|---|---|
| Package name (OPEN-01; proposed `investment_engine`) | Owner | M1-00 |
| The per-field determination **results**, and which independent sources count as citable anchors for as-traded prices, volumes and dividend amounts | Run in M1-12; sources agreed in review | M1-12 |
| How far back yfinance hourly history reaches | Measured in M1-13 | M1-13 |
| `pyarrow` and `duckdb` versions with wheels for Python 3.11 – 3.14 | Checked in M1-10 | M1-10 |
| NVDA's listing date for the seed record (cited; otherwise a labelled lower bound) | Checked in M1-17 | M1-17 |
| Whether DataHealth results are persisted for lineage | Deferred to M2 (lineage); not stored in M1 | M2 |

### 4.5 M1 completion criteria
- The CLI report runs **offline** on stored NVDA data and shows daily and hourly candles for one provider, with price and volume bases, revision, availability basis and times, plus a DataHealth report.
- **Every stored field has an established semantics** documented with cited evidence and precision limits, and carries its basis. **No field is blocked.** If verification blocks a field, M1 isn't complete. A proposed ADR doesn't complete it; only an accepted ADR, implemented, can.
- Reconstruction uses the complete split history, including splits after the requested window (tested).
- Replay never shows a revision or corporate action before its availability, including under non-zero latency (tested for both).
- Providers never mix in identity, revisions, reads, replay, resampling or health (two-provider tests).
- All M1 acceptance tests pass. Every test that passed in the M1-00 baseline still passes, and any failure is listed by test ID. `ruff check .` and the clean-install smoke import pass, and the CI workflow is green once it runs.
- These invariants are tested:
  - history is never overwritten;
  - later revisions are never backdated;
  - business code never reads the system clock;
  - money values are Decimal with explicit units;
  - replay delivers only CLOSED bars.
- `tradingagents/`, `cli/`, existing tests and `architecture/` are unchanged.
- Every M1 task has gone through the full workflow in Section 1.1, including the owner-approved merge.

---

## 5. M2 – M10 (provisional)

Everything below is **provisional**. M2's draft tasks are linked below; M3 – M10 rows remain work packages, with larger rows split into reviewed 1–3 hour tasks before implementation. Names and estimates are for planning only, not a promise of elapsed completion time.

### M2 — Quant + initial evaluation *(SQLite)*
**Before it starts:** M1's merged daily scope, accepted M2 specifications and initial OPEN-09 experiment assumptions. **Scheduling amendment** (owner, 2026-10-14: M2 starts on M1's **merged daily scope** (`main` `53c51bd`); M1's hourly parts stay unfinished and M1 completion criteria are unchanged. No M2 code reads H1 data.)** This is a planning change, not an architecture change: Part K doesn't order M2 after a finished M1, but it lists hourly candles in M1's visible result, so M1 is not declared complete without them. On 2026-10-14 the owner accepted the M2 specs, approved the whole milestone as one package and accepted the provisional research configuration in the [M2 pack](tasks/M2-README.md) (OPEN-06 option A; OPEN-08 provisional `valid_until`; OPEN-09 horizon, costs and windows provisional; promotion thresholds not accepted).

| Group | Tasks | Est. (planning only) |
|---|---|---|
| **M2-A** | [M2-00](tasks/M2-00.md) PIT split-adjusted view; [01](tasks/M2-01.md) versioned definitions; [02](tasks/M2-02.md) indicators; [03](tasks/M2-03.md) FeatureSnapshot | 8–10 h |
| **M2-B** | [04](tasks/M2-04.md) strategy interface; [05](tasks/M2-05.md) two daily strategies; [06](tasks/M2-06.md) MarketView/policy; [07](tasks/M2-07.md) pipeline and complete append-only lineage | 9–11 h |
| **M2-C** | [08](tasks/M2-08.md) price/total returns and completed labels; [09](tasks/M2-09.md) base-rate direction/IC metrics; [10](tasks/M2-10.md) next-open SIMULATED research with raw prices and explicit costs | 8–9 h |
| **M2-D** | [11](tasks/M2-11.md) split into [11a](tasks/M2-11a.md) walk-forward and leakage guards and [11b](tasks/M2-11b.md) evaluation run records; [12](tasks/M2-12.md) honest static HTML report | 6 h |

[M2 pack and dependencies](tasks/M2-README.md). The groups are planning labels: the owner approved the whole milestone as one package on 2026-10-14 (14 tasks, M2-11 split into 11a and 11b), with separate task commits and checks and one combined Codex review. The M2 merge needs its own approval.

**Complete when:** the report shows views over NVDA history with honest, cost-inclusive results; replay tests give identical views across runs; lineage explains every view.

### M3 — Portfolio, policy, risk *(move to PostgreSQL)*
**Before it starts:** OPEN-07 (default limits), OPEN-08 (approval and view validity windows).

**Done (2026-10-17):** merged into local `main` at `84494f2` after Codex's final review. History: **Draft pack (2026-10-16):** [M3 pack](tasks/M3-README.md), 15 tasks in groups M3-A – M3-E, with a revised planning estimate of ≈ 52 h that replaces the provisional range below. OPEN-07 and OPEN-08 are proposed there as decisions D1–D12 and D18 (partial selling), with D13–D17 (order price, starting cash, promotion rule, local PostgreSQL, CLI approvers).

| Provisional work package | Est. |
|---|---|
| PostgreSQL move: local setup, schema port, full suite on PostgreSQL (ADR-008) | 5–7 h |
| `PortfolioSnapshot` and position sizer → `OrderIntent` v1 | 4–5 h |
| Versioned `OrderIntent` and the G2 state machine (ADR-004) | 4–5 h |
| Policy checks (autonomy, restricted list, trading window) | 3–4 h |
| Risk checks: approve / reject / **reduce = new version** | 4–6 h |
| Audit store (`AuditEvent`) | 3 h |
| Admin CLI: Level 1 approve/decline at the CLI | 3 h |
| CLI report of proposed intents with reasons | 2–3 h |

**Complete when:** the CLI shows proposed intents with their approve, reject or reduce reasons. No orders are created yet. Concurrency tests run on PostgreSQL.

### M4 — OMS + Execution Worker (simulated)
**Before it starts:** OPEN-16 is settled: each proposal is either adopted through a reviewed, accepted ADR plus an architecture update, or explicitly left out. OPEN-09 thresholds are set, and walk-forward evaluation is in place.

**Draft pack (2026-10-18, v0.3):** [M4 pack](tasks/M4-README.md), 14 tasks in groups M4-A – M4-E, ≈ 73 h (above the provisional range below). OPEN-16 is proposed there as D19–D20 (both left out; G3 unchanged) and OPEN-09 as D21–D22. D23 reads the completion criterion "only walk-forward-passed strategies run" as applying to PAPER accounts; the visible run uses a RESEARCH account through the simulated broker. That is a clarification for review, not yet accepted.

| Provisional work package | Est. |
|---|---|
| Shared Order state-machine module, compare-and-set on `aggregate_version`, transition ownership (G3) | 5–7 h |
| Core: create `NEW` with `client_order_id`; cancel-request command rows | 3 h |
| Outbox table, publisher, consumer de-duplication (ADR-005) | 5–7 h |
| Execution Worker process skeleton (own secrets file; ADR-002) | 3–4 h |
| Pre-Execution Gate with every Law 13 check | 4–6 h |
| Simulated broker behind the broker port: own state, fees, slippage, next-bar fills | 6–8 h |
| Kill-switch flag and Admin CLI (sole writer); gate read; fail closed; cancels allowed (ADR-006) | 4–5 h |
| Crash recovery: reconcile `SUBMITTING`/`UNKNOWN` by `client_order_id`, re-gate `NEW`, send pending cancels; outbox republish (G4) | 6–8 h |
| Part J invariant and fault-injection tests | 8–10 h |
| Simulated paper run and order-log report | 3–4 h |

**Complete when:** a simulated paper run completes and the order log is produced; crash tests pass on both processes; every Part J order invariant is tested; only walk-forward-passed strategies run.

### M5 — Ledger + reconciliation
**Before it starts:** **ADR-010** (securities ledger model) is accepted; OPEN-12.

| Provisional work package | Est. |
|---|---|
| Double-entry ledger per ADR-010; reversing entries only | 6–8 h |
| Fills → ledger entries, including fees | 4–5 h |
| Positions, cash and P&L derived from the ledger | 4–6 h |
| `BrokerSnapshot` from the simulator (written by the Execution Worker) | 3 h |
| Reconciliation and `ReconciliationIncident` | 5–6 h |
| P&L and reconciliation reports | 4 h |
| Daily DB backup and market-data snapshot (Part M) | 2–3 h |

**Complete when:** P&L and reconciliation reports run; ledger transactions balance and rows are never updated; a seeded mismatch raises an incident.

### M6 — TradingAgents adapter
**Before it starts:** OPEN-10 (provider, models, measured request count per run, budget), OPEN-11.

| Provisional work package | Est. |
|---|---|
| Research job table and Research Worker process (LLM keys only; ADR-001, ADR-002) | 4–5 h |
| Adapter around TradingAgents; the one documented upstream change (structured output, Part I) | 5–7 h |
| `ResearchRecord` capture through LangChain callbacks | 4–6 h |
| `ResearchContext` parsing with `valid_until` and warnings | 3–4 h |
| Daily LLM budget enforcement | 3 h |
| Research shown alongside the MarketView, labelled advisory | 3–4 h |

**Complete when:** research appears next to the view and is labelled advisory; a Research Worker crash or missing research doesn't affect execution; research lineage is complete.

### M7 — Paper broker + hosting
**Before it starts:** **ADR-011** (broker and data provider, incl. whether the data key can trade) and **ADR-012** (hosting and OS-level isolation) are accepted; OPEN-02, 03, 04, 11 and 14 are decided.

| Provisional work package | Est. |
|---|---|
| Paper-broker adapter passing the simulator's contract suite | 8–10 h |
| Broker fills recorded as reported; `BrokerSnapshot` from the broker | 4–5 h |
| Production market-data ingestion by the process allowed to hold its key | 4–6 h |
| VPS setup; separate OS users or containers per process | 6–8 h |
| Read-only kill-switch flag for the Execution Worker (OS permissions) | 2–3 h |
| Deployment checks: each process reads only its own secrets | 3–4 h |
| Paper-account runbook, including the broker's own "cancel all" | 2–3 h |

**Complete when:** real paper orders run on the broker's paper account; the isolation checks pass; reconciliation runs against broker snapshots.

### M8 — API + dashboard
**Before it starts:** OPEN-13 (team and roles), OPEN-15 (dashboard technology), OPEN-17 (reporting needs); `docs/design-principles.md` approved.

| Provisional work package | Est. |
|---|---|
| FastAPI server, with no external credentials | 4–5 h |
| Login and roles (Admin, Trader, Viewer) | 5–6 h |
| Command endpoints (approve, decline, cancel request) as database command rows | 4–5 h |
| WebSocket updates from recorded state | 4–5 h |
| Dashboard shell: command bar with PAPER, autonomy and trading status (design principles S-01 – S-03) | 5–6 h |
| Dashboard panels per design principles (several tasks) | 25–35 h |
| Accessibility and reduced-motion pass (A-01 – A-07) | 4–6 h |

**Complete when:** the dashboard runs with roles; every review-checklist item in the design principles passes; the dashboard has no kill-switch write control.

### M9 — ML
**Before it starts:** dataset and model-registry design (an ADR if it touches boundaries).

| Provisional work package | Est. |
|---|---|
| Point-in-time datasets | 8–10 h |
| Model registry | 6–8 h |
| Calibrated `probability_up`, with calibration tests | 8–10 h |
| Walk-forward evaluation extended to ML models | 6–8 h |
| Champion/challenger report | 4–6 h |

**Complete when:** the champion/challenger report is produced; `probability_up` is shown only from calibrated models, with their version (design principles D-11).

### M10 — Live
**Not planned in v1.** It needs long paper validation, governance, verified jurisdiction and broker eligibility, and the promotion path in Part K. Autonomy levels 3–4 stay disabled.

---

## 6. Promotion path for any strategy (Part K)
```
replay tests pass → evaluation with costs and walk-forward → shadow mode (views only) → paper Level 1 → paper Level 2 → (future) live
```
The roadmap never schedules a strategy past a step whose thresholds (OPEN-09) aren't set.

---

## 7. Open decisions by deadline

| Needed by | Decisions |
|---|---|
| **M1-00** | OPEN-01 package name |
| **M2** | OPEN-06 (option A, selected); OPEN-09 initial assumptions (provisional, accepted 2026-10-14); OPEN-05 if more instruments are needed |
| **M3** | OPEN-07, OPEN-08 |
| **Before M4** | OPEN-09 thresholds; OPEN-16 (follow-up ADR or explicitly out) |
| **Before M5** | ADR-010; OPEN-12; OPEN-17 (partly) |
| **M6** | OPEN-10, OPEN-11 |
| **Before M7** | ADR-011, ADR-012; OPEN-02, 03, 04, 14 |
| **M8** | OPEN-13, OPEN-15, OPEN-17 |

## 8. Risks to the schedule
- **Single developer and tool limits:** handover depends on up-to-date task specs and `PROGRESS.md`.
- **Data quirks:** Yahoo field semantics may fail verification (M1-12). That blocks the affected imports and M1 completion until investigation succeeds, or until an accepted ADR is implemented. yfinance limits and corrections may expand M1-13, M1-15 and M1-16.
- **The PostgreSQL move (M3)** and **multi-process testing (M4)** are the largest technical steps; their estimates are the least certain.
- **External decisions** (jurisdiction, broker, budget) gate M7 regardless of engineering progress.
