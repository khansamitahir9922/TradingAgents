# ADR-001: TradingAgents is an asynchronous research service

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Laws 1, 4, 18, 19 · Parts E, F (Research), G6, I |
| **Milestone** | M6 (TradingAgents adapter, Research Worker) |

## Context
The platform starts from the TradingAgents repository (upstream v0.6.0): a LangGraph pipeline of LLM agents (analysts, researchers, trader, risk debaters, portfolio manager) that produces a written rating for one ticker and date.

Its properties don't fit a trading decision path:
- **Slow.** A run takes minutes.
- **Quota-limited.** Free and low-cost LLM tiers cap daily use. The owner reported hitting a free-tier quota during the baseline work (PRD OPEN-10).
- **Not exactly reproducible.** The same inputs can produce a different answer.
- **Exposed to untrusted text.** News, social posts and web content enter its prompts, so its output can be wrong or manipulated (prompt injection).
- **Daily granularity.**

The platform's quality goals put safety and reconstructability first (Part B4). Analysis must not have the power to move money (Law 1).

## Decision
TradingAgents runs as an **asynchronous, advisory research service**:
1. It runs **only in the Research Worker**, behind one adapter. That process holds LLM and research-data keys and **no broker credentials** (Law 2).
2. Work arrives as **job rows** in the Operational Database and runs within a **daily LLM budget**.
3. Each run saves a **ResearchRecord** (settings, provider and model, prompt and input snapshot, tool results, raw response, warnings, code version) and a parsed, typed **ResearchContext** (`rating`, `suggested_levels`, `horizon`, `generated_at`, `valid_until`, `warnings`), then publishes an event.
4. Research is **never on the bar-to-order path**. The Decision module may read the latest *valid* ResearchContext as optional evidence for a MarketView; it never waits for a run.
5. Research output is **untrusted evidence** (Law 4). It can't execute, size, or bypass portfolio, policy, risk or the gate. LLM price levels never become order prices without passing risk.
6. Upstream changes stay **minimal and listed**. One is planned: keep the Trader's and Portfolio Manager's structured output. Prompts and tool results are captured through LangChain callbacks inside the adapter.

## Alternatives considered
**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **TradingAgents as the decision-maker** (its rating drives orders). It would give an LLM authority over trades, violating Laws 1 and 3.
- **Run research inline on each bar**, before the MarketView. Minutes of latency and quota limits would stall or skip decisions, and a provider outage would stop the decision path.
- **Run TradingAgents inside the Core Engine.** LLM keys would sit next to the decision path, and a slow or failing run would share a process with OMS work. A separate process makes the credential boundary physical.
- **Fork and restructure TradingAgents heavily.** It would make upstream releases hard to merge (Part I keeps upstream changes minimal).

The lineage in Part A doesn't record alternatives for this decision specifically; it's stated as a frozen decision in Parts E, G6 and I.

## Consequences
- **Positive.** A slow, failing or quota-limited LLM can't block or corrupt trading. If the Research Worker crashes, execution is unaffected; views run without new research, or ABSTAIN where a strategy requires it (Part E crash matrix). Every research result can be reconstructed and audited later.
- **Negative.** Research can be stale. Every ResearchContext needs a `valid_until`, and expired research must be handled (and shown: design principles E-01). LLM research can be reconstructed but **not reproduced exactly**, so evaluation of research-dependent strategies needs care.
- **Follow-ups.** The adapter, job table, budget and record schemas are specified in M6 tasks. The planned upstream change is documented when made.

## How we check it
- Part J invariants: no process other than the Execution Worker can load broker credentials; no path reaches the broker without Policy, Risk and the Gate.
- Fault injection: missing research; Research Worker crash.
- Review: the Decision module has no call that waits on a research job.

## References
Architecture Parts E, F, G6, I; Laws 1–4, 18, 19. Diagram 8 (research slow path). PRD UC-03 and OPEN-10.
