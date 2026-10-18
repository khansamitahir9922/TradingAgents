# M4 milestone review package (Claude, 2026-10-18)

For Codex, and for the owner's review of the whole milestone: one review covering every M4 commit and how they work together. The owner approved M4 as one package on 2026-10-18 (D19–D34 as recommended, including D23's roadmap reading; 14 tasks, about 74 h, with the over-3 h exception). Merges, pushes, API keys, market-data downloads and M5 are not part of it. **Nothing here has been reviewed yet.**

## Scope and branch

- **Branch** `m4/milestone`, worktree `C:/Users/LOQ/TradingAgents-m4`. It was created from `docs/m4-specs` at `c59a863`, where Codex accepted the specs (`docs/reviews/codex-m4-spec-accepted-c59a863.md`). `main` is `4c56ac1` (M3 complete, not pushed).
- **Review range:** `c59a863..<closing commit>`, where the closing commit is the one that adds this file, named in the hand-off. Every commit has its own tests, checks and PROGRESS entry, so each can be reviewed alone.
- **Architecture:** v1.0 frozen and unchanged. **No ADR is proposed.**
  - **Processes:** the two from Part E, the Core Engine and the Execution Worker (`python -m investment_engine.core`, `python -m investment_engine.execution`). They exchange work only through database rows: NEW orders, cancel requests, and the outbox → event log.
  - **The kill switch** follows ADR-006.
  - **The research harness** (`simulation/`) is the narrow offline composition D24 allows, and is not a deployment topology.

## Commits

| Commit | Task | Notes |
|---|---|---|
| `99346f2` | Step 0 | The owner's approval and Codex's spec acceptance, recorded. |
| `5af0551` | M4-00 | Order contracts, `order_store`, the G3 state machine (D19/D20), `0011_orders.sql`, role triggers on `investment_engine.process_role`. |
| `e4f824d` | M4-01 | Outbox, event log, idempotent consumers (`processed_events` in the effect's transaction), `0012_outbox.sql`. |
| `2cf3a35` | M4-02 | `convert_approved`, the economic fingerprint, cancel requests, `orders cancel`. |
| `e075223` | M4-03 | Broker port, secrets loader, factory allowlist, worker and Core skeletons, layering rules, the secrets canary. |
| `6f566a3` | M4-04 | Kill switch: checksummed flag, OS lock, INTENT/APPLIED journal, `kill-switch status/halt/resume/sync-audit`. |
| `275311f` | M4-05 | The Pre-Execution Gate: 8 checks, typed `Missing`, the account-control lock before fresh reads. |
| `0fee5b7` | M4-06 | Simulated broker: the decision moment D, conclusive pre-open cancels, the cutoff, 5 bps slippage capped at the limit, `0013_sim_broker.sql`, `fees.json`. |
| `c55414a` | M4-07 | Worker step: publish, ingest, cancels, UNKNOWN lookups, submissions. |
| `77e02aa` | M4-08 | Crash recovery for both processes; the OS-process harness. |
| `dcb20ce` | M4-09 | Provisional projection: fills, splits, dividend receivables, reservations; Unavailable for anything unsupported. |
| `c8f9173` | M4-10 | Promotion assessment, `proposed_thresholds.json`, `0014_promotion.sql`; PAPER never ACCEPTED in M4. |
| `a2a6c08` | M4-11 | Part J invariants over 200 seeded sequences each. |
| `04480fa` | M4-12 | Part J's fault list with real OS processes (12 scenarios). Its full run had 2 layering failures caused by M4-13's then-uncommitted files and a flaw in the rule; diagnosed in the entry and fixed in M4-13. |
| `83e7dbb` | M4-13 | `intents simulate` and `intents order-log`; the harness; the order log. The rule-4 stop and replay knowledge were found and fixed before this commit (see below). |
| `653e4fb` | M4-09 follow-up | Whole shares after a split stored as `4.000000000000` (found by the full NVDA run). |
| `35f784a` | M4-10 follow-up | Self-review: the promotion metrics cross into float through `to_float64`, which refuses NaN. |
| `50a5a79` | M4-03 follow-up | The process tests decode UTF-8, which fixes 2 PowerShell-only failures. |
| (closing) | Milestone close | This package and PROGRESS; documents only. |

## Batch checks

- **Git Bash full suite** (`check4.sh`, at the tree of `50a5a79`): **1 failed, 3258 passed**, 7 skipped, 3 deselected, 20 warnings, 99 subtests passed, in 1285.08 s. The failure is the baseline cache-location test. **No new failures.**. No `postgres` test skipped.
- **PowerShell full suite**, `& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfEs` from the M4 worktree:
  - **First run, at `653e4fb`:** 4 failed, 3254 passed, 7 skipped, 3 deselected, 23 warnings, 99 subtests passed, in 1736.04 s.
    - Two failures are the recorded PowerShell baseline: `test_cli_commands.py::test_every_command_is_registered_when_run_as_a_module` (cp1252) and `test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`.
    - **Two were new:** `test_execution_process.py::test_no_other_process_reads_the_workers_secrets[admin-cli-intents]` and `[admin-cli-orders]`. They had the same cp1252 cause, in M4-03's new test, so they were fixed in `50a5a79` rather than added to the baseline.
  - **Final run, at `50a5a79`:** RESULT_PS.
- **`ruff check .`:** passed. `git diff --check`: clean.
- **Clean install:** two fresh `py -3.11` venvs, then `pip install .` and `pip install ".[engine]"`; the CI import passes in both.
  - Installed-code smoke (`-I`, from outside the repository, after a `--force-reinstall --no-deps` of the final tree): passed. **Base:** 6 M4 modules (order states and orders, envelope, kill-switch flag, order log, intents CLI) load from site-packages, and psycopg is absent. **Engine:** 22 M4 modules load from site-packages; `schema_pg` `0001`–`0014`, `risk/proposed_limits.json`, `execution/fees.json` and `evaluation/proposed_thresholds.json` are packaged; `build_broker("simulated", PAPER)` is refused; psycopg is 3.3.6; the CLI registers `intents simulate|order-log` and `kill-switch halt|resume`.
- **Not run:**
  - CI (nothing pushed);
  - Python 3.12–3.13 and the `TZ=America/New_York` job;
  - any live, provider or network call, or market download;
  - a PostgreSQL server restart (the owner's shared server; M4-08 rule 6 uses a dropped connection instead).
- **Suite time:** about 16 minutes at M4-00, rising to about 28 at the end (M3 closed at about 12–13). The growth comes from M4-11's 200-seed invariant runs, M4-12's real-process scenarios (69 s for the file), the process tests and M4-13's runs. Run-to-run variance is large on this machine. Nothing was weakened to save time; `IE_INVARIANT_FLOW_SEEDS` can lower the seed count locally.

## The optional full NVDA run (M4-13, recorded, not asserted)

**Setup.** Everything ran in a throwaway PostgreSQL database and a scratch data directory. The data directory held a *copy* of the M2 report's verified market store. The M2 report's `operational.sqlite3` was copied in with `db copy-from-sqlite`: 1954 lineage records, the instrument and its symbol mapping. Then came M3-14's documented setup: R2, RESEARCH, Level 2, a 100,000 USD start, risk-1/policy-1, kill switch resumed. Then `intents simulate --account R2 --from 2019-01-02 --to 2026-10-09` (159.5 s) and `intents order-log`. Nothing was downloaded, and the owner's data and database were untouched.

**Result.**

| Outcome | Count or detail |
|---|---|
| Orders | 3, all FILLED |
| BUY 50, 2019-10-17 | 196.10 at the open |
| BUY 1, 2019-10-21 | 192.39, an intraday touch stamped at the close |
| SELL 204, 2022-04-21 | 216.98 at the open, after the 4:1 split of 2021-07-20 |
| Filled notional | 54261.31 USD (fees 0) |
| UNKNOWN orders, stops | none |
| Dividends | ten, 8.16 USD receivable each |
| RISK_REJECTED (drawdown halt from 2023-01-24) | 831 |
| BEARISH, nothing held | 218 |
| ABSTAIN (warm-up) | 199 |
| NEUTRAL | 93 |

The halt checks out:

- The strategy only adds, so the position grew to about 40% of equity.
- The April 2022 sale realized about 134.4k against a peak near 158k, which is 15.1%.
- The check first ran at the next bullish proposal, and only an Admin clears it (D3).

Three runs gave identical order ids.

**What the run found, all fixed before review.**

1. `simulate` first used `StoreKnowledge`, which counts a bar only after its download time. That gave 0 orders.
2. The order log printed `None` and blanks for an empty account.
3. Split share counts carried the ratio's scale, as in `653e4fb`.

## Where to look hardest

1. **The transition authority and compare-and-set** (`oms/order_store.py`, `0011_orders.sql`):
   - CORE creates NEW, and EXECUTION does everything else;
   - one event per `aggregate_version`;
   - fill accounting is separate from state edges;
   - anomalies create neither a version nor an event;
   - the session variable is a consistency check, not authentication (documented).
2. **No broker call inside a transaction** (`execution/worker.py`, `cancels.py`, `ingest.py`, `recovery.py`):
   - each call precedes its own transaction;
   - SENDING and an UNKNOWN on timeout mean nothing is ever resent (M4-07, M4-08, and M4-12 scenarios 1 and 3).
3. **The gate** (`execution/gate.py`, `reads.py`):
   - typed `Missing` versus False;
   - the account-control lock before fresh reads;
   - pre-open submission;
   - the `view` check catching a revision received after the proposal (M4-12 scenario 9, and the short-range M4-13 test).
4. **Kill switch atomicity** (`killswitch/flag.py`, `admin.py`):
   - the flag replace is the publication point;
   - a missing flag with no APPLIED line resolves to NOT_APPLIED;
   - a resume is refused while the step itself recorded UNRESOLVED;
   - cancels are never blocked.
5. **The simulator's causality** (`simulated_broker.py`):
   - D is the first time a CLOSED bar is actually known, delivery latency included;
   - materialization happens before every call;
   - pre-open cancels are conclusive, then PENDING until D, then TOO_LATE;
   - the missing-bar cutoff is the next open.
6. **Provisional projection order** (`portfolio/provisional.py`):
   - at equal times, actions come before fills;
   - dividend entitlement is fixed at the previous close;
   - an unresolved order crossing an action is Unavailable;
   - valuation waits for a post-action close.
7. **M4-13's knowledge** (`intents_cli.py` `simulate`): the replay's, fed from 60 days before the first view to three weeks after the range. See open item 2.

## Deviations and choices for review (each detailed in its task entry)

1. **M4-02:** the intent-store writer-set test now lists `convert`. That is the store method M4-02's file list allows.
2. **M4-03 → M4-06:** `test_execution_process.py` asserts the allowlist as built (`simulated` for RESEARCH only).
3. **M4-07: no stored broker cursor**, because it would need a schema change outside the task's files. Ingestion is idempotent by `broker_ref` and fill id instead.
4. **M4-08 and M4-09: `execution/__main__.py` edits** (entry-point wiring: `--once` runs recovery; the gate reads).
5. **M4-10: the gate's PAPER promotion read stays a fixed "not assessed".** M4-03's layering forbids `execution` importing `evaluation`. This is safe while nothing can be ACCEPTED (D22).
6. **M4-13: `execution/factory.py` gains `build_gate_reads`** (M4-06's file). The harness may import only the factory, worker, port and simulator.
7. **M4-13: the layering rule** now handles `from module import attribute`, with a test of both cases.
8. **M4-13: "cancels aren't blocked with the flag disabled"** isn't asserted inside the simulated run. With the flag off, every order is GATE_REJECTED before reaching the broker. The same worker class is covered by `test_worker_cancels.py::test_a_cancel_goes_through_with_trading_disabled_and_closes_when_final`.
9. **M4-13 rule 2 phases, as built:** a worker step at each view's time (ingests everything decided by then), the Core's proposal and conversion, then a worker step one microsecond later (pre-open submission). The spec's phase "at d's decision moment" is reached at the next view's time, or at the final step. Fills are always ingested before the next proposal is sized.

## Open items for Codex and the owner

1. **Duplicate stored views.** `stored_views`, like M3's `_views_between`, proposes every lineage record in the range. Running `views replay` over a range that already has records (for example after `db copy-from-sqlite`) doubles the views; the first full-run attempt showed 3908. The proposals stay idempotent per lineage id, but they are proposed twice. A later task could deduplicate by decision content.
2. **Equal-time events in `simulate`.** M3's `propose_over_replay` uses `through_sequence` to hide equal-time events after a view's own bar. `simulate` feeds the whole range up front and uses `complete_through`, so an event delivered at exactly a view's time with a later sequence would be visible to that proposal. Daily single-instrument data hasn't produced such a pair. Exact parity would need the harness to take a per-view knowledge factory.
3. **The order log's corporate-action list** comes from the latest stored snapshot, so it lists the actions applied up to the last proposal.
4. **Carried over from M3:** the S1 condition, the private replay-reader access debt, and the `listen_addresses = 'localhost'` setup item.
