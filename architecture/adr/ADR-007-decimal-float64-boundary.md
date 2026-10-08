# ADR-007: Decimal/float64 boundary

| | |
|---|---|
| **Status** | Accepted: frozen in Architecture v1.0 (2026-10-07). This record: Codex document review passed (2026-10-09); awaiting review of the M0 commit and merge. |
| **Date** | Decision 2026-10-07 · recorded 2026-10-08 |
| **Architecture** | Law 16 · Parts A, H (`Candle`, `OrderIntent`, `Fill`, `LedgerEntry`) |
| **Milestone** | M1 (converters, Candle boundary) · used in every later milestone |

## Context
Two kinds of number work happen in the platform:
- **Accounting and orders** (cash, balances, prices on orders and fills, fees, quantities) must be exact. Binary floating point can't represent values like 0.1 exactly, and small errors accumulate into ledgers that don't balance or reconcile.
- **Quant and ML** (indicators, features, model inputs) need fast vectorised maths. Libraries such as NumPy and pandas work in `float64`, and `Decimal` would be slow and awkward there.

The two drafts disagreed: v0.1 proposed Decimal everywhere; v0.2 proposed Decimal for money and float for quant.

## Decision
1. **Money uses `Decimal`**, always with an explicit **currency or unit**: cash, balances, order prices, fill prices, fees and quantities.
2. **Quant features and ML use `float64`.**
3. **Conversion happens only through explicit converters**, never implicitly. Candle OHLC values are `Decimal` at the boundary (Part H) and are converted when they enter quant code.
4. A float value never becomes an order price or quantity without passing an explicit converter and the risk checks (see also Law 4 for LLM-suggested levels).

## Alternatives considered
**Documented in the architecture lineage:**
- **Decimal everywhere** (Claude v0.1; Part A, "Money type"). Impractical for ML and vectorised indicators.
- **Decimal for money, float for quant** (ChatGPT v0.2). Adopted, with explicit converters added.

**Retrospective analysis** (added by Claude while writing this record; not necessarily considered at the time):
- **float everywhere.** Inexact accounting; ledgers and reconciliation would show spurious differences.
- **Integer minor units** (e.g. cents). Share quantities and prices can need more precision than cents, and units differ by instrument. Decimal with an explicit unit covers both.

## Consequences
- **Positive.** Exact accounting and reconciliation; practical numerics for analysis. The places where precision changes are few, named and testable.
- **Negative.** Converters must define precision and rounding explicitly, and a mistake there is a real bug. Developers must keep the two worlds apart, which reviews must check.
- **Follow-ups.** M1 task specs define the converters, including their rounding and precision rules and tests. ADR-010 (securities ledger model, before M5) builds on this.

## How we check it
- Unit tests: converter round-trips and rounding cases; mixing `float` into a money field is rejected.
- Part J: ledger transactions balance.
- Review: no implicit `float(…)` or `Decimal(float)` on money paths.

## References
Architecture Law 16; Parts A, H. Design principles T-04 (precision on screen).
