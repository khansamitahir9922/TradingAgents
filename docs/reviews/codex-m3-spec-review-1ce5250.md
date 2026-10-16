# Codex review: M3 specification package at 1ce5250

Reviewed 2026-10-16. **Changes requested before implementation.** Six blocking findings below. This is a specification review, not a claim that M3 implementation or PostgreSQL tests ran.

Snapshot: `1ce5250bf252e4180537b2bda2bd7810b90ad28b`, branch `docs/m3-specs`, parent/main `b7c5d2add753332c5f52a653a9056e0798b1c1f0`. Reviewed in a clean detached checkout at `C:/Users/LOQ/TradingAgents-reviews/codex-m3-specs-1ce5250`. All file:line references below refer to this snapshot.

Read the entire documentation commit: 36 Markdown files, including all 15 M3 task specs, the package README/review packet, and the M2 completion edits. Checked against the frozen architecture, particularly C, F, G1/G2, H and K, ADR-004/005/008, the existing M1/M2 interfaces and the shared workflow. Dependencies point only to earlier M3 tasks; the estimates sum to 49 hours. M2's completion/status changes are accepted. M1's hourly work remains blocked separately.

## Blocking findings

### B1. The default cash-only account cannot obtain the required first-buy reference price

**Where:** `docs/tasks/M3-08.md:43`, `docs/tasks/M3-08.md:72`; `docs/tasks/M3-07.md:29`, `docs/tasks/M3-07.md:41`.

The sizer receives a view, its lineage and a portfolio snapshot, but no raw quote/bar or reader. Its reference must be the raw close of the view's decision bar and equal the snapshot's price for that instrument. The snapshot contains prices only for actual positions. D14 starts with cash and no positions. M2's feature snapshot contains an adjusted floating-point `decision_close`, not a raw Decimal close; its BarRefs identify observations but do not supply their prices.

**Failure scenario:** the first bullish NVDA view arrives for the default $100,000 account. There is no NVDA PositionValue and no raw price in any sizer input. A conforming implementation cannot construct the BUY without inventing an input, inserting a fictitious position, or misusing the adjusted float.

**Fix:** provide an explicit raw Decimal reference observation, separate from holdings. Specify how the pipeline obtains the exact source/instrument/decision-bar revision named by the view's lineage, and passes it to sizing and risk. A missing holding means zero held quantity/value; it does not mean a missing quote. Pin availability/delivery and currency checks without converting adjusted features into order prices.

**Acceptance:** end-to-end first BUY from an empty account; held-position SELL; missing reference; wrong provider, instrument or revision; adjusted/float values refused. All must work through the declared contracts.

### B2. PolicyRules cannot round-trip through the specified canonical codec within the allowed scope

**Where:** `docs/tasks/M3-06.md:41`, `docs/tasks/M3-06.md:46`, `docs/tasks/M3-06.md:64`; `docs/tasks/M3-04.md:35`, `docs/tasks/M3-04.md:52`.

PolicyRules contains two `frozenset` fields. Audit before/after values use the existing canonical codec and must round-trip as registered domain values. That codec accepts tuples/lists and mappings, but not frozensets. Registering a dataclass does not teach it how to encode its field types. No task currently permits the corresponding codec extension: M3-02 allows changes to `lineage/records.py` for storage only; M3-06 does not list it.

**Observed probe on the exact snapshot:** `canonical_json(frozenset({'EQ_US_NVDA'}))` raises `TypeError: cannot encode frozenset in lineage`.

**Failure scenario:** publishing even the empty proposed policy requires an audit event containing PolicyRules. Serialization fails, so the atomic publish cannot complete; dropping the fields or audit event would break the contract.

**Fix:** choose a supported deterministic representation, or explicitly permit and specify a narrowly scoped codec extension. Preserve all existing M2 canonical bytes and IDs. If sets are supported, define type-preserving decoding and canonical ordering; do not depend on set iteration order or unrestricted type registration.

**Acceptance:** policy publish/read/audit with empty and populated sets; insertion-order independence; fresh-process read after registration; existing old/current evaluation and lineage IDs remain unchanged. Amend allowed files in the task that owns the change.

### B3. Rejected paths require decisions that were never run

**Where:** `docs/tasks/M3-12.md:24`, `docs/tasks/M3-12.md:27`, `docs/tasks/M3-12.md:54`, `docs/tasks/M3-12.md:55`, `docs/tasks/M3-12.md:59`; `docs/tasks/M3-10.md:34`.

Every final intent version must have IntentLineageRecord, whose policy and risk decisions are both mandatory. But a policy failure terminates the pipeline before risk runs. Missing configuration can terminate even before an OrderIntent can be constructed, because sizing and that value require policy/risk versions. The current text calls those missing-input cases POLICY_REJECTED without defining whether an intent exists.

**Failure scenario:** a PAPER account fails the promotion check, or a Level 0 account fails policy. The rejected intent needs lineage, but there is no RiskDecision to put in it. Fabricating an unexecuted risk result misstates what happened. With no limits, there may not even be a valid intent to reject.

**Fix:** define the record shape for each outcome. Permit explicitly absent/not-run decisions with a reason; never make an unexecuted check look like a pass or failure. Use a ProposalRecord without an intent when prerequisites prevent sizing, and distinguish that from rejection of an actual intent. Include pre-reduction decisions in reconstructable history as well as the final version.

**Acceptance:** a table-driven end-to-end matrix for missing limits/account settings, unavailable snapshot, NO_INTENT, policy rejection, risk rejection, reduction and both approval levels. Assert exactly which records/decisions exist, with no invented versions or results, and atomic rollback on each failed write.

### B4. Locking the instrument row does not protect reverse symbol uniqueness

**Where:** `docs/tasks/M3-01.md:31`; `docs/tasks/M3-02.md:46`, `docs/tasks/M3-02.md:54`. Existing rule: `investment_engine/market/symbols.py:74`.

The shared M1 rule forbids overlapping mappings for either the same provider/instrument or the same provider/symbol. The proposed PostgreSQL lock covers only an instrument row.

**Failure scenario:** two transactions map provider P's symbol XYZ to different instruments A and B for overlapping dates. They lock different instrument rows, each sees no conflicting mapping, and both can commit under READ COMMITTED. XYZ then resolves ambiguously. A same-instrument race test would miss this.

**Fix:** serialize both conflict dimensions, including when no mapping row exists yet. Specify a consistent lock order, or an equivalent database constraint/isolation-and-retry design. Preserve the existing half-open date rules and provider separation.

**Acceptance:** real PostgreSQL races for different instruments/same provider-symbol and same instrument/different symbols; exactly one conflicting insert commits. Non-overlapping reuse and different providers remain valid. These are counterexamples to the proposed locking rule, not PostgreSQL race tests already run in this review.

### B5. Per-intent atomicity does not enforce the account-wide daily buy cap

**Where:** `docs/tasks/M3-11.md:24`, `docs/tasks/M3-11.md:41`; `docs/tasks/M3-12.md:57`, `docs/tasks/M3-12.md:66`; `docs/tasks/M3-09.md:49`.

Risk receives an already-read count. The pipeline's transaction and compare-and-set protect one intent, whereas the cap covers every intent for one account/target session. Different views have different intent IDs, so their aggregate guards do not conflict.

**Failure scenario:** four qualifying BUY intents exist with a cap of five. Two concurrent proposals for different views both read four and pass. Each commits its own AWAITING_APPROVAL intent; six now exist. Both per-intent CAS checks succeeded.

**Fix:** serialize admission for the account/session, re-read the count inside that protected transaction, and commit the qualifying state transition with it. Count distinct intent IDs, not versions or both the waiting and approved states. Preserve the proposed treatment of later decline/expiry unless the owner chooses otherwise. Do not introduce a service or message broker.

**Acceptance:** two connections/barrier with four of five slots occupied: exactly one new distinct intent is admitted. Cover a reduced v2, waiting-to-approved, idempotent reruns, expiry/decline and rollback without consuming an extra slot. Broader pending-order reservations can be specified separately; they are not required by this finding.

### B6. A host-only libpq guard can still connect off-machine

**Where:** `docs/tasks/M3-00.md:35`, `docs/tasks/M3-00.md:46`.

Checking only `host` is insufficient. For example, `host=localhost hostaddr=203.0.113.10` passes the proposed host test while libpq uses the non-loopback address. Environment variables and service definitions can supply connection parameters not present in the explicit string. PostgreSQL documents both behaviors in its [connection parameters](https://www.postgresql.org/docs/17/libpq-connect.html#LIBPQ-PARAMKEYWORDS) and [environment variables](https://www.postgresql.org/docs/17/libpq-envars.html).

**Failure scenario:** a developer's ambient PGHOSTADDR/service setting redirects a nominally local test DSN. libpq bypasses the Python socket guard, so a non-integration test reaches a remote database.

**Fix:** validate/control the effective connection parameters, including hostaddr, keyword overrides, multi-host forms and environment/service defaults. Reject unsupported forms or pin a validated numeric loopback destination. Protect the connection entry points actually used by the implementation and harness; do not weaken the existing HTTP/socket guards. Never expose the DSN in diagnostics.

**Acceptance:** fake connection-call probes for explicit/ambient hostaddr, service files, multi-host/URI/keyword overrides, unmarked tests and supported local connections. Assert refusal before the real connection function is reached; no remote request is needed.

## Answers to the package's five review points

1. **Accounts/operators in Policy:** acceptable as an implementation detail; no ADR needed if these remain account/control metadata, Portfolio owns snapshots and the later ledger remains authoritative for balances. D17 is attribution on a trusted local CLI, not authenticated identity. RESEARCH must never become an execution bypass or a separate trading engine.
2. **SQLite:** PostgreSQL is mandatory for the operational path and all M3 concurrency/transaction acceptance. Keeping legacy SQLite fixtures, read/copy checks and historical-format regression tests is reasonable. Narrow M3-02's writable compatibility promise for old notebooks and reconcile it with M3-03's "reading old files" limit. I am not approving SQLite as an alternative writable M3 Operational Database. If that broader support is intended, propose an ADR against frozen ADR-008 first; otherwise no architecture change is needed.
3. **libpq guard:** not sufficient as written; B6 supplies the correction. PGHOST alone is not the only ambient setting that matters.
4. **49-hour estimate:** the arithmetic is correct. This is a revised planning estimate, not a completion guarantee. Record it consistently rather than treating the older provisional 35–45-hour range as a limit. Four tasks estimate four hours despite the roadmap's 1–3-hour convention; explicitly accept that planning exception or split task specs, without adding per-task approval interruptions.
5. **Expired/declined BUY slots:** reasonable as a proposed conservative anti-churn policy, subject to the owner's D5 decision. Name it a cap on admitted new BUY intents, not executed buys. Count each distinct intent once; B5 must hold under concurrency. This review does not approve the numeric cap or other D-values for the owner.

## Suggestions and integration clarifications for the same revision

These are separate from the six blocking findings. Capture the choices/tests now where practical; they should not generate separate documentation-only approval rounds.

- **S1 — Transaction ownership:** `M3-01.md:22`, `M3-02.md:28`, `M3-04.md:50`. Define managed transaction ownership and nesting, including an implicit transaction opened by an earlier SELECT. With autocommit disabled, psycopg can create a transaction on a read; a later transaction context may only release a savepoint. Add read-then-write visibility from another connection, nested failure/rollback, and audit atomicity cases. Do not equate any driver-open transaction with the caller's managed scope. [Psycopg transaction documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
- **S2 — Research setup and replay knowledge:** `M3-05.md:42`, `M3-06.md:64`, `M3-07.md:54`, `M3-12.md:60`, `M3-14.md:22`. Show exact commands for creating research account/settings/starting state at a declared replay time before historical proposals. Publishing limits today and querying them in 2019 must not silently backdate them. Specify how the reader retains delivery-time and equal-time sequence knowledge for snapshot, raw reference and ADV reads. Ordinary availability-only reads are not equivalent to M2's ReplayKnowledgeReader. Existing view.generated_at already includes feed latency; name any additional proposal latency separately. Test setup plus replay through the CLI, a correction available before but delivered after T, equal-time ordering, and a missing expected session rather than reusing an arbitrarily old CLOSED bar. None of this permits backdating PAPER actions.
- **S3 — Migration calendar context:** `M3-03.md:31`, `M3-03.md:36`. The required EvaluationRunStore read-back takes `calendars` (`M3-02.md:38`), but the copy API provides no mapping/resolver. Specify that dependency or an explicit supported-calendar resolver; refuse unknown versions atomically rather than binding an arbitrary current calendar to an old name. Also exercise source schemas 1 and 2, which lack later record tables, as well as 3/4, both historical evaluation formats and unchanged source bytes. Preserve base-package imports without installing the engine extra; PostgreSQL should be required when invoked, not accidentally at CLI import.
- **S4 — Control history and races:** `M3-05.md:34`, `M3-13.md:30`. Make "autonomy changed since proposal" testable for 1→2→1, not just current-level inequality. The full setting is already available in intent lineage; pin a deterministic setting identity/order, including equal timestamps. Add concurrent bootstrap, concurrent version publication and approval/control-change cases to define intended serialization, without claiming that intent CAS alone serializes unrelated control rows.
- **S5 — G2 and expiry wording:** `M3-12.md:56`, `M3-09.md:58`. State the legal transition sequence for an already-late proposal, with the exact `>=` boundary; G2 has no direct PROPOSED→EXPIRED edge. Existing legal intermediate states can satisfy the outcome, so no new transition/ADR is necessary. Distinguish the frozen ALLOWED table from M3's explicit CONVERTED guard in the exhaustive acceptance test. Give race tests initial states where both competing moves are legal; AWAITING_APPROVAL→SUPERSEDED is not a frozen edge.
- **S6 — Owner policy semantics:** `M3-11.md:38`, `M3-11.md:42`, `M3-06.md:66`. Clarify risk-reducing SELLs and halt clearing in the owner list. For example, a $100,000 concentrated holding under a $10,000 position cap needs a large sale, while a $10,000 order-liquidity cap permits only a small one; no quantity satisfies both rules as written. State whether partial de-risking is allowed or rejected. Clearing a halt while equity remains below the unchanged peak threshold will immediately trigger it again; specify whether that is intended. These are product choices, not a claim that the proposed thresholds are validated or safe.
- **S7 — Durable review references:** `M3-README.md:3` and the status edits cite `docs/reviews/codex-m2-accepted-b7c5d2a.md`, which exists in the root working copy but not this commit's tree. Preserve/import the exact review record in an authorized documentation scope, or state where it can actually be found. A fresh checkout should not present an unresolved link as a committed artifact.

## Verification and limits

- Verified parent/branch/main refs, clean source and detached-review worktrees; examined the one commit and its whole integrated documentation diff. No source checkout was changed.
- `git diff --check b7c5d2a 1ce5250`: exit 0, clean.
- Read-only stdlib script: asserted 36 changed Markdown files, 15 M3 specs, sum of estimates 49 hours, and all M3 dependency references point backward. Passed.
- Exact-code probe through `C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe`: canonical encoding of a frozenset produced the B2 TypeError. This is a codec probe, not a test-suite run.
- Consulted primary PostgreSQL/psycopg documentation for connection resolution and transaction behavior. No keys used, no vendor access or market-data downloads.
- Full pytest/Ruff/clean-install/PostgreSQL concurrency tests: **not run for this documentation-only review**. Earlier accepted M2 results remain historical evidence, not new M3 check results. CI not run.
- Wrote only this review and the root PROGRESS handoff, uncommitted. No commit, merge, push, M3 code or owner setting applied. D1–D17 remain proposals. Main remains `b7c5d2a`.

The two read-only Python checks were run from the detached snapshot in PowerShell as `$script = @'... '@; & C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe -c $script`, with these exact script bodies:

```python
import pathlib,re,subprocess
files=subprocess.check_output(['git','diff','--name-only','b7c5d2a','1ce5250'],text=True).splitlines()
assert len(files)==36 and all(f.endswith('.md') for f in files)
specs=[pathlib.Path('docs/tasks') / ('M3-%02d.md' % n) for n in range(15)]
assert all(p.is_file() for p in specs)
hours=sum(int(re.search(r'\*\*Estimate\*\* \| (\d+) h',p.read_text(encoding='utf-8')).group(1)) for p in specs)
assert hours==49
for n,p in enumerate(specs):
    deps=re.search(r'\*\*Depends on\*\* \| (.*)',p.read_text(encoding='utf-8')).group(1)
    assert all(int(d)<n for d in re.findall(r'M3-(\d+)',deps)), (p,deps)
print('36 changed Markdown files; 15 M3 specs; 49 estimated hours; all M3 dependencies point to earlier tasks.')
```

```python
from investment_engine.lineage.records import canonical_json
try:
    canonical_json(frozenset({'EQ_US_NVDA'}))
except TypeError as exc:
    print(type(exc).__name__ + ': ' + str(exc))
else:
    raise AssertionError('Expected current codec to reject frozenset')
```

## Single handoff to Claude

Revise the M3 documentation package in one pass against B1–B6, answer the five review points, and fold in the integration clarifications above where applicable. Keep fixes within frozen architecture; propose an ADR only if deliberately changing a frozen decision. Return one fixed snapshot with a finding-to-change/acceptance-test matrix and one short owner decision list. Do not implement M3 yet or silently approve D1–D17. Existing separate approvals for merge, push, installation, keys and downloads remain unchanged. Once the corrected specs pass and the owner approves M3, build the whole authorized milestone without per-task approval interruptions, keeping task commits/checks and the final combined review.
