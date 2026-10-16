# M3 specification pack: portfolio, policy, risk (draft for review)

**Draft v0.2, 2026-10-16.** Prepared by Claude on `docs/m3-specs`. v0.1 (`1ce5250`) was reviewed by Codex (`docs/reviews/codex-m3-spec-review-1ce5250.md`, imported unchanged into this branch). v0.2 applies blocking findings B1–B6 and suggestions S1–S7; see `docs/reviews/claude-m3-spec-package.md` for the correction table. **No M3 code has been written or authorized.** M2 is complete: local `main` was fast-forwarded to `b7c5d2a` on 2026-10-16 after Codex's final review (`docs/reviews/codex-m2-accepted-b7c5d2a.md`, also imported unchanged).

**Milestone (architecture Part K, frozen):** move to PostgreSQL; PortfolioSnapshot, position sizer, versioned OrderIntent, policy (autonomy), risk, audit. **Visible result:** a CLI that shows proposed intents with their approve, reject or reduce reasons, and Level 1 approve/decline at the CLI. **No orders are created or executed in M3** (PRD §8). Concurrency tests run on PostgreSQL (ADR-008).

**Architecture:** unchanged; no ADR proposed.
- Portfolio, Policy and Risk run in the Core Engine (Part F, Control group).
- `OrderIntent` is in the OMS module (G2, ADR-004); `Order` stays in M4.
- The Audit store arrives from M3 (Part F); approvals go through the Admin CLI (Part E).
- No new process, service, broker connection, outbox or credential holder.
- Serialization uses PostgreSQL advisory locks inside existing transactions.

## Owner decisions (all proposed; none accepted)

Plain English, with Claude's recommendation. Limits are stored as **versioned configuration**, so any value can change later without code changes. A change creates a new version, and approvals made under an older version are refused.

**Risk limits (OPEN-07)**

| # | Choice | Recommendation |
|---|---|---|
| D1 | Largest holding in one stock | **10% of the account's value** (applies to buys). |
| D2 | Borrowing and short selling | **Neither.** Buys must be paid from cash, and you can only sell shares you hold. |
| D3 | Losing-streak stop (drawdown halt) | If the account falls **15% below its highest value**, stop new buys until an Admin clears the halt. Selling stays allowed. **Clearing resets the starting point** to the account's value at that moment, so the halt doesn't re-trigger at once. *(Alternative: keep measuring from the old peak, which means the limit must also change before buying can resume.)* |
| D4 | Order size compared with trading volume | One order at most **1% of the stock's average daily traded value** over the last 20 sessions; any missing session means no trade. |
| D5 | New buys per day | At most **5 new buy intents admitted** per account per trading day. Declined or expired ones still count. |
| D6 | Cheapest stock allowed | **$5 per share** minimum. |
| D7 | When orders may trade | **Regular market hours only**, as DAY limit orders. No pre-market or after-hours. Half-days are allowed. |
| D8 | Restricted list | **Starts empty.** An Admin adds or removes a stock with a written reason; every change is recorded. |
| D9 | A buy that's too big | **Cut it down to the limit**; the smaller version needs approval again. If less than one whole share is left, reject it. Whole shares only. |
| D18 | A sell larger than the market can absorb (new) | **Allow partial selling:** cut the sell to the volume limit and sell the rest on later days, rather than blocking the sale. |

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
| D15 | Strategies that haven't passed promotion | **Paper accounts reject every intent until promotion thresholds (OPEN-09) are accepted.** M3 is demonstrated on a **research (replay) account**, which can never trade and is never an execution bypass. |
| D16 | PostgreSQL on this PC | **Install PostgreSQL 17 with the official Windows installer, local connections only.** CI uses a PostgreSQL service. The owner installs it; nothing secret goes into the repository. |
| D17 | Who may approve at the CLI | **An Admin or a Trader, by named operator.** Recorded for attribution on a trusted local CLI; it isn't a login (logins come in M8). |

Until the owner accepts them, D1–D18 are proposals. The specs use them as defaults. M3-06 ships them only as a **proposed** limit file that an Admin must publish explicitly. An account without published limits gets no intent (PREREQUISITE_MISSING), so missing limits fail closed.

## Tasks

| Group | Task specs | Est. |
|---|---|---|
| M3-A: PostgreSQL move | [00](M3-00.md) dev and test setup, [01](M3-01.md) schema and migrations, [02](M3-02.md) existing stores on PostgreSQL, [03](M3-03.md) copy existing SQLite data and switch the CLI | 14 h |
| M3-B: records and configuration | [04](M3-04.md) audit store, [05](M3-05.md) accounts, operators and autonomy, [06](M3-06.md) versioned limits and halts | 9 h |
| M3-C: proposal | [07](M3-07.md) raw reference prices and PortfolioSnapshot, [08](M3-08.md) OrderIntent and sizer, [09](M3-09.md) intent store and G2 state machine | 11 h |
| M3-D: checks | [10](M3-10.md) policy checks, [11](M3-11.md) risk checks (approve, reject, reduce) | 7 h |
| M3-E: flow and CLI | [12](M3-12.md) intent pipeline and lineage, [13](M3-13.md) approve, decline and expire at the CLI, [14](M3-14.md) intents report and research setup | 11 h |

**Revised planning estimate ≈ 52 h** (v0.1: 49 h). It replaces the roadmap's older provisional 35–45 h; it's a planning figure, not a completion promise. **Planning exception:** seven tasks (00, 02, 07, 09, 11, 12, 14) are estimated at 4 h, above the 1–3 h convention. They're kept whole because each one's tests belong together. Under the milestone-package workflow this adds no approval interruptions.

**Order (15 tasks, one commit each):** M3-00 through M3-14. Every dependency points to an earlier task.

**Checkpoint.** M3-00 needs a working local PostgreSQL (D16). Without one, M3 stops at M3-00 and reports. From M3-00 on, the per-task and batch checks require the PostgreSQL tests to **run**, not skip: a run with any `postgres` test skipped doesn't count as a pass.

## Contracts carried through the pack

- **Money is Decimal** (Law 16): cash, prices, quantities and limits in `Decimal`, stored as PostgreSQL `NUMERIC`. Percent limits are Decimal fractions (`0.10`), not floats.
- **Time comes from an injected Clock** (Law 5): every `at`, `decided_at`, `approved_at` and expiry is UTC and supplied. The CLI builds a LiveClock for paper accounts and a ReplayClock for research accounts. Research settings carry an explicit `effective_at` replay time beside the live `recorded_at`; paper settings can't be backdated.
- **Order prices are raw, as traded, and always explicit** (B1). Every intent's reference price is a `RawReference`: exactly the view's decision bar revision, known at T. It never comes from holdings or from M2's adjusted float close.
- **Point-in-time knowledge.** Snapshot, reference and volume reads respect delivery time and equal-time sequence (M2-07 B2). A missing expected session is missing, never replaced by an older bar.
- **Missing data never becomes a trade** (Law 9): missing prerequisites give no intent (PREREQUISITE_MISSING), and missing data inside a check rejects. Each comes with a reason, never a default.
- **What ran is recorded; what didn't is "not run"** (B3). No decision is invented for a check that never executed.
- **Approved intents are immutable** (Law 12): material fields are enforced in code and by database triggers. Any change, a risk reduction included, creates a new version that needs its own checks and approval.
- **Every write is a compare-and-set** (Law 10) on the intent's `aggregate_version`. Rules spanning several rows use advisory locks in a fixed order:
  - account control before buy admission;
  - mapping instrument and symbol keys in ascending order.
- **History is never overwritten** (Law 8): audit events, limit versions, autonomy changes, halts, snapshots, intent versions, transitions, proposal records and intent lineage are append-only. UPDATE, DELETE and TRUNCATE are refused, and conflicting inserts are refused or leave the original unchanged.
- **The canonical codec is unchanged** (B2): M3 contracts use sorted tuples, never sets, so every M2 lineage and evaluation id stays exactly as it was.
- **Every privileged action is audited** (B2 of the architecture drivers) in the same managed transaction as the change it records.
- **Every decision is reconstructable** (Law 18). Each intent version links:
  - its view's lineage;
  - its raw reference and portfolio snapshot;
  - its policy and limit versions, autonomy setting and sizer version;
  - the decisions that actually ran.

  Replaying the same data and versions gives the same intents, decisions and ids (Part J).
- **No orders.** Nothing in M3 creates an `Order`, calls a broker, reads broker credentials, writes the kill-switch flag or publishes to an outbox. `APPROVED -> CONVERTED` is refused until M4.

## Review answers taken over (Codex, `1ce5250`)

1. Accounts and operators live in Policy as account/control metadata. Portfolio owns snapshots, and the ledger (M5) becomes authoritative for balances. D17 is attribution, not authentication. RESEARCH accounts can never trade. No ADR.
2. PostgreSQL is the only operational database from M3. SQLite stays legacy and test-only: reading old files, historical-format tests and M2's offline report script. There's no writable compatibility promise (M3-02 rule 5).
3. The libpq guard checks the effective parameters (M3-00 rule 4).
4. The estimate is recorded as a revised 52 h planning figure, with the 4 h exception above.
5. D5 counts admitted new BUY intents, each distinct intent once, under concurrency (M3-12 rule 4).
