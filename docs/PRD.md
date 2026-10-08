# Product Requirements Document (PRD)

| | |
|---|---|
| **Product** | **Investment Platform** (working product name; public branding not decided, see OPEN-01) |
| **Python package** | `investment_engine` (**proposed**; confirmed in M1-00, see OPEN-01) |
| **Document status** | **Reviewed v0.1.** Codex document review passed (2026-10-09); committed with the owner's approval; awaiting review of the M0 commit and the owner-approved merge into `main`. |
| **Date** | 2026-10-08 |
| **Product owner** | Repository owner |
| **Source of truth for architecture** | `architecture/architecture-v1.0.md` (v1.0 FROZEN). This PRD describes *what* to build and *why*; the architecture describes *how* it's structured. If they disagree, the architecture wins until an ADR changes it. |

**How to read the markers**
- **[Arch §X]** traces a statement to a section of the frozen architecture.
- **OPEN-nn** marks an unresolved product decision (all listed in Section 10). Nothing marked OPEN may be assumed during implementation; resolve it first or record a default in the relevant task spec.

---

## 1. Product summary

A **safe, auditable, reconstructable** platform for investment research, portfolio management and **paper** execution of US equities and ETFs. It combines:
- slow AI research (TradingAgents);
- deterministic quant analysis;
- deterministic policy and risk controls;
- order management, a ledger and reconciliation.

All of this is presented in a dashboard that a small team can trust. **[Arch B1]**

The first goal is **correctness and safety**, not profit or speed. The platform is designed to grow toward institutional-style workflows, but v1 is not a Bloomberg AIM or Aladdin replacement. **[Arch B1]**

## 2. Problem and opportunity

- **Impressive screens aren't evidence.** A trading dashboard is only trustworthy if every number on it can be traced to a recorded fact: a ledger, reconciliation against the broker, and an honest evaluation. Analysis tools must also not have direct power to trade.
- **Raw LLM research isn't safe to act on.** TradingAgents produces useful research, but its output is untrusted text with no execution safeguards. **[Arch I]**
- **The opportunity** is a platform where AI research is *one advisory input*. Every trade passes deterministic checks, a human can approve each paper order, and every number on screen traces back to a recorded fact.

## 3. Product goals

| ID | Goal | Architecture basis |
|---|---|---|
| G1 | **Safety first.** Policy, risk and autonomy checks (plus human approval at Level 1) must pass **before** the Core Engine creates a `NEW` order. The **Execution Worker** then runs the final Pre-Execution Gate before each broker submission. The Admin's kill switch **stops new submissions**, even if the rest of the app is down; cancels are still allowed. | Laws 1–3, 12, 13, 15; Part G1 |
| G2 | **Trustworthy decisions.** Every market view, intent and order is reconstructable: which data, rules, research, versions and person produced it. | Laws 8, 18 |
| G3 | **Honest uncertainty.** When required data or research is missing or stale, the system says **ABSTAIN / WAIT**; it doesn't guess. | Law 9 |
| G4 | **Realistic paper trading.** In **simulation and evaluation**, fills follow a stated model (fees, slippage, next-bar fills). With a **real paper broker**, fills are recorded exactly **as the broker reports them**. Either way they go into a double-entry ledger reconciled against the broker's state. | Laws 14, 16, 17; Part K M4–M7 |
| G5 | **AI as an advisor, not a trader.** TradingAgents research enriches decisions but can never execute, size or bypass controls. | Laws 1, 2, 4; Part I |
| G6 | **Honest evaluation.** Strategies are judged with costs, slippage, point-in-time data and walk-forward tests before they affect paper trading. | Part F Evaluation; Part K promotion gates |
| G7 | **Usable by a small team.** Admin, Trader and Viewer roles; a clear dashboard; changes are auditable. | B2; Part E |
| G8 | **Buildable by one developer with AI tools.** Small milestones, each with a visible result. | B4.4; Part K |

## 4. Users and roles

One organisation, a small team, no multi-tenancy. Every privileged action is audited with the person's identity. **[Arch B2]**

| Capability | Admin | Trader | Viewer |
|---|:---:|:---:|:---:|
| View dashboard, market views, research, positions, P&L, health | ✅ | ✅ | ✅ |
| View decision lineage ("why did we do this?") | ✅ | ✅ | ✅ |
| Request a TradingAgents research run (within budget) | ✅ | ✅ | ❌ |
| Approve / decline a paper order intent (Level 1) | ✅ | ✅ | ❌ |
| Request cancellation of an open paper order | ✅ | ✅ | ❌ |
| Acknowledge / resolve a reconciliation incident | ✅ | OPEN-12 | ❌ |
| Set an account's autonomy level (0–2) | ✅ | ❌ | ❌ |
| See the kill-switch state, autonomy level and PAPER mode (dashboard displays them) | ✅ | ✅ | ✅ |
| Turn the kill switch on/off: **Admin CLI only** (sole writer; not possible from the dashboard or API) | ✅ | ❌ | ❌ |
| Manage users, roles, instruments, policy and risk limits | ✅ | ❌ | ❌ |

**Personas**
- **Admin.** Owns configuration and safety: users, accounts, autonomy levels, the kill switch, limits. **[Arch D]**
- **Trader.** Reviews research and market views, approves or declines paper orders, monitors positions. **[Arch D]**
- **Viewer.** Read-only stakeholder who follows performance and decisions. **[Arch D]**

> Before M8 (login and roles), a single configured local identity acts through the Admin CLI, and its actions are audited.

## 5. Autonomy levels (product view)

| Level | Name | User experience | v1 |
|---|---|---|---|
| 0 | Advisory | Research and market views only; no orders. **Default for every account.** | ✅ |
| 1 | Approved paper | The system proposes paper orders; a Trader approves or declines each exact version before it expires. | ✅ |
| 2 | Automatic paper | Paper orders that pass policy, risk and the gate run automatically. | ✅ |
| 3 | Approved live | — | ⛔ disabled |
| 4 | Automatic live | — | ⛔ disabled by policy |

**[Arch B3]**

## 6. Use cases

| ID | Use case | Primary role | Outcome | Arch |
|---|---|---|---|---|
| UC-01 | **See the current view of an instrument.** On each closed bar, see BULLISH / BEARISH / NEUTRAL / ABSTAIN (shown as ↑ UP / ↓ DOWN / ● WAIT) with strength, horizon, validity and reasons. | All | A transparent market view | G1, H |
| UC-02 | **Understand an abstention.** See which required source was stale or missing. | All | Trust through honesty | Law 9 |
| UC-03 | **Request AI research.** Ask for a TradingAgents run on an instrument; it runs in the background within a daily budget, and its result is stored and expires. | Trader, Admin | Fresh advisory research | G6, I |
| UC-04 | **Approve a paper trade (Level 1).** Review a proposed intent (side, size, price, policy and risk results, reasons); approve that exact version or decline it before it expires. The Core then creates the `NEW` order, and the Execution Worker's gate re-checks it before submission. | Trader | A human-controlled paper order | Laws 12, 13; G2 |
| UC-05 | **Run automatic paper trading (Level 2).** Approved-by-rule intents execute without clicks; every step is visible and audited. | Admin (sets level) | Hands-off paper trading | B3 |
| UC-06 | **Halt trading.** Turn the kill switch off from the **Admin CLI** (its only writer); the Execution Worker stops **new submissions**, while cancels still work. The dashboard shows the halted state but can't change it. | Admin | Immediate, reliable stop | Law 15; G5 |
| UC-07 | **Cancel an open order.** Request a cancel; it's sent even while trading is halted; late fills are still recorded. | Trader, Admin | Control over open exposure | G3, G5 |
| UC-08 | **See positions, cash and P&L.** Derived from the ledger, including fees. | All | Accurate accounting | Law 17 |
| UC-09 | **Reconcile with the broker.** Compare the ledger and orders with the broker snapshot; differences raise an incident. | Admin | Confidence the books are right | Part F, G1 |
| UC-10 | **Explain any decision.** From a view, intent or order, open its lineage: bars, features, rules, research, versions, approver. | All | Reconstructability | Law 18 |
| UC-11 | **Evaluate a strategy historically.** Replay history through the same code with a stated cost model and **simulated** next-bar fills; produce an evaluation report. Grows by milestone:<br>• initial evaluation at M2;<br>• **walk-forward evaluation must be in place, and passed (thresholds OPEN-09), before any strategy is promoted to paper trading** (promotion path, Section 7);<br>• through the order path at M4;<br>• with ledger P&L at M5;<br>• M9 **extends** walk-forward evaluation to ML models. It isn't first introduced there. | Admin, Trader | Honest evidence before paper | Law 20; Part F |
| UC-12 | **Monitor system health.** Data freshness, process status, research budget, kill switch, last reconciliation. | All | Early warning | Part E crash matrix |
| UC-13 | **Recover after a crash.** *(Automatic; results are visible in health and audit.)*<br>(a) When the **Execution Worker** restarts, it reconciles uncertain orders (`SUBMITTING` / `UNKNOWN`) by `client_order_id` and never resends blindly.<br>(b) When **any process** restarts, it resumes publishing its unsent outbox messages with their original `event_id`, so consumers take no duplicate actions. | — | No lost or duplicated trades | G4; Laws 11, 14 |
| UC-14 | **Administer the platform.** Manage users, roles, instruments, policy and risk limits, autonomy levels; every change is audited. | Admin | Controlled configuration | B2 |

## 7. Features per milestone

Each milestone ends with something you can see. **[Arch K]** Capabilities arrive in order:
- **evaluation** begins at M2;
- **intent proposal and review** at M3;
- **execution** at M4;
- **accounting** at M5;
- **real paper-broker trading** at M7;
- the **web UI** at M8.

Coverage is marked **(partial)** until a use case is complete.

| Milestone | User-visible result | Key features | Use-case coverage |
|---|---|---|---|
| **M0 Architecture** | Frozen architecture, diagrams, PRD, ADRs, roadmap | Documentation and the agreed working method | — |
| **M1 Market foundation** | CLI: replay **NVDA** (the frozen M1 baseline) → clean daily/hourly candles + data-health report | Instrument master + dated symbol mappings, calendar (US equities), clock, candles with revisions, corporate actions, replay feed, resampler, DataHealth (SQLite) | UC-02 (partial: data health only, no views yet) |
| **M2 Quant + initial evaluation** | HTML report: NVDA chart with market views over history + an **initial** evaluation | Indicators, features, rule strategies, MarketView, lineage, **initial evaluation with a stated cost model and next-bar prices**. This is *not* full execution replay: there are no orders, OMS or ledger yet. | UC-01; UC-02; UC-10 (partial: views only); UC-11 (partial: initial evaluation) |
| **M3 Portfolio, policy, risk** | CLI: **proposed** intents with approve / reject / reduce reasons, and Level 1 approve/decline at the CLI | PostgreSQL, portfolio snapshot, position sizer, versioned OrderIntent, policy (autonomy), risk, audit. **No orders are created or executed yet.** | UC-04 (partial: proposal and review; no execution); UC-10 (partial: intents); UC-14 (partial: CLI) |
| **M4 OMS + Execution Worker (simulated)** | Simulated paper run, order log, crash tests | Order state machine, Core creates `NEW`, Execution Worker with the Pre-Execution Gate, **simulated** broker (fees, slippage, next-bar fills), kill switch (Admin CLI), outbox, crash recovery | UC-04 (complete in simulation); UC-05; UC-06; UC-07; UC-10 (partial: orders); UC-13; UC-11 (partial: replay now runs through the order path). **Only strategies that have passed walk-forward evaluation may run as paper trading.** |
| **M5 Ledger + reconciliation** | P&L and reconciliation reports | Securities ledger (ADR first), positions, cash, P&L, BrokerSnapshot from the simulator, reconciliation incidents | UC-08; UC-09; UC-11 (partial: evaluation can include ledger P&L) |
| **M6 TradingAgents adapter** | Research shown alongside the market view | Research Worker, ResearchRecord, ResearchContext, LLM budget | UC-03; UC-10 (complete: research lineage added) |
| **M7 Paper broker + hosting** | Real orders on a broker's **paper** account | Broker adapter in the Execution Worker (ADR after the jurisdiction check); fills **recorded as the broker reports them**; VPS with process isolation | UC-04 – UC-09 against a real paper account |
| **M8 API + dashboard** | Web dashboard (see `docs/design-principles.md`, review draft) | FastAPI, WebSocket, login and roles, cockpit-style UI. The dashboard **displays** safety state (kill switch, autonomy level, PAPER mode) and crash-recovery results; **kill-switch writes remain Admin CLI-only**. | UC-01 – UC-05, UC-07 – UC-12 and UC-14 in the UI; UC-06 is **displayed** only (written via the Admin CLI); UC-13 results **displayed** |
| **M9 ML** | Champion / challenger report | Datasets, model registry, calibrated probabilities, **walk-forward evaluation extended to ML models** | UC-11 (extended to ML) |
| **M10 Live** | — | Only after long paper validation and governance | Not in v1 |

**Promotion path for any strategy:** replay tests pass → evaluation with costs and walk-forward → shadow mode (views only) → paper Level 1 → paper Level 2 → (future) live. **[Arch K]**

## 8. Product requirements that apply everywhere

1. **Paper only in v1.** No live broker connection, no real money. Live levels 3–4 stay disabled. **[Arch B3, L]**
2. **Always-visible safety state.** Every screen shows PAPER mode, the account's autonomy level and the kill-switch state.
3. **No invented numbers on screen.** Every displayed number traces to a stored record: ledger, OMS, market data, research, or a **recorded simulator/replay result**. Simulator and replay results are allowed only when **clearly labelled** (e.g. `SIMULATED`, `REPLAY`). Decorative, placeholder or made-up figures are never shown. *(The design and honesty rules are set out in `docs/design-principles.md`, currently a review draft.)*
4. **Fills are facts, not assumptions.** Next-bar fills, slippage and fee models apply **only** in simulation and evaluation. Fills from a real paper broker are recorded exactly as the broker reports them.
5. **ABSTAIN / STALE / HALTED are unmissable.** They're the most prominent state on screen when they occur.
6. **AI output is labelled advisory.** Research shows its generation time, expiry, model and warnings. LLM-suggested price levels are never used as order prices without the risk checks. **[Law 4]**
7. **Every privileged action is audited** with actor, time, before → after, and reason. **[Arch H AuditEvent]**
8. **Times are shown in exchange time with UTC available;** all storage is in UTC. **[Law 5]**
9. **Money shown exactly** (Decimal) with currency. **[Law 16]**

## 9. Non-goals for v1

- Live trading with real money (Levels 3–4). **[Arch L]**
- Crypto, forex, options, futures or any non-US-equity asset class (crypto is designed for, not built). **[Arch B2, L]**
- Intraday 1-minute strategies or any latency-sensitive / HFT trading. **[Arch B2]**
- Multi-tenancy, external clients or SSO. **[Arch B2, L]**
- A browser extension, mobile app or public website.
- Advanced execution algorithms (TWAP/VWAP), multiple brokers, smart routing. **[Arch L]**
- Microservices, Kafka, Redis, Prometheus/Grafana. **[Arch L]**
- Investment advice to third parties, or any product that implies guaranteed returns.
- Replicating institutional platforms (Bloomberg AIM, Aladdin). **[Arch B1]**

## 10. Unresolved product decisions

These are **open**. Each needs an owner decision (and an ADR where it touches architecture) before the milestone shown.

| ID | Decision | Needed by | Notes / recommendation |
|---|---|---|---|
| **OPEN-01** | **Public branding** and **Python package name** (two separate decisions) | Package: M1-00. Branding: before any public use | **Working product name: Investment Platform.** **Proposed package name: `investment_engine`**, to be confirmed in M1-00; it must **not** be `platform` (clashes with Python's standard library). Public branding is decided later and doesn't block development. |
| **OPEN-02** | **Jurisdiction and broker eligibility** | M7 (ADR-011) | Decides the paper broker and data feed. No live-execution design is final until verified. **[Arch M]** |
| **OPEN-03** | **Paper broker choice** | M7 | Must offer a free paper account and an API for US equities; check whether its data key can trade (Law 2). |
| **OPEN-04** | **Production market-data provider** | M7 | yfinance stays research-only. **[Arch M]** |
| **OPEN-05** | **Instrument universe beyond NVDA** | Before M2/M3 evaluations need more instruments | **NVDA is the frozen M1 baseline.** Which additional US equities and ETFs, and how many, is open, and doesn't block the M1-00 skeleton or M1. |
| **OPEN-06** | **First rule strategies and required data sources** | M2 | Which indicators and rules produce the MarketView, and which sources are *required* (Law 9)? |
| **OPEN-07** | **Default risk and policy limits** | M3 | Max position % of equity, concentration, drawdown halt, trading windows, restricted list. |
| **OPEN-08** | **Approval expiry and view validity windows** | M3 | How long a Level 1 approval stays valid; how long a MarketView stays valid per timeframe. |
| **OPEN-09** | **Evaluation and promotion thresholds** | M2 / before M4 | What metrics and minimum values (after costs) a strategy needs to move to shadow, Level 1 and Level 2; holding horizon and benchmark. |
| **OPEN-10** | **Research cadence, LLM provider/models and daily budget** | M6 | Rate limits vary by model, project and tier, so they must be **verified from the provider's current quota documentation and console** before M6. The **request count and cost per TradingAgents run must be measured**, not estimated. *Reported observation (no saved record):* the owner reported hitting a free-tier daily quota during the baseline work, which suggests rationing or a paid tier may be needed. |
| **OPEN-11** | **Monthly budget** (data + LLM + hosting) | M6 / M7 | **[Arch M]** |
| **OPEN-12** | **Who may resolve reconciliation incidents** | M5 | Admin only, or Admin + Trader? |
| **OPEN-13** | **Team members and role assignment** | M8 | Who the users are; how many Admins. |
| **OPEN-14** | **Hosting** | M7 | Recommendation: laptop for M1–M6, a small VPS with per-process OS users or containers from M7. **[Arch M]** |
| **OPEN-15** | **Dashboard technology** | M8 | Recommended direction: React + TradingView lightweight-charts + WebGL/D3 for the decision graph. Must follow `docs/design-principles.md`. |
| **OPEN-16** | **Proposed order-lifecycle extensions (unaccepted)** | Before M4 | Two **unaccepted proposals**: (a) a partially filled DAY order whose remainder expires at the close; (b) the state to record when the broker has no record of an `UNKNOWN` order. **ADR-004 documents the frozen Part G3 lifecycle as it stands.** Adopting either proposal needs a **reviewed follow-up ADR** plus an update to `architecture-v1.0.md`; until then G3 is unchanged. |
| **OPEN-17** | **Reporting needs** | M5 / M8 | Which reports the team needs (daily P&L, decision log, research digest) and in what format. |

## 11. Success metrics

Targets marked *(proposed)* are starting points for the owner to confirm (OPEN-09 covers strategy thresholds).

**Safety and correctness (must hold at all times; enforced by automated tests [Arch J])**

| Metric | Target |
|---|---|
| Orders reaching the broker without passing policy, risk and the gate | **0** |
| New submissions while the kill switch is off or unreadable | **0** |
| Duplicate orders or fills after crashes or duplicate messages | **0** |
| `UNKNOWN` orders automatically resubmitted | **0** |
| Unbalanced or modified ledger transactions | **0** |
| Replay determinism (same data and versions → same views, intents, orders) | **100%** |

**Operations (paper trading)**

| Metric | Target |
|---|---|
| Reconciliation incidents left unresolved | 0 older than 1 business day *(proposed)* |
| Decisions with complete lineage | 100% of market views, intents and orders |
| Abstentions with a stated reason | 100% |
| Research runs within the daily LLM budget | 100% |

**Product and usability**

| Metric | Target |
|---|---|
| Time for a new user to answer "Should I trade? Why / why not? What happened?" on the dashboard | ≤ 10 seconds *(proposed; checked by a usability walkthrough at M8)* |
| Every milestone ends with its visible result (Section 7) | Yes, checked at milestone review |
| Paper-trading period before *any* live discussion | At least 3 months of reconciled paper trading at Level 1/2 *(proposed)* |

**Strategy quality** is measured by the evaluation module (after costs, simulated next-bar fills, walk-forward). Thresholds are **OPEN-09**. A strategy that doesn't pass them never reaches paper trading.

## 12. Assumptions and risks

| Type | Statement | Mitigation |
|---|---|---|
| Assumption | One developer working with AI tools (Claude Code builds, Codex reviews). | Small milestones and tasks; repo docs are shared memory. |
| Assumption | Free or low-cost data and LLM tiers are enough for M1–M6. | Budget decision OPEN-11; research rationing. |
| Risk | Broker or data availability in the owner's jurisdiction may limit M7. | Resolve OPEN-02 early; M1–M6 don't depend on it. |
| Risk | LLM research quality varies and can't be reproduced exactly. | Advisory only; ResearchRecord stores inputs and outputs (Law 18). |
| Risk | Backtests can look better than reality (look-ahead, costs, survivorship). | Evaluation module with point-in-time data, costs, next-bar fills, walk-forward. |
| Risk | Scope creep toward live trading or new assets. | Non-goals (Section 9); architecture change rule (ADR required). |

## 13. Glossary (plain English)

| Term | Meaning |
|---|---|
| **MarketView** | The system's opinion on an instrument right now: BULLISH, BEARISH, NEUTRAL or ABSTAIN, with reasons. |
| **OrderIntent** | A *proposed* trade waiting for checks and approval. Not yet an order. |
| **Order** | An approved intent turned into something that can be sent to the broker. |
| **Pre-Execution Gate** | The last automatic safety check right before sending an order. |
| **Kill switch** | An emergency stop that blocks new submissions to the broker (cancels and fill recording continue). Only the Admin CLI writes it. |
| **Paper trading** | Trading with fake money to test the system safely. |
| **Ledger** | The platform's own accounting record of every trade, fee and cash movement. |
| **Reconciliation** | Comparing our records with the broker's to make sure they agree. |
| **Lineage** | The trail showing exactly what produced a decision. |
| **Autonomy level** | How much the system may do on its own (0 = advice only). |
| **ADR** | Architecture Decision Record: the written process for changing the architecture. |
