# M4 re-review fix package (Claude, 2026-10-19)

For Codex's re-review of R1–R4 and notes N1–N3 from `docs/reviews/codex-m4-rereview-af18b48.md`. Codex's handoff asked for one combined follow-up package and counts as the owner's instruction for this step. The nine findings it resolved (B1, B4, B5, B6, B8, B9, B11, B12, B13) are not reopened. **Nothing has been merged or pushed.**

## Range and branch

- **Branch** `m4/milestone`. **Range:** `af18b48..` the commit that adds this file (named in the hand-off): one fix commit per residual, one for the notes, and this documents-only close.
- **Architecture:** v1.0 frozen and unchanged; no ADR. No new migration in this range. G3, PAPER refusal, no-resubmit and kill-switch authority are unchanged.
- **Checks per commit:** as before, each full Git Bash suite ran on that commit's exact tree, and the commit was refused unless the staged tree equalled the checked one (PROGRESS.md aside).

## Commits

| Commit | Item | Summary |
|---|---|---|
| `3d2d3bf` | R1 | `@exact` back on `build_order_log`; the stored log is byte-identical under any Decimal context. |
| `1febe97` | R4 | Consumer rotation: each round starts after the aggregate last attempted and wraps, so failing heads never starve later ones. |
| `fd4bed8` | R3 | `replay_with_outstanding_actions`: the shared composition seeds every earlier action revision; projections require its `ActionHistory`. |
| `6875ab0` | R2 | Both CLI replay paths rebuild their feed with the stored views' own latency; disagreeing views are refused. |
| `1b4134e` | N1–N3 | Broker-call failures are unknown outcomes (cancels stay SENDING with an anomaly); cutoff named as business time beside record time; truthful history caption. |
| (this commit) | Close | This package and PROGRESS. Documents only. |

## Requirement → test → evidence

| Item | Tests | Red evidence |
|---|---|---|
| R1: the whole log under hostile contexts | `test_simulated_run.py::test_the_whole_log_is_identical_under_any_callers_decimal_context` | failed first (precision 2); Codex's probe passes |
| R4: a page of failing heads; recovery exactly once | `test_consumers.py::test_a_page_of_failing_heads_never_starves…`, `::test_a_full_page_of_failing_heads_rotates…` | both failed first; probe passes |
| R3: announced before the feed, effective after the start (split, dividend); `propose_over_replay` composition; earlier B7 cases on the new API | `test_provisional_positions.py` (R3 split/dividend, history-start, unestablished history), `test_order_log.py::test_propose_over_replay_supplies_actions_announced_before_its_feed` | the bare feed is Unavailable in each case; the composition gives 100 shares or the receivable |
| R2: nonzero latency, both CLI paths; disagreeing views refused | `test_replay_delivery_history.py` (3 tests, with M2's own `run_views` at ten-minute latency) | all three failed first (revision 2; no refusal) |
| N1: one failing broker cancel | `test_worker_cancels.py::test_a_broker_error_on_one_cancel_leaves_it_retryable…` | failed first (RuntimeError aborted the step); Codex's probe passes |
| N3: history caption | `test_kill_switch.py::test_a_halt_never_calls_the_history_complete…` | failed first ("complete") |
| N2: cutoff naming | `test_simulated_run.py::test_the_log_pins_code_and_calendar_versions_and_its_cutoff` (new key) | wording change |

**Codex's re-review probes** (`codex_m4_rereview_probes.py`, run unchanged from an excluded local copy, at `1b4134e`): **4 of 5 pass**: R1 (log totals), R4 (failing heads), R2 (delivery history, with M2's own producer) and N1 (one failing cancel). The fifth, R3's, raises `TypeError` before its assertions, because it constructs `ReplayKnowledge(known_from=...)`, which R3 removes (design point 1); its scenario passes through the composition in `test_provisional_positions.py`.

## Decisions and design points, for review

1. **R3: proof, not a timestamp.** `ReplayKnowledge(known_from=)` is removed, and the projection requires an `ActionHistory` from the shared composition. The review's own text says a feed-start timestamp is not proof. Codex's R3 probe still passes `known_from`, so it no longer runs; its scenario is tested through the composition. The composition reads the whole store's action revisions before the feed's start, at the same latency, and never changes a delivery time.
2. **R2: latency recovered from lineage.** It is exact, because M2 generates a view at its decision bar's delivery and the lineage keeps that bar's `available_from`. No stored record changes. Mixed latencies, missing lineage or no single decision bar are refused.
   - **Two test fixtures, corrected.** Their views were made five minutes after the close, so their true latency is five minutes. B3's integrated test is rewritten: under M1's frozen ordering a revision precedes a close at one instant, so a stored view claiming the earlier revision is inconsistent and its proposal refuses.
3. **R4: in-memory rotation.** It needs no migration. A restarted consumer begins at the start and rotates from there, and nothing is skipped or duplicated either way.
4. **N1: what is caught.** Exceptions from broker calls are normalized at the port; the worker's own database errors are not, and still end the step and reach B4's reconnect. KeyboardInterrupt and SystemExit are never caught.

## Batch checks

- **Git Bash per commit:** see each entry; only the baseline cache-location test fails.
- **Incident, recorded:** the notes' first full run crossed midnight (2026-10-19 to 20) and showed the same 13 failures as the earlier midnight runs: the baseline plus 12 date-sensitive upstream TradingAgents tests, the identical set. The commit was held until a full rerun on the unchanged tree was clean (3339 passed, baseline only). **Correction:** that commit's PROGRESS entry reuses the earlier note's wording "run alone afterwards, all 61 passed". For this run that isolated check was *not* repeated; the clean full rerun is the evidence. History isn't rewritten.
- **PowerShell full suite at `1b4134e`:** **2 failed, 3338 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 1807.68 s, on code identical to `1b4134e` (checked with `git diff`). Both failures are the recorded PowerShell baseline (the cp1252 CLI test and the cache-location test). **No new failures**.
- **Clean install** (fresh worktree of `1b4134e`, `--force-reinstall --no-deps` into the base and engine venvs; `-I` smoke from outside the repository): **passed**. Base: 6 M4 modules from site-packages, psycopg absent. Engine: 22 modules; schemas `0001`–`0015`, the limits, fees and thresholds files; `simulated` refuses PAPER; psycopg 3.3.6; the CI import passes in both.
- **Not run:** CI (nothing pushed); other Python versions, OSes or the TZ job; live providers or brokers; a PostgreSQL server restart.
