"""The one documented upstream change (architecture Part I; docs/dev/upstream-changes.md):
the Trader's and Portfolio Manager's parsed structured output stays in the final state."""

from __future__ import annotations

import pytest

from tests.engine.research_fakes import (
    TEXT,
    TRADE_DATE,
    ScriptedModel,
    offline,  # noqa: F401  (fixture, applied with usefixtures)
    scripted_config,
    use_model,
)
from tradingagents.graph import trading_graph

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("offline")]


def run(tmp_path, monkeypatch, structured):
    use_model(monkeypatch, ScriptedModel(structured=structured))
    graph = trading_graph.TradingAgentsGraph(config=scripted_config(tmp_path, max_debate_rounds=1,
                                                                     max_risk_discuss_rounds=1))
    state, signal = graph.propagate("NVDA", TRADE_DATE)
    return state, signal


def test_structured_run_keeps_both_parsed_objects(tmp_path, monkeypatch):
    state, signal = run(tmp_path, monkeypatch, structured=True)
    assert state["trader_proposal_structured"] == {
        "action": "Buy", "reasoning": "r", "entry_price": 120.5, "stop_loss": 110.0,
        "position_sizing": None}
    decision = state["final_decision_structured"]
    assert decision["rating"] == "Overweight" == signal == state["final_rating"]
    assert {"executive_summary", "investment_thesis"} <= decision.keys()


def test_free_text_fallback_keeps_none_and_the_unchanged_text(tmp_path, monkeypatch):
    state, signal = run(tmp_path, monkeypatch, structured=False)
    assert state["trader_proposal_structured"] is None
    assert state["final_decision_structured"] is None
    assert state["trader_investment_plan"] == TEXT == state["final_trade_decision"]
    assert signal == "Overweight"
