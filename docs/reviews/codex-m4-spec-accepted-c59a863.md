# Codex acceptance: M4 specification pack at c59a863

**Verdict: PASS. The M4 specification pack is technically accepted as the implementation plan at `c59a863144e8e64e2844a21d91921703078b3fe3`. No blocking findings remain.** This is acceptance of the specifications, not approval of product decisions or authorization to begin M4.

Reviewed the single follow-up commit `43bd95da5bcaf88075adbc5c06c3437cc8dd86a3..c59a863144e8e64e2844a21d91921703078b3fe3`, its v0.4 correction table, the revised task contracts and acceptance cases, and preservation of the previously reviewed package. Review worktree:

`C:/Users/LOQ/TradingAgents-reviews/codex-m4-specs-c59a863`

## Findings and notes closed

| Item | Resolution verified in the actual documents |
|---|---|
| **V1 — availability versus delivery** | M4-06 defines `Knowledge.first_known_closed` on both StoreKnowledge and ReplayKnowledge, using actual knowledge time with availability, receipt/delivery, replay latency and equal-time sequence. Its shared implementation and exact test file are now in allowed scope. The decision uses that historical revision, not the newest at polling time. A bar delivered after the cutoff counts as missing. M4-13 and D25 carry the same rule. Zero/nonzero latency, equal-time ordering, correction and polling cases are required. |
| **V2 — late cancels** | Every broker call first materializes outcomes with `D <= t`. Only cancels received strictly before D can affect that outcome; equality is explicitly too late. Conclusive results replace PENDING after the outcome is fixed, and existing messages remain unchanged. The specified cases cover cancels just before/at/after D, after the missing-data cutoff, and frequent/delayed polling, with restart/idempotency retained. |
| **V3 — action boundary and valuation basis** | The guard uses `created_at < e <= at`, includes NEW and every other non-final state, and uses actions known at the query cutoff rather than assuming the gate knew them. Reservations and approved terms remain unchanged. Valuation is Unavailable until a compatible post-action raw close is known, and no snapshot/peak is saved in that interval. Dividend entitlement and receivable recognition have distinct specified times. The equality, delayed-action knowledge, split-day valuation and peak cases are required alongside the earlier action/revision/legacy-ID cases. |
| **Note 1 — journal sequence greater than an unresolved intent** | M4-04 explicitly keeps the older intent UNRESOLVED after the permitted emergency-halt overwrite, rather than falsely concluding NOT_APPLIED. An acceptance case covers it. The fail-safe halt and pre/post-publication failure distinctions remain. |
| **Note 2 — provider identity in promotion evidence** | M4-10 refuses lineage whose `snapshot.source` or instrument differs from the evaluation context. Mixed-provider evidence has an explicit refusal test. Recipe identity still derives from resolved decision lineage without rewriting existing evaluations. |
| **Note 3 — committed state** | The package and new PROGRESS entry record the existing `43bd95d` commit, its review, and the v0.4 follow-up. The earlier commit is unchanged. Historical v0.2/v0.3 text is retained as history. |

The earlier B1–B9 and R1–R4 changes remain in force: frozen state edges with separate fill accounting; durable cancel retries; versioned outbox effects and database-only consumers; broker calls outside transactions; typed gate inputs and fresh locked reads; pending exposure; append-only history and compatible M3 IDs; Admin-only normal kill-switch writes with database-independent fail-safe halts; early ports and permitted wiring; and pinned, honestly calculated promotion evidence. The earlier three small corrections remain intact.

Nine numbered M4 task documents are byte-identical to the reviewed parent: M4-00, 01, 02, 03, 05, 07, 08, 11 and 12. The five revised task documents were checked in full. All fifteen numbered M3 documents still differ from main only in their status row.

## Implementation interpretation and retained limits

- Implement the specified delivery/equal-time tests against both early processing and later queries. The first-known helper must preserve the sequence at which the first CLOSED state became known; it must not substitute a later revision merely because timestamps coincide. `not_after` is a cutoff, not permission to use undelivered data.
- The daily-bar decision time applies to outcomes requiring that bar. The separately specified conclusive pre-open cancellation requires no price and keeps its receipt-time delivery. Preserve its existing acceptance case.
- These are implementation checks under the accepted contracts, not another specification approval round. Actual behavior, scope compliance, intermediate commits and test evidence still require the full milestone review after implementation.
- The offline harness exception does not merge the deployed processes or permit credentials outside the worker. RESEARCH reaches only the simulator; no PAPER trading or promotion bypass is accepted. No architecture/ADR, execution-authority or G3 changes are included.
- M1 hourly remains separately blocked. Prior M3 conditions/debt remain unchanged; no retained database reset, schema rewrite or test weakening is authorized.

## Verification

Exact check:

`C:/Users/LOQ/TradingAgents/.venv/Scripts/python.exe C:/Users/LOQ/TradingAgents-proposals/codex-m4-specs-c59a863/check_specs.py`

**Passed:**

- exact fixed head and parent; one follow-up commit;
- ten documentation files changed in the follow-up, 35 documentation files across the complete spec package;
- no runtime, test, dependency, CI, architecture, SVG, secret-file or private-memory changes in either commit;
- fourteen task specs, **74 hours**, twelve estimates above three hours; required sections present;
- the nine unchanged M4 task blobs and all fifteen numbered M3 status-only diffs verified;
- `tests/engine/test_raw_reference.py` exists at the named path;
- whitespace/trailing-space checks, including `git diff --check` for the follow-up and the complete package;
- clean detached review checkout; `main` still `4c56ac1904cd7228e917df0e105093d5f517eece`.

Read the full follow-up diff, correction table and changed contracts, and checked the first-known method extension against the existing Knowledge/ReplayKnowledge interface. Preserved the 35 committed documents externally at `C:/Users/LOQ/TradingAgents-proposals/codex-m4-specs-c59a863/snapshot`; manifest SHA-256:

`293c0a7251bc8161529ea6a830906aaa2e8c427341cb9349227f4c423db164c6`

**Not run:** runtime tests, installs, CI, executable M4 regressions, downloads, key use or database/server operations. These commits contain documents only, and the new methods and scenarios have not been implemented. Acceptance cases were reviewed as requirements, not claimed as passing tests.

## Owner decisions and next step

**D19–D34 remain proposals.** In particular, accepting this plan does not select promotion thresholds, fees/fill assumptions, the D23 roadmap clarification or D34 projection policy. The owner must decide those choices and approve the whole **14-task, approximately 74-hour M4 milestone**, including the twelve over-three-hour task estimates, before implementation starts.

The approved work can then proceed as one milestone package with separate task commits/checks and one combined implementation review, under the existing stop rules. Merges, pushes, keys and downloads retain their separate authorization requirements.

Codex made no commit, merge, push or implementation edit and did not start M4. Claude's checkout and main were left untouched. The detached review worktree and external evidence are retained; this acceptance record and the root handoff update remain unstaged/uncommitted.
