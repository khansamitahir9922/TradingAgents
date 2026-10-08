# HYBRID ARCHITECTURE v1.0 — FROZEN

> **Architecture frozen:** 2026-10-07
> **Change rule:** changes to the architectural laws, domain boundaries or execution authority **require a new ADR**: problem → alternatives → decision → consequences → update this document. Implementation work (Claude Code, Codex or a human) must not change the architecture without one.
> **Lineage:** merges Claude Code v0.1, ChatGPT v0.2, Claude's critique of v0.2, ChatGPT's v0.95 review, Claude's RC1 break-it findings, and ChatGPT's freeze review (Execution Worker + kill-switch permissions) with Claude's four follow-on fixes (Part O).
> **Source of truth:** this file (`architecture/architecture-v1.0.md`) and the ADRs in Git. Eraser diagrams are drawn *from* this document: the export is `architecture/diagrams/architecture-v1.0.svg`, and the diagram code is `architecture/eraser-diagrams.md`. If a diagram and this document disagree, this document wins.

---

## Part A — How this document was made

| Topic | Claude v0.1 | ChatGPT v0.2 | **Hybrid decision** | Why |
|---|---|---|---|---|
| Source of truth | "The database" | One store per domain | **One authoritative store per domain** | One place to look when state is disputed |
| Money type | Decimal everywhere | Decimal for money, float for quant | **Decimal at money boundaries; float64 in quant; explicit converters** | ML needs floats; accounting needs exact numbers |
| Decision object | UP / DOWN / WAIT | MarketView | **MarketView internally; UP/DOWN/WAIT only in the UI** | Rich and testable, still beginner-friendly |
| Data quality | — | Single 0–1 score | **Status per source + required sources per strategy** | A single score can't be justified |
| Confidence numbers | — | probability + confidence | **`strength` from rules; `probability_up` only from calibrated models** | Prevents fake precision |
| Approval vs order | One OMS | One state machine | **OrderIntent (approval) ≠ Order (execution)** | Small, correct state machines |
| Changing an approved trade | — | (v0.95) must not mutate silently | **Approved intents are immutable and versioned** | Approval means exactly what was approved |
| Last check before sending | Kill switch only | (v0.95) PreExecutionGate | **Final deterministic gate before every submission** | Approvals and data go stale |
| Risk modifying orders | — | approve / modify / reject | **Approve, reject, or reduce size (creates a new version)** | No hidden decisions |
| Kill switch | works without the app | external state | **Flag outside the DB; fails closed; never blocks cancels; only the Admin can write it** | Safe in an emergency, and can't be re-enabled by a compromised worker |
| Who holds broker credentials | Core Engine | (freeze review) Execution Worker | **Only the Execution Worker** | Module boundaries are not a security boundary |
| Event ordering | per instrument | (v0.95) per aggregate | **Event envelope + ordering per aggregate** | Orders, accounts and instruments are different streams |
| Market data | immutable | (v0.95) append-only revisions | **Never overwritten; corrections are new revisions** | Real vendors correct data; backtests stay point-in-time |
| Instruments | ID + vendor symbols | (v0.95) lifecycle + dated mappings | **Lifecycle + effective-dated symbol mappings** | Tickers change, firms delist (e.g. TWTR) |
| Ledger | append-only | double-entry | **Double-entry; securities model fixed by ADR before M5** | Shares and dollars are different units |
| Evaluation | replay tests | (v0.95) explicit capability | **Evaluation module (costs, slippage, walk-forward…)** | Backtests must be honest before ML |
| Reproducibility | "reproducible" | (v0.95) reconstructable | **All decisions reconstructable; deterministic parts reproducible** | LLMs can't be replayed exactly |
| Database | Postgres, SQLite in dev | (v0.95) SQLite only M1–M2 | **SQLite M1–M2; PostgreSQL from M3** | Concurrency and transactions must be tested for real |
| First asset class | US + crypto | US equities | **US equities/ETFs; crypto designed for, not built** | Halves the first build |
| Scope | One big v1 | Milestones | **Milestones M0–M10, each with a visible output** | Buildable by one developer |
| Diagrams | Eraser as truth | Git as truth | **Git as truth; Eraser for drawing** | Survives any tool change |

---

## Part B — Architecture drivers

### B1. Mission
Build a **safe, auditable, reconstructable** platform for investment research, portfolio management and **paper** execution. It combines slow AI research (TradingAgents), deterministic quant analysis, portfolio management, deterministic policy and risk checks, order management, execution, a ledger, reconciliation and audit.
It can grow toward institutional-style workflows without trying to replicate Bloomberg AIM or Aladdin. The first goals are **correctness and safety**, not profit or speed.

### B2. Decisions
| Driver | Decision |
|---|---|
| Trading horizon | **Swing trading on daily and hourly bars.** Contracts must also support 1-minute bars later without redesign. No HFT. |
| Asset class | **US equities and ETFs first.** Crypto has reserved interfaces only. |
| Users | **One organisation, a small team.** Roles: **Admin, Trader, Viewer.** No multi-tenancy. Every privileged action records who did it. |
| Autonomy | Highest level in v1 is **Level 2 (automatic paper)**. The default is **Level 0.** |
| Style | **Event-driven modular monolith with ports and adapters.** One shared Python codebase and domain model, run as **four processes** (API Server, Core Engine, Execution Worker, Research Worker). Not microservices. |

### B3. Autonomy levels (per account)
| Level | Name | What happens | v1 |
|---|---|---|---|
| 0 | Advisory | Research and market views only; no orders | ✅ **Default** |
| 1 | Approved paper | The system proposes paper orders; a human approves each one | ✅ |
| 2 | Automatic paper | Paper orders that pass policy and risk run automatically | ✅ |
| 3 | Approved live | A human approves each real order | ⛔ Reserved, disabled |
| 4 | Automatic live | Real orders without approval | ⛔ Disabled by policy |

### B4. Quality goals (in priority order)
1. **Safety**: nothing trades unless every policy, risk, autonomy and pre-execution check passes.
2. **Correctness and reconstructability**: every decision can be reconstructed; deterministic components are also exactly reproducible.
3. **Auditability and recoverability**: we can always explain what happened and recover from a crash.
4. **Simplicity and maintainability**: buildable by one developer with AI tools.
5. **Cost efficiency**: free or low-cost services during research.
6. **Performance and latency**: lowest priority, since this is swing trading.

---

## Part C — The 20 architectural laws

**Authority and safety**
1. **Models never execute.** LLMs, ML models, strategies and signals have no broker access. Only the path **OMS (approved Order) → Execution Worker (Pre-Execution Gate → Broker Adapter) → Broker** can submit orders. *Why: analysis must not have the power to move money.*
2. **Least capability (credential separation by process).** Each process holds only the credentials it needs:

   | Process | Holds | Never holds |
   |---|---|---|
   | **Execution Worker** | broker credentials | LLM keys, research keys |
   | **Core Engine** | market-data credentials that **cannot place orders** | broker trading credentials, LLM keys |
   | **Research Worker** | LLM + research-data keys | broker credentials |
   | **API Server** | user sessions only | any external-service credential |

   If a broker's market-data key can also trade, the Core Engine must not hold it. The Execution Worker ingests that feed instead, or a separate data vendor is used (ADR-011). Separation is by secret files per process in development, and enforced by **separate OS users or containers from M7**. *Why: module boundaries are not a security boundary. A misbehaving component must physically lack the credentials to trade.*
3. **Policy and risk are deterministic.** Every executable intent passes deterministic policy, risk and autonomy checks, and no LLM can override them. *Why: safety rules must be predictable and testable.*
4. **External data and LLM output are untrusted.** News, social posts, web pages and all LLM output are evidence, never instructions. LLM price levels never become order prices without passing risk. *Why: such content can be wrong or malicious (prompt injection).*

**Time and data**

5. **Time is explicit.** Business code never reads the system clock; time comes from an injected `Clock` (LiveClock or ReplayClock). Every event records `event_time`, `received_at` and `processed_at`, all in UTC. In replay, `received_at = event_time + simulated latency` (default 0), and events with equal times are ordered by a sequence number. *Why: backtest, paper and live must behave the same, and replays must be deterministic.*
6. **Calendars are explicit.** Sessions, holidays and half-days come from a Calendar service, with one implementation per market. *Why: not every hour is tradable.*
7. **Bars have state; strategies use closed bars.** Every candle is `FORMING` or `CLOSED`. In v1, strategies use **CLOSED bars only**. *Why: unfinished bars make live differ from backtest.*
8. **History is never overwritten.** Market data, corporate actions, ledger entries and audit events are append-only. A data correction is a **new revision**. A point-in-time view answers "what did we know at time T?". *Why: point-in-time backtests and financial history need the original record.*
9. **Missing data forces abstention.** Each strategy declares its required data sources. If one is STALE or MISSING, the MarketView is `ABSTAIN`. *Why: missing information must never become false confidence.*

**State and events**

10. **One authoritative store per domain** (Part F). Events announce changes; they're never the state itself. The order store has exactly **two writers with strictly separated transitions** (Part G3). Every write is a compare-and-set on `aggregate_version`, so a stale write fails instead of overwriting. *Why: there's exactly one place to check in a dispute, and no lost updates between processes.*
11. **Save, then publish.** State and its outbox row are committed in one transaction, then published. Every event carries the envelope in Part H. Ordering is guaranteed **per aggregate** (one order, one account, one instrument), using `aggregate_version`. Delivery is at least once, and consumers are idempotent. *Why: crashes must not desynchronise state and notifications.*

**Orders**

12. **Approved intents are immutable and versioned.** After approval, side, instrument, quantity, type, limit price and time-in-force never change. Any change, including a risk reduction made after approval, creates a **new intent version**. A material change needs a fresh approval. *Why: an approval must mean exactly what was approved.*
13. **A final gate runs before every submission.** The **Pre-Execution Gate** runs inside the Execution Worker; it's deterministic and cheap. It checks that:
    - the intent version is unchanged and its approval hasn't expired;
    - the MarketView and the reference price are still within their validity window;
    - the policy and risk decisions are still current, with no limit or position change since;
    - the market session allows the order's time-in-force;
    - the kill switch is enabled.

    It does not rerun the strategy. *Why: the world can change between approval and submission.*
14. **Orders are idempotent.** Every order gets a client order ID **before** it's submitted. The Execution Worker saves `SUBMITTING` before calling the broker. An order whose broker state is unknown goes to `UNKNOWN` and is reconciled, **never resent blindly**. *Why: retries and crashes must never create duplicate trades.*
15. **The kill switch is independent, fails closed and is Admin-only.** It's a trading-enabled flag stored **outside** the main database, read by the gate before every new submission. A missing, unreadable or disabled flag means no new orders. **Cancels are always allowed.** Only the **Admin CLI can write** the flag. The Execution Worker can **only read** it (OS file permissions; enforced from M7). *Why: trading must be stoppable when anything else is broken. Stopping must never trap open orders. A compromised worker must not be able to turn trading back on.*

**Money and records**

16. **Money uses Decimal.** Cash, balances, order and fill prices, fees and quantities are `Decimal` with an explicit currency or unit. Quant features and ML use `float64`. Conversion only happens through explicit converters. *Why: exact accounting, practical number crunching.*
17. **The ledger is double-entry and append-only.** Each transaction balances; errors are fixed with reversing entries. How cash value and **security quantities** are recorded is fixed by an ADR **before M5**. *Why: shares and dollars are different units and must not be balanced against each other carelessly.*
18. **Every decision is reconstructable.** Each recommendation and order links to its lineage (Part H). Deterministic components must reproduce exactly. LLM research must be *reconstructable*: its inputs, tool results, raw output, parsed result, settings and code version are stored, without claiming the LLM would answer identically again. *Why: "why did we do this?" must be answerable months later.*

**Change control**

19. **Research is separated from execution.** Experimental code, prompts and models never affect paper or live trading automatically; they must pass the promotion gates (Part K). *Why: experiments must never silently become production behavior.*
20. **Backtest, paper and live share the code.** The same strategy, portfolio, policy, risk, gate and OMS code runs in every mode. Only the adapters change: clock, market data and broker. In backtest, the simulated broker sits behind the same broker port, called by the same Execution Worker code. *Why: a backtest only means something if it runs the real code.*

---

## Part D — System context (C4 Level 1)

**People:** **Admin** (users, accounts, autonomy levels, kill switch, configuration) · **Trader** (reviews research and views, approves paper orders) · **Viewer** (read-only).

**The system:** *Investment Platform* (name to be decided).

| External system | Direction | Purpose | v1 |
|---|---|---|---|
| Research data sources (yfinance, SEC EDGAR, FRED, news, Reddit, StockTwits, Polymarket) | in | TradingAgents research; yfinance is research-only | ✅ |
| Market-data provider (paper broker feed or licensed vendor) | in | Bars and quotes for paper trading | ✅ M7 |
| LLM providers (Gemini now) | out/in | TradingAgents research | ✅ |
| Paper broker (to be chosen after the jurisdiction check) | out/in | Paper orders, fills, account state | ✅ M7 |
| Live broker | out/in | Real orders | ⛔ Future |

```
   Admin      Trader      Viewer
      \          |          /
       ▼         ▼         ▼
   ┌─────────────────────────────┐
   │     INVESTMENT PLATFORM     │
   └─────────────────────────────┘
     ▲        ▲          ▲      ▲
 Research   LLM      Market-   Paper broker
 data       providers data     (future: live broker)
 sources              provider
```

---

## Part E — Containers (C4 Level 2)

| Container | Technology | Responsibility | Credentials it holds | Milestone |
|---|---|---|---|---|
| **Web Dashboard** | Browser app (framework TBD) | Human interface | user session only | M8 |
| **API Server** | Python, FastAPI (REST + WebSocket) | Login, roles; records human commands (approve, decline, cancel request) | none to external services | M8 |
| **Core Engine** | Python modular monolith | Market, analysis, control, OMS (order creation and cancel requests), ledger, reconciliation, audit, lineage | market data **without trading rights** | M1–M7 |
| **Execution Worker** | Python process | Pre-Execution Gate, broker adapter, submission, cancellation, acknowledgements, fill ingestion, broker snapshots (and the broker data feed if its key can trade) | **broker credentials only** | M4 (simulated) / M7 (paper broker) |
| **Research Worker** | Python + TradingAgents | Slow LLM research jobs from a job table | LLM + research data only | M6 |
| **Operational Database** | SQLite in M1–M2, **PostgreSQL from M3** | Authoritative stores, outbox, job table, commands, broker snapshots | — | M1+ |
| **Market-Data Store** | Parquet (+ DuckDB queries) | Raw bars, corporate actions, append-only revisions | — | M1 |
| **Kill-Switch Flag** | Small file outside the main DB | Trading-enabled state; **Admin writes, Execution Worker reads** | — | M4 |
| **Admin CLI** | Python command-line tool | Kill switch (sole writer), approvals before M8, replays, reports | local admin only | M1+ |

```
                         Web Dashboard
                              │
                          API Server ──(human commands)──┐
                                                         ▼
  Research Worker ──(jobs, research records)──► OPERATIONAL DATABASE ◄──── Core Engine ──► Market-Data Store
   │  (LLM keys only)                         (orders, outbox, ledger,     (no broker keys)   ▲
   ▼                                           audit, broker snapshots)          ▲            │
 LLM providers + research data                        ▲                          │      Market-data provider
                                                      │                    (non-trading key)
                                            Execution Worker  ──read only──► Kill-Switch Flag ◄──write── Admin CLI
                                            (broker keys only)
                                                      │
                                                      ▼
                                                 Paper broker
```

**How processes talk:** only through the Operational Database (commands, job tables, outbox events), never by calling each other directly. If any process is down, the others keep their state, and work resumes from durable rows.

| If this crashes… | …then |
|---|---|
| Research Worker | Execution unaffected; views run without new research (or ABSTAIN if research is required) |
| API Server / Dashboard | Execution unaffected; the Admin CLI still works |
| Core Engine | Already-approved orders are durable; the Execution Worker carries on |
| Execution Worker | Orders stay recorded; on restart it reconciles by `client_order_id` |

---

## Part F — Modules and where they run (C4 Level 3)

| Group | Module | Runs in | Owns (authoritative) | Main contracts | Milestone |
|---|---|---|---|---|---|
| Market | **Instruments** | Core | Instrument master | `Instrument`, `SymbolMapping` | M1 |
| Market | **Calendar** | Core (shared library) | Session definitions | `TradingCalendar` | M1 |
| Market | **Time** | all (shared library) | — | `Clock` (Live, Replay) | M1 |
| Market | **Market Data** | Core (or Execution Worker for a trading-capable feed) | Market-data store | `MarketEvent`, `Candle`, `CorporateAction` (revisioned) | M1 / M7 |
| Market | **Data Quality** | Core | — | `DataHealth` | M1 |
| Analysis | **Quant** | Core | Feature definitions (versioned) | `FeatureSnapshot`, rule strategies | M2 |
| Analysis | **Evaluation** | Core / research tools | Evaluation runs | point-in-time datasets, cost/slippage models, walk-forward, benchmarks, universe rules | M2 → M9 |
| Analysis | **Research** | Research Worker (writes) / Core (reads) | Research records | `ResearchContext`, `ResearchRecord` | M6 |
| Analysis | **Decision** | Core | — | `MarketView` (deterministic, versioned policy) | M2 |
| Control | **Portfolio** | Core | Portfolio snapshots | `PortfolioSnapshot`, position sizer → `OrderIntent` | M3 |
| Control | **Policy** | Core | Policy rules (versioned) | `PolicyDecision` | M3 |
| Control | **Risk** | Core | Risk limits (versioned) | `RiskDecision` (approve / reject / reduce) | M3 |
| Trading | **OMS** | Core (create, cancel request) + Execution Worker (broker transitions) | **Order store** | `OrderIntent` (versioned), `Order` | M4 |
| Trading | **Pre-Execution Gate** | **Execution Worker** | — | `GateDecision` | M4 |
| Trading | **Execution / Broker Adapter** | **Execution Worker** | — | Broker port; simulated broker; paper adapter; `BrokerSnapshot` | M4 / M7 |
| Records | **Ledger** | Core | **Ledger store** | `Fill`, `LedgerEntry` | M5 |
| Records | **Reconciliation** | Core (compares) / Execution Worker (fetches `BrokerSnapshot`) | Incident records | `ReconciliationIncident` | M5 |
| Records | **Audit** | all processes (append) | **Audit store** | `AuditEvent` | M3+ |
| Records | **Lineage** | Core | Lineage records | `LineageRecord` | M2+ |

**Authoritative stores**
| Question | The answer lives in |
|---|---|
| What orders exist and what state are they in? | OMS order store |
| What cash, positions and P&L do we have? | Ledger (the broker is reconciled against it via `BrokerSnapshot`) |
| What did the market data say, and when did we know it? | Market-data store (revisioned) |
| Who did what? | Audit store |
| Why was this decision made? | Lineage + research records |

---

## Part G — Key flows

### G1. Trade lifecycle (paper, Level 1 or 2)
```
── CORE ENGINE (no broker keys) ──────────────────────────────────────────────
1  Market Data        CLOSED bar arrives (event_time, received_at)
2  Data Quality       DataHealth per source
3  Quant              FeatureSnapshot
4  Research           latest valid ResearchContext (optional)
5  Decision           MarketView (BULLISH / BEARISH / NEUTRAL / ABSTAIN)
6  Portfolio          sized OrderIntent v1 (PROPOSED)
7  Policy             autonomy, restricted list, trading window → pass / reject
8  Risk               limits, concentration, drawdown, stale data → approve / reject / reduce
9  Approval           Level 1: a human approves a specific version (audited). Level 2: automatic.
10 OMS                Order (NEW) with client_order_id, linked to intent version → save + outbox
── EXECUTION WORKER (broker keys only) ───────────────────────────────────────
11 Pre-Exec Gate      intent version, approval expiry, view validity, decisions current, session/TIF, kill switch
12 Execution          save SUBMITTING → submit → SUBMITTED
13 Broker             acknowledge → fills
14 Execution          record broker transitions + fills (compare-and-set; idempotent; late fills accepted)
── CORE ENGINE ───────────────────────────────────────────────────────────────
15 Ledger             double-entry entries for each new fill and its fees
16 Reconciliation     OMS + ledger vs latest BrokerSnapshot → incident if they differ
17 Audit + Lineage    at every step, in every process
```

### G2. OrderIntent lifecycle (approval, Core Engine only)
```
PROPOSED → POLICY_REJECTED | RISK_REJECTED
PROPOSED → SUPERSEDED (risk reduced it → new version PROPOSED)
PROPOSED → AWAITING_APPROVAL (Level 1) → APPROVED | DECLINED | EXPIRED
PROPOSED → APPROVED (Level 2)
APPROVED → CONVERTED (an Order is created) | EXPIRED | SUPERSEDED (material change → new version)
```

### G3. Order lifecycle and who owns each transition
```
NEW → GATE_REJECTED                         (the gate failed; nothing was sent)
NEW → SUBMITTING → SUBMITTED → PARTIALLY_FILLED → FILLED
SUBMITTED | PARTIALLY_FILLED → CANCEL_PENDING → CANCELLED
CANCEL_PENDING → PARTIALLY_FILLED | FILLED  (late fills are always accepted)
SUBMITTING | SUBMITTED → REJECTED | EXPIRED
SUBMITTING (timeout, state unknown) → UNKNOWN → reconciled to the true state (never resent)
```
| Transition | Owner (only writer) |
|---|---|
| create `NEW` | Core Engine (OMS) |
| record a **cancel request** (a command row; not a state change) | Core Engine or API Server command |
| `NEW → GATE_REJECTED / SUBMITTING`, and every broker-driven transition (SUBMITTED, PARTIALLY_FILLED, FILLED, CANCEL_PENDING, CANCELLED, REJECTED, EXPIRED, UNKNOWN and its resolution) | Execution Worker |

Both processes use **one shared state-machine module**. Every write is a compare-and-set on `aggregate_version`.

### G4. Crash recovery
- **Execution Worker restart:** orders in `SUBMITTING` or `UNKNOWN` are looked up at the broker by `client_order_id` and set to their true state. Orders still `NEW` go through the gate again before submission. Cancel requests not yet acted on are sent.
- **Any restart:** unpublished outbox rows are published again; consumers ignore duplicates using `event_id`.

### G5. Kill switch
The Admin flips the flag through the Admin CLI, the only writer; it works when everything else is down. The Execution Worker's gate reads it before every **new** submission and has no write permission. Missing or unreadable means reject. Cancels always pass. The runbook covers the broker's own "cancel all".

### G6. Research (slow path)
A request creates a job row. The Research Worker (LLM credentials only) runs TradingAgents within a daily LLM budget. It saves a **ResearchRecord** (settings, model, prompt and input snapshot, tool results, raw response, warnings, code version) and the parsed **ResearchContext**, then publishes an event. Research is **never** on the bar-to-order path, and it physically has no broker credentials.

---

## Part H — Core contracts (key fields; full schemas are written in each milestone)

- **EventEnvelope**: `event_id`, `event_type`, `schema_version`, `aggregate_type`, `aggregate_id`, `aggregate_version`, `occurred_at`, `recorded_at`, `correlation_id`, `causation_id`, `payload`.
- **Instrument**: `instrument_id` (e.g. `EQ_US_NVDA`), `asset_class`, `currency`, `exchange`, `timezone`, `status: ACTIVE|DELISTED|SUSPENDED`, `active_from`, `active_to`.
- **SymbolMapping**: `instrument_id`, `provider`, `symbol`, `valid_from`, `valid_to`.
- **Candle**: `instrument_id`, `timeframe`, OHLC (Decimal at the boundary), `volume`, `start_time`, `end_time`, `state: FORMING|CLOSED`, `source`, `event_time`, `received_at`, `processed_at`, `revision`. Prices are raw (unadjusted).
- **CorporateAction**: `instrument_id`, `type: SPLIT|DIVIDEND|SYMBOL_CHANGE|DELISTING`, `ex_date`, `ratio/amount`, `source`, `revision`.
- **DataHealth**: per source `{status: OK|STALE|MISSING|DEGRADED, age, detail}`; `required_sources_ok`.
- **MarketView**: `instrument_id`, `direction: BULLISH|BEARISH|NEUTRAL|ABSTAIN`, `strength` (0–1, **not** a probability), `probability_up?` (calibrated models only), `horizon`, `generated_at`, `valid_until`, `regime?`, `data_health`, `evidence_refs`, `policy_version`.
- **ResearchContext**: `run_id`, `instrument_id`, `rating`, `suggested_levels` (untrusted), `horizon`, `generated_at`, `valid_until`, `warnings`.
- **ResearchRecord**: `run_id`, provider/model/version, settings, prompt/input snapshot, tool results, data-source snapshot refs, raw response, parsed `ResearchContext`, warnings, code version, timestamps.
- **OrderIntent**: `intent_id`, `version`, `account_id`, `instrument_id`, `side`, `quantity` (Decimal), `order_type`, `limit_price?`, `time_in_force`, `reference_price`, `state`, `policy_decision`, `risk_decision`, `approved_by?`, `approved_at?`, `approval_expires_at?`, `lineage_id`.
- **Order**: `order_id`, `client_order_id`, `intent_id`, `intent_version`, `time_in_force`, `state`, `aggregate_version`, `filled_qty`, `avg_price`, `broker_order_id?`.
- **CancelRequest**: `order_id`, `requested_by`, `requested_at`, `reason`, `status`.
- **GateDecision**: `order_id`, `passed`, failed checks with reasons, `checked_at`.
- **Fill**: `fill_id`, `order_id`, `quantity`, `price`, `fee`, `currency`, `executed_at`, `broker_fill_id` (unique, for de-duplication).
- **BrokerSnapshot**: `taken_at`, positions, open orders, cash, as reported by the broker. Written by the Execution Worker.
- **LedgerEntry**: `entry_id`, `transaction_id`, `account`, `debit`, `credit`, `unit` (currency or instrument), `posted_at`, `reverses?`. The exact securities model is set by the ADR before M5.
- **ReconciliationIncident**: what differed (internal vs `BrokerSnapshot`), when, status.
- **AuditEvent**: `actor` (user or process), `action`, `target`, `before`, `after`, `at`, `reason`.
- **LineageRecord**: references to bars (with revisions), feature version, strategy version, research run, model version, portfolio snapshot, policy/risk versions, DataHealth, code version.

**UI mapping:** BULLISH → ↑ UP · BEARISH → ↓ DOWN · NEUTRAL, ABSTAIN or expired → ● WAIT.

---

## Part I — TradingAgents boundary
- Runs only in the **Research Worker** (no broker credentials), behind one adapter.
- Produces a `ResearchRecord` and a typed `ResearchContext`. This needs one small, documented upstream change: keep the Trader's and Portfolio Manager's structured output. Prompts and tool results can be captured through LangChain callbacks inside the adapter.
- It can't execute, size, or bypass portfolio, policy, risk or the gate. Its output is advisory evidence with `valid_until`.
- Upstream changes stay minimal and listed, so new upstream releases can be merged.
- Known limits: daily granularity, minutes per run, LLM quota, untrusted text in prompts, and no exact reproducibility.

---

## Part J — Testing strategy
- **Unit tests** for individual logic.
- **Property/invariant tests**:
  - rejected intents never become orders;
  - a REJECTED or GATE_REJECTED order never becomes FILLED;
  - duplicate broker messages never create duplicate fills;
  - UNKNOWN orders are never resubmitted;
  - nothing new is submitted while the kill switch is off or unreadable, and cancels still pass;
  - an approved intent version never changes;
  - a stale compare-and-set write on an order always fails;
  - each order transition is written only by its owning process;
  - ledger transactions balance and ledger rows are never updated;
  - no path reaches the broker without Policy, Risk and the Gate;
  - no process other than the Execution Worker can load broker credentials.
- **Contract tests**: each broker adapter passes the same suite as the simulator.
- **Replay tests**: same data and versions give the same views, intents and orders.
- **Scenario tests**: the full G1 lifecycle across processes.
- **Fault injection**: kill the Execution Worker mid-submission; kill the Core Engine after approval; broker timeout; DB restart; duplicate fill; late fill after cancel; duplicate WebSocket message; stale feed; missing research; data revision mid-run; approval expiring before submission; a concurrent cancel request and fill.

---

## Part K — Milestones and promotion gates

| Milestone | Builds | You can see |
|---|---|---|
| **M0** Architecture | This document, ADRs, C4 diagrams | v1.0 frozen + diagrams |
| **M1** Market foundation | Instrument + SymbolMapping, Clock, Calendar, Candle, CorporateAction, revisions, replay feed, resampler, DataHealth (SQLite) | CLI: replay NVDA → clean daily/hourly candles + health report |
| **M2** Quant + basic evaluation | Indicators, FeatureSnapshot, rule strategies, MarketView, lineage, evaluation with costs and next-bar prices (SQLite) | HTML report: NVDA chart with MarketViews + an honest evaluation |
| **M3** Portfolio, policy, risk | **Move to PostgreSQL.** PortfolioSnapshot, sizer, versioned OrderIntent, policy (autonomy), risk, audit | CLI: proposed intents with approve/reject/reduce reasons |
| **M4** OMS + Execution Worker (simulated) | Order state machine with transition ownership + compare-and-set, **Execution Worker process**, Pre-Execution Gate, simulated broker (own state, fees, slippage, next-bar fills), kill switch (Admin-only write), outbox, crash recovery | Simulated paper run + order log + crash tests on both processes |
| **M5** Ledger + reconciliation | **ADR: securities ledger model first.** Double-entry ledger, positions/cash/P&L, BrokerSnapshot from the simulator, reconciliation | P&L + reconciliation reports |
| **M6** TradingAgents adapter | Research Worker, ResearchRecord, ResearchContext, LLM budget | Research shown alongside the MarketView |
| **M7** Paper broker + hosting | **ADR: broker choice after the jurisdiction check (incl. whether its data key can trade).** Paper-broker adapter in the Execution Worker; move to a VPS with **separate OS users/containers per process and a read-only kill-switch flag for the Execution Worker** | Real paper orders on the broker's paper account |
| **M8** API + dashboard | FastAPI, WebSocket, login/roles, minimal UI | Web dashboard |
| **M9** ML | Datasets, model registry, calibrated `probability_up`, walk-forward evaluation | Champion/challenger report |
| **M10** Live | Only after long paper validation and governance | — |

**Promotion gates** (from research to paper; live comes later): replay tests pass → evaluation with costs and walk-forward → shadow mode (views only) → paper at Level 1 → paper at Level 2 → (future) live.

**ADRs to write in M0:**
- ADR-001: TradingAgents is an asynchronous research service.
- ADR-002: Models never execute; credential separation by process (Execution Worker is the only broker-credential holder).
- ADR-003: Internal instrument IDs + effective-dated symbol mappings.
- ADR-004: OrderIntent/Order split, versioning, transition ownership and the Pre-Execution Gate.
- ADR-005: Event envelope, outbox, per-aggregate ordering, communication only through the database.
- ADR-006: Kill-switch mechanism (outside the DB, fail closed, cancels allowed, Admin CLI sole writer, Execution Worker read-only).
- ADR-007: Decimal/float64 boundary.
- ADR-008: Database choice (SQLite → PostgreSQL at M3).
- ADR-009: Append-only revisions and point-in-time views.

**Later:**
- ADR-010: securities ledger model (before M5).
- ADR-011: broker and data provider, including whether the data key can trade (before M7).
- ADR-012: hosting and OS-level process isolation (before M7).

---

## Part L — Designed for, but deferred
Crypto · 1-minute live strategies · ML and model registry · browser extension · separate compliance service · Redis/NATS/Kafka · microservices · Prometheus/Grafana/OpenTelemetry · SSO · multi-tenancy · multiple live brokers · TWAP/VWAP execution · live trading.

---

## Part M — Open decisions (with a recommendation for each)
| Decision | Recommendation |
|---|---|
| Jurisdiction and broker eligibility | **Decide first.** It sets the paper broker and the data feed. |
| Paper broker | Free paper account + API for US equities (verify eligibility; check whether its data key can trade) |
| Production market data | The paper broker's feed in M7, ingested by whichever process may hold its key; yfinance stays research-only |
| Hosting | Laptop for M1–M6; a small VPS with per-process OS users/containers from M7 |
| Monthly budget | To be decided (data + LLM + hosting) |
| Authentication | Username/password + roles in M8; SSO later |
| Retention | Market data, ledger, audit, research records: keep forever; logs: 90 days |
| Backup | Daily DB backup + market-data store snapshot from M5 |

**No live-execution design is final until broker eligibility and the regulatory rules in your jurisdiction are verified.**

---

## Part N — Diagrams (Eraser)
Nine diagrams, in this order:
1. System context (Part D)
2. Containers, with credentials and the Execution Worker (Part E)
3. Modules and where they run (Part F)
4. Sequence: trade lifecycle across Core Engine and Execution Worker (G1)
5. State machine: OrderIntent (G2)
6. State machine: Order, with transition owners (G3)
7. Sequence: kill switch and cancel (G5)
8. Sequence: research slow path (G6)
9. Sequence: crash recovery: Execution Worker reconciliation, plus outbox recovery after any restart (G4)

Diagram 2 has a companion, 2b (the Part E crash matrix), and Diagram 9 is drawn as 9A (Execution Worker restart) and 9B (outbox recovery). The SVG is a full-canvas snapshot that also holds superseded earlier copies; `eraser-diagrams.md` maps every block.

- **Exported diagrams:** `architecture/diagrams/architecture-v1.0.svg`
- **Diagram code:** `architecture/eraser-diagrams.md`

---

## Part O — Change log
- **RC1**: added credential separation, revisions, immutable intents, the Pre-Execution Gate and the event envelope; reconstructable research; kill switch never blocks cancels; late fills; replay tie-breaks; time-in-force; Instrument lifecycle + SymbolMapping; Evaluation module; ResearchRecord; PostgreSQL from M3; ADR list.
- **v1.0 FROZEN** (2026-10-07):
  - **Execution Worker** split from the Core Engine; it's the only holder of broker credentials, and the gate runs inside it (ChatGPT freeze review).
  - The kill-switch flag is **Admin-only write**, and the Execution Worker can only read it (ChatGPT freeze review).
  - Order-store **transition ownership + compare-and-set** for the two writers (Claude follow-on).
  - **BrokerSnapshot** lets reconciliation run without broker credentials in the Core Engine (Claude follow-on).
  - The Core Engine may hold only **non-trading** market-data credentials (Claude follow-on).
  - **OS-level process isolation from M7**, with development-time separation stated honestly as convention (Claude follow-on).
  - Processes communicate **only through the database**.
  - Crash matrix added.
  - Change rule added.
- **Housekeeping, 2026-10-08 (no architectural change):** file renamed from `hybrid-architecture-v1.0-draft.md`; nine diagrams exported to `architecture/diagrams/architecture-v1.0.svg`; `eraser-diagrams.md` synced with the drawn diagrams.

---

## Part P — Changing this architecture
Frozen doesn't mean unchangeable. It means every change goes through:

```
problem found → ADR (context, alternatives, decision, consequences) → review → accept/reject → update this document
```

Coding work must not introduce new processes, services, message brokers or boundary changes (e.g. "add Kafka", "split into microservices") without an accepted ADR. Implementation details *inside* a module's boundary are free to evolve.
