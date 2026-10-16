# Codex: M3 specification re-review at e7ec7e1

2026-10-16. **Changes requested: three integration blockers remain.** The original six blocking findings are addressed in the revised contracts. This is acceptance of their specification changes, not a claim that their future implementation/tests have passed. No M3 implementation or owner decision is authorized by this review.

Reviewed the sole follow-up commit `1ce5250bf252e4180537b2bda2bd7810b90ad28b..e7ec7e19d42446598ef9a6366b038b289cba2ace`, branch `docs/m3-specs`. Used a clean detached checkout at `C:/Users/LOQ/TradingAgents-reviews/codex-m3-specs-e7ec7e1`; Claude's source worktree was preserved. Main remains `b7c5d2a`. References below are to this exact snapshot.

Read all revised task specifications and the complete follow-up documentation change, including the correction table, owner list, status/roadmap edits and imported review records. Checked the integrated contracts against existing callers and the frozen laws, G2 and ADR-004/005/008.

## Original findings and suggestions

| Item | Re-review result |
|---|---|
| B1: first-buy raw reference | Addressed. RawReference is an explicit raw Decimal input independent of holdings, pinned to the view's source/instrument/decision revision. Empty-account and negative acceptance cases are specified. |
| B2: set serialization | Addressed. PolicyRules uses normalized sorted tuples. The codec stays unchanged; a fixed audit decoding registry and old-ID/fresh-process checks are specified. |
| B3: failed-path lineage | Addressed. NotRun, PREREQUISITE_MISSING and the outcome matrix distinguish missing prerequisites from rejected real intents. Both sides of a reduction retain lineage. |
| B4: both mapping conflict keys | Addressed. Transaction locks cover both provider/instrument and provider/symbol, including absent rows, with ordered acquisition and both real-race acceptance cases. |
| B5: account/session buy cap | Addressed in the admission path. The protected transaction reads the distinct-intent count and commits admission under the shared lock. Sequential-only testing is no longer the acceptance requirement. See S3 below for the pure-check input clarification. |
| B6: libpq destination | Addressed structurally. Ambient connection settings are neutralized, unsupported forms are refused and the permitted destination is pinned to numeric loopback. See S1 for inconsistent test wording; no remote connection was attempted in this review. |
| S1: transaction ownership | Addressed. Autocommit plus explicit managed outer/nested scopes and rollback/visibility tests replace the ambiguous driver-open transaction rule. |
| S2: setup/replay knowledge | Partly addressed: effective/recorded times, explicit research setup, delivery-aware reference/valuation/ADV, expected-session checks and named proposal delay are now specified. R2/R3 below cover remaining integration problems. |
| S3: migration context | Addressed: explicit calendars, supported older schemas, unknown-calendar rejection and base-install/lazy-driver behavior. R1 covers a new caller migration problem. |
| S4: control history | Addressed at the specification level: setting identity/sequence, shared control locks, ABA refusal and concurrent publication/bootstrap tests. |
| S5: G2/expiry | Addressed: legal intermediate states, explicit boundaries, separate CONVERTED guard and valid race starting states. R3 concerns the scope of expiry, not those legal edges. |
| S6: SELL/halt semantics | Now explicit proposals: BUY-only position/cash checks, partial liquidity-limited SELLs and reset-on-clear baseline. These are choices for the owner (amended D3/new D18), not approval by Codex. |
| S7: durable review records | Addressed. Both committed Git blobs are byte-identical to the root originals; hashes below. |

## Blocking findings

### R1. Removing raw-connection compatibility requires caller changes outside M3-02's allowed files

**Where:** `docs/tasks/M3-02.md:15`, `docs/tasks/M3-02.md:17`, `docs/tasks/M3-02.md:52`.

The revised task explicitly removes the raw `sqlite3.Connection` shim and requires repository callers to move to SqliteDatabase in this task. Its allowed files omit several existing callers. An inventory of the exact source tree found these raw-connection constructor calls outside that list:

- `investment_engine/cli.py:113`, `:200`, `:261`;
- `tests/engine/test_data_health.py:66`;
- `tests/engine/test_feature_snapshot.py:66`;
- `tests/engine/test_view_pipeline.py:67`, `:81`;
- `tests/engine/test_yfinance_actions.py:63`, `:66`;
- `tests/engine/test_yfinance_bars.py:82`, `:85`;
- `tests/engine/test_walk_forward.py:112`, `:119`.

These callers construct the reference stores and/or LineageStore with the raw connection returned by the existing SQLite opener. The port uses connection-level fetchone/fetchall and its own managed transactions; a raw SQLite connection is not that interface.

**Failure scenario:** M3-02 switches store constructors to the Database contract and removes the shim. The unchanged feature/view/importer fixtures and CLI still pass raw connections. Fixing them violates task scope, while leaving them unchanged prevents the mandatory full-suite check from passing. The CLI changes currently assigned to M3-03 come too late: M3-02 needs its own passing checks and commit first.

**Fix:** inventory all callers and explicitly allow the minimal adapter/setup changes in M3-02, including the transitional CLI wrapping needed before M3-03 switches it to PostgreSQL. Alternatively, specify a narrowly scoped staged compatibility transition and exactly when it is removed. Do not weaken assertions, monkeypatch away incompatible calls or restore SQLite as an alternative M3 operational backend. State what happens to the external offline report script's raw-connection calls if its continued use is promised.

**Acceptance:** the whole pre-existing suite still passes its recorded baseline at the end of M3-02, before M3-03. Check all migrated constructors/callers and the temporary CLI path. This is a source/spec incompatibility finding; no M3 code exists yet, so these future failures were not presented as observed test results.

### R2. A present-day operator cannot approve a historical research intent under the new time rules

**Where:** `docs/tasks/M3-05.md:43`, `docs/tasks/M3-05.md:55`; `docs/tasks/M3-13.md:30`, `docs/tasks/M3-13.md:32`; `docs/tasks/M3-14.md:27`.

The documented setup bootstraps the operator now, then gives the RESEARCH account/configuration an explicit historical effective time. Operator history has changed_at, not a historical research effective time. Approval nevertheless looks up that operator at `at`, and for RESEARCH the same `at` is the simulated historical approval time.

**Failure scenario:** OWNER is bootstrapped on 2026-10-16. The CLI creates the documented 2021 replay proposals. `intents approve ... --operator OWNER --at <2021 time before the deadline>` searches for OWNER's active role in 2021, before the operator existed, and refuses. The default demonstrated historical workflow cannot reach its human-approved result. Conversely, looking up a past active role must not let a currently deactivated operator perform a new command by choosing an earlier replay time.

**Fix:** distinguish command authorization/attribution time from simulated business time. A straightforward choice is to validate the named local operator at an injected current command time, while checking intent expiry, account settings and approved_at at the explicit replay time. Record and label both, keeping PAPER wholly on live time. If simulated historical operator permissions are intended instead, define that separate input explicitly rather than silently backdating today's operator registry. No new authentication service is needed.

**Acceptance:** bootstrap an operator today through the actual CLI, configure a historical research account, propose and approve before its simulated deadline; the current active operator succeeds. A currently inactive or wrong-role operator fails, even with an earlier replay `--at`. Audit/display fields identify the actual command time and simulated approval time. PAPER still refuses replay timestamps. Extend this distinction consistently to other privileged research commands.

### R3. Global expiry mixes independent research account timelines

**Where:** `docs/tasks/M3-12.md:54`, `docs/tasks/M3-12.md:61`; `docs/tasks/M3-09.md:46`; `docs/tasks/M3-13.md:26`, `docs/tasks/M3-13.md:33`.

`propose(account_id, at)` first calls a global `expire_due(at)` before even validating the account. Neither expire_due nor the store's due query has an account/timeline filter. The standalone expire CLI also lacks an account, while its `--at` may be research time. RESEARCH accounts can legitimately be replaying different historical dates in the same Operational Database.

**Failure scenario:** account A has a pending research intent and its replay is still before the 2021 approval deadline. A proposal for account B at a 2024 replay time globally expires A's intent. Advancing B's replay has now changed A's state, and A cannot approve at its own otherwise-valid replay time. Even a missing-account proposal currently reaches global expiry before returning PREREQUISITE_MISSING.

**Fix:** make research expiry account/timeline-scoped end to end: pipeline call, store query and CLI. Validate the account/time mode before mutation. A bulk PAPER live-time sweep can be a distinct explicit operation, but it must not apply one replay's clock to other research accounts or to PAPER state. Preserve the existing legal G2 transitions, atomic audit and CAS behavior.

**Acceptance:** put two RESEARCH accounts at different replay times in one PostgreSQL database. Proposing/expiring B leaves A's state and audit history unchanged; expiring A at its own boundary changes only A. A missing-account proposal cannot expire another account. PAPER rejects supplied replay times, including through the expiry command. Scope the new signatures and acceptance tests in M3-09/12/13 together.

## Non-blocking clarifications to include with the same revision

- **S1 — Neutralize versus reject environment settings:** `M3-00.md:37` removes ambient PG connection variables, while `M3-00.md:51` says the probes must refuse merely because PGHOST/PGHOSTADDR/PGSERVICEFILE were set. After successful neutralization an explicit supported DSN may safely reach the pinned loopback recorder. Choose one behavior and make the acceptance text match it. Retain rejection of explicit unsupported connection parameters. This is a test-contract inconsistency, not a claim that scrubbing leaves the remote destination active.
- **S2 — Replay identity inputs:** `M3-05.md:35`, `M3-07.md:48`, `M3-12.md:100`. New live recorded_at values enter hashed setup records and downstream lineage. Specify that deterministic replay reuses the same recorded setup inputs/manifest, including original timestamps, or separate nondeterministic command provenance from deterministic replay content. Do not require two independently recreated present-day setups to produce identical IDs while hashing their different command times. Preserve all provenance.
- **S3 — Admission membership in the pure check:** `M3-11.md:26`, `M3-11.md:42`. RiskInputs supplies a total count, but the rule also distinguishes an intent already occupying a slot. Make that fact explicit, or supply a count excluding the current ID. Version > 1 alone is not evidence of prior admission: reductions also create v2 before first admission. Cover both admitted and unadmitted reduced intents at the cap. The pipeline's protected first-admission path remains the B5 fix accepted above.
- **S4 — D18 wording:** `M3-README.md:31`, `M3-11.md:44`. Partial selling is a sizing policy, not a guarantee that the remaining shares will be sold later: later views may change or abstain, and M3 has no fills. Keep that limitation in the owner-facing choice. No remainder-execution subsystem is requested here.

## Verification and limits

- `git log --oneline 1ce5250..e7ec7e1`: one documentation follow-up commit. `git diff --check 1ce5250 e7ec7e1`: clean, exit 0. The 22 changed paths are all Markdown; no runtime, schema, dependency, architecture or CI files changed.
- Read-only Python static checks confirmed 15 M3 specs, 52 total estimated hours, seven four-hour tasks and backward dependencies. A separate AST/caller inventory confirmed the raw-connection calls listed in R1 and their absence from M3-02's allowed list.
- Imported review Git blobs equal the root originals byte for byte:
  - `codex-m2-accepted-b7c5d2a.md`: SHA-256 `ce1c7fc4d92f78ec20d1781b18d51844e276b409a6172491cc471348c42d6339`.
  - `codex-m3-spec-review-1ce5250.md`: SHA-256 `42e55de829b79a3897360fe6f28912547e53b1df7c46f5284200de38931b4182`.
- The initial direct checkout-byte comparison failed because Git materialized CRLF in the detached checkout. Comparing committed blobs established that the import is exact; normalized text also matches. No document-content mismatch is alleged.
- No full pytest, Ruff, clean-install, PostgreSQL or concurrency tests were run for this docs-only re-review. No new runtime pass counts claimed. CI not run. No keys, vendor access, market-data downloads or PostgreSQL installation.
- Codex wrote only this root review and the root PROGRESS handoff, uncommitted. The source specification worktree is preserved. No commit, merge or push. D1–D18 and the planning exception remain proposals pending the owner's approval; this review does not certify the proposed numeric limits as validated risk settings.

## One combined handoff

Claude: preserve the accepted B1–B6 corrections. Fix R1–R3 together in the M3 specs, align the small test/wording clarifications above, and return one fixed documentation snapshot with an updated correction table. Keep D1–D18 proposed and frozen architecture unchanged. No M3 code yet. After the corrected plan passes, the owner can approve the complete milestone/settings and arrange PostgreSQL; implementation then follows the existing uninterrupted whole-milestone workflow with task commits/checks and a final combined review.
