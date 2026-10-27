# M6 milestone package (implementer: Claude Code, 2026-10-27)

| | |
|---|---|
| Branch / worktree | `m6/milestone`, `C:/Users/LOQ/TradingAgents-m6`, from `main` `d277440` |
| Range | `d277440..` this commit: specs `e49c670`, M6-00..10, review fixes `e312999..e5c3169`, handoff `5e13b97`, and the M6-11 commit that adds this file |
| Review state | Codex **accepted M6-00..10 at `5e13b97`** (`codex-m6-rereview-e5c3169.md`, root checkout, untracked). The M6-11 commit (measurement, live checks, records) is new and awaits Codex. |
| Merge / push | Neither done. The merge needs the owner's separate approval. |

## Commit map

- **Specs:** `e49c670` (M6-README, M6-00..11; D45–D54 approved, D47 = USD 0).
- **Tasks:**
  - `767b2f0` M6-00
  - `1f80ce6` M6-03 (upstream U1)
  - `10d1498` M6-01
  - `88e29c3` M6-02
  - `70af044` M6-04
  - `711504d` M6-05
  - `7c087d8` M6-06
  - `ab72383` M6-07
  - `5872958` M6-08
  - `b183b96` M6-09
  - `d09e850` M6-10
  - `06c1161` B7 clock fix
  - `e312999` first handoff
- **Review fixes:** see `claude-m6-review-fix-package.md` for the map of finding to commit to regression (B1–B11, N1–N6, R1–R3). Handoff: `5e13b97`.
- **M6-11:** this commit adds `docs/reviews/m6-measurement.md`, `tests/engine/test_research_live.py`, this file, and the M6-11 records in the spec, README and PROGRESS.

## Checks

- **Package, on `e5c3169`** (code identical to `5e13b97`):
  - Git Bash and PowerShell full suites: 3968 passed each. The only failure is the baseline `test_yfinance_keeps_its_cache_out_of_the_users_home`.
  - Fresh base and `[engine]` installs passed; Ruff passed; whitespace clean.
  - Codex separately ran 282 focused tests in Git Bash and 9 in PowerShell.
- **M6-11:**
  - The live checks are integration-marked: the default run deselects both.
  - With `-m integration` against `ie_m6_live` and run `rrn-8f8641c8…`: 2 passed. Red check against a failed run: 1 failed.
  - Ruff passed.
  - The full suites were **not rerun** for M6-11. It adds documentation and one integration-only test module, which the default run collects and deselects. No production code changed after `e5c3169`.
- **CI:** not run (nothing pushed).

## Deviations and owner decisions

- **Scope extensions:** cross-task M6 file changes and the additive migration 0022, approved by the owner on 2026-10-26.
- **Live run setup:**
  - A dedicated run database, `ie_m6_live`.
  - `ANTHROPIC_API_KEY` is kept at user level but stripped from the worker process.
  - Attempts used: one approved attempt; one more the same day with deep model `gemini-3.6-flash`, which needed budget v2; then up to three scheduled tries with budget v3, where the first succeeded and the other two were cancelled.
  - Final caps: about 8 runs per day at measured usage, through request and token caps (budget v5: 180 requests and 1,400,000 tokens per UTC day). There is no run counter, so this is not an exact limit. v4 (240 requests and 2,000,000 tokens) would have admitted 11 runs (Codex M6-11 review B2).
- **One-attempt control:** before every attempt, no other process was running and the job was the only claimable one; each attempt was a single `--once` step. The budget was a secondary safeguard only.

## Open issues carried

See PROGRESS "Open issues". For M6 these are:
- **Database and budget:**
  - The owner's CLI database is not set up, so the budget must be set there too.
  - The ledger tables have no SQL writer-role guard.
  - Budget totals count by reservation day, not by the provider's day.
- **Provider and quotas:**
  - Shared Google project quotas.
  - No per-minute limiter (the quick model peaked at 14 of 15 RPM).
  - Slow deep calls, about 4 minutes each.
  - An abandoned run's thread may keep using quota.
- **Records and display:**
  - Cache origin is not distinguished.
  - Snapshot precision is 10 decimal places.
  - The cache warning is printed twice by `research show`.
- **Carried from M5:** R3 and N1–N6, the M1 hourly block, and the PAPER gates.
