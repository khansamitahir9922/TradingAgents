# October delivery acceleration proposal

Prepared 2026-10-14 after the owner set an end-of-month completion target. **Target: October 31, 2026.** Claude implements; Codex reviews. This is a planning proposal, not approval to merge, change checks/architecture, spend money, use keys, download market data or implement an unapproved milestone.

## Scope and feasibility

- The owner wants all milestones completed this month. The existing v1 build scope is M1–M9; M0 is complete. **M10 live trading is not planned in v1** and requires long paper validation/governance under frozen Part K. It cannot be added to this deadline silently.
- M2–M9's milestone-overview estimates sum approximately **340–450 hours of effort**, excluding unfinished M1 and external waiting. They are provisional planning estimates, not measured Claude execution time or a guaranteed calendar forecast. Detailed work-package estimates differ; Claude should reconcile them when preparing an execution forecast.
- Full M1–M9 by October 31 is an **unvalidated stretch target**. Do not promise it or mark incomplete milestones done to meet a date. External evidence, accepted decisions/ADRs, genuine checks, provider access and available working time constrain delivery.

## Remove workflow waiting

1. **One scope approval per milestone-sized package:** exact tasks, contracts, decisions and dependencies specified first. M2 already has thirteen reviewed draft task specs; don't rewrite them. After M1 completes and M2 configuration/scope is accepted, all thirteen may be proposed as one package instead of separately approving A/B/C/D.
2. **Uninterrupted implementation:** Claude proceeds through every approved task, makes its task commits automatically under that package's authorization, records checks, and does not ask the owner after each file, command or task. Progress messages should not end the work session.
3. **One combined independent review:** Codex reviews all task commits and integrated behavior at the milestone/package boundary; genuine findings get follow-up fixes and re-review. Avoid repeating already accepted reviews on identical snapshots. Keep the existing per-task/full/batch/install check requirements; this proposal does not weaken them or change commit granularity.
4. **Use review waiting productively:** Claude may prepare the next approved independent specifications/ADR drafts/decision proposals while Codex reviews a fixed code snapshot. Do not start dependent code before its prerequisite gates. Earlier M6/M9 work is only a scheduling proposal until the owner approves it and all existing prerequisites are met; the current roadmap keeps the original order.
5. **Batch owner decisions:** collect the next package's actual choices into one concise recommendation with tradeoffs. Resolve them before coding. Do not re-ask already settled decisions or turn advisory suggestions into approvals. Merges/pushes and authenticated/download gates retain their separate permissions.

## Critical path and decisions to bring forward

| Work | Gate to resolve before runtime implementation | Useful preparation while waiting |
|---|---|---|
| Current reviewed M1 work | Explicit local merge approval: main `0661d46` → reviewed `53c51bd`; clean prepared checkout `C:/Users/LOQ/TradingAgents-main` | No new fixes needed; R-07 passed. Preserve root's uncommitted handoff files. |
| Remaining M1 hourly portions | A4 applicable retention/publication terms, then authorized access/condition checks, approved checkpoint R estimate, complete protocol evidence and reviewed unblocking | Prepare one precise permission/evidence decision list using accepted v0.3.10; do not redo its accepted offline corrections. |
| Full M2 package | Completed M1; accepted specs/configuration, including OPEN-08/09 and documented coverage/return assumptions; owner package approval | Reconcile draft estimates and present the remaining decisions together. No M2 runtime yet. |
| M3–M4 | M2 prerequisite, PostgreSQL task specs, OPEN-07/08/09 and disposition of OPEN-16 | Draft precise task boundaries and decision proposals; preserve deterministic risk, Worker authority, gate/crash/kill-switch checks. |
| M5 | M4 prerequisite; reviewed/accepted ADR-010 securities ledger model and OPEN-12 | Draft the ADR and reconciliation acceptance cases, without adopting an unaccepted model. |
| M6 | Existing M1/M2 prerequisites; OPEN-10 provider/model/budget and OPEN-11 | Prepare measured-cost procedure and exact allowed upstream change. No model/provider choices accepted by this plan. |
| M7 | M4/M5 prerequisites; ADR-011 broker/data and ADR-012 hosting/isolation, jurisdiction/account decisions | Collect owner decisions and prepare adapters/runbook contracts; no purchase, credentials, hosting changes or broker orders authorized here. |
| M8 | M5/M6/M7 prerequisites and team/UI/reporting decisions | Prepare concrete panel/API contracts from existing design principles. No invented dashboard numbers or bypass of prerequisites. |
| M9 | M2 evaluation and accepted dataset/registry design; M8 recommended | Prepare model/data/calibration contracts without starting unapproved code or presenting strengths as probabilities. |

## First Claude response under this proposal

Read current root CLAUDE.md/PROGRESS.md and `claude-return-handoff.md`. Verify accepted heads once; retain R-07 acceptance. Return one consolidated critical-path/owner-decision list, with recommended choices clearly labelled as proposals, and a complete-M2 package proposal ready for approval once its gates pass. Identify which work is authorized now and what is truly blocked. Do not return another generic acknowledgment or repeat completed specification work.

After a package is approved, continue all its tasks and required checks before returning the combined review result, unless an existing stop rule triggers. Track observed throughput and revise the October 31 forecast honestly. If full scope becomes infeasible, present the owner's choices explicitly: additional capacity, a later date, or a smaller first-release scope. Any change to frozen scope/boundaries or required promotion gates follows the reviewed ADR route; this document adopts no such change.

## Current state and permission limits

Main remains `0661d46`; M1 remains **12/18 merged**, with reviewed work ready to bring that to **15/18** after the prepared merge. M1-12/13/17 hourly portions remain incomplete. M2 specs at `71133c1` are reviewed drafts, not implementation authorization. Claude has returned; Codex is reviewer again. No runtime, architecture, check cadence or git action was changed to prepare this proposal. No tests/CI were run for this documents-only addition; whitespace checked.
