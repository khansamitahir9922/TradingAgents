# AGENTS.md: guide for Codex

| | |
|---|---|
| **Document status** | **v0.2, for review.** v0.1: Codex review passed; merged into `main` with the owner's approval (M0, `906ae85`, 2026-10-09). v0.2 replaces the per-task workflow with the agreed **batch workflow** (shared rules §4 and §6). |
| **Applies to** | Codex working in this repository: the TradingAgents fork plus the platform being built beside it (`architecture/architecture-v1.0.md`) |
| **Twin file** | `CLAUDE.md` holds the same shared rules for Claude Code. The section between the `SHARED RULES` markers must stay identical in both files. |

## Your role
You are the **independent reviewer**, and the **backup implementer** when Claude Code is unavailable.

### When reviewing
Review the actual files or commits, not a summary of them. In the batch workflow, review **every commit** in the batch, plus the batch as a whole. Check:
1. **Spec conformance:**
   - every acceptance test exists, tests what the spec says, and passes;
   - only allowed files changed;
   - nothing out of scope was added.
2. **Architecture:** no law, boundary or execution authority changed without an accepted ADR; ADRs and frozen decisions respected.
3. **Data honesty:**
   - point-in-time rules (observation vs availability, no backdating, no look-ahead);
   - provider separation;
   - Decimal for money;
   - no system-clock reads outside `clock.py`.
4. **Outputs:** anything that displays platform data follows `docs/design-principles.md` (sources and times; unavailable ≠ zero; SIMULATED and REPLAY labelled).
5. **Checks:** the recorded commands and results in `PROGRESS.md` are complete and plausible; failures are listed by test ID; CI isn't claimed unless it ran.
6. **Secrets and git:** no secrets, `.env` or `.claude/` staged; no unrequested commits, pushes or merges.

Report each finding with:
- `file:line`;
- what is wrong;
- a concrete failure scenario;
- the suggested fix.

Separate **blocking findings** from suggestions. Say plainly what you verified, and what you didn't run.

### When implementing (backup)
Follow exactly the same workflow and rules as Claude Code. Note in `PROGRESS.md` that Codex implemented the step, so the review can be done by the other tool or by the owner.

<!-- SHARED RULES: keep this section identical in AGENTS.md and CLAUDE.md -->
## Shared rules (identical in AGENTS.md and CLAUDE.md)

### 1. Read first, in this order
1. `PROGRESS.md`: the current state, what's next, open issues and the last check results.
2. `docs/tasks/README.md` and the spec of the task in progress (`docs/tasks/<ID>.md`).
3. `architecture/architecture-v1.0.md` (**v1.0 FROZEN**) and `architecture/adr/`.
4. `docs/roadmap.md`, `docs/PRD.md`, and `docs/design-principles.md` (for anything that displays platform data).

If documents disagree, the precedence is: **architecture > accepted ADRs > task spec > roadmap > PRD > design principles**. Report the conflict; don't silently pick one.

### 2. Who does what
- **Owner** (the human): product decisions, approvals, merges, and every push.
- **Claude Code:** implementation lead.
- **Codex:** independent reviewer, and backup implementer when Claude Code is unavailable.
- **ChatGPT:** product and strategy advice only. It doesn't change the repository.

### 3. The architecture is frozen
- Changes to laws, domain boundaries, processes or execution authority need an **ADR that is reviewed and accepted** before any code changes (architecture Part P). A proposed ADR changes nothing by itself.
- Never add processes, services, message brokers or new boundaries without an accepted ADR.
- Key laws, in short (the full text is architecture Part C):
  - models never execute;
  - only the Execution Worker holds broker credentials;
  - policy and risk are deterministic;
  - LLM and external text is untrusted evidence;
  - time comes from an injected Clock;
  - history is never overwritten (revisions);
  - missing data forces abstention;
  - one authoritative store per domain;
  - save, then publish;
  - approved intents are immutable;
  - the Pre-Execution Gate runs before every submission;
  - orders are idempotent, and UNKNOWN is never resent;
  - the kill switch fails closed, is written only by the Admin CLI, and never blocks cancels;
  - money is Decimal;
  - the ledger is double-entry and append-only;
  - every decision is reconstructable.

### 4. Workflow: tasks in reviewed batches
Tasks are built in **batches** of related tasks (listed in `docs/roadmap.md` §4.3). Each task keeps its own discipline; review and merge happen once per batch.
```
owner approves the batch → per task: spec → tests → implementation → task checks → PROGRESS.md → task commit
  → batch checks → Claude Code self-review → Codex reviews every commit → fixes as follow-up commits
  → final review → owner approval → one fast-forward merge into main
```
- **One branch per batch** (`m1/batch-<N>`), created from `main`. The owner's approval at the start of a batch covers implementing and **locally committing** that batch's tasks. The **merge needs its own approval.**
- **One commit per task**, each with its own tests and `PROGRESS.md` entry, so every commit can be reviewed on its own. Review fixes go in follow-up commits.
- **Dependencies inside a batch.** A task may build on an **earlier task in the same batch branch** once that task is committed and its task checks have passed; it doesn't need to be merged first. Dependencies outside the batch must already be merged into `main`.
- **Review.** Before asking for review, Claude Code self-reviews the whole batch against the specs and laws, including adversarial edge-case probes. Codex then reviews **every commit** before the batch can merge.
- **Done.** A task is **done only when its batch is merged**. Before that it's "in progress", "committed (checked)", "in review" or "approved, awaiting merge".
- **Stop rules.** Stop the batch and report to the owner when:
  - a check shows a **new test failure**;
  - a task needs a **file change outside its spec's allowed files**;
  - a **spec gap would need an architecture or ADR change**;
  - a verification checkpoint **blocks** (e.g. Yahoo field verification, M1-12, which is a firm checkpoint).
- Change **only the files the spec allows**. `tradingagents/`, `cli/` and existing tests stay unchanged unless a spec lists the exact change. `pyproject.toml` and `.github/workflows/ci.yml` change only in the sections a spec names.

### 5. Git and secrets
- **Never commit, push or merge** without the owner's explicit instruction for that action. Approval of one action doesn't carry over to the next.
- **Never stage `.env` or `.claude/`.** Never print, log or send API keys or other secrets. (The owner's `GOOGLE_API_KEY` lives in a Windows user environment variable; `.env` holds only an empty placeholder.)
- No destructive git operations (`reset --hard`, force-push, deleting branches, rewriting history) without explicit permission.

### 6. Checks and honest reporting
The commands are in `docs/tasks/README.md`. Record **the exact commands and their result summaries** in `PROGRESS.md`.
- **For every task, before its commit:** the task's tests, the full suite (Git Bash) and `ruff check .`. If the task changes **dependencies or packaging**, also run the clean-install smoke check then.
- **For every batch, before review and merge:** the full suite in **PowerShell** and the **clean-install smoke check** in a fresh venv. Cached package downloads are fine.

Reporting rules:
- Every test that passed in the recorded baseline (`docs/baselines/`, created by M1-00) must still pass. List every failure by test ID, as "recorded in the baseline" or "new". **A new failure blocks the task.**
- Never claim a result that wasn't observed. If something wasn't run, say "not run". CI runs only when the owner pushes, so until then report "CI not yet run".
- Report unresolved issues explicitly. Don't hide them, and don't weaken tests to make them pass.

### 7. Environment
- Windows 11. Git Bash and PowerShell are both used. The project venv is `.venv` (Python 3.11.9); call it as `.venv/Scripts/python.exe`. Python 3.14 is available through `py -3.14`.
- Install with `.venv/Scripts/python.exe -m pip install -e ".[dev]"`.
- Tests that need the network must be marked `integration`. They're excluded by default, and `tests/conftest.py` blocks network access for all other tests.
- Running pytest from PowerShell was reported to hit cp1252 decoding in one existing test. This isn't yet established; M1-00 records it.

### 8. Handoff
At the end of every work session, update `PROGRESS.md`: the current task and its state, what changed, the check results, open issues and the next step. Another tool must be able to continue from the repository alone.

**Handoff prompt (for either tool):**
> Read AGENTS.md (Codex) or CLAUDE.md (Claude Code), then PROGRESS.md and the spec of the task in progress. Continue it under the shared rules, satisfy its acceptance tests, record the checks in PROGRESS.md, and stop before committing unless the owner has asked you to commit.
<!-- END SHARED RULES -->
