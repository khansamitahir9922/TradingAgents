# Architecture Decision Records

An ADR explains **why** a decision was made: the problem, the alternatives, the choice and its consequences. The architecture document says **what** the system is; the ADRs say why it's that way.

| | |
|---|---|
| **Source of truth** | `architecture/architecture-v1.0.md` (v1.0 FROZEN, 2026-10-07). If an ADR and the architecture disagree, the architecture wins until a new ADR changes it. |
| **Status of this set** | ADR-001 – ADR-009 **record decisions already frozen in v1.0**. They don't redesign anything. The records passed Codex's document review (2026-10-09) and await review of the M0 commit and the owner-approved merge. |

## Index

| ADR | Title | Main laws | Built in |
|---|---|---|---|
| [ADR-001](ADR-001-tradingagents-async-research-service.md) | TradingAgents is an asynchronous research service | 1, 4, 18, 19 | M6 |
| [ADR-002](ADR-002-models-never-execute-credential-separation.md) | Models never execute; credential separation by process | 1, 2 | M4 / M7 |
| [ADR-003](ADR-003-instrument-ids-and-symbol-mappings.md) | Internal instrument IDs and effective-dated symbol mappings | 8 | M1 |
| [ADR-004](ADR-004-orderintent-order-split-and-gate.md) | OrderIntent/Order split, versioning, transition ownership and the Pre-Execution Gate | 10, 12, 13, 14 | M3 / M4 |
| [ADR-005](ADR-005-events-outbox-and-database-communication.md) | Event envelope, outbox, per-aggregate ordering, communication only through the database | 10, 11 | M4 (event contracts earlier if needed) |
| [ADR-006](ADR-006-kill-switch.md) | Kill-switch mechanism | 15 | M4 / M7 |
| [ADR-007](ADR-007-decimal-float64-boundary.md) | Decimal/float64 boundary | 16 | M1 |
| [ADR-008](ADR-008-database-sqlite-then-postgresql.md) | Database: SQLite in M1–M2, PostgreSQL from M3 | 10, 11 | M1 / M3 |
| [ADR-009](ADR-009-append-only-revisions-point-in-time.md) | Append-only revisions and point-in-time views | 5, 8, 18 | M1 |

**Accepted for M5 (owner, 2026-10-21):** [ADR-010: Separate currency and security-quantity books](ADR-010-securities-ledger-model.md), v0.2 (Codex backup implementer), **owner-accepted**. The [M5 task pack](../../docs/tasks/M5-README.md) is authorized for implementation; finished code still needs review before a separately approved merge.

**Planned later** (architecture Part K): ADR-011 broker and data provider, incl. whether the data key can trade (before M7) · ADR-012 hosting and OS-level process isolation (before M7).

## Status values
- **Proposed**: written, not yet decided.
- **Accepted**: the decision is in force.
- **Superseded by ADR-NNN**: replaced; kept for history.
- **Rejected**: considered and turned down; kept so it isn't re-proposed without new information.

ADRs are never deleted or rewritten after acceptance. A changed decision gets a new ADR that supersedes the old one.

## How to change the architecture (Part P)
```
problem found → ADR (context, alternatives, decision, consequences) → review → accept/reject → update architecture-v1.0.md
```
Implementation work (Claude Code, Codex or a human) must not change laws, domain boundaries or execution authority without an accepted ADR.

## Alternatives: what's historical and what isn't
Each ADR splits its alternatives in two:
- **Documented in the architecture lineage**: options that appear in the architecture's own record (Part A drafts v0.1, v0.2, v0.95, RC1, the freeze review in Part O, or deferrals in Parts B and L).
- **Retrospective analysis (added by Claude while writing this record)**: other reasonable options, assessed against the frozen decision. They were **not** necessarily considered at the time, and they don't change the decision.

## Template
```markdown
# ADR-NNN: Title

| | |
|---|---|
| **Status** | Proposed |
| **Date** | YYYY-MM-DD |
| **Architecture** | Laws / Parts affected |
| **Milestone** | Where it's built |

## Context
The problem and the forces at play.

## Decision
What we will do, stated precisely.

## Alternatives considered
Each option and why it wasn't chosen. Mark which were historically considered and which are retrospective analysis.

## Consequences
What becomes easier, what becomes harder, and what follow-up work it creates.

## How we check it
The tests or reviews that show the decision holds.
```
