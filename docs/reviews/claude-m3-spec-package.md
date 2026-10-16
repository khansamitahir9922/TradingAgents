# M3 specification package (Claude, 2026-10-16)

For Codex: a review of the draft M3 pack. The owner asked for the complete M3 specification package, PROGRESS updated to record M2's completion, and the risk-limit and approval-expiry choices as one short decision list with recommendations. Architecture unchanged. **No M3 code, merge, push, keys or downloads.**

**Commit:** the single documentation commit on `docs/m3-specs` that adds this file, based on `main` at `b7c5d2a`. Worktree `C:/Users/LOQ/TradingAgents-m3-specs`.

## What's in it

- `docs/tasks/M3-README.md`: scope, the owner decision list D1–D17, task groups, contracts carried through the pack, and three points for review.
- `docs/tasks/M3-00.md` – `M3-14.md`: 15 task specs (about 49 h), each with goal, dependencies, allowed files, contracts, rules, choices, acceptance tests and out of scope.
- M2 completion recorded: the M2 spec status rows (Done, `b7c5d2a`), `M2-README.md`, `docs/tasks/README.md`, `docs/roadmap.md` (status line and M3 section link) and PROGRESS (status table, next steps, session entry).

## Decision list (owner)

These are in `M3-README.md`, in plain English with recommendations:

- **D1–D9** (risk limits, OPEN-07): 10% per stock, no borrowing or shorting, a 15% drawdown halt cleared by an Admin, 1% of average daily traded value, 5 new buys a day, $5 minimum price, regular-hours DAY limit orders, an empty restricted list, and cutting too-big orders to the limit as a new version.
- **D10–D12** (OPEN-08): views valid to the next session's close; approve before the next open, with the approval lasting to that close; hourly not set.
- **D13–D17:** a limit 1% from the last close, $100,000 declared starting cash, paper accounts rejected until promotion thresholds exist (research accounts for M3's demonstration), PostgreSQL 17 installed locally by the owner, and named Admin or Trader approvers.

## Self-review

- **Laws checked task by task:**
  - 3 (deterministic checks with no store or clock reads inside them);
  - 5 (injected clocks; replay vs live time for approvals);
  - 8 (append-only stores, including TRUNCATE and `ON CONFLICT` routes on PostgreSQL);
  - 9 (every missing input rejects or yields no intent, with a reason);
  - 10 (one `aggregate_version` per intent covering all versions, so a reduction and an approval can't both win);
  - 12 (material fields immutable, protected by a trigger; reductions are new versions);
  - 16 (Decimal only; floats refused in the limit files);
  - 18 (intent lineage plus a ProposalRecord for every view, including those without an intent);
  - 19 (the promotion check rejects paper intents).
- **No orders:** `CONVERTED` is explicitly refused in M3, and no broker, kill-switch or outbox code is touched.
- **Lessons from M2 carried forward:**
  - The R1 compatibility rule: copied SQLite records must re-hash on PostgreSQL in both evaluation formats.
  - The B1 replacement routes: PostgreSQL has its own (`ON CONFLICT`, `TRUNCATE`), and each is tested.
  - The B2 delivery cutoff: snapshots value positions with it.
  - The R2 boundary discipline: approval and expiry are tested exactly at the deadline.
  - The PostgreSQL tests must run, not skip, for a check to pass.
- **Ordering fix found while drafting:** the decision contracts are defined in M3-08, so M3-09 can store them before M3-10 and M3-11 fill them in.

## Points for Codex's judgement

1. **Placement of account kinds and operators.** `kind: RESEARCH | PAPER` and the local operator registry sit in the Policy module. Claude reads this as a module detail, not a boundary change. Is an ADR needed?
2. **Dual-backend tests for the M1–M2 stores** (M3-02). ADR-008 says tests use PostgreSQL from M3. The plan runs the stores' tests on both backends, because SQLite remains the format of existing local files (M3-03 copies them).
3. **The libpq network guard** (M3-00 rule 4): psycopg bypasses today's socket guard, so the spec blocks psycopg outside `postgres` tests and allows only loopback hosts inside them. Is that enough, or should the guard also inspect `PGHOST` and service files?
4. **The estimate** (≈ 49 h) is above the roadmap's 35–45 h.
5. **Daily buy cap counting** (M3-11): expired or declined intents still use their slot, which is simpler and stricter. Accept, or free the slot?

## Checks

Documents only: `git diff --check` is clean and no runtime file changed, so no test run is needed. CI not yet run. Nothing was merged or pushed. The root checkout, the M2 worktree and `TradingAgents-main` were not edited.
