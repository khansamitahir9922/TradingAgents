# Changes to upstream TradingAgents

Architecture Part I keeps changes to the vendored upstream package (`tradingagents/`) **minimal and listed**, so new upstream releases can still be merged. Every change is recorded here with its reason and what to check when merging an upstream release.

| # | Change | Files | Since |
|---|---|---|---|
| U1 | Keep the Trader's and Portfolio Manager's parsed structured output in the final graph state | `tradingagents/agents/trader/trader.py`, `tradingagents/agents/managers/portfolio_manager.py`, `tradingagents/agents/state.py` | M6-03 (2026-10-25) |

## U1: keep the parsed Trader and Portfolio Manager output

**Why.** Upstream already asks both agents for structured output (`TraderProposal`, `PortfolioDecision`). It renders the result back to markdown and keeps only the Portfolio Manager's rating as a typed field. The Research Worker (M6) needs the typed fields, such as the trader's action and its entry and stop levels, to build a `ResearchContext` without re-parsing prose. Architecture Part I and ADR-001 plan exactly this one change.

**What changed.**
- Two optional state keys:
  - `trader_proposal_structured`: `TraderProposal.model_dump(mode="json")`;
  - `final_decision_structured`: `PortfolioDecision.model_dump(mode="json")`.
- Each key is `None` when that agent fell back to free text.
- The Trader now calls `invoke_structured` and renders or falls back inline. This is the same logic as `invoke_structured_or_freetext`, which other agents still use, so it can keep the parsed object.

**Unchanged.** Prompts, ratings, the rendered markdown, the memory log, saved reports and checkpoints. The upstream test suite passes unchanged.

**Tests.** `tests/test_structured_output_retained.py` covers:
- a structured run keeps both objects;
- a free-text run keeps `None` and the unchanged text.

**When merging an upstream release.**
1. Check that `trader_node` and `portfolio_manager_node` still return the two keys.
2. Check that the `AgentState` entries still exist.
3. If upstream adds its own typed fields, prefer theirs and retire U1.
