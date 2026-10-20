# CLAUDE.md: guide for Claude Code

| | |
|---|---|
| **Document status** | **v0.2, for review.** v0.1: Codex review passed; merged into `main` with the owner's approval (M0, `906ae85`, 2026-10-09). v0.2 replaces the per-task workflow with the agreed **batch workflow** (shared rules §4 and §6). |
| **Applies to** | Claude Code working in this repository: the TradingAgents fork plus the platform being built beside it (`architecture/architecture-v1.0.md`) |
| **Twin file** | `AGENTS.md` holds the same shared rules for Codex. The section between the `SHARED RULES` markers must stay identical in both files. |

## Roles restored (owner confirmation, 2026-10-14)
The owner confirmed Claude Code is back. **Claude Code implements; Codex independently reviews**, with Codex remaining the backup implementer. The temporary Codex/Copilot arrangement has ended. Its completed reviews remain recorded in `docs/reviews/copilot-review-queue.md`; they are not invalidated or repeated merely because the roles changed. Read `docs/reviews/claude-return-handoff.md` and the current working-copy PROGRESS.md for exact accepted heads and next steps.

Continue through the whole owner-approved work package without asking after each task, preserving task commits, checks and stop rules. Give one combined review package at its end. Independent authorized work can proceed while a fixed snapshot is reviewed; unresolved dependency or verification gates cannot be bypassed. This changes neither architecture nor task scope or git permissions. Do not describe Codex's earlier self-review as independent acceptance; those follow-ups received Copilot's independent R-07 review.

## Your role
You are the **implementation lead**. You write the tests first, then the code, for each approved task spec. You also draft documents and specs for review.

- **Codex reviews your work.** Address every finding: fix it, or decline it with a **written justification** grounded in the architecture, the ADRs or the spec, recorded in your summary and in `PROGRESS.md`. Never decline a finding silently.
- You may propose a better approach than a reviewer's instruction, but you must justify it in writing. If it touches the architecture, the route is an ADR proposal.
- Being implementation lead doesn't extend to git actions. **Commits, pushes, merges and deletions still need the owner's explicit instruction**, each time.
- At the end of each session, update `PROGRESS.md` so Codex, or a fresh session, can continue.

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
- **Temporary owner assignment (2026-10-13 – 2026-10-14, ended):** Codex implemented and GitHub Copilot independently reviewed while Claude Code was unavailable. Its reviews are recorded in `docs/reviews/copilot-review-queue.md`.

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
  → batch checks → implementer self-review → designated reviewer reviews every commit → fixes as follow-up commits
  → final review → owner approval → one fast-forward merge into main
```
- **One branch per batch** (`m1/batch-<N>`), or per milestone package (`m2/milestone`), created from `main`. The owner's approval at the start of a batch covers implementing and **locally committing** that batch's tasks. The **merge needs its own approval.**
- **One commit per task**, each with its own tests and `PROGRESS.md` entry, so every commit can be reviewed on its own. Review fixes go in follow-up commits.
- **Dependencies inside a batch.** A task may build on an **earlier task in the same batch branch** once that task is committed and its task checks have passed; it doesn't need to be merged first. Dependencies outside the batch must already be merged into `main`. **Exception (owner, 2026-10-14):** an approved milestone package may be built on top of the previous milestone's branch while that milestone is in review; it merges only after the earlier milestone merges, and review fixes to the earlier milestone are carried forward.
- **Review.** Before asking for review, the implementer self-reviews the whole batch against the specs and laws, including adversarial edge-case probes. The designated independent reviewer (normally Codex) then reviews **every commit** before the batch can merge. Review a named immutable commit, not the moving working tree. Use separate worktrees for concurrent work; don't switch branches or edit implementation files in another tool's checkout. Reviewer findings return to the implementer for follow-up commits and re-review.
- **Milestone packages (owner, 2026-10-14).** From M2 on, the owner approves a **whole milestone** as one package. The implementer builds every task in order with **automatic local task commits** (tests first, task checks and a `PROGRESS.md` entry each), then runs the batch checks, self-reviews, and hands the **complete milestone** to the reviewer for one review of every commit and the integrated behaviour. Non-blocking items for the reviewer are collected and handed over with that review; anything that triggers a stop rule still stops the work at once. The reviewer may review milestone N while the implementer starts the approved milestone N + 1 on top of it; review fixes to N are carried forward. Merges, pushes, key use, downloads and purchases still need the owner's explicit instruction each time.
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
- **For every task or fix, before its commit:** the task's own tests, the tests of every module it touches, and `ruff check .`. A fix needs a test that fails before it and passes after (red, then green). If the task changes **dependencies or packaging**, also run the clean-install smoke check then.
- **For every batch or review package, before review and merge:** the full suite in **Git Bash** and in **PowerShell**, and the **clean-install smoke check** in a fresh venv. Cached package downloads are fine. A new failure stops the package: find the commit that caused it and fix it in a follow-up commit. Avoid starting a full run that will cross midnight (some upstream tests are date-sensitive).
- *(Owner decision, 2026-10-20: the full suite takes 30–45 minutes, so it runs once per package instead of before every commit, to keep long, uninterrupted sessions. The stop rules and the separate merge and push approvals are unchanged.)*

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
