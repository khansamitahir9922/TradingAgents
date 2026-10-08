# Architecture v1.0 — Eraser diagram code

> **Source of truth:** `architecture/architecture-v1.0.md`. These diagrams are drawn *from* it; if a diagram and the document disagree, the document wins, so fix the diagram.
> **Exported drawing:** `architecture/diagrams/architecture-v1.0.svg`. It's a **complete snapshot of the Eraser canvas**, so it contains the current diagrams plus two **superseded earlier copies** kept on the canvas. See "Map of the exported canvas" below for which block is which.
> **Purpose of this file:** keep the diagram code in Git, so the drawings can be rebuilt even if Eraser changes or disappears.

## How to use
1. Open the Eraser file **Investment Platform Architecture** at https://app.eraser.io.
2. On the canvas, insert a **diagram-as-code** block, choose the type shown for each diagram (*Flow chart* or *Sequence*), and paste the code.
3. If Eraser reports a syntax error, delete the `icon:`/`color:` value on the reported line, or use Eraser's AI generation with the Part of `architecture-v1.0.md` named under each diagram.
4. After changing any diagram, re-export to `architecture/diagrams/architecture-v1.0.svg` and commit both files together.

**Arrow convention (used in every flow chart):**
- `A > B` points from the actor to what it acts on, when the data flows mainly one way (a write, a feed, a command).
- `A <> B` is a **request with a meaningful response** (prompts and responses, reads, orders and fills).
- `A --> B` (dashed) means the link is disabled or in the future.
- The drawing and this code must use the same arrows.

## Index
The diagrams are numbered in reading order, which matches Part N of `architecture-v1.0.md`.

| # | Diagram | Type | Architecture section |
|---|---|---|---|
| 1 | System context | Flow chart | Part D |
| 2 | Containers and credentials | Flow chart | Part E, Law 2 |
| 2b | Crash matrix (companion to Diagram 2) | Flow chart | Part E |
| 3 | Modules: Core Engine vs Execution Worker | Flow chart | Part F |
| 4 | Trade lifecycle | Sequence | G1 |
| 5 | OrderIntent state machine | Flow chart | G2, Law 12 |
| 6 | Order state machine with transition owners | Flow chart | G3, Laws 10, 14 |
| 7 | Kill switch and cancel | Sequence | G5, Law 15 |
| 8 | Research slow path | Sequence | G6, Laws 2, 4 |
| 9A | Crash recovery: Execution Worker restart | Sequence | G4, Law 14 |
| 9B | Crash recovery: outbox recovery after any process restart | Sequence | G4, Law 11 |

## Map of the exported canvas
`architecture-v1.0.svg` is a full-canvas export. The corrected Diagram 6 and Diagram 9, and the new 2b, were added **below** the earlier copies rather than replacing them. Read the blocks from top to bottom like this:

| Position in SVG | Block | Status |
|---|---|---|
| 1 | Diagram 1 — System context | ✅ current |
| 2 | Diagram 2 — Containers and credentials | ✅ current |
| 3 | Diagram 3 — Modules | ✅ current |
| 4 | Diagram 4 — Trade lifecycle | ✅ current |
| 5 | Diagram 5 — OrderIntent states | ✅ current |
| 6 | Earlier Order states copy | ⚠️ **superseded** by position 11 |
| 7 | Diagram 7 — Kill switch and cancel | ✅ current |
| 8 | Diagram 8 — Research slow path | ✅ current |
| 9 | *Earlier* Crash recovery (Execution Worker only, no outbox recovery) | ⚠️ **superseded** by positions 12–13 |
| 10 | Diagram 2b — Crash matrix | ✅ current |
| 11 | Diagram 6 — Order states (G3-exact) | ✅ current |
| 12 | Diagram 9A — Execution Worker restart | ✅ current |
| 13 | Diagram 9B — Outbox recovery after any restart | ✅ current |

Superseded copies are kept so the export preserves the full canvas. **Where an earlier copy and a current one differ, the current one and `architecture-v1.0.md` win.** When the canvas is next edited, the superseded blocks can be deleted and 2b moved beside Diagram 2.

---

## Diagram 1 — System context (C4 Level 1) · Flow chart
*Shows:* who uses the platform and which outside systems it talks to.

```
direction down

Admin [icon: user, color: blue]
Trader [icon: user, color: blue]
Viewer [icon: user, color: blue]
Market data provider [icon: bar-chart, color: gray]

Investment Platform [icon: server, color: green]

Research data sources [icon: globe, color: gray]
LLM providers [icon: cpu, color: gray]
Paper broker [icon: briefcase, color: gray]
Live broker FUTURE [icon: briefcase, color: red]

Admin > Investment Platform: configures, kill switch
Trader > Investment Platform: reviews, approves paper orders
Viewer > Investment Platform: reads reports
Market data provider > Investment Platform: bars and quotes
Investment Platform <> Research data sources: research data requests and responses
Investment Platform <> LLM providers: research prompts and responses
Investment Platform <> Paper broker: paper orders and fills
Investment Platform --> Live broker FUTURE: disabled
```

---

## Diagram 2 — Containers and credentials (C4 Level 2) · Flow chart
*Shows:* the processes and stores, **which credentials each process holds (Law 2)**, and that processes talk **only through the Operational Database**. The kill-switch flag is written only by the Admin CLI and read only by the Execution Worker.

```
direction right

People [color: blue] {
  Viewer [icon: user]
  Trader [icon: user]
  Admin [icon: user]
}

Platform [color: green] {
  Core Engine no broker keys [icon: cpu]
  Market Data Store [icon: database]
  Research Worker LLM and research keys only [icon: cpu]
  Web Dashboard [icon: monitor]
  API Server no external keys [icon: server]
  Admin CLI [icon: terminal]
  Kill Switch Flag [icon: flag]
  Execution Worker broker keys only [icon: cpu, color: orange]
  Operational Database [icon: database]
}

External [color: gray] {
  LLM providers [icon: globe]
  Research data sources [icon: globe]
  Market data provider [icon: bar-chart]
  Paper broker [icon: briefcase]
}

Viewer > Web Dashboard
Trader > Web Dashboard
Admin > Web Dashboard
Admin > Admin CLI
Web Dashboard <> API Server no external keys: REST and WebSocket
API Server no external keys <> Operational Database: human commands and reads
Admin CLI <> Operational Database: approvals, cancel requests and reports
Admin CLI > Kill Switch Flag: write enabled or disabled
Core Engine no broker keys <> Market Data Store: bars, corporate actions and revisions
Core Engine no broker keys <> Operational Database: orders, cancel requests, outbox, ledger and audit
Research Worker LLM and research keys only <> Operational Database: jobs, research records and outbox
Research Worker LLM and research keys only <> LLM providers: prompts and responses
Research Worker LLM and research keys only <> Research data sources: research data requests and responses
Market data provider > Core Engine no broker keys: feed using non-trading keys
Execution Worker broker keys only > Kill Switch Flag: read only before each new submission
Execution Worker broker keys only <> Operational Database: approved orders, cancel commands, order states, fills and BrokerSnapshot
Execution Worker broker keys only <> Paper broker: orders, cancels, acknowledgements and fills
```
*Arrow notes:*
- The Admin CLI → Kill Switch Flag link is one-way on purpose: the CLI is the **sole writer**.
- The Execution Worker → flag link points from the actor; the worker only **reads** it (Law 15).
- The market-data feed is inbound only.

### Diagram 2b — Crash matrix (companion to Diagram 2) · Flow chart
*Shows:* Part E's crash matrix, i.e. what keeps working when each process is down. The export has it at canvas position 10 (see the map); ideally it sits beside Diagram 2.

*Why short IDs and quoted labels:* full sentences with commas and full stops can break Eraser's parser, because commas separate node names. Short IDs keep the code safe, and the quoted labels hold the exact wording of the drawn diagram.

```
direction right

2b Crash matrix [color: gray] {
  rw_down [label: "Research Worker crashes", icon: x-circle, color: purple]
  rw_ok [label: "Execution unaffected. Views run without new research, or ABSTAIN if research is required.", icon: check-circle, color: green]
  api_down [label: "API Server or Dashboard crashes", icon: x-circle, color: blue]
  api_ok [label: "Execution unaffected. Admin CLI still works.", icon: check-circle, color: green]
  core_down [label: "Core Engine crashes", icon: x-circle, color: blue]
  core_ok [label: "Approved orders remain durable. Execution Worker carries on.", icon: check-circle, color: green]
  ew_down [label: "Execution Worker crashes", icon: x-circle, color: orange]
  ew_ok [label: "Orders stay recorded. On restart, reconcile by client_order_id. See Diagram 9A.", icon: check-circle, color: green]
}

rw_down > rw_ok
api_down > api_ok
core_down > core_ok
ew_down > ew_ok
```
*Any process restart:* its unpublished outbox rows are published again with their original `event_id` (Diagram 9B).

---

## Diagram 3 — Modules: Core Engine vs Execution Worker (C4 Level 3) · Flow chart
*Shows:* which modules run where. The Core Engine creates `NEW` orders and cancel requests. Every broker-driven transition, the Pre-Execution Gate, broker calls, fill ingestion and broker snapshots belong to the Execution Worker. They meet only through the Operational Database.

```
direction right

Core Engine no broker keys [color: blue] {
  Market Instruments Calendar Clock Market Data Data Quality [icon: bar-chart, color: blue]
  Analysis Quant Evaluation Research reads Decision [icon: activity, color: purple]
  Control Portfolio Policy Risk [icon: shield, color: orange]
  OMS create NEW orders and cancel requests [icon: list, color: orange]
  Records Ledger Reconciliation Audit Lineage [icon: book-open, color: green]
}

Operational Database [icon: database, color: gray]

Execution Worker broker keys only [color: orange] {
  Pre Execution Gate [icon: lock]
  OMS broker transitions compare and set [icon: list]
  Broker Adapter [icon: send]
  Fill Ingestion [icon: download]
  Broker Snapshots [icon: camera]
}

Kill Switch Flag [icon: flag, color: red]
Paper broker [icon: briefcase, color: gray]

Market Instruments Calendar Clock Market Data Data Quality > Analysis Quant Evaluation Research reads Decision: healthy market data
Analysis Quant Evaluation Research reads Decision > Control Portfolio Policy Risk: MarketView
Control Portfolio Policy Risk > OMS create NEW orders and cancel requests: approved intent version
Core Engine no broker keys <> Operational Database: orders, commands and records
Operational Database <> Execution Worker broker keys only: orders, cancels, states, fills and BrokerSnapshot
Pre Execution Gate > OMS broker transitions compare and set: gate passed
Pre Execution Gate > Kill Switch Flag: read only, fail closed
OMS broker transitions compare and set > Broker Adapter: submit after SUBMITTING is durable
Broker Adapter > Fill Ingestion: fills including late fills
Broker Adapter > Broker Snapshots: positions, open orders and cash
Fill Ingestion > OMS broker transitions compare and set: fill-driven state updates
Broker Adapter <> Paper broker: orders, cancels, fills and snapshot queries
```

---

## Diagram 4 — Trade lifecycle · Sequence
*Shows:* one closed bar becoming a paper trade, across both processes. Every order-state write is a compare-and-set.

```
Market Data > Core Engine no broker keys: Closed bar arrives
Core Engine no broker keys > Core Engine no broker keys: Data Quality checks, then Quant features
opt [label: Optional research] {
  Core Engine no broker keys > Operational Database: Read latest valid research
  Operational Database > Core Engine no broker keys: Research context or absent
}
Core Engine no broker keys > Core Engine no broker keys: Decision produces MarketView
Core Engine no broker keys > Core Engine no broker keys: Portfolio creates versioned OrderIntent
Core Engine no broker keys > Core Engine no broker keys: Policy and Risk approve the intent version
Core Engine no broker keys > Core Engine no broker keys: Approval confirmed for this exact version
Core Engine no broker keys > Operational Database: OMS saves NEW order, client_order_id and outbox
Execution Worker broker keys only > Operational Database: Pick up NEW order and current gate inputs
Operational Database > Execution Worker broker keys only: Order, intent version and approval context
Execution Worker broker keys only > Kill Switch Flag: Read trading-enabled flag
Kill Switch Flag > Execution Worker broker keys only: Enabled
Execution Worker broker keys only > Execution Worker broker keys only: Gate checks version, expiry, view, policy, risk and session/TIF
Execution Worker broker keys only > Operational Database: Compare-and-set NEW to SUBMITTING
Operational Database > Execution Worker broker keys only: SUBMITTING committed
Execution Worker broker keys only > Paper broker: Submit using client_order_id
Paper broker > Execution Worker broker keys only: Acknowledgement
Execution Worker broker keys only > Operational Database: Compare-and-set state to SUBMITTED
Paper broker > Execution Worker broker keys only: Fills including late fills
Execution Worker broker keys only > Operational Database: Save fills idempotently and update state using compare-and-set
Execution Worker broker keys only > Paper broker: Fetch positions, open orders and cash
Paper broker > Execution Worker broker keys only: Broker state
Execution Worker broker keys only > Operational Database: Save timestamped BrokerSnapshot
Core Engine no broker keys > Operational Database: Read new fills, fees, order states and BrokerSnapshot
Operational Database > Core Engine no broker keys: Stored records
Core Engine no broker keys > Core Engine no broker keys: Ledger creates double-entry entries
Core Engine no broker keys > Operational Database: Save ledger entries
Core Engine no broker keys > Core Engine no broker keys: Reconciliation compares orders and ledger with BrokerSnapshot
Core Engine no broker keys > Operational Database: Record incident if values differ
```

---

## Diagram 5 — OrderIntent state machine · Flow chart
*Shows:* approval before any order exists. An approved version never changes; any change creates a new version (Law 12). Owned by the Core Engine.

```
direction right

PROPOSED [color: blue]
POLICY_REJECTED [color: red]
RISK_REJECTED [color: red]
AWAITING_APPROVAL [color: orange]
DECLINED [color: red]
APPROVED [color: green]
EXPIRED [color: gray]
CONVERTED [color: green]
SUPERSEDED [color: gray]

PROPOSED > POLICY_REJECTED: policy fails
PROPOSED > RISK_REJECTED: risk rejects
PROPOSED > AWAITING_APPROVAL: Level 1, human approval
PROPOSED > APPROVED: Level 2, automatic approval
PROPOSED > SUPERSEDED: risk reduces size, new version required
AWAITING_APPROVAL > APPROVED: human approves exact version
AWAITING_APPROVAL > DECLINED: human declines
AWAITING_APPROVAL > EXPIRED: approval window expires
APPROVED > CONVERTED: OMS creates a NEW Order
APPROVED > EXPIRED: intent validity expires
APPROVED > SUPERSEDED: material change, new version required
```

---

## Diagram 6 — Order state machine with transition owners · Flow chart
*Shows:* the order after approval. **Core** writes only the creation of `NEW`; the **Worker** (Execution Worker) writes every other transition. Every write is a compare-and-set on `aggregate_version`. Cancel *requests* are command rows, not state changes. Late fills are always accepted; `UNKNOWN` is reconciled, never resent.

```
direction right

Core OMS creates Order [shape: oval, color: blue]
NEW [color: blue]
GATE_REJECTED [color: red]
SUBMITTING [color: orange]
UNKNOWN reconcile never resend blindly [color: purple]

Broker lifecycle [color: gray] {
  SUBMITTED [color: blue]
  REJECTED [color: red]
  CANCEL_PENDING [color: orange]
  CANCELLED [color: gray]
  EXPIRED [color: gray]
  PARTIALLY_FILLED [color: blue]
  FILLED [color: green]
}

Core OMS creates Order > NEW: Core - create
NEW > GATE_REJECTED: Worker - gate failed
NEW > SUBMITTING: Worker - gate passed
SUBMITTING > SUBMITTED: Worker - broker acknowledges
SUBMITTING > REJECTED: Worker - broker rejects
SUBMITTING > EXPIRED: Worker - broker expires
SUBMITTING > UNKNOWN reconcile never resend blindly: Worker - uncertain timeout
UNKNOWN reconcile never resend blindly > Broker lifecycle: Worker - set to whichever state the broker confirms
SUBMITTED > REJECTED: Worker - broker rejects
SUBMITTED > EXPIRED: Worker - broker expires
SUBMITTED > PARTIALLY_FILLED: Worker - partial fill
SUBMITTED > FILLED: Worker - full fill
SUBMITTED > CANCEL_PENDING: Worker - act on cancel command
PARTIALLY_FILLED > CANCEL_PENDING: Worker - act on cancel command
PARTIALLY_FILLED > FILLED: Worker - remaining fills
CANCEL_PENDING > CANCELLED: Worker - cancel confirmed
CANCEL_PENDING > PARTIALLY_FILLED: Worker - late fill
CANCEL_PENDING > FILLED: Worker - late fill completes order
```
*Notes:*
- These transitions are exactly Part G3's list. Every "Worker" transition is written by the Execution Worker as a compare-and-set on `aggregate_version`.
- `UNKNOWN` points to the **whole Broker lifecycle group**: G3 says it is "reconciled to the true state", whichever state the broker confirms. It is never resubmitted.
- **Candidate ADR, not part of v1.0:** two broker behaviors are real but not covered by G3, so they are deliberately **not** drawn:
  - a partially filled DAY order whose remainder expires at the close (`PARTIALLY_FILLED → EXPIRED`);
  - what state to record when the broker has **no record** of an `UNKNOWN` order.

  Both belong in ADR-004 (order lifecycle) before M4. Adding them silently here would break the change rule.

---

## Diagram 7 — Kill switch and cancel · Sequence
*Shows:* the Admin CLI is the **sole writer** of the flag. The Execution Worker only **reads** it before each new submission and fails closed. Cancels are **always allowed**, even while trading is off.

```
Admin CLI > Admin CLI: Admin requests trading OFF
Admin CLI > Kill Switch Flag: Write DISABLED, sole writer
Execution Worker > Operational Database: Read pending NEW order
Operational Database > Execution Worker: Order and gate context
Execution Worker > Kill Switch Flag: Read only before new submission
Kill Switch Flag > Execution Worker: Disabled, missing or unreadable
Execution Worker > Execution Worker: Pre-Execution Gate fails closed
Execution Worker > Operational Database: Compare-and-set NEW to GATE_REJECTED
opt [label: Separate cancel request for an existing broker order] {
  Core or API Server > Operational Database: Save cancel command row
  Execution Worker > Operational Database: Read pending cancel commands
  Operational Database > Execution Worker: Cancel command and current order state
  Execution Worker > Operational Database: Compare-and-set eligible order to CANCEL_PENDING
  Operational Database > Execution Worker: CANCEL_PENDING committed
  Execution Worker > Paper broker: Send cancel, allowed while trading is OFF
  Paper broker > Execution Worker: Cancel status and any late fills
  Execution Worker > Operational Database: Save broker state using compare-and-set
  Execution Worker > Operational Database: Record any fills idempotently
}
```

---

## Diagram 8 — Research slow path · Sequence
*Shows:* TradingAgents runs only in the Research Worker, which has **no broker keys**. Research is never on the bar-to-order path; the Core Engine only reads the latest *valid* stored research.

```
Trader > API Server: Request research for NVDA
API Server > Operational Database: Create research job
Research Worker no broker keys > Operational Database: Pick up job
Operational Database > Research Worker no broker keys: Job settings and inputs
par [label: Research runs in the background] {
  Research Worker no broker keys > Research Worker no broker keys: Run TradingAgents within daily LLM budget
  Research Worker no broker keys > Research data sources: Fetch news, filings and prices
  Research data sources > Research Worker no broker keys: Research inputs
  Research Worker no broker keys > LLM providers: TradingAgents prompts and input context
  LLM providers > Research Worker no broker keys: Analysis responses
  Research Worker no broker keys > Research Worker no broker keys: Build ResearchRecord and parsed ResearchContext
  Research Worker no broker keys > Operational Database: Save records and research-ready outbox event
}
and [label: Core processes bars independently] {
  Core Engine no broker keys > Core Engine no broker keys: Next closed bar arrives
  Core Engine no broker keys > Operational Database: Read latest valid stored research
  Operational Database > Core Engine no broker keys: Valid context or absent
  Core Engine no broker keys > Core Engine no broker keys: Decision uses available valid context
  Core Engine no broker keys > Core Engine no broker keys: ABSTAIN if required research is unavailable
}
```

---

## Diagram 9 — Crash recovery · Sequence
*Shows:* Part G4 in full, as two parts:
- **A.** When the **Execution Worker** restarts, it never resends blindly. It reconciles uncertain orders by `client_order_id`, re-gates `NEW` orders, and sends pending cancels.
- **B.** When **any process** restarts (Core Engine, Execution Worker, Research Worker or API Server), its unpublished outbox rows are published again **with their original `event_id`**. Consumers skip any `event_id` they've already processed, so a repeated message never causes a repeated action.

All communication goes through the Operational Database (Part E).

### 9A — Execution Worker restart
```
Execution Worker > Execution Worker: Restart
Execution Worker > Operational Database: Find SUBMITTING and UNKNOWN orders
Operational Database > Execution Worker: Uncertain orders with client_order_id
loop [label: For each uncertain order] {
  Execution Worker > Paper broker: Look up by client_order_id
  alt [label: Broker confirms true state] {
    Paper broker > Execution Worker: Confirmed order state
    Execution Worker > Operational Database: Save confirmed state using compare-and-set
  }
  else [label: Lookup remains inconclusive] {
    Paper broker > Execution Worker: State cannot yet be confirmed
    Execution Worker > Operational Database: Retain or set UNKNOWN using compare-and-set
    Execution Worker > Execution Worker: Continue reconciliation, never resend blindly
  }
}
Execution Worker > Operational Database: Find orders still NEW
Operational Database > Execution Worker: NEW orders
loop [label: For each NEW order] {
  Execution Worker > Operational Database: Read current intent and approval context
  Operational Database > Execution Worker: Current gate inputs
  Execution Worker > Kill Switch Flag: Read trading-enabled flag
  Kill Switch Flag > Execution Worker: Flag status
  Execution Worker > Execution Worker: Re-run Pre-Execution Gate
  alt [label: Gate passes] {
    Execution Worker > Operational Database: Compare-and-set NEW to SUBMITTING
    Operational Database > Execution Worker: SUBMITTING committed
    Execution Worker > Paper broker: Submit using existing client_order_id
    Paper broker > Execution Worker: Acknowledgement or rejection
    Execution Worker > Operational Database: Save broker outcome using compare-and-set
  }
  else [label: Gate fails or flag is unreadable] {
    Execution Worker > Operational Database: Compare-and-set NEW to GATE_REJECTED
  }
}
Execution Worker > Operational Database: Find pending cancel command rows
Operational Database > Execution Worker: Pending cancel requests
loop [label: For each pending cancel] {
  Execution Worker > Paper broker: Send cancel, always allowed
  Paper broker > Execution Worker: Cancel status and any late fills
  Execution Worker > Operational Database: Save state using compare-and-set and deduplicate fills
}
```

### 9B — Outbox recovery after any process restart
```
Restarted process > Restarted process: Restart of Core Engine, Execution Worker, Research Worker or API Server
Restarted process > Operational Database: Find this process's outbox rows not yet published
Operational Database > Restarted process: Unpublished rows with their original event_id
loop [label: For each unpublished row] {
  Restarted process > Operational Database: Publish again with the same event_id, never a new one
  Restarted process > Operational Database: Mark row published
}
Consumer process > Operational Database: Read newly published events
Operational Database > Consumer process: Events with event_id and aggregate_version
loop [label: For each event] {
  alt [label: event_id not yet processed] {
    Consumer process > Operational Database: Apply the effect and record event_id as processed in one transaction
  }
  else [label: event_id already processed] {
    Consumer process > Consumer process: Skip - a duplicate message causes no duplicate action
  }
}
```
*Why this is safe:*
- Publishing is **at least once**, so a crash between "publish" and "mark published" can send the same event twice (Law 11).
- Duplicates are harmless, because the event keeps its original `event_id`, and each consumer records processed `event_id`s in the **same transaction** as the effect.
- Per-aggregate order is kept by `aggregate_version`.

---

## Checklist: what the diagrams must show
- [ ] Only the **Execution Worker** touches the broker (Diagrams 2, 3, 4, 7, 9). Law 2.
- [ ] The Core Engine, API Server and Research Worker hold **no broker keys** (Diagrams 2, 3, 8). Law 2.
- [ ] **Processes talk only through the Operational Database** (Diagrams 2, 3, 9). Part E.
- [ ] **Transition owners**: Core creates `NEW`; the Worker owns every other transition (Diagram 6). G3.
- [ ] Order transitions are **exactly G3**: includes `SUBMITTING → EXPIRED`; no `PARTIALLY_FILLED → EXPIRED`; `UNKNOWN` resolves to whichever state the broker confirms (Diagram 6).
- [ ] Every order-state write is a **compare-and-set** (Diagrams 3, 4, 6, 7, 9). Law 10.
- [ ] `SUBMITTING` is saved **before** the broker call; `UNKNOWN` is **never resent** (Diagrams 4, 6, 9). Law 14.
- [ ] Kill switch: **Admin CLI writes, Execution Worker reads**; it fails closed; **cancels always allowed** (Diagrams 2, 3, 7). Law 15.
- [ ] Late fills are accepted in `CANCEL_PENDING` (Diagrams 6, 7). G3.
- [ ] **Outbox recovery on any restart** keeps the original `event_id`, and consumers skip processed `event_id`s (Diagram 9B). G4, Law 11.
- [ ] Crash matrix (2b) present as Diagram 2's companion; it's at canvas position 10 in the current export. Part E.
- [ ] Superseded canvas copies (positions 6 and 9) are marked in the canvas map and never treated as current.
- [ ] Request/response links use `<>` in **both** the drawing and the code (arrow convention above).
