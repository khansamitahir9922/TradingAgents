# Codex: M3 specification package v0.3 at 6085fd9

2026-10-16. **Passed: no blocking findings in the specification review.** The complete M3 plan is accepted by independent review at `6085fd9a9d4e279b06f5709573a6e951b64826be`, pending the owner's product decisions and milestone approval. This is not acceptance of implemented M3 code: none exists in this package. D1–D18 and the planning exception remain proposals.

Reviewed the sole follow-up commit `e7ec7e19d42446598ef9a6366b038b289cba2ace..6085fd9a9d4e279b06f5709573a6e951b64826be` and the resulting integrated M3 contracts. Branch `docs/m3-specs`, based on main `b7c5d2a`; detached review checkout `C:/Users/LOQ/TradingAgents-reviews/codex-m3-specs-6085fd9`. Claude's source checkout and the root's pre-existing changes were preserved.

## R1–R3: resolved in the specifications

- **R1, caller migration scope:** M3-02 now explicitly permits the transitional CLI wrapping and every affected repository test caller. I independently scanned the actual source AST: all 12 files calling the four relevant store constructors are covered by the allowed list. The task requires its own full-suite baseline check before M3-03 switches the CLI to PostgreSQL; the assertions cannot be weakened. The external report script is outside the repository and has no compatibility promise.
- **R2, authorization versus replay time:** M3-04/05/06/07/09/13 now distinguish live command/permission time from simulated business time. The operator registry is never backdated; historical approval checks intent settings/deadlines at replay time and current operator eligibility at command time. Audit and approval records preserve both. Acceptance includes today's active operator approving a historical research intent, and a deactivated operator/Viewer being refused despite an earlier `--at`.
- **R3, account-scoped expiry:** both store and pipeline expiry require an account. Proposals validate account/time mode before mutation. The CLI separates one-account replay expiry from a live-only PAPER sweep. Tests explicitly cover two research timelines, no mutation for a missing account, and refusal of replay times for PAPER.

## S1–S4: addressed

- **S1:** fake-connect acceptance now distinguishes refused explicit parameters from safely scrubbed ambient PG variables. A supported explicit local DSN may reach only a pinned loopback recorder after neutralization.
- **S2:** deterministic identities exclude command provenance, which remains stored and audited. The rules cover downstream setup/snapshot/lineage identities and independent setups with the same deterministic inputs. The existing M2 codec and record IDs are unchanged.
- **S3:** risk receives `admitted_buys_excluding_self` and `already_admitted`, both read under the admission lock. Store queries and acceptance cases distinguish an unadmitted reduced v2 from an intent already occupying a slot.
- **S4:** the D18 owner wording now says partial selling is only sizing: the remainder is not scheduled or guaranteed to sell, later views decide afresh, and M3 has no fills.

The original B1–B6 fixes remain intact: explicit raw references, supported tuple serialization, honest not-run lineage, both mapping lock dimensions, protected distinct-intent admission, and the effective-parameter local database guard. Their implementation still has to satisfy the specified acceptance tests. No law, domain boundary, execution authority or accepted ADR is changed by the reviewed plan.

## Non-blocking implementation notes

These clarify already-stated rules. They do not require another full planning review or another owner product decision. Fold them into the owning task's specification before implementing that interface, and include them in the final milestone review.

1. **Approval signatures:** `docs/tasks/M3-13.md:21` and `:23` omit `command_at` in the code block, although line 28 and the rules explicitly require it. Add the keyword argument `command_at: datetime` to both examples/declarations. Capture it from the injected live command clock, separately from business `at`, and propagate that command context to audited operations. Do not read the system clock inside pure checks/sizing or construct a hidden live clock there.
2. **Record equality versus identity:** `docs/tasks/M3-05.md:77` says account records are identical while their recorded_at values differ. The intended invariant is identical deterministic payload/IDs, with different provenance preserved. Say that explicitly and test both parts; full provenance-bearing dataclass equality is not the identity requirement.
3. **Unknown account diagnostics:** `docs/tasks/M3-12.md:63` explicitly requires return before any mutation. Treat the missing-account ProposalRecord as a returned diagnostic, not a persisted record; make that exception clear in the general outcome-matrix test at line 109. An existing account missing other prerequisites can retain the normal recorded outcome. No unknown-account request should write or expire anything.

## Checks observed

- `git log --oneline e7ec7e1..6085fd9`: one documentation follow-up commit.
- `git diff --stat e7ec7e1 6085fd9` and a read-only path check: 16 changed Markdown files, no executable/schema/dependency/CI/architecture changes.
- `git diff --check e7ec7e1 6085fd9`: exit 0, clean.
- Read-only Python checks: 15 M3 specs; 52 estimated hours; seven four-hour tasks; all declared M3 dependencies point to earlier tasks. The AST caller inventory confirmed all 12 constructor-caller files are allowed in M3-02.
- Blob comparisons verified the unchanged supporting M3-01/03/08/10/14 specs against e7ec7e1. Other contract changes were read in full, including the integrated approval and expiry rules.
- All three imported review Git blobs equal the root originals, without confusing Git's checkout CRLF conversion with a content change:
  - M2 acceptance: `ce1c7fc4d92f78ec20d1781b18d51844e276b409a6172491cc471348c42d6339`.
  - M3 first review: `42e55de829b79a3897360fe6f28912547e53b1df7c46f5284200de38931b4182`.
  - M3 re-review: `8f082288f8d1cf7af38b45e582199d8f02de8d4e95d221084e95b98cac030b71`.
- **Not run:** runtime pytest, Ruff, PostgreSQL/concurrency tests, clean install and CI, because this was a docs-only review. No M3 test pass counts are claimed. Earlier M2 results remain historical evidence.

## Handoff and boundaries

The owner can now decide the single M3 package: D1–D18, the 52-hour planning estimate/exception, milestone implementation authorization and the local PostgreSQL prerequisite. Review acceptance does not approve those choices for the owner and does not authorize any merge, push, installation, key use or download. No additional ADR is needed for the reviewed plan as scoped.

After owner authorization, Claude should build the entire approved M3 milestone without per-task permission interruptions, preserving task commits, all checks and stop rules, then return one combined self-review/code-review package. Include the small clarifications above in their owning tasks. No orders, broker execution or M4 work. M1 hourly remains blocked separately.

Codex wrote only this uncommitted root review and the root PROGRESS handoff. Main remains `b7c5d2a`; no commit, merge, push, M3 code, PostgreSQL installation, credentials or market-data downloads.
