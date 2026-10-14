# M2 milestone review package (Claude, 2026-10-14)

For Codex: one review of the whole M2 milestone, covering every commit and the integrated behaviour. The owner approved the milestone as one package on 2026-10-14. Merges, pushes, key use and downloads are not part of it.

## Scope and branch

- **Branch** `m2/milestone`, worktree `C:/Users/LOQ/TradingAgents-m2`, created from `main` at `53c51bd` (the reviewed M1 daily work, fast-forwarded with the owner's approval; not pushed).
- **Review range:** `main..m2/milestone` (`53c51bd..HEAD`).
- **Data:** verified **daily** NVDA data only. Nothing in M2 reads H1. M1's hourly parts stay unfinished (batch 3b), and M1 completion criteria are unchanged.

## Commits

| Commit | Task | Notes |
|---|---|---|
| `0b2afae`, `54b9297`, `75ce29e` | M2 specs | Cherry-picks of the reviewed `bb86480`, `6df10da`, `71133c1`; spec files byte-identical to `71133c1`. PROGRESS conflicts were resolved in step 0. |
| `cdde038` | Step 0 | Codex's five package-review corrections; provisional configuration; milestone workflow in shared rules §4; PROGRESS three-way merge; review records. |
| `be99efa` | M2-00 | PIT split-adjusted view; structured coverage evidence; completed-bar cutoff. |
| `1b4b5c0` | M2-01 | Versioned feature definitions; float64 boundary. |
| `0bf399e`, `bbafcb8` | M2-02 | Indicators. The follow-up declares RSI14's 200-session seed window, which M2-02 rule 2 requires. |
| `69352f1` | M2-03 | FeatureSnapshot. |
| `1e2a38f` | M2-04 | Strategy interface; guarded feature access. |
| `4545b93` | M2-05 | Trend and pullback strategies. |
| `2a8c3ac`, `4edfd57` | M2-06 | MarketView and policy 0.1.0. The follow-up removes two unused test imports that slipped through; see the process notes. |
| `b99d124` | M2-07 | Pipeline, `ReplayKnowledgeReader`, LineageRecord and store, migration 0002. |
| `85dfc39` | M2-08 | Price and total returns; completed labels. |
| `f1b6552` | M2-09 | Direction metrics; matched baselines. |
| `1074094` | M2-10 | SIMULATED research with costs. |
| `57f797e` | M2-11a | Walk-forward folds and leakage guards; `RevisionCache`. |
| `0b7db92` | M2-11b | Evaluation records; migration 0003. |
| `7028523`, `d155e29` | M2-12 | Report renderer. **`7028523` carries M2-11b's message by mistake**; `d155e29` corrects PROGRESS. History was not rewritten. |
| (final) | Milestone close | Batch checks, self-review, report results, this package. |

## Batch checks (at `d155e29`; the closing commit changes only documents)

- **Git Bash full suite:** **2341 passed, 1 failed** (baseline `test_yfinance_keeps_its_cache_out_of_the_users_home`), 4 skipped, 3 deselected. Every task commit's own run is in PROGRESS.
- **PowerShell full suite** (`& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`, cwd the M2 worktree): **2340 passed, 2 failed**, 4 skipped, 3 deselected. Both failures are the recorded PowerShell baseline: `test_every_command_is_registered_when_run_as_a_module` (cp1252) and the cache-location test. **No new failures.**
- **`ruff check .`:** passed. Whitespace is clean.
- **Clean install: passed.** (A fresh `py -3.11` venv with `pip install ".[engine]"`, the CI import from the repository root, and an installed smoke check from outside it covering the M2 modules, schemas 0001–0003 and the append-only triggers.)
- **Not run:** CI (nothing pushed), other Python versions, any live or provider call, market download or hourly gate.

## The report (offline, from the saved verified recordings)

- **Output:** `C:/Users/LOQ/TradingAgents-proposals/m2-report/nvda-research-report.html` (374,462 bytes), plus `summary.json`. Built by `build_report.py` in the same folder, outside the repository (M2-12 adds no command).
- **Inputs:** `tests/engine/fixtures/yfinance` (recorded 2026-10-12 08:25:51 UTC with yfinance 1.7.0), imported through the verified M1 importers with their fetchers fed from the recordings; no network.
- **Pipeline output:** 1954 daily bars, 33 actions and 1954 views with lineage (1443 BULLISH, 219 BEARISH, 93 NEUTRAL, 199 ABSTAIN, mostly warm-up in 2019). Two evaluation records: 11 complete 24/6/6 folds at 5 bps and at the 10 bps stress cost.
- **What the numbers say (SIMULATED, not advice):**
  - Directional accuracy mostly **equals always-up on the same dates**, because the rules were long most of the time.
  - In 2022-H1 they beat always-up (43.0% vs 38.3%); in 2022-H2, 2023-H1 and 2025-H1 they did worse.
  - The information coefficient is **negative** in every fold where it is defined (−0.11 to −0.31).
  - Strategy returns trail buy-and-hold in rising folds and lose less in 2022-H1 (−37.2% vs −52.0%).
  - **No profitability or significance is claimed, and promotion is not assessed.**

## Where to look hardest

1. **Point in time and leakage:**
   - `quant/adjusted.py` (`require_coverage`, `completed_daily_bars`, `visible_actions`);
   - `decision/pipeline.py` (`ReplayKnowledgeReader`; health and snapshot both read through it);
   - `evaluation/returns.py` (`training_eligible`);
   - `evaluation/walk_forward.py` (cutoffs, purge counts, test filtering).
2. **Law 9:** `decision/market_view.py::_law9`. DEGRADED abstains; a missing health entry abstains; unestablished coverage and an unavailable snapshot abstain.
3. **Lineage integrity:** `lineage/records.py`. The codec covers enums before strings, the hash excludes the id and evidence references, and stored content is re-verified on `get`.
4. **Money:** `evaluation/simulation.py`. Decimal throughout; whole shares; costs quantized to 0.0001; cash non-negative.
5. **Report honesty:** `reporting/html.py`. Unavailable values show their reason, strengths are scales, every string is escaped, and there are no remote resources.

## Contract deviations and extensions (decide or accept)

- **M2-03 `FeatureSnapshot`** adds `warmup` (feature keys still warming up from the history boundary) and `decision_close` (the adjusted close of the decision bar).
- **M2-02 `RSI14`** declares `seed_sessions=200` (follow-up `bbafcb8`), so its inputs are a fixed window.
- **M2-07** gathers health inputs with M1-16's private `_lookback`; M1-16's public contract is unchanged. Lineage and evaluation content is stored zlib-compressed. The SQL triggers use SQLite syntax and need rewriting for PostgreSQL in M3.
- **M2-09** takes `PredictionView(source, prediction_session, view)`, because a MarketView carries neither, and a required `calendar` to check horizons. It also adds `disclosures`.
- **M2-10 `EvaluationRun`** adds `source`, `instrument_id`, `first`, `last`, `as_of`, `cash_curve`, `ending_shares` and `complete`, plus a `Benchmark` type.
- **M2-11** stores an `EvaluationRecord`, the whole walk-forward evaluation, rather than a bare `EvaluationRun`, because rule 5 requires fold boundaries and versions in the stored run. `walk_forward` takes the replay's views and coverage evidence rather than a pipeline object. `RevisionCache` (an in-memory PIT projection, tested equal to the store reader) keeps evaluation fast.
- **M2-12** takes an optional `adjusted_closes` series for the chart. Each view's own close is adjusted as of its own T, so plotting those would show a false crash across 2024-06-10.

## Process notes (honest record)

- **Tests-first evidence:**
  - M2-00 to M2-08: tests were written before the code, but **not run before implementing**. The M2-00 and M2-01 PROGRESS entries say the test file "failed to import before the module existed"; that was inferred, not observed.
  - M2-07's implementation was drafted **before** its tests.
  - From M2-09 on, every test file was run first and the collection failure observed.
- **Slipped commits:**
  - `2a8c3ac` was committed with a ruff F401 failure because my local check script didn't stop on it; it now does.
  - `7028523` has the wrong message, as described in the commit table.

## Pending items for this review (non-blocking)

- **M1 deferred review items** (PROGRESS "Open issues"), including the M1-08 contract accepting `received_at < end_time` for a CLOSED bar. M2 refuses such bars itself (M2-00 rule 7).
- **`FeatureDefinition` is unhashable** (its parameter mapping is read-only); a key-based `__hash__` is a small M2-01 follow-up.
- **Dividend coverage:** the report treats the imported Yahoo dividend list as complete. That is an explicit, labelled research assumption; only split history is checked against cited filings.
- **Promotion thresholds** (OPEN-09) remain unaccepted; **OPEN-08** is still due by M3.
