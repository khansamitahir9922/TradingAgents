# PROGRESS

The handoff log, shared by Claude Code, Codex and the owner. Update it at the end of every work session (AGENTS.md / CLAUDE.md, Section 8). The newest entry goes at the top of the session log.

---

## Current state (2026-10-09)

| | |
|---|---|
| **Milestone** | **M0 Architecture: Codex document review passed; committed with the owner's approval; awaiting Codex review of the commit (M0-10)**, then the owner-approved merge (M0-11). Not merged. |
| **M1** | **Not started.** It starts only after M0 closes, with its reviewed, owner-approved merge into `main` (roadmap Section 3). |
| **Branch** | `m0-architecture`, created from `main` at `559f8c2` |
| **`main`** | Local `main` is at `559f8c2` (`fix(memory): scope settlement warnings to current ticker`), **1 commit ahead of `origin/main`, not pushed**. Pushing needs the owner's instruction. |
| **Runtime code** | Unchanged on `m0-architecture`: no changes to `tradingagents/`, `cli/`, tests, `pyproject.toml` or CI. The M0 commit contains documents only. |
| **Runtime tests** | **Not run for the M0 documentation review or commit.** Only documents changed. See "Last check results". |

### M0 work items
| ID | Item | State |
|---|---|---|
| M0-01 | `architecture/architecture-v1.0.md`, `architecture/diagrams/architecture-v1.0.svg`, `architecture/eraser-diagrams.md` | Reviewed; committed. The SVG is unchanged since it was staged. |
| M0-02 | `docs/PRD.md` (v0.1) | Reviewed; committed |
| M0-03 | `docs/design-principles.md` (v0.3) | Reviewed; committed |
| M0-04 | `architecture/adr/README.md`, ADR-001 – ADR-009 | Reviewed; committed |
| M0-05 | `docs/roadmap.md` (v0.3) | Reviewed; committed |
| M0-06 | `docs/tasks/README.md` (v0.2), `docs/tasks/M1-00.md` – `M1-17.md` | Reviewed; committed |
| M0-07 | `AGENTS.md`, `CLAUDE.md` (v0.1) | Reviewed; committed |
| M0-08 | `PROGRESS.md` (this file) | Reviewed; committed |
| M0-09 | Commit the M0 set on `m0-architecture` (excluding `.env` and `.claude/`) | **Done, with the owner's approval (2026-10-09)**: commit `docs: record Architecture v1.0 and M0 working documents`. The hash is in `git log`; a file can't contain its own commit's hash. |
| M0-10 | Codex review of the commit; fixes recommitted; final review | **Next** |
| M0-11 | Owner approval and merge into `main` (pushing is a separate, owner-instructed step) | Not started |

**Never stage:** `.env`, `.claude/`.

---

## Next steps
1. **M0-10:** Codex reviews the M0 commit on `m0-architecture`. Any fixes go in follow-up commits (with the owner's go-ahead), followed by a final review.
2. **M0-11:** the owner approves, and `m0-architecture` is merged into `main`. Push only if the owner asks.
3. Then **M1-00** (package skeleton and recorded test baseline), on `m1/M1-00-skeleton` from the updated `main`. **M1 has not started.**

Parked idea (not scheduled): the owner will share captions from an ML-prediction Instagram account. Claude Code will assess the method against the M2 and M9 promotion rules. Nothing changes in the plan until that assessment is reviewed.

---

## Open issues and decisions
| Item | Owner | Needed by |
|---|---|---|
| OPEN-01: package name (proposed `investment_engine`) | Owner | M1-00 |
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
| Earlier full-suite run (before M0, on the `559f8c2` work) | Two Windows failures were **reported** in that session: `test_yfinance_keeps_its_cache_out_of_the_users_home`, and `test_every_command_is_registered_when_run_as_a_module` (PowerShell only). **Reported, not established:** no saved output, and not reproduced by Codex. | None saved. M1-00 records the baseline under `docs/baselines/`. |
| Documentation checks (2026-10-08 / 09) | No trailing whitespace in `docs/`, `architecture/adr/`, `AGENTS.md`, `CLAUDE.md` or `PROGRESS.md`. Every M1 spec has the required sections. The shared-rules blocks in AGENTS.md and CLAUDE.md are identical. The staged architecture files are unchanged. | Script checks by Claude Code, 2026-10-08 |
| Codex document review | **Passed (2026-10-09).** No blocking issues in the reviewed M0 documents. Codex verified the volume-evidence and replay-ordering fixes, the document structure, dependencies, whitespace, the unchanged SVG and runtime files, and that `.env` and `.claude/` weren't staged. Runtime tests weren't run. | Codex review, relayed by the owner |
| Pre-commit checks | The staged file list matches the owner-approved set; `git diff --cached --check` is clean | Claude Code, 2026-10-09 |
| CI | Not yet run for this branch (nothing pushed) | — |

---

## Session log

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
