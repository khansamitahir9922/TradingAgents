# ADR-006: Kill-switch mechanism

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Law 15 · Parts A, E (Kill-Switch Flag, Admin CLI), G5 · Part O (freeze review) |
| **Milestone** | M4 (flag, gate check, Admin CLI) · M7 (OS-enforced read-only access for the Execution Worker, ADR-012) |

## Context
There must be a way to stop trading that works **when other parts are broken**: the database is down, a process is misbehaving, or the dashboard is unreachable. Stopping must not make things worse: open orders must still be cancellable, and fills that arrive must still be recorded.

The freeze review also raised a security point: if the process that trades can also re-enable trading, a compromised or buggy worker can undo an emergency stop.

## Decision
1. The kill switch is a **trading-enabled flag stored outside the main database** (a small file; Part E).
2. **The Admin CLI is its only writer.** It works when everything else is down.
3. **The Execution Worker can only read it.** Its Pre-Execution Gate (ADR-004) reads the flag before **every new submission**.
4. **Fails closed.** A missing, unreadable or disabled flag means **no new submissions**.
5. **Cancels are always allowed**, and fills keep being recorded. The runbook also covers the broker's own "cancel all".
6. **No other writer.** The dashboard and the API Server **display** the state but have no halt or resume control (design principles S-01 – S-03; PRD UC-06).
7. **Enforcement:** in development, write access is limited by convention. From **M7**, the Execution Worker's read-only access is enforced with **OS file permissions** under separate OS users or containers (ADR-012).

## Alternatives considered
**Documented in the architecture lineage:**
- **A kill switch that works without the app** (Claude v0.1) and **external state** (ChatGPT v0.2) (Part A, "Kill switch"). Combined into a flag outside the database that fails closed.
- **A kill switch that also blocks cancels.** Ruled out in RC1: the kill switch never blocks cancels (Part O).
- **A flag the trading process can write.** Ruled out at the freeze review: Admin-only write, Execution Worker read-only (Part O).

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **A flag in the main database.** Unusable when the database is what's broken, and writable by any process with DB access.
- **A process signal or in-memory switch.** Lost on restart, and doesn't fail closed.
- **A halt button in the dashboard or API.** It appeared in the Signal Desk prototype and is excluded by design principles S-02: it would add a writer reachable from a network-facing process.

## Consequences
- **Positive.** Trading can be stopped from a terminal even when the database, API and dashboard are down. A bad or missing flag is safe by default. Stopping never traps open orders.
- **Negative.** Halt and resume need Admin CLI access to the host, so Admins must be able to reach it quickly. Displaying the state in the dashboard needs a read path that doesn't add a writer. The dashboard must keep two cases apart (design principles S-01): a flag the **gate** can't read blocks new submissions, but a status the **dashboard** can't observe doesn't stop trading, and is shown as "Trading status cannot be verified" rather than guessed. Before M7, read-only access is a convention only.
- **Follow-ups.** M4 tasks define the flag format, the Admin CLI commands (including how each halt and resume is recorded for audit) and the gate check. ADR-012 defines the M7 permissions.

## How we check it
- Part J: nothing new is submitted while the kill switch is off or unreadable, and cancels still pass.
- Fault injection: missing flag file; unreadable flag file; flag flipped between approval and submission.
- From M7: a deployment check that the Execution Worker's user can't write the flag.

## References
Architecture Law 15; Parts E, G5, O. Diagram 7 (kill switch and cancel). Design principles S-01 – S-03. PRD UC-06.
