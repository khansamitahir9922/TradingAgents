# ADR-004: OrderIntent/Order split, versioning, transition ownership and the Pre-Execution Gate

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Laws 10, 12, 13, 14 · Parts A, G1, G2, G3, G4, H (`OrderIntent`, `Order`, `CancelRequest`, `GateDecision`) |
| **Milestone** | M3 (versioned OrderIntent, policy, risk) · M4 (Order state machine, Execution Worker, gate) |

## Context
Several problems meet at the point where a decision becomes an order:
- **Approval and execution are different lifecycles.** A trade proposal is approved, declined or expires. A broker order is submitted, partially filled, cancelled or rejected. One state machine covering both becomes large and error-prone.
- **Approvals can be undermined.** If an approved trade can be edited afterwards (by risk, a person or a bug), the approval no longer means what the approver saw.
- **The world changes between approval and submission.** Approvals expire, data goes stale, limits change, markets close, and the kill switch may be thrown.
- **Two processes write the order store.** The Core Engine creates orders; the Execution Worker (ADR-002) drives broker transitions. Without rules, concurrent writes can be lost.
- **Retries and crashes can duplicate trades.** A timeout during submission leaves the broker state unknown.

## Decision
**1. Two objects.**
- **OrderIntent** (Core Engine only) is the proposal and its approval. Lifecycle (G2):
  ```
  PROPOSED → POLICY_REJECTED | RISK_REJECTED
  PROPOSED → SUPERSEDED (risk reduced it → new version PROPOSED)
  PROPOSED → AWAITING_APPROVAL (Level 1) → APPROVED | DECLINED | EXPIRED
  PROPOSED → APPROVED (Level 2)
  APPROVED → CONVERTED (an Order is created) | EXPIRED | SUPERSEDED (material change → new version)
  ```
- **Order** is the execution record, linked to one `intent_id` and `intent_version`. Lifecycle (G3):
  ```
  NEW → GATE_REJECTED                         (the gate failed; nothing was sent)
  NEW → SUBMITTING → SUBMITTED → PARTIALLY_FILLED → FILLED
  SUBMITTED | PARTIALLY_FILLED → CANCEL_PENDING → CANCELLED
  CANCEL_PENDING → PARTIALLY_FILLED | FILLED  (late fills are always accepted)
  SUBMITTING | SUBMITTED → REJECTED | EXPIRED
  SUBMITTING (timeout, state unknown) → UNKNOWN → reconciled to the true state (never resent)
  ```

**2. Immutable, versioned intents** (Law 12). After approval, side, instrument, quantity, type, limit price and time-in-force never change. Any change, including a risk reduction after approval, creates a **new version**; a material change needs a fresh approval. Risk may **approve, reject or reduce**, and a reduction is a new version, never a silent edit.

**3. Transition ownership and compare-and-set** (Law 10, G3).

| Transition | Only writer |
|---|---|
| create `NEW` | Core Engine (OMS) |
| record a **cancel request** (a command row, not a state change) | Core Engine or API Server command |
| `NEW → GATE_REJECTED / SUBMITTING`, and every broker-driven transition (SUBMITTED, PARTIALLY_FILLED, FILLED, CANCEL_PENDING, CANCELLED, REJECTED, EXPIRED, UNKNOWN and its resolution) | Execution Worker |

Both processes use **one shared state-machine module**. Every write is a **compare-and-set on `aggregate_version`**, so a stale write fails instead of overwriting.

**4. Pre-Execution Gate** (Law 13). It runs **inside the Execution Worker** before every submission, is deterministic and cheap, and **doesn't rerun the strategy**. It checks that:
- the intent version is unchanged and its approval hasn't expired;
- the MarketView and the reference price are still within their validity window;
- the policy and risk decisions are still current, with no limit or position change since;
- the market session allows the order's time-in-force;
- the kill switch is enabled (ADR-006).

A failure records a `GateDecision` with reasons and moves the order to `GATE_REJECTED`. Nothing is sent.

**5. Idempotent submission** (Law 14). Every order gets a `client_order_id` **before** submission. The Execution Worker saves `SUBMITTING` before calling the broker. An order whose broker state is unknown goes to `UNKNOWN` and is reconciled by `client_order_id`, **never resent blindly**. On restart (G4), `SUBMITTING` and `UNKNOWN` orders are looked up at the broker, orders still `NEW` go through the gate again, and pending cancel requests are sent.

## Alternatives considered
**Documented in the architecture lineage:**
- **One OMS / one combined state machine** (Claude v0.1, ChatGPT v0.2; Part A, "Approval vs order"). Replaced by separate OrderIntent and Order machines.
- **Approved trades that can be changed** (raised in the v0.95 review: "must not mutate silently"; Part A). Replaced by immutable, versioned intents.
- **Risk may approve, modify or reject** (ChatGPT v0.2; Part A, "Risk modifying orders"). Replaced by approve, reject or reduce, where a reduction creates a new version.
- **Kill switch as the only check before sending** (Claude v0.1; Part A, "Last check before sending"). Replaced by the Pre-Execution Gate (v0.95 review).
- **The Core Engine performs execution** (before the freeze review). Replaced by the Execution Worker, with transition ownership and compare-and-set as a follow-on (Part O).

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **A single writer for the order store** (the Core Engine relays broker updates). The Core Engine would need broker results in real time and become part of the execution path; giving the credential holder its transitions is simpler.
- **Last-write-wins updates.** Lost updates between two processes.
- **Retry the broker call on timeout.** It can create duplicate trades.

## Consequences
- **Positive.** Each state machine is small and testable. An approval means exactly one version. Stale approvals and changed limits are caught at the last moment. Lost updates and duplicate submissions are prevented structurally.
- **Negative.** More records (versions, gate decisions, cancel requests). A changed limit can cause gate rejections of already-approved orders, which users must be able to see (design principles D-16, E-01). UNKNOWN orders need a reconciliation path and can stay unresolved for a while.
- **Follow-ups.** M3 and M4 task specs define the schemas, the shared state-machine module and the Part J tests.

## Not decided here (proposals, not accepted)
These were raised during diagram review. They are **not** part of v1.0. Each needs a **reviewed and accepted follow-up ADR**, followed by an **update to `architecture-v1.0.md`** (Part P), before it can be built. This ADR is not amended for them.
- a `PARTIALLY_FILLED → EXPIRED` transition (e.g. a day order that expires partly filled);
- what happens when the broker **has no record** of an order in `UNKNOWN`.

Until they're accepted, implementation follows G3 exactly as frozen.

## How we check it
Part J invariants:
- rejected intents never become orders;
- a REJECTED or GATE_REJECTED order never becomes FILLED;
- duplicate broker messages never create duplicate fills;
- UNKNOWN orders are never resubmitted;
- an approved intent version never changes;
- a stale compare-and-set write on an order always fails;
- each order transition is written only by its owning process;
- no path reaches the broker without Policy, Risk and the Gate.

Fault injection: kill the Execution Worker mid-submission; kill the Core Engine after approval; broker timeout; late fill after cancel; approval expiring before submission; a concurrent cancel request and fill.

## References
Architecture Laws 10, 12–14; Parts G1–G4, H, J. Diagrams 4, 5, 6 and 9A. PRD OPEN-16.
