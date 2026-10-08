# ADR-002: Models never execute; credential separation by process

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Laws 1, 2, 3, 4 · Parts A, D, E, F · Part O (v1.0 changes) |
| **Milestone** | M4 (Execution Worker, simulated broker) · M7 (paper broker; OS-level isolation, ADR-012) |

## Context
The platform mixes components with very different trustworthiness: LLM research, ML models, rule strategies, and deterministic policy and risk code. Some read untrusted external text.

Earlier drafts gave the **Core Engine** the broker credentials, with module boundaries meant to keep analysis away from them. The freeze review pointed out that **module boundaries aren't a security boundary**: any code in the process that holds a key can, in principle, use it. A bug, a compromised dependency or injected instructions could place an order.

## Decision
1. **Models never execute** (Law 1). LLMs, ML models, strategies and signals have no broker access. The only path that can submit orders is:
   **OMS (approved Order) → Execution Worker (Pre-Execution Gate → Broker Adapter) → Broker.**
2. **Least capability by process** (Law 2):

   | Process | Holds | Never holds |
   |---|---|---|
   | **Execution Worker** | broker credentials | LLM keys, research keys |
   | **Core Engine** | market-data credentials that **cannot place orders** | broker trading credentials, LLM keys |
   | **Research Worker** | LLM and research-data keys | broker credentials |
   | **API Server** | user sessions only | any external-service credential |

3. If a broker's market-data key can also trade, the Core Engine must not hold it. The Execution Worker ingests that feed instead, or a separate data vendor is used (decided in ADR-011).
4. Reconciliation runs in the Core Engine **without** broker credentials. The Execution Worker writes a **BrokerSnapshot** (positions, open orders, cash as the broker reports them), and the Core compares against it.
5. **Enforcement:** in development, separation is by **separate secret files per process**. That is a **convention, stated honestly as such**. From **M7**, it's enforced by **separate OS users or containers** (ADR-012).

## Alternatives considered
**Documented in the architecture lineage:**
- **The Core Engine holds broker credentials, protected by module boundaries** (Claude v0.1; Part A, "Who holds broker credentials"). Replaced at the freeze review (Part O): module boundaries aren't a security boundary.
- **Microservices.** Part B2 chooses a modular monolith run as four processes, "not microservices"; Part L defers microservices. Four processes on one codebase give the needed boundary at lower operational cost.

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **A single process with a secrets manager.** Any code in the process can still request the secret, so it doesn't separate capability.

## Consequences
- **Positive.** A misbehaving component **physically lacks** the credentials to trade. Analysis and LLM code can be experimented with freely without touching execution authority.
- **Negative.** Four processes instead of one: they must communicate (through the database, ADR-005), and crashes must be handled per process (Part E crash matrix). Reconciliation depends on BrokerSnapshot freshness. Until M7, the boundary is only as strong as the development convention.
- **Follow-ups.** ADR-011 (whether the data key can trade) and ADR-012 (OS-level isolation) before M7. Configuration loading must make it impossible for a process to read another process's secret file by default.

## How we check it
- Part J invariants: no process other than the Execution Worker can load broker credentials; no path reaches the broker without Policy, Risk and the Gate.
- Contract tests: each broker adapter is reachable only through the Execution Worker.
- From M7: a deployment check that each OS user or container can read only its own secrets.

## References
Architecture Laws 1–4; Parts D, E, F, G1; Part O (freeze review and Claude follow-ons). Diagrams 2 and 2b.
