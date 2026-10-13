# Task specifications

| | |
|---|---|
| **Document status** | **v0.3, for review.** v0.2: Codex review passed; merged into `main` with the owner's approval (M0, `906ae85`, 2026-10-09). v0.3 introduces the agreed **batch workflow** and splits the checks into per-task and per-batch checks. |
| **Date** | 2026-10-08 |
| **Sources** | `architecture/architecture-v1.0.md` (v1.0 FROZEN), `architecture/adr/`, `docs/roadmap.md`, `docs/PRD.md`, `docs/design-principles.md`. Where a spec and the architecture disagree, the architecture wins. A spec that needs an architecture change stops and proposes an ADR. |

Each task has one spec here (`M1-00.md` … `M1-17.md`). A spec is the contract for its task: anyone, whether Claude Code, Codex or a human, can pick it up from the repository alone.

**M2 planning:** [draft M2 pack](M2-README.md), M2-00 – M2-12. The pack is awaiting independent review; it does not authorize M2 code. Existing check/commit/batch discipline applies to future accepted M2 tasks too. Completed M1 and resolved prerequisite decisions remain mandatory.

## Sections in every spec
1. **Goal**: what the task delivers.
2. **Dependencies**: tasks that must be done first. Merged into `main`, or committed and checked earlier on the same batch branch (see Workflow).
3. **Allowed files**: the only files the task may create or change. Anything else means stop and ask.
4. **Contracts**: types, fields, functions and rules other tasks rely on.
5. **Implementation choices**: **Resolved** choices (decided here, with the reason) and **Unresolved** decisions (marked, with who decides and what happens meanwhile).
6. **Acceptance tests**: the tests that must exist and pass.
7. **Out of scope.**

## Workflow (roadmap Section 1.1)
```
owner approves the batch → per task: spec → tests → implementation → task checks → PROGRESS.md → task commit
  → batch checks → Claude Code self-review → Codex reviews every commit → fixes as follow-up commits
  → final review → owner approval → one fast-forward merge into main
```
- **Batches:** listed in `docs/roadmap.md` §4.3. **One branch per batch:** `m1/batch-<N>`, from `main`. The `Branch` line in each M1 spec is **superseded** by its batch branch; M1-00 and M1-01 used their own branches.
- **Approvals:** the owner's approval at the start of a batch covers implementing and locally committing its tasks. The merge needs a separate approval.
- **One commit per task**, with its own tests and `PROGRESS.md` entry. Review fixes go in follow-up commits.
- **Dependencies:** a task may build on an earlier task in the same batch branch once that task is committed and its task checks have passed. Dependencies outside the batch must be merged into `main`.
- **Review:** Claude Code self-reviews the batch, including adversarial edge-case probes. Codex reviews **every commit** before the merge.
- **Done** means the batch is merged. Before that, a task is "in progress", "committed (checked)", "in review" or "approved, awaiting merge". A task split across two batches (M1-12 and M1-13: batches 3a and 3b; M1-17: 5a and 5b) is done only when its **last** batch merges.
- **Stop rules:** stop and report on a new test failure, a needed file change outside the spec's allowed files, a spec gap needing an architecture or ADR change, or a blocked verification checkpoint (M1-12 is a firm checkpoint).
- **Nothing is pushed** without the owner's explicit instruction. `.env` and `.claude/` are never staged.

## Checks
Run from the repository root with the project venv. Record the **exact command and its result summary** in `PROGRESS.md`.

**Task checks: every task, before its commit**

| # | Command (Git Bash) | Must show |
|---|---|---|
| 1 | `.venv/Scripts/python.exe -m pytest -q tests/engine/<this task's test files>` | All of this task's acceptance tests pass |
| 2 | `.venv/Scripts/python.exe -m pytest -q` | Every test that passed in the **M1-00 recorded baseline** still passes. Any failure is listed by test ID as "recorded in the baseline" or "new". **A new failure blocks the task.** |
| 3 | `.venv/Scripts/python.exe -m ruff check .` | `All checks passed!` |
| 4 | Clean-install smoke, **only if the task changes dependencies or packaging** (e.g. M1-05, M1-06, M1-07, M1-10, M1-17) | As in batch check B2 |

**Batch checks: every batch, before review and merge**

| # | Command | Must show |
|---|---|---|
| B1 | PowerShell: `& .venv\Scripts\python.exe -m pytest -q` | The PowerShell baseline failing set, and nothing new |
| B2 | Clean-install smoke: `py -3.11 -m venv <scratch>`; `<scratch>/Scripts/python.exe -m pip install .`; then, from the repository root, `<scratch>/Scripts/python.exe -c "import tradingagents, cli.main, investment_engine; print('clean-install import OK')"`; and from **outside** the repository, `<scratch>/Scripts/python.exe -c "import <the batch's new modules>; …"`, to prove they're packaged. **Both imports must run with the fresh environment's Python** (`<scratch>/Scripts/python.exe`), never a plain `python`, which could resolve to the project venv and hide a broken installation. Cached downloads are fine. | Both imports succeed without dev extras |

**CI:** the GitHub workflow runs only when the owner pushes or opens a pull request. Until then, a task reports **"CI not yet run"**. It never claims a CI result it didn't see. Python 3.12 – 3.13 and the `TZ=America/New_York` job can't be reproduced on this Windows machine and stay unverified until CI runs. Python 3.11 is the venv; 3.14 is available through `py -3.14` for optional local runs.

## Rules for all M1 code
- **Package:** `investment_engine/` (proposed name; OPEN-01 is confirmed in M1-00). If the owner chooses another name, every path in these specs is renamed mechanically.
- **Tests:** `tests/engine/`, with `__init__.py`. The repository's `tests/conftest.py` already blocks network access in every test not marked `integration`. Engine tests rely on that and never weaken it.
- **Markers:** `unit` for isolated tests, `integration` for anything that touches the network (excluded by default), `smoke` for quick sanity checks.
- **Time:** from M1-01 on, only `investment_engine/clock.py` may read the system clock. All datetimes in contracts are timezone-aware UTC.
- **Money:** from M1-02 on, money, prices and quantities are `Decimal` with an explicit currency or unit. Floats cross into Decimal only through the M1-02 converters.
- **Vendor libraries:** `yfinance` is imported only under `investment_engine/market/importers/`. `pyarrow` and `duckdb` are imported only under `investment_engine/market/store/`, and never at package import time.
- **Files on disk:** tests use `tmp_path` only. Default data locations come from `investment_engine/config.py` (M1-05) and are never the repository.
- **Style:** match the repository's ruff configuration. Don't reformat existing files.
- **Providers never mix.** The provider (`source`) is part of every market-data record's identity, and every read, replay, resample and health check is per provider (M1-08 – M1-16).
- **Replay can't know the future.** Observation (`received_at`) and availability (`available_from`) stay separate, and later revisions are never backdated (M1-08, M1-10, M1-14).
- **Raw values are verified, not assumed** (M1-12). A blocked field blocks every task that writes it, and blocks M1 completion. A proposed ADR alone unblocks nothing.
- **No architecture change** without an accepted ADR. **No outbox infrastructure** in M1 (ADR-005).

## M1 specs
| ID | Title |
|---|---|
| [M1-00](M1-00.md) | Package skeleton, layering tests and recorded test baseline |
| [M1-01](M1-01.md) | Clock |
| [M1-02](M1-02.md) | Decimal boundary |
| [M1-03](M1-03.md) | Instrument |
| [M1-04](M1-04.md) | SymbolMapping |
| [M1-05](M1-05.md) | SQLite operational store and data-directory config |
| [M1-06](M1-06.md) | Trading calendar 1: regular sessions |
| [M1-07](M1-07.md) | Trading calendar 2: holidays, half-days, special closures |
| [M1-08](M1-08.md) | Candle contract, provider, field bases and availability |
| [M1-09](M1-09.md) | CorporateAction contract |
| [M1-10](M1-10.md) | Market-data store: append-only writes |
| [M1-11](M1-11.md) | Market-data store: point-in-time reads and revision histories |
| [M1-12](M1-12.md) | Yahoo field-semantics verification and corporate-action import |
| [M1-13](M1-13.md) | yfinance bar import with verified field transformations |
| [M1-14](M1-14.md) | Replay feed |
| [M1-15](M1-15.md) | Resampler |
| [M1-16](M1-16.md) | DataHealth |
| [M1-17](M1-17.md) | NVDA CLI report |
