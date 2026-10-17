# M3 milestone review package (Claude, 2026-10-17)

For Codex, and for the owner's complete milestone review: one review of the whole M3 milestone, covering every commit and the integrated behaviour. The owner approved M3 as one package on 2026-10-16 (D1–D18 as recommended, 15 tasks, 52 h, the 4 h exception). Merges, pushes, API keys, market-data downloads and M4 are not part of it. **Nothing here has been reviewed yet.**

## Scope and branch

- **Branch** `m3/milestone`, worktree `C:/Users/LOQ/TradingAgents-m3`, created from `docs/m3-specs` at `6085fd9` (Codex accepted the specs there). `main` is `b7c5d2a` (M2 complete, not pushed).
- **Review range:** `6085fd9..<closing commit>`: the commit that adds this file, named in the hand-off. Every commit is reviewable on its own: each has its own tests, checks and PROGRESS entry.
- **Architecture:** v1.0 frozen and unchanged. No ADR is proposed. PostgreSQL (ADR-008, D16) is the Operational Database from M3. No process, service or broker is added; admission is serialized with database locks inside existing transactions.

## Commits

| Commit | Task | Notes |
|---|---|---|
| `9e996ba` | Step 0 | Specs accepted; PostgreSQL checked; milestone started. |
| `7b18eb4`, `f95517e` | M3-00 | Local PostgreSQL harness and the libpq connection guard. The follow-up retries a test-database drop while autovacuum holds it. |
| `fde0fa3`, `5c84aa0`, `37f635d` | M3-01 | Schema and migration runner. Follow-ups: psycopg imported lazily; schema tests follow the latest script. |
| `a0976f8` | M3-02 | The existing stores on PostgreSQL through the database port. |
| `5ca7136`, `6eafb86` | M3-03 | Copy SQLite into PostgreSQL; the CLI moves onto it. The follow-up makes the copy test follow the latest script. |
| `d9d790f` | M3-04 | Append-only audit store. |
| `8d213af`, `588536a` | M3-05 | Accounts, operators, autonomy, Admin CLI. The follow-up lets the Admin CLI register its own groups, so later tasks don't touch `cli.py`. |
| `c689d07` | M3-06 | Versioned risk limits, policy rules, latched halts. |
| `d4229d7`, `093cc2f` | M3-07 | Raw reference prices and the declared snapshot. The follow-up adds `complete_through` for replay knowledge and a drawdown-peak query; it edits `0008` in place (see below). |
| `8d037c4` | M3-08 | OrderIntent contract, decision contracts, position sizer. |
| `075b88e` | M3-09 | Intent store, G2 state machine, compare-and-set. |
| `43af754` | M3-10 | Deterministic policy checks. |
| `d1678fb` | M3-11 | Deterministic risk checks; reduce as a new version. |
| `485ed75`, `c273a9b` | M3-12 | The intent pipeline, intent lineage, replay proposals. The follow-up never stores a proposal for a view that names no lineage. |
| `e333c22` | M3-13 | Approve, decline and expire at the Admin CLI. |
| `4224fa5` | M3-14 | CLI report of proposed intents with reasons; `cli.py` registration only. |
| `bd18615` | M3-04/05/06/07/09 | Fresh-process probes take the test DSN from the environment, never argv (see incident 3). |
| (closing) | Milestone close | Batch checks, this package, PROGRESS. Documents only. |

## Batch checks (at `bd18615`; the closing commit changes only documents)

- **Git Bash full suite** (the last task-level run, `check3.sh`): **1 failed, 2816 passed**, 7 skipped, 3 deselected, 99 subtests passed, in 625.84 s. The failure is the baseline `test_yfinance_keeps_its_cache_out_of_the_users_home`. No `postgres` test skipped.
- **PowerShell full suite** (`& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfEs`, cwd the M3 worktree): **2 failed, 2815 passed**, 7 skipped, 3 deselected, 21 warnings, 99 subtests passed, in 645.18 s. Both failures are the recorded PowerShell baseline: `test_every_command_is_registered_when_run_as_a_module` (cp1252) and the cache-location test. The extra warning comes from the cp1252 test, as in M2's PowerShell run. **No new failures.**
- **`ruff check .`:** passed. `git diff --check` clean.
- **Clean install: passed**, in two fresh `py -3.11` venvs.
  - `pip install .`: the CI import (`tradingagents, cli.main, investment_engine`) passed from the repository root. From outside it, `investment_engine.intents_cli` imports from site-packages without psycopg installed.
  - `pip install ".[engine]"`: the CI import passed. From outside the repository, eleven M3 modules load from site-packages; all ten `schema_pg` scripts (`0001`–`0010`) and `risk/proposed_limits.json` are packaged; psycopg is 3.3.6 (binary); the CLI registers `intents approve|decline|expire|list|propose|show` and `views`.
- **Not run:** CI (nothing pushed); Python 3.12–3.13 and the `TZ=America/New_York` job; any live, provider or network call; any market download.
- **Suite time:** about 10–11 minutes now, against about 6 at M3-11. The new time is mostly the race tests: 50 repetitions each for admission (M3-12) and for approval against `set_autonomy` and `limits publish` (M3-13). The owner accepted a five-minute suite. A later optimisation could cache the 20 Parquet reads per proposal behind the average daily value; nothing was weakened to save time.

## Where to look hardest

1. **Intent pipeline atomicity and the outcome matrix** (`oms/pipeline.py`, M3-12 rules 1–8):
   - one managed transaction per (account, view), under the account-control lock;
   - the test injects a failure at every write of a successful run in turn;
   - exactly the records of the B3 matrix exist, with `NotRun` for risk after a policy rejection.
2. **BUY admission (B5):**
   - `buy-admission|account|session` is taken after the account-control lock, and the admission commits under it;
   - `admitted_buys` counts intents ever admitted, so expiry, decline and rollback never free a slot;
   - the 50-repetition race test.
3. **Approval serialization (S4, M3-13):**
   - the command acts on the intent as read before the lock; a change meanwhile is "intent changed meanwhile" through the aggregate-version check;
   - the race tests gate both sides just before the account-control lock and record lock order (commit order). The assertion is "the change first means refused; the approval first means approved".
4. **Two times, never merged (R2, R3):**
   - authorization is at the real command time, and the intent's controls at the business time;
   - RESEARCH needs an explicit replay time, and PAPER takes none (see deviation 1);
   - expiry runs per account; `expire_paper_due` never touches RESEARCH accounts.
5. **Replay determinism (S2):**
   - identities hash deterministic content only;
   - `IntentLineageRecord` hashes the autonomy setting's `setting_id`, not its provenance. A test recreating the setup on another day found this bug and now covers it;
   - CLI-only setup and replay is byte-identical across fresh databases set up on different days, and matches `propose_over_replay` called directly with a feed over the whole store.
6. **Point in time:** `ReplayKnowledge` with `through_sequence` and `complete_through`. The tests cover a correction available before T but delivered after it, an equal-time pair, a decision bar not yet delivered, and a gap in the volume window. None of these ever falls back to an older bar.

## Incidents and deviations (all recorded in the task entries)

**Incidents**
1. **Test-file recovery (M3-07).** A file write with an invalid newline argument truncated the then-untracked `tests/engine/test_portfolio_snapshot.py`, and a retry appended to the empty file. I rebuilt it in full from this session's own text before running anything; nothing in git was affected. **Please check the restored tests against M3-07's acceptance list.** The same write bug came up again in a later helper script and was caught before it ran, with backups taken.
2. **Discounted M3-14 run.** The first full run after M3-14 showed 10 new failures. Every one was a subprocess that Windows couldn't start (exit 0xC0000142, DLL initialisation failed), including the unrelated `cli.main backtest --help`. That run probably overlapped a check I had just stopped. The failing files passed alone, and the rerun passed with only the baseline failure. Both runs are in the M3-14 entry.
3. **Test DSN printed on failure.** In that failed run, five fresh-process tests printed their subprocess command line, which carried the test DSN **with its password**. It reached a local scratch log, now redacted, and this session's tool output; nothing was committed or sent anywhere else. `bd18615` moves the DSN into the subprocess environment. **Owner action suggested:** change the local `ie_dev` test password and update `INVESTMENT_ENGINE_TEST_PG_DSN`.

**Deviations and choices for review**
1. **PAPER takes no time.** `propose` and `expire_due` take `at=None` for PAPER and read the live clock once; a supplied time raises. The M3-12 draft compared a supplied time with a second clock read, which a real LiveClock never matches. The contract's `at: datetime` became `datetime | None`, and `expire_paper_due` takes `clock=` as the contract shows.
2. **Private M2 reader access.** `ReplayKnowledge` reads `ReplayKnowledgeReader`'s private `_candles`, `_check_at` and `_delivered_until`, because `decision/pipeline.py` isn't in M3's allowed files. A public `candle_revision` and a public "complete through T" query on the reader would be cleaner in a later reviewed change.
3. **`complete_through` (M3-07 follow-up).** The reader refuses any T after its last delivered event. The pipeline proposes at the view's time, after the last bar; `propose_over_replay` has fed every event delivered by then, so it vouches for completeness up to that time.
4. **`0008_portfolio.sql` edited in place** to add `equity` for the peak query. The branch is unmerged and only per-test databases used the script; a new script would be needed after any merge.
5. **Contract extensions:**
   - `build_snapshot` takes `source`, and the `Knowledge` port gains `actions_between` (M3-07);
   - `clear_halt` takes an optional `equity_now` and `effective_at` (M3-06);
   - `approve`/`decline` take `os_user`, and `record_refusal` audits a CLI-decided refusal (M3-13).
6. **M3-13 CLI:** `--version` and `--reason` are checked by the command, not by Typer's required options. Typer's usage box isn't ASCII, and a missing reason is an audited refusal. A PAPER `--at` is refused even when it equals the live time. A missing RESEARCH `--at` is a usage error and isn't audited.
7. **M3-14:**
   - `list` shows each intent's current state beside its proposal outcome;
   - `list` and `show` open the database read-only;
   - `propose` passes no action coverage, so an account declared with holdings gets PREREQUISITE_MISSING. M3 accounts are cash-only by default.
8. **Lineage `final_state`** is the state the pipeline routed a version to. A later expiry or approval is in the intent's transition history.
9. **M3-08:** the OrderIntent tests are in `test_sizer.py`; there's no separate `test_order_intent.py`.
10. **M3-00:**
    - tests-first wasn't observed for the guard and fixture;
    - "dropped even after a failing test" is tested through the fixture's own teardown, not a nested pytest run;
    - the async probes run without an event loop, because Windows' loop opens a socket pair the socket guard refuses.

## Owner items

- `listen_addresses` is still `'*'`; `pg_hba.conf` allows only loopback. Set it to `'localhost'` (setup guide step 3).
- Change the `ie_dev` test password (incident 3).
- Merge and push need your explicit word. M4 hasn't been started.
