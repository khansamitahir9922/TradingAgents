# ADR-005: Event envelope, outbox, per-aggregate ordering, communication only through the database

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Laws 10, 11 · Parts A, E, G4, H (`EventEnvelope`) |
| **Milestone** | **M4**: outbox implementation, publishing, consumer de-duplication and crash recovery (Part K). Earlier milestones may define **event contracts** (e.g. the envelope schema) when they need them, without building outbox infrastructure. |

## Context
Four processes (ADR-002) need to tell each other about changes: a new bar, a new view, an approved intent, a new order, a fill, a research result. The usual failure modes are:
- **State saved, notification lost** (or the reverse) when a process crashes between the two;
- **duplicate notifications** after a retry, causing a repeated action;
- **out-of-order** updates for the same order or account;
- processes calling each other directly, so one being down blocks the others.

The platform is built by one developer, so heavy infrastructure (message brokers, service meshes) is a cost to avoid unless it's needed (Part L).

## Decision
1. **Communication only through the Operational Database.** Processes exchange **commands, job rows and outbox events** in the database. They never call each other directly. If a process is down, the others keep their state and work resumes from durable rows.
2. **One authoritative store per domain** (Law 10). Events announce changes; they're never the state itself.
3. **Save, then publish** (Law 11). A state change and its **outbox row** are committed in **one transaction**, then published.
4. **Event envelope** (Part H): `event_id`, `event_type`, `schema_version`, `aggregate_type`, `aggregate_id`, `aggregate_version`, `occurred_at`, `recorded_at`, `correlation_id`, `causation_id`, `payload`.
5. **Ordering per aggregate.** Order is guaranteed within one aggregate (one order, one account, one instrument) using `aggregate_version`, not globally.
6. **At-least-once delivery, idempotent consumers.** After any restart, a process republishes its unpublished outbox rows **with their original `event_id`**. Consumers record each processed `event_id` **in the same transaction** as its effect and skip any they've already processed (G4; Diagram 9B).

## Alternatives considered
**Documented in the architecture lineage:**
- **Ordering per instrument** (Claude v0.1; Part A, "Event ordering"). Replaced by per-aggregate ordering (v0.95 review): orders, accounts and instruments are different streams.
- **A message broker** (Redis, NATS, Kafka). Deferred in Part L.
- **Processes calling each other directly.** Ruled out at freeze: "processes communicate only through the database" (Part O).

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **Exactly-once delivery.** Not achievable across a crash without the same idempotency work; at-least-once plus idempotent consumers is the standard, testable approach.
- **Global ordering.** Unnecessary and limiting; correctness needs order only within an aggregate.

## Consequences
- **Positive.** Crash-safe notifications with no extra infrastructure. Any process can restart without losing or doubling work. The database holds a full record of what was announced.
- **Negative.** Latency is bounded by polling or the database's notification mechanism. That's acceptable for swing trading (Part B4 puts performance last). Every consumer must be written idempotently. The database carries more load, which is one reason for PostgreSQL from M3 (ADR-008).
- **Follow-ups.** M4 task specs define the outbox table, the publisher, the consumer de-duplication table and the retention of published rows. Before M4, a task may define event contracts only.

## How we check it
- Part J: duplicate broker messages never create duplicate fills; a stale compare-and-set write always fails.
- Fault injection: crash between publish and mark-published (the event is delivered twice and applied once); DB restart; duplicate WebSocket message.
- Review: no process imports another process's runtime entry point or calls it over the network.

## References
Architecture Laws 10, 11; Parts E, G4, H. Diagrams 2, 2b and 9B. `architecture/eraser-diagrams.md` (9B "why this is safe").
