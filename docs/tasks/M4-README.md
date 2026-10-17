# M4 specification pack: OMS and Execution Worker, simulated (draft v0.4, for review)

**Draft v0.4, 2026-10-18.** Prepared by Claude on `docs/m4-specs` (worktree `C:/Users/LOQ/TradingAgents-m4-specs`, from `main` `4c56ac1`). Documents only: no M4 code has been written or authorized.

v0.4 applies Codex's review of the fixed commit `43bd95d` (`docs/reviews/codex-m4-spec-review-43bd95d.md`): V1–V3 and the three notes. v0.3 applied Codex's re-review of v0.2 (`docs/reviews/codex-m4-draft-rereview-v02-2026-10-18.md`): R1–R4 and three small corrections. v0.2 had applied the preliminary review of v0.1 (`docs/reviews/codex-m4-draft-review-2026-10-18.md`): B1–B9 and the clarifications. Both are in the root checkout, and the correction tables are in `docs/reviews/claude-m4-spec-package.md`.

**D19–D34 remain proposals.** D34 is new in v0.2, and D25, D27 and D28 are refined. The owner answers them and decides on approving the whole milestone after Codex reviews a fixed commit.

**Milestone (architecture Part K, frozen):**
- the Order state machine, with transition ownership and compare-and-set;
- the **Execution Worker process**;
- the Pre-Execution Gate;
- a simulated broker (its own state, fees, slippage, next-bar fills);
- the kill switch (Admin-only write);
- the outbox;
- crash recovery.

**Visible result:** a simulated run, its order log, and crash tests on both processes.

**Roadmap completion criteria (§5):**
- a simulated paper run completes and its order log is produced;
- crash tests pass on both processes;
- every Part J order invariant is tested;
- only walk-forward-passed strategies run. D23 settles how this applies; owner acceptance is needed.

**Architecture: unchanged; no ADR.** Codex's preliminary answers (below) confirm this for D23, D24, the ownership trigger and the provisional portfolio, under the stated safeguards. No message broker, network call between processes or new boundary is added.

**Pre-M4 gates (roadmap §2, §7):**
- OPEN-16: D19 and D20, both left out, so G3 is unchanged.
- OPEN-09: D21 and D22.
- Walk-forward: in place since M2-11.

## Owner decisions (proposals; Claude's recommendation in bold)

Plain English. Thresholds, fees and timeouts are versioned configuration. Numbering continues from M3's D1–D18.

**OPEN-16: order-lifecycle proposals**

| # | Choice | Recommendation |
|---|---|---|
| D19 | A DAY order partly filled at the close | **Leave the proposal out (G3 unchanged).** The simulator fills completely or not at all. Partial fills exist only in a test double, so the state machine's PARTIALLY_FILLED is still tested. A broker's expiry of a partly filled order would be recorded as an anomaly, with no new state edge. Revisit with the real broker's rules (ADR-011) before M7. *(Alternative: write ADR-013 now to add PARTIALLY_FILLED → EXPIRED.)* |
| D20 | An UNKNOWN order the broker has no record of | **Leave the proposal out (G3 unchanged).** It stays UNKNOWN, is never resent, has each lookup result recorded, and keeps its cash or shares reserved. Revisit before M7. *(Alternative: an ADR adding a terminal state.)* |

**OPEN-09: promotion thresholds**

| # | Choice | Recommendation |
|---|---|---|
| D21 | What passes walk-forward, for shadow mode | **After costs, over the out-of-sample folds of one pinned evaluation record:** daily-series Sharpe ≥ 0.5; maximum drawdown no worse than buy-and-hold; at least 30 trades in total across the folds; a positive result in at least 60% of folds. The formulas are in M4-10. *(Stricter alternative: Sharpe ≥ 0.8 and at least 50 trades.)* The outcome is computed by M4-10, not predicted. |
| D22 | Level 1 and Level 2 for PAPER accounts | **Level 1** needs a passed D21 assessment **and** shadow-mode evidence. The shadow period and its comparison band are **not yet specified**; they must be decided before any PAPER promotion. **Level 2:** not set. M4 has no live data, so no shadow mode exists and **no PAPER account can trade in M4.** |

**The simulated run**

| # | Choice | Recommendation |
|---|---|---|
| D23 | Which account runs M4's visible result | **A RESEARCH (replay) account at Level 2, through the full order path to the simulated broker** (Law 20; UC-11). RESEARCH accounts reach **only** the simulated broker: the factory allowlist holds no trading credentials and no external broker. Runs are labelled `SIMULATED \| RESEARCH \| NOT PROMOTED`. M3's D15 wording "can never trade" becomes "never reaches a real or paper broker", and the PAPER refusal is unchanged. **The roadmap criterion "only walk-forward-passed strategies run" is read as applying to PAPER accounts**: a roadmap clarification that needs the owner's acceptance. |
| D24 | Two processes during a replay | **An offline research and test harness (`investment_engine/simulation/`) builds the unchanged Core and worker role objects and steps them on one ReplayClock.** They exchange work only through database rows, and only worker code calls the broker port. The harness can build only the simulated broker and never loads secrets. **It is not a deployment topology:** the deployed processes stay separate, and the real two-process path is proved in M4-08 and M4-12. A general merged runtime would need an ADR. |
| D25 | The simulator's daily fill model | **Orders must rest from the open:** the gate requires submission before the target session's open. **At the open:** a BUY with open ≤ limit fills at the open, stamped at the open. **Intraday:** if only the day's low reaches the limit, it fills at the limit, **stamped at the close as "intraday, time unknown"**, never at the open. SELLs mirror this. Slippage is 5 bps against the order, never past the limit; commission is $0. The full quantity always fills. A cancel received after the open is acknowledged as **pending**, because the price isn't known yet. It is resolved when the session's bar is first actually known (availability and delivery both counted), using the recorded receipt time; a cancel arriving at or after that moment is too late: an open fill stands, while an intraday-only fill loses to the cancel (the conservative assumption, recorded). Each session is decided once, on the first bar revision known, whatever the polling. A session bar not known by the next session's open expires the order, or cancels it if a cancel was pending, with "no market data"; no fill is invented. *(Alternative: fill at the limit only.)* |
| D26 | Timing settings | **The broker call times out after 10 s and gives UNKNOWN. The live-mode loop polls every 2 s.** |

**Kill switch (ADR-006)**

| # | Choice | Recommendation |
|---|---|---|
| D27 | Where the flag lives, and who may change it | **A checksummed JSON file `<data dir>/control/trading_enabled.json`. Missing or bad means disabled; it starts out disabled.** **Halt and resume are Admin-only** (PRD §4, UC-06, unchanged). If the database is down, an emergency halt is still applied, marked "identity unverified". A resume always needs a verified Admin. |
| D28 | Serializing changes and auditing them when the database is down | **An OS file lock serializes changes. Replacing the flag is the moment a change happens.** Under the lock, each change first settles any earlier unfinished change against the current flag, then writes an INTENT line, then the flag, then an APPLIED line, then the audit event. A halt is published even if journalling fails, and is reported incomplete. A resume is refused if its journalling **before** publication fails; if journalling fails **after** publication, it is reported as applied, never as refused. History that can't be established is marked unresolved, never invented. |

**Positions before the ledger (M5)**

| # | Choice | Recommendation |
|---|---|---|
| D29 | Where positions and cash come from in M4 | **A provisional projection: the declared start plus recorded fills, point in time, labelled PROVISIONAL.** M5's ledger replaces it. |
| D30 | Orders still open | **They count against funding and the limits.** An open BUY reserves its cash and adds its pending amount to the position cap and gross exposure. An open SELL reserves its shares and never reduces holdings for a cap. UNKNOWN counts in full. |
| D34 (new) | Splits and dividends in the projection | **Adjust for them, within M3's established action coverage, in time order.** A split applies at the ex-date's open: 10 shares, then a 10-for-1 split, then a buy of 10, gives 110. A dividend goes to the shares held at the previous close, as a receivable recognized at the ex-date's open that counts in equity but isn't spendable cash. Until a close after the action is known, the holding isn't valued (never an old price × new shares) and no snapshot or peak is stored. An order still unresolved across an action (any open order created before the action takes effect, including a split at its own session's open), a fraction of a share, an unsupported action, or no coverage makes the projection unavailable for new proposals, with the reason. The order's terms and reservation are never changed. This matters because NVDA pays a dividend every quarter and split 10-for-1 in June 2024. A fail-closed rule alone would stop the run within months. *(Alternative: keep M3's fail-closed rule and restrict the run to periods without actions while holding.)* |

**Other choices M4 needs**

| # | Choice | Recommendation |
|---|---|---|
| D31 | Who may request a cancel | **An Admin or a Trader, by named operator** (as D17). Accepted even while trading is halted, and carried through retries until the order is final. |
| D32 | Execution Worker secrets file | **`<data dir>/secrets/execution_worker.env`, read only by the worker's entry point.** It is empty for the simulator. A development convention until M7, enforced by a layering test. |
| D33 | Property tests | **Seeded random sequences in plain pytest; no new dependency.** *(Alternative: add `hypothesis` to the dev extra.)* |

## Tasks

| Group | Task specs | Est. |
|---|---|---|
| M4-A: order core | [00](M4-00.md) order contracts, store, state machine and event port, [01](M4-01.md) outbox, event log and consumers, [02](M4-02.md) conversion, fingerprints and cancel requests | 13 h |
| M4-B: Execution Worker | [03](M4-03.md) processes, ports and credential separation, [04](M4-04.md) kill switch, [05](M4-05.md) Pre-Execution Gate, [06](M4-06.md) simulated broker, [07](M4-07.md) submission, ingestion and cancels, [08](M4-08.md) crash recovery | 35 h |
| M4-C: portfolio feedback | [09](M4-09.md) provisional positions, exposure and corporate actions | 7 h |
| M4-D: promotion | [10](M4-10.md) promotion assessment (OPEN-09) | 4 h |
| M4-E: proof and result | [11](M4-11.md) Part J invariants, [12](M4-12.md) two-process fault injection, [13](M4-13.md) the simulated run and the order log | 15 h |

**Planning estimate ≈ 74 h** (v0.3: 73 h; v0.2: 71 h; v0.1: 64 h). v0.2 added the B1–B9 scope (the kill-switch protocol, the gate's locking, the causal fill model with provenance, cancel progress, exposure with corporate actions, and the promotion formulas). v0.3 added pending-cancel resolution (M4-06) and the chronological projection (M4-09). v0.4 adds the Knowledge port's first-known lookup (M4-06). It is above the roadmap's provisional 55–70 h. It's a planning figure, not a completion promise.

**Planning exception:** twelve tasks (00, 01, 04 – 13) are estimated above the 1–3 h convention, each kept whole because its tests belong together. The owner may approve this with the milestone, and task commits and checks stay separate.

**Order (14 tasks, one commit each):** M4-00 through M4-13.
- Every dependency points to an earlier task.
- Each task introduces the ports its own work needs, and later tasks only fill them in (B8):
  - the event port in 00;
  - the fingerprint port in 02;
  - the broker port, the factory and a test-only broker double in 03;
  - the gate read provider in 05;
  - simulator wiring in 06;
  - provisional wiring in 09;
  - promotion inputs in 10.
- Each intermediate task passes the full suite without a future import.

**Checkpoint.** PostgreSQL tests must **run**, not skip, at every task and batch check. Two-process tests start real OS processes, so a process-start failure is reported, never counted as a pass. The owner's PostgreSQL server is never stopped by a test.

## Contracts carried through the pack

- **The frozen G3 lifecycle, exactly** (D19, D20). A fill updates the totals by compare-and-set, and changes the state only along a G3 edge. Delayed fills on CANCELLED or EXPIRED orders are accounting-only, with anomalies (M4-00 rule 4).
- **Compare-and-set and contiguous versions** (Law 10). Each write is +1, with one event (M4-00 rule 7). Cancel requests are their own aggregate.
- **Save, then publish** (Law 11). Consumers do database work only, and **no broker call ever runs inside a database transaction**. Submission and cancels are commit, then call, then commit (M4-07).
- **Models never execute; only worker code reaches the broker port** (Laws 1, 2). Layering is enforced. The only exception is the narrow offline harness (D24), which can build only the simulator.
- **The gate runs before every submission** (Law 13). Its inputs are typed (Missing is not False), it reads fresh under a shared account-control lock, it uses an economic fingerprint for "no position change", and it requires pre-open submission. A cancel needs neither the gate nor the kill switch (Law 15).
- **Idempotent submission** (Law 14). The `client_order_id` is fixed at creation, SUBMITTING is committed before the call, a timeout gives UNKNOWN, and nothing is ever resent.
- **Causal simulated time.** Submitted, executed, delivered and recorded times are kept apart. No fill uses a price from before the order existed, an intraday touch is never stamped at the open, and missing data never invents a fill.
- **Money is Decimal; time comes from an injected Clock; history is never overwritten; missing data never becomes a trade** (Laws 16, 5, 8, 9).
- **Reconstructable** (Law 18). Orders pin their intent version and content id and the proposal's fingerprint. Gate decisions store their inputs, and fills store their provenance. The order log reads only the order store, intents, lineage and audit.

## Codex's preliminary answers (2026-10-18), adopted

1. **D23:** no ADR for an offline research simulation, under the safeguards above. The roadmap wording still needs the owner's explicit acceptance.
2. **D24:** acceptable only as an offline research and test harness, not a deployment topology (M4-03 rule 2, M4-13 rule 1).
3. **The process-role trigger:** no ADR. It is a consistency check, not authentication, and it fails closed when the role is unset (M4-00 rule 2).
4. **Provisional positions:** no ADR, as a labelled projection. B6 is resolved in M4-09, and M5's ledger stays authoritative.
5. **The estimate** is a planning figure, and the over-3 h exception is for the owner to approve with the milestone.
