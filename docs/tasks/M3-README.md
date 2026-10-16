# M3 specification pack: portfolio, policy, risk (draft for review)

**Draft v0.1, 2026-10-16.** Prepared by Claude on `docs/m3-specs` for Codex's review and the owner's decisions. **No M3 code has been written or authorized.** M2 is complete: local `main` was fast-forwarded to `b7c5d2a` on 2026-10-16 after Codex's final review (`docs/reviews/codex-m2-accepted-b7c5d2a.md`).

**Milestone (architecture Part K, frozen):** move to PostgreSQL; PortfolioSnapshot, position sizer, versioned OrderIntent, policy (autonomy), risk, audit. **Visible result:** a CLI that shows proposed intents with their approve, reject or reduce reasons, and Level 1 approve/decline at the CLI. **No orders are created or executed in M3** (PRD §8). Concurrency tests run on PostgreSQL (ADR-008).

**Architecture:** unchanged. Every task stays inside existing modules and laws: Portfolio, Policy and Risk in the Core Engine (Part F, Control group); `OrderIntent` in the OMS module (G2, ADR-004; `Order` stays M4); the Audit store (Part F, from M3); the Admin CLI (Part E). No new process, service, broker connection, outbox or credential holder. Two placements are flagged for Codex's judgement (see "For review" below).

## Decisions needed before M3 starts (OPEN-07, OPEN-08 and four more)

Plain-English choices with Claude's recommendation. Limits are stored as **versioned configuration**, so any value can change later without code changes. Changing one creates a new version, and the Pre-Execution Gate (M4) will refuse intents approved under an older version.

**Risk limits (OPEN-07)**

| # | Choice | Recommendation |
|---|---|---|
| D1 | Largest holding in one stock | **10% of the account's value.** |
| D2 | Borrowing and short selling | **Neither.** Holdings can't exceed the account's value, and you can only sell shares you hold. |
| D3 | Losing-streak stop (drawdown halt) | If the account falls **15% below its highest value**, stop new buys until an Admin clears the halt. Selling stays allowed. |
| D4 | Order size compared with trading volume | One order at most **1% of the stock's average daily traded value** (last 20 sessions). |
| D5 | New buys per day | At most **5 new buy intents** per account per trading day. |
| D6 | Cheapest stock allowed | **$5 per share** minimum. |
| D7 | When orders may trade | **Regular market hours only**, as DAY limit orders. No pre-market or after-hours. Half-days are allowed. |
| D8 | Restricted list | **Starts empty.** An Admin adds or removes a stock with a written reason; every change is recorded. |
| D9 | An order that's too big | **Cut it down to the limit.** The smaller version is a new version and needs approval again. If less than one whole share is left, reject it. Whole shares only. |

**Approval expiry and view validity (OPEN-08)**

| # | Choice | Recommendation |
|---|---|---|
| D10 | How long a daily market view stays valid | **Until the close of the next trading session** (keeps M2's provisional setting). |
| D11 | How long a Level 1 approval lasts | **You have until the next market open to approve; the approval lasts until that day's close.** An intent nobody approves expires at the open. This matches M2's research, which traded at the next open. |
| D12 | Hourly views | **Not set now.** Hourly data is still blocked, so hourly intents are refused until this is decided. |

**Other choices M3 needs**

| # | Choice | Recommendation |
|---|---|---|
| D13 | Order price | **Limit order at the last close +1% for buys, -1% for sells.** It stops a buy filling far above the price that was analysed. |
| D14 | Starting paper money | **$100,000 cash, no positions**, labelled "declared". Real balances come from the ledger in M5. |
| D15 | Strategies that haven't passed promotion | **Paper accounts reject every intent until promotion thresholds (OPEN-09) are accepted.** M3 is demonstrated on a **research (replay) account**, which can never trade. This keeps Law 19. |
| D16 | PostgreSQL on this PC | **Install PostgreSQL 17 with the official Windows installer, local connections only.** CI uses a PostgreSQL service. The owner installs it; nothing secret goes into the repository. |
| D17 | Who may approve at the CLI | **An Admin or a Trader, by named operator.** The name is recorded in the audit store; it isn't a login (logins come in M8). |

Until the owner accepts them, D1–D17 are proposals. The specs below use them as defaults. M3-06 ships them only as a **proposed** limit file, which an Admin must publish explicitly. An account without published limits rejects every intent (fail closed).

## Tasks

| Group | Task specs | Est. |
|---|---|---|
| M3-A: PostgreSQL move | [00](M3-00.md) dev and test setup, [01](M3-01.md) schema and migrations, [02](M3-02.md) existing stores on PostgreSQL, [03](M3-03.md) copy existing SQLite data and switch the CLI | 13 h |
| M3-B: records and configuration | [04](M3-04.md) audit store, [05](M3-05.md) accounts, operators and autonomy, [06](M3-06.md) versioned limits and halts | 9 h |
| M3-C: proposal | [07](M3-07.md) PortfolioSnapshot, [08](M3-08.md) OrderIntent and sizer, [09](M3-09.md) intent store and G2 state machine | 10 h |
| M3-D: checks | [10](M3-10.md) policy checks, [11](M3-11.md) risk checks (approve, reject, reduce) | 7 h |
| M3-E: flow and CLI | [12](M3-12.md) intent pipeline and lineage, [13](M3-13.md) approve, decline and expire at the CLI, [14](M3-14.md) intents report | 10 h |

**Total ≈ 49 h**, above the roadmap's provisional 35–45 h. The PostgreSQL move (13 h) is the least certain part, as the roadmap warns.

**Order (15 tasks, one commit each):** M3-00 through M3-14. Dependencies are listed in each spec; every task depends only on earlier tasks.

**Checkpoint.** M3-00 needs a working local PostgreSQL (D16). Without one, M3 stops at M3-00 and reports. From M3-00 on, the per-task and batch checks require the PostgreSQL tests to **run**, not skip: a run with any `postgres` test skipped doesn't count as a pass.

## Contracts carried through the pack

- **Money is Decimal** (Law 16): cash, prices, quantities and limits in `Decimal`, stored as PostgreSQL `NUMERIC`. Percent limits are Decimal fractions (`0.10`), not floats.
- **Time comes from an injected Clock** (Law 5): every `at`, `decided_at`, `approved_at` and expiry is UTC and supplied. The CLI builds a LiveClock for paper accounts and a ReplayClock for research accounts.
- **Prices for orders are raw, as traded.** Reference prices, limit prices and valuations use raw closes (ADR-009). Split-adjusted prices stay inside features and evaluation.
- **Missing data never becomes a trade** (Law 9): an ABSTAIN view, an expired view, a missing reference bar, a missing volume history, missing limits or an unavailable snapshot gives no intent or a rejection with its reason, never a default.
- **Approved intents are immutable** (Law 12): material fields can't change after creation, enforced in code and by database triggers. Any change, a risk reduction included, creates a new version that needs its own checks and approval.
- **Every write is a compare-and-set** (Law 10) on the intent's `aggregate_version`, so a stale write fails.
- **History is never overwritten** (Law 8): audit events, limit versions, autonomy changes, halts, snapshots, intent versions, transitions and intent lineage are append-only. UPDATE, DELETE and TRUNCATE are refused by triggers, and conflicting inserts are refused or leave the original unchanged.
- **Every privileged action is audited** (B2) in the same transaction as the change it records.
- **Every decision is reconstructable** (Law 18): an intent links its view's lineage, portfolio snapshot, policy and limit versions, sizer version and reference bar. Replaying the same data and versions gives the same intents, decisions and ids (Part J).
- **No orders.** Nothing in M3 creates an `Order`, calls a broker, reads broker credentials, writes the kill-switch flag or publishes to an outbox. `APPROVED → CONVERTED` is refused until M4.

## For review (Codex's judgement asked)

1. **Account kinds and operators.** Accounts carry `kind: RESEARCH | PAPER` (D15), and operators are local named identities with a role (D17). Both live in the Policy module (`investment_engine/policy/`), which owns autonomy and roles until M8 adds logins in the API Server. Claude reads this as a module detail, not a boundary change; an ADR would be needed if Codex disagrees.
2. **SQLite after M3.** ADR-008 says development and tests use PostgreSQL from M3. The M1–M2 stores move to one store code base over a small database port (M3-02). Their tests run on PostgreSQL and also keep running on SQLite, because SQLite remains the format of existing local databases, which M3-03 copies. New M3 stores are PostgreSQL only.
3. **The estimate** exceeds the roadmap's provisional range by about 4–14 h.
