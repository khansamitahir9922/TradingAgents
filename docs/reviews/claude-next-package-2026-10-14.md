# Critical path, owner decisions and the M2 package (Claude, 2026-10-14)

For the owner (decisions) and Codex (review). Uncommitted planning document; it authorizes nothing by itself. It replaces Claude's earlier draft of the same date. It follows `october-acceleration-plan.md` and the owner's instruction of 2026-10-14:

> Complete each milestone in one go, one by one; give Codex the complete milestone for review. Anything pending goes to Codex in that next review.

## 1. Working method from now on (owner instruction, 2026-10-14)

- **One approval per milestone package:** its tasks, configuration and gates are listed in one document and approved once.
- **During implementation:**
  - Claude builds every task in order and makes the **task commits automatically**, as the package approval authorizes;
  - each task still gets tests first, task checks and a PROGRESS entry;
  - after the last task: batch checks (PowerShell full suite, clean install), a self-review, then **one review of the whole milestone by Codex**, covering every commit and the integrated behaviour.
- **Not changed:** merges and pushes still need the owner's explicit word each time. Key use, downloads and purchases need their own authorization. The stop rules still hold: a new test failure, a file outside the spec, an ADR need, or a blocked checkpoint.
- **Pending items** are not raised one by one. They are collected in §6 and handed to Codex with the next milestone review.

## 2. Re-verified state (2026-10-14)

- **Commits:** `main` is `0661d46`. The reviewed M1 head `53c51bd` is a fast-forward from it, and contains the code and test content of `7ef63f6` exactly (files byte-identical). The M2 drafts are at `71133c1`. The hourly assessment is at `699f9fa`. All worktrees are clean.
- **Tests at `53c51bd`, rerun by Claude (Git Bash):**
  - 2035 passed, 1 failed (the baseline failure `test_yfinance_keeps_its_cache_out_of_the_users_home`), 4 skipped, 3 deselected;
  - `ruff check .` passed.
- **Integrating the M2 drafts:** a simulated merge of `71133c1` into `53c51bd` conflicts only in PROGRESS.md.

## 3. The real blockers

| # | Blocker | Kind | Who clears it |
|---|---|---|---|
| B1 | `main` hasn't received the reviewed M1 work | Approval only | Owner: one sentence |
| B2 | M1's hourly portions (M1-12, M1-13, M1-17) need verified hourly data. A4 (permission to use and keep data) is unresolved. | **External evidence and permission** | Owner, with Alpaca's terms or answer |
| B3 | The roadmap makes M2 wait for a **completed** M1, so B2 currently blocks all of M2 | Planning rule (roadmap, not architecture) | Owner decision D2 |
| B4 | M2's configuration (OPEN-08 and OPEN-09 initial values) isn't accepted | Decision | Owner decision D3 |

Notes:
- Bigger commits don't remove B2. Only permission and evidence do.
- Architecture Part K does **not** order M2 after a finished M1. It does, however, list hourly candles in M1's result, so **M1 can't be declared complete without hourly data**.
- M2 reads only daily data. Every M1 task it depends on (M1-02, 05, 07, 08, 09, 11, 13 daily, 14, 16) is in `53c51bd`.

## 4. Owner decisions, all in one list

| # | Decision | Recommendation (a proposal only) | Trade-off |
|---|---|---|---|
| **D1** | Fast-forward local `main` from `0661d46` to `53c51bd` (no push) | **Yes** | None; it is fully reviewed. M1 then stands at 15 of 18 tasks done. |
| **D2** | Let M2 start on M1's merged daily scope, while M1 stays "in progress" until hourly verification passes | **Yes (option A).** A roadmap amendment that Codex reviews. M2 code may never read H1 data. | With option A, M2 proceeds now. Without it, M2, and every milestone after it, waits for Alpaca. |
| **D3** | Accept M2's provisional configuration: see the table below | **Accept as provisional experiment assumptions** | The values can change later. Changing them reruns the evaluation, but no code changes. |
| **D4** | Approve the **M2 package** in §5 as one milestone, with automatic task commits | **Yes**, once D1 to D3 are settled | — |
| **D5** | Hourly route (unblocks only batch 3b): see the list below | **Internal-only evidence** as the default | Which permissions it needs (retention, and whether derived summaries count as disclosure) is **unverified**; A4 must establish it. |

**D3, the provisional configuration:**

| Setting | Value |
|---|---|
| Views valid until (OPEN-08) | The close of the next session after T. The final choice is still due by M3. |
| Horizon (OPEN-09) | 5 sessions, split-adjusted price return. Total return is reported separately. |
| Costs | 5 bps per side; a stress run at 10 bps |
| Walk-forward windows | 24 months training, 6 months testing, moving 6 months at a time |
| Promotion thresholds | **Not accepted**; the report shows "PROMOTION NOT ASSESSED" |
| M2-11 | Split into two tasks, so each fits the 1–3 hour rule |

**D5, the hourly answers needed:**
1. **Your situation:** which Alpaca account agreement applies, whether your use is personal and non-commercial, and whether the repository is public or will become public.
2. **The inquiry:** send or skip the prepared message to Alpaca (in `docs/hourly-access-review`, M1-12).
3. **Where the evidence lives:**
   - **internal-only:** raw data and individual values stay in `C:/Users/LOQ/hourly-verification`; the repository gets only verdicts, counts and file hashes. Whether even that is permitted is unverified (Codex review, 2026-10-14);
   - **derived summaries in the repository:** needs written permission.
4. **Later, each authorized separately:** account-key use for A3, A1 and A2, then checkpoint R, then the full run.

**Not reopened:** OPEN-01 and OPEN-06 (option A), protocol v0.3.10, R-07's accepted findings, and the reviewed M2 contracts.

## 5. The M2 package (one milestone, one Codex review)

**Gates before coding:** D1, D2, D3 and D4. **Branch:** `m2/milestone`, created from the merged `main`.

**Task order** (follows the dependency chain; specs are **not rewritten**):

| Step | Content | Est. (from specs) |
|---|---|---|
| 0 | **Docs integration:** cherry-pick `bb86480`, `6df10da` and `71133c1`, resolving PROGRESS by keeping the newer handoff state. Record D2 (roadmap §5), D3 (the M2 README configuration table), and the milestone workflow (shared rules §4 in AGENTS.md and CLAUDE.md, kept identical; `docs/tasks/README.md`; roadmap §4.3). Mark the specs accepted. Split M2-11 into 11a and 11b. | 1–1.5 h |
| 1 | M2-00 PIT split-adjusted view, with the coverage-evidence contract | 2–3 h |
| 2 | M2-01 versioned feature definitions | 2 h |
| 3 | M2-02 indicators | 2–3 h |
| 4 | M2-03 FeatureSnapshot | 2 h |
| 5 | M2-04 strategy interface | 2 h |
| 6 | M2-05 two daily rule strategies | 2–3 h |
| 7 | M2-06 MarketView and the ABSTAIN policy | 3 h |
| 8 | M2-07 pipeline and append-only lineage | 2–3 h |
| 9 | M2-08 returns and completed labels | 3 h |
| 10 | M2-09 metrics against matched baselines | 2–3 h |
| 11 | M2-10 SIMULATED research with costs | 3 h |
| 12 | M2-11a walk-forward folds and leakage guards | 1.5–2 h |
| 13 | M2-11b evaluation run records | 1.5–2 h |
| 14 | M2-12 static HTML report | 3 h |
| — | Batch checks, self-review, combined review package | 1–2 h |
| | **Total** | **≈ 33–42 h of estimated effort** (the roadmap says 35–45 h) |

**How it runs:**
- **Each task:** tests first, then that task's tests, the full suite in Git Bash and `ruff check .`. Then the PROGRESS entry and the task commit.
- **At the end:** the PowerShell suite and a clean install.
- **Delivery:** one review package for Codex, covering every commit, with §6 attached.
- **Stop only for:** a new test failure, a file outside a spec's allowed list, an ADR or architecture gap, or a contract that turns out to be unimplementable as written. Anything I stop for is reported with options; I don't fix it quietly.
- **The result:** M2 is "complete" only after Codex's review passes and you approve the merge. The visible result is the HTML report on NVDA daily history.

## 6. Pending for Codex at the next (milestone) review

1. **This document.** Claude's checks of the recorded state, the D2 reasoning (Part K vs the roadmap), and the M2-11 split.
2. **M1 deferred review items, still unscheduled:**
   - the M1-08 contract accepts `received_at < end_time` for a CLOSED bar;
   - `decide_prices` doesn't enforce one anchor per split epoch, and `decide_daily_volume` doesn't flag disagreement between anchors and documentation;
   - `series_values` counts entries from before the range among the skipped rows;
   - whether one bad vendor row should abort a whole import;
   - the `yfinance>=1.7.0` bound.

   **Proposal:** fix them as an M1 close-out package together with batch 3b, so M1 is finished in one go when the hourly evidence arrives. The M1-08 contract fix could instead go first in the M2 package, if the owner prefers.
3. **The workflow change** recorded in the shared rules (step 0 above), for review as a document change.
4. Codex's earlier self-reviewed follow-ups were accepted by Copilot in R-07. They are not re-reviewed.

## 7. October 31: an honest forecast

- **Remaining work by estimate:**
  - M2 needs about 33–42 h;
  - M3 to M9 add about 300–400 h on the roadmap's estimates;
  - M10 is outside version 1.
- **Observed throughput:** batch 4 (M1-14 to M1-16) took one session, but merging it took about 2 days of review and waiting.
- **What fits by October 31:** completing **M2**, and probably **M3**, looks realistic if D1 to D4 are answered quickly. **M1 completion** depends on Alpaca's answer, not on effort.
- **What doesn't fit:** M4 to M9 by October 31 is not credible. Each also needs ADRs or decisions first (ADR-010 to ADR-012, OPEN-07 and OPEN-10 to OPEN-17), and M7 needs a broker account and jurisdiction.
- **I'll revise this forecast after M2,** using measured time. If the full scope still looks infeasible, the choices are: more capacity, a later date, or a smaller first release. Changing scope or gates goes through the ADR route.
