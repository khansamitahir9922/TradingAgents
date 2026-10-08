# Dashboard Design Principles

| | |
|---|---|
| **Document status** | **Reviewed v0.3.** Codex document review passed (2026-10-09); committed with the owner's approval; awaiting review of the M0 commit and the owner-approved merge into `main`. v0.2 applied Codex's first review (V-08, V-14, T-05, H-03, S-01 – S-03, D-01, D-16, scope); v0.3 separates the gate's flag reading from the dashboard's observation (S-01, S-03, E-01). |
| **Date** | 2026-10-08 |
| **Applies to** | The M8 web dashboard, and any report or UI that shows platform data (CLI reports, HTML reports from M2 onward). Which rules apply where is set out in **Scope** below. |
| **Sources** | `architecture/architecture-v1.0.md` (v1.0 FROZEN) and `docs/PRD.md` (draft). Where this document and the architecture disagree, the architecture wins. |
| **Reference prototype** | "Signal Desk", a browser simulator built by the Astra assistant (ChatGPT). It's a **visual reference only**, not a specification; see Appendix A. |

These are **rules for how the dashboard looks and presents information.** They don't build the UI, and they don't choose a technology (Section 10).

**Rule IDs** (e.g. `T-03`) let reviews and task specs cite a rule. **MUST** means required; **SHOULD** means the default unless a reviewed reason says otherwise.

**Scope.** Not every rule fits every output:

| Rules | Apply to |
|---|---|
| Honesty, provenance, safety state and exceptional states: Sections 2, 3, 4, 5, and D-06 – D-11 | **Every output** that shows platform data: CLI reports, HTML reports, exports and the dashboard |
| Layout, motion, interaction and keyboard: Section 1, Section 7 (A-04 – A-07), Section 8, and the interactive parts of Section 6 | **Browser interfaces** (the M8 dashboard and any interactive HTML) |
| Readability, contrast and never colour alone (A-01 – A-03) | Every output with visual styling, including static HTML reports |

A static report has no motion or keyboard interaction to govern, but it still never invents a number, labels SIMULATED and REPLAY results, and states its sources and times.

---

## 0. The idea in one sentence

**A cinematic mission-control cockpit where every pixel is true.** It's dense, luminous and alive, and every number, animation and colour reflects recorded platform state.

---

## 1. Look and layout (mission control)

### 1.1 Visual identity
- **V-01** Dark base (near-black / deep navy), thin luminous panel borders, and neon accents used **only for meaning**, never for decoration alone.
- **V-02 Two separate colour scales.** They must never be mixed:

  | Scale | Meaning | Suggested tokens (final values set at M8) |
  |---|---|---|
  | **Direction** | up / bullish vs down / bearish | `dir-up` green, `dir-down` magenta |
  | **Severity** | OK / attention / blocked | `sev-ok` green-cyan, `sev-warn` amber, `sev-block` red |
  | **Identity** | research / AI, informational data | `id-ai` violet, `id-data` cyan |

  A down candle uses the direction colour and **never** the "blocked" red. A halt uses the severity red and **never** a direction colour.
- **V-03** Typography: a **monospace** face for numbers, IDs and labels (tabular digits, so values don't jump), and a clean sans-serif for headings and explanations.
- **V-04** Glow and particles are reserved for **live, meaningful** elements (the decision graph, a changed value, an active alert). Static content stays flat.

### 1.2 Panels: dense but readable
- **V-05** Every panel uses the same "HUD frame":
  - a panel ID and title (e.g. `MKT-01 · NVDA / 1H`);
  - a status chip at the top right;
  - an optional **Focus** button that opens the panel full-size.
- **V-06** Density comes from **meaningful micro-visuals** (sparklines, gauges, bars, small tables), never from filler. An empty panel shows an honest empty state (Section 3), not a blank box.
- **V-07** The main screen fits a 1920×1080 display without page scrolling. Secondary detail (activity terminal, notes) lives in a collapsible drawer or in Focus views. Smaller screens reflow into a single column without hiding safety state (Section 4).

### 1.3 Screen regions (reference layout)

| Region | Contents |
|---|---|
| **Command bar** (always visible) | Product name · `PAPER` badge · autonomy level · kill-switch status · event ticker · clock (exchange time) |
| **Headline numbers** | Equity · cash · P&L incl. fees · open orders · data health · reconciliation; each with source and time (Section 2) |
| **Main row** | Market (candles + indicators) · **decision graph** (centre) · market view + approval card |
| **Execution circuit** | The trade pipeline with the process boundary (Section 6.4) |
| **Bottom row** | Orders & fills tape · twin ledger (internal vs broker) · system health |
| **Drawer** | Activity terminal (event tape), audit trail, notes |

### 1.4 Signature components
- **V-08 Central decision graph.** The centrepiece: the MarketView verdict in the middle, with **its inputs** around it: **Data** (DataHealth), **Quant** (FeatureSnapshot, rule strategy) and, when present, **Research** (advisory). **Policy and Risk are not inputs to the MarketView.** They check the OrderIntent that is sized *from* the view (architecture G1 steps 5 → 6 → 7 → 8), so they appear **downstream** of the verdict, in the execution circuit (D-12), never as nodes feeding it. Rules in Section 6.1.
- **V-09 Research consensus panel.** Shows which contributors support, oppose, are neutral or are missing, and **how** the decision policy combines them. Rules in Section 6.3.
- **V-10 Headline numbers.** Large monospace values with a sparkline of their recorded history. Rules in Section 2.
- **V-11 Status chips.** Short, uppercase, icon + text (e.g. `■ HALTED`, `▲ STALE 140s`, `✓ MATCHED`). They are never colour-only (Section 7).
- **V-12 Live event tapes.** Orders & fills, and the activity terminal, scroll newest-first, show timestamps, and flash a new row **once**. Rules in Section 6.2.

### 1.5 Motion
- **V-13** Motion must **mean something**: a new bar, a pipeline step, an approval countdown, a fill, a reconciliation result. Gentle ambient motion (e.g. slow rotation of the graph) is allowed. Constant blinking is reserved for true alarms (Section 5).
- **V-14 Never animate through invented numbers.** A changed financial value (balance, P&L, quantity, price) is shown as the **exact recorded value immediately**. The change may be emphasised by animating its highlight, border, glow or position (≈150–400 ms), but never by counting through intermediate values that were never recorded.
- **V-15** Opening a panel, inspector or replay **never pauses or changes** the platform. Viewing is read-only.

---

## 2. Every number has a recorded source

- **T-01** Every displayed number traces to **one authoritative record** (architecture Law 10, Part F). The same quantity is never shown from two different sources on one screen. (Historical evidence and the current value of the same quantity may both appear, labelled as T-05 requires.)

  | What is shown | Authoritative source |
  |---|---|
  | Cash, positions, cost basis, P&L, fees | **Ledger** (and the latest `BrokerSnapshot` only in the twin-ledger comparison) |
  | Orders, states, fills, fill prices | **OMS order store** (fills as recorded) |
  | Candles, prices, indicators | **Market-data records** (with revision) and versioned feature definitions |
  | MarketView, strength, reasons | **MarketView** record (with `policy_version`) |
  | AI research summary, rating, suggested levels | **ResearchRecord / ResearchContext** |
  | Approvals, autonomy changes, and halt/resume actions **where recorded** | **Audit store** |
  | Data health | **DataHealth** record |
  | Trading (kill-switch) status | The backend's observation of the **kill-switch flag**, or the Execution Worker's recorded **gate result**, with its observation time (read-only display; S-01) |

- **T-02** **Derived values explain themselves.** Equity, exposure, remaining position allowance and P&L show their formula and inputs on inspection (e.g. *Equity = cash + Σ(shares × last price) = $8,517.12 + 8 × $185.20*).
- **T-03** **Every value carries its time.** Prices show the bar time; health shows age; research shows `generated_at` and `valid_until`; headline numbers show "as of". Times are shown in **exchange time, with UTC available** (PRD §8).
- **T-04** **Units and currency are always explicit** (USD, shares, %, bars). Money is shown at its recorded precision, never rounded in a way that changes meaning.
- **T-05** **Historical evidence keeps the values used at the time.** A past decision's explanation (reason, evidence inspector, replay) shows the **exact values, record revisions and versions** used when the decision was made, taken from its lineage (architecture Law 18, Part H). Current panels may legitimately show different values: newer bars, or a later data revision (Law 8). The two are labelled separately, e.g. `AT DECISION · 10:00 bar · rev 1: RSI 45` versus `CURRENT · rev 2: RSI 47`. A reason that disagrees with **its own** recorded evidence, or a historical value shown without its label, is a bug.
- **T-06** **Every chart says what it plots.** If a series isn't what it might look like (e.g. a lower histogram of candle range rather than volume), its label says so.
- **T-07** Sparklines plot **recorded history** for the period shown, labelled with that period.

---

## 3. Honest about what's unknown, simulated or replayed

- **H-01** **Never invent a number.** No placeholder, decorative or "example" figures; no fake activity counters.
- **H-02** **Unavailable isn't zero.** A missing value shows a labelled state, never `0`, `$0.00` or an empty chart that looks like "nothing happened":

  | Situation | Shown as |
  |---|---|
  | Not yet computed | `— NOT YET` with what it's waiting for |
  | Source unavailable | `UNAVAILABLE` with the reason (e.g. "feed down since 10:04") |
  | Stale | The last value **dimmed**, plus `▲ STALE 140s` |
  | Not applicable | `N/A` with a short reason |
  | Truly zero | `0` (only when the record says zero) |

- **H-03** **SIMULATED and REPLAY are always labelled.** Recorded simulator or replay results may be shown, but every such value, panel or report carries a `SIMULATED` or `REPLAY` chip.
  - **Dashboard inspection and replay are read-only.** They can't place external orders, and they can't change the active account or any other platform state.
  - **Backend evaluation and replay are different.** Run in isolation, they may exercise the OMS, the Execution Worker code and the simulated broker, as M4 and architecture Law 20 require. Their results belong to that evaluation run, are labelled `SIMULATED` or `REPLAY`, and never appear as the active account's orders, fills or balances.
- **H-04** **Simulation and demo controls are segregated.** Controls that only exist in a simulator (scenario pickers, "next candle", reset, walkthroughs) live in a clearly labelled `SIMULATION CONTROLS` area and never appear in product panels.
- **H-05** **Never use the word "LIVE" for anything that isn't live.** Use `SIM FEED`, `REPLAY` or `PAPER`. Even real data in v1 is paired with `PAPER`.

---

## 4. Always-visible safety state

- **S-01** These three facts are visible **on every screen and at every size**:
  1. **`PAPER` mode**;
  2. the account's **autonomy level** (e.g. `LEVEL 1 · HUMAN APPROVAL`);
  3. the **trading (kill-switch) status**.

  Two different things must not be confused:
  - **What the Execution Worker's gate sees.** The gate reads the flag before every new submission. If the flag is disabled, missing or unreadable **at the gate**, new submissions are blocked (architecture Law 15).
  - **What the dashboard can observe.** The dashboard learns the status from the backend. If that information is missing (lost connection, no recent report), **trading has not stopped because of it**: the Execution Worker may still be operating.

  So the status is one of:

  | Status | Shown only when | Display |
  |---|---|---|
  | **Enabled** | A current observation shows the flag enabled | `● TRADING ENABLED` |
  | **Halted** | A current observation shows the flag disabled | `■ HALTED · New submissions blocked` |
  | **Flag unreadable at the gate** | The Execution Worker's recorded gate result says it couldn't read the flag | `■ FLAG UNREADABLE AT GATE · New submissions blocked` |
  | **Cannot be verified** | The dashboard has no current observation of either of the above | `? TRADING STATUS CANNOT BE VERIFIED` |

  - **"New submissions blocked" is claimed only when supported** by an observed disabled flag or a recorded gate result. It's never inferred from missing information.
  - Every status shows **when it was observed** (e.g. `■ HALTED · observed 10:14:05 ET`). When the status can't be verified, the **last-known** status stays visible, dimmed and labelled `LAST KNOWN · observed 10:14:05 ET`; it's never presented as current.
  - **Who** halted trading and **when** are shown only if a recorded audit event says so; otherwise the display says `actor and time not recorded`. They're never inferred or invented.
- **S-02** **The dashboard displays the kill switch; only the Admin CLI writes it** (architecture Law 15). There is **no halt or resume control** in the dashboard or API. A "How to halt" help link may explain the Admin CLI procedure.
- **S-03** Full-width banners, by status (S-01):
  - **Halted** or **flag unreadable at the gate:** the status, when it was observed, who halted it and when **if recorded**, and what still works: "**New submissions blocked.** Cancels and fill recording continue." (Orders already created stay recorded; the gate blocks their submission to the broker.)
  - **Cannot be verified:** "**Trading status cannot be verified.** The Execution Worker may still be submitting orders." It also shows the last-known status with its observation time, the reason (e.g. "connection to backend lost at 10:16:40 ET"), and a link to the Admin CLI procedure for checking or halting (S-02). It **doesn't** say that submissions are blocked.
- **S-04** Autonomy levels 3–4 never appear as selectable options in v1.

---

## 5. Exceptional states are prominent and explain why

- **E-01** Every exceptional state is **the most prominent thing on screen** while it's active, and always says **why** and **what happens next**.

  | State | Where it shows | Must explain |
  |---|---|---|
  | **ABSTAIN** | Market view (`● WAIT · ABSTAIN`), decision-graph centre, headline data health | Which required source failed and its age (e.g. "quote stale 140s; required by strategy S-1") |
  | **Stale data** | Affected panel dimmed + `▲ STALE` chip; data-health headline | Source, age, threshold |
  | **Expired research** | Research card + consensus contributor marked expired | `valid_until` passed; whether the strategy requires research; when a refresh is possible (budget) |
  | **Halted, flag unreadable at the gate, or status cannot be verified** | Banner + command-bar chip (S-03) | Status and observation time; who and when only if recorded; "new submissions blocked" only when an observed flag or gate result supports it; otherwise "cannot be verified" and the last-known status |
  | **Reconciliation incident** | Twin ledger turns to the incident state; headline reconciliation `✗ MISMATCH` | The exact difference (internal vs broker), when detected, incident status. Corrections appear as **reversing ledger entries**, never as a rebuilt ledger. |
  | **Gate rejected** | Order row + execution circuit | Which gate check failed |
  | **UNKNOWN order** | Order row + health | "Reconciling with broker; never resent"; last attempt time |
  | **Late fill after cancel** | Order row | That the fill was recorded as reported |

- **E-02** **WAIT always carries its reason.** UP / DOWN / WAIT is the friendly mapping, but WAIT is shown with its cause: `● WAIT · ABSTAIN: …`, `● WAIT · NEUTRAL`, `● WAIT · VIEW EXPIRED`, or `● WAIT · NO VIEW YET`.
- **E-03** Alerts are cleared by **state changes**, never by dismissing them. A user can collapse an alert, but its chip stays until the state is resolved.

---

## 6. Decision graph, tapes, research and consensus

### 6.1 Decision graph
- **D-01** The graph shows **recorded activity only**, in the **frozen decision order**:
  - **Input nodes** are only the MarketView's real inputs: Data (DataHealth), Quant (FeatureSnapshot) and optional Research (ResearchContext). Edges light up when a recorded event flows (e.g. a new FeatureSnapshot, a research result).
  - **Policy and Risk** are shown as **downstream checks** of the resulting OrderIntent (D-12), visually after the verdict. They're never drawn as contributors to it.
  - Ambient particles are allowed as decoration but **must not encode data** that isn't explained.
- **D-02** The centre shows the current MarketView verdict, colour-coded by direction (or by severity for ABSTAIN), with `valid_until`.
- **D-03** Each node is clickable or focusable and opens its **evidence**: the exact records, values, versions and timestamps used (lineage, architecture Law 18).

### 6.2 Live event tapes
- **D-04** Tapes show **recorded events** (OMS states, fills, audit events), newest first, with timestamps and status chips. Nothing is synthesised for effect.
- **D-05** Every order row shows its current state, including `GATE_REJECTED`, `CANCEL_PENDING`, `UNKNOWN` and late fills. Cancel actions belong **on the order row**, not on the approval card.

### 6.3 Research is advisory; consensus is explained
- **D-06** Research is labelled **`ADVISORY`**. Its card shows provider and model, `generated_at`, `valid_until`, warnings, and a link to the ResearchRecord. LLM-suggested price levels are labelled *untrusted suggestions*.
- **D-07** **The consensus panel explains its calculation.** It names the decision policy and version that combine the inputs (e.g. "Policy S-1 v3: required sources must be OK; Quant direction is primary; Research may not overrule a NEUTRAL quant view").
- **D-08** **It shows disagreement and missing contributors.** Each contributor is listed with its stance (`BULLISH` / `BEARISH` / `NEUTRAL` / `MISSING` / `STALE` / `EXPIRED`). It's never collapsed into a single agreement number that hides dissent or gaps.
- **D-09** **It isn't presented as a vote unless the policy really is one.** Readiness counts (e.g. "3 / 5 checks ready") are labelled as such.

### 6.4 Strength isn't probability
- **D-10** Rule **strength** (0–1) is labelled `STRENGTH`. It's **never** called probability, confidence or a percentage chance.
- **D-11** `probability_up` may be shown **only** when it comes from a calibrated model, together with the model version (architecture Part H; M9).

### 6.5 Execution circuit
- **D-12** The pipeline shows the frozen flow: `Market → View → Intent → Policy → Risk → Approval → Order (Core) ┃ Gate → Broker (Execution Worker) ┃ Ledger → Reconcile`. A visible divider marks the **broker-key boundary** between the Core Engine and the Execution Worker.
- **D-13** Each step shows its recorded outcome (passed, rejected with reason, reduced with old → new, waiting) and its time.

### 6.6 Approval card (Level 1)
- **D-14** The card shows the **exact intent version** being approved (side, quantity, type, limit price, time-in-force), its policy and risk results, and any reduction (`10 → 8, reason: position limit`). It has **Approve** and **Decline** only.
- **D-15** The approval expiry is shown as a countdown with the absolute expiry time. When the backend records a new intent version, the card shows that the old version was superseded.
- **D-16** **The card displays backend state; it doesn't decide it.**
  - Risk limits are **displayed read-only**. Editing them is an Admin setting.
  - A limit change makes earlier risk decisions **stale**. Before submission, the Execution Worker's Pre-Execution Gate checks that the policy and risk decisions are still current, and rejects the order if they aren't (architecture Law 13). The card shows that outcome as the backend records it.
  - **Material intent changes** (side, instrument, quantity, type, limit price, time-in-force) create a **new intent version that needs a fresh approval** (Law 12).
  - These principles **don't introduce** any automatic, blanket change to approval states. The dashboard never changes approval state itself.

---

## 7. Readable, keyboard-friendly, not colour-dependent

- **A-01** **Readable type:** body and data text ≥ 12px equivalent; headline numbers large; no informational text below ~11px.
- **A-02** **Contrast:** informational text and status chips meet **WCAG 2.x AA** contrast. Dim text is only for secondary or decorative content.
- **A-03** **Never colour alone.** Every status pairs colour with a **text label and a symbol** (`✓ MATCHED`, `✗ MISMATCH`, `▲ STALE`, `■ HALTED`, `● WAIT`). Direction pairs colour with an arrow (`↑`, `↓`).
- **A-04** **Full keyboard navigation:** every interactive element (panel focus, graph nodes, approve/decline, inspectors, replay) is reachable in a logical tab order, has a visible focus ring, and works with Enter/Space. Dialogs trap focus and close with Escape.
- **A-05** **Screen readers:** important state changes (new view, approval required, halt, incident) are announced through live regions; charts have text summaries.
- **A-06** **Reduced motion:** respect `prefers-reduced-motion` with a static but complete version of every animated element, including the decision graph.
- **A-07** **Role-appropriate UI:** a Viewer sees no Approve/Decline/Cancel controls at all (not disabled ones); a Trader sees approval and cancel; Admin-only settings appear only to Admins (PRD §4).

---

## 8. Sound and attention
- **N-01** Sound is **off by default**. When enabled, sounds accompany only significant recorded events (approval required, fill, halt, incident) and are never the only signal.

---

## 9. Review checklist (for any dashboard or report change)
- [ ] Every number has a source and a time; historical evidence labelled apart from current values (T-01, T-03, T-05).
- [ ] Financial values never animate through invented intermediate numbers (V-14).
- [ ] Policy and Risk shown downstream of the MarketView, not as its inputs (V-08, D-01).
- [ ] Dashboard replay and inspection read-only; backend evaluation results labelled and kept off the active account (H-03).
- [ ] No invented or placeholder values; unavailable ≠ zero (H-01, H-02).
- [ ] SIMULATED / REPLAY labelled; demo controls segregated (H-03, H-04).
- [ ] PAPER, autonomy level and trading status visible with observation time; "submissions blocked" only when an observed flag or gate result supports it, otherwise "cannot be verified"; no kill-switch write control; actor and time never invented (S-01 – S-03).
- [ ] Exceptional states prominent with a reason; WAIT carries its cause (E-01, E-02).
- [ ] Consensus explains its calculation and shows dissent and missing contributors (D-07, D-08).
- [ ] Strength never labelled as probability (D-10).
- [ ] Direction and severity colours not mixed; no colour-only status (V-02, A-03).
- [ ] Keyboard-navigable, reduced-motion safe, role-appropriate (A-04, A-06, A-07).

---

## 10. Technology is open

No framework, chart library or rendering technology is chosen here. That decision is **OPEN-15** in the PRD, decided before M8. Whatever is chosen MUST:
- support every rule above, including reduced motion and keyboard access;
- render the main screen smoothly on a normal laptop;
- receive state from the backend (the browser is **never** authoritative for accounts, orders or safety controls);
- keep third-party attribution and licence notices required by any bundled library.

---

## Appendix A — Reference prototype: "Signal Desk" (Astra / ChatGPT)

**What it is.** The owner asked the Astra assistant (a ChatGPT-based model) to build a dashboard simulator for this project. Astra produced "Signal Desk", a **browser-only simulator**:
- HTML/CSS/JavaScript, with TradingView Lightweight Charts for candles and a Canvas-2D "decision core";
- a scripted trading engine, synthetic NVDA prices and $10,000 of fake cash;
- scripted research, a 9-step pipeline, Level 1 approval, a simulated broker and a twin ledger;
- extras: replay, a "Why this trade?" inspector and a risk map.

It isn't connected to TradingAgents, any broker or real data. The owner shared screenshots (normal and stale states), two versions of its `index.html`, and Astra's handoff summary.

**Status in this project.** A **visual and interaction reference** for these principles and for M8. It's **not** an implementation specification. Astra's handoff document and its suggested Codex instruction propose their own module boundaries and build phases. Those are **not adopted**: they must be reviewed against the frozen architecture, and any useful parts (e.g. test scenarios for expired approvals, cancel races and partial fills) are folded into our task specs. Conflicts are rejected or raised as ADRs.

**Adopted from the prototype:**
- the dark HUD look and panel IDs;
- the always-visible `PAPER · SIMULATED DATA` badge, autonomy level and ticker;
- headline numbers that include data health and reconciliation;
- the particle decision core with input nodes;
- honesty labels such as "ADVICE ONLY", "1/5 checks ready · NOT A VOTE", "CANDLE RANGE · VOLUME N/A" and "QUOTE VALIDITY · not network latency";
- the prominent stale state;
- the 9-step circuit with a plain-language explanation line;
- the twin ledger;
- the evidence inspector and read-only replay;
- sound off by default, and Focus mode.

**Corrected relative to the prototype** (each mapped to the rule it violates):

| Prototype behaviour | Problem | Rule |
|---|---|---|
| A "HALT" button in the dashboard header | The kill switch is written only by the Admin CLI | S-02 |
| A mismatch "repair" that rebuilds the ledger from fills | The ledger is append-only; corrections are reversing entries | E-01 |
| A position-limit slider on the approval card | Limits are Admin settings; shown read-only | D-16 |
| "● LIVE SIM" label | "LIVE" is never used for non-live data | H-05 |
| A pipeline without the Order step and process boundary | Must show Core `NEW` → Execution Worker gate | D-12 |
| "WAIT" without a reason | WAIT carries its cause | E-02 |
| The same red/pink for down candles and danger | Direction and severity scales are separate | V-02 |
| Scenario/next-candle/reset controls inside product panels | Demo controls are segregated | H-04 |
| "Cancel order" on the approval card | Cancel belongs on the order row | D-05 |
| Small, low-contrast grey text | Readability and contrast minimums | A-01, A-02 |
| The reason's RSI differs from the panel's RSI for the same bar, with no label | One source per value; historical evidence labelled apart from current values | T-01, T-05 |
| Opening the evidence panel pauses the simulation | Viewing never affects the platform | V-15 |

**Missing in the prototype, required here:**
- a research card with model, times and warnings (D-06);
- `UNKNOWN`, `CANCEL_PENDING`, late-fill and `GATE_REJECTED` order states (D-05, E-01);
- crash and recovery visibility in health;
- audit trail access;
- role-specific UI (A-07);
- reduced motion (A-06);
- timezone and units on timestamps (T-03, T-04).
