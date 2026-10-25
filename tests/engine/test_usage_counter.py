"""M6-00: count every LLM request, token and tool call of one TradingAgents run, offline."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.research.usage import UsageCounter, UsageSummary
from tests.engine.research_fakes import (
    TRADE_DATE,
    ScriptedModel,
    offline,  # noqa: F401  (fixture, applied with usefixtures)
    scripted_config,
    use_model,
)
from tradingagents.graph import trading_graph

T = datetime(2026, 1, 9, 21, tzinfo=UTC)
pytestmark = pytest.mark.unit

AGENT_NODES = {"Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst", "Bull Researcher",
               "Bear Researcher", "Research Manager", "Trader", "Aggressive Analyst", "Conservative Analyst",
               "Neutral Analyst", "Portfolio Manager"}


def run(tmp_path, monkeypatch, model, **config):
    counter = UsageCounter(clock=ReplayClock(T))
    use_model(monkeypatch, model)
    graph = trading_graph.TradingAgentsGraph(config=scripted_config(tmp_path, **config), callbacks=[counter])
    state = graph.create_run_state("NVDA", TRADE_DATE)
    graph.graph.invoke(state, **graph.propagator.get_graph_args(callbacks=[counter]))
    return counter.summary(), model


@pytest.mark.usefixtures("offline")
def test_every_model_request_and_tool_call_is_counted_once(tmp_path, monkeypatch):
    summary, model = run(tmp_path, monkeypatch, ScriptedModel(structured=True, usage={
        "input_tokens": 10, "output_tokens": 3, "total_tokens": 13}),
        max_debate_rounds=1, max_risk_discuss_rounds=1)
    assert isinstance(summary, UsageSummary)
    assert summary.requests == len(model.calls)  # the provider saw exactly what was counted
    assert summary.input_tokens == 10 * summary.requests and summary.output_tokens == 3 * summary.requests
    assert {node for node, _ in summary.per_agent} == AGENT_NODES  # every request attributed to its agent
    assert summary.tool_calls >= 12  # every tool-using analyst called each of its tools
    assert summary.warnings == ()


@pytest.mark.usefixtures("offline")
def test_silent_provider_usage_is_unknown_not_zero(tmp_path, monkeypatch):
    summary, model = run(tmp_path, monkeypatch, ScriptedModel(), max_debate_rounds=1, max_risk_discuss_rounds=1)
    assert summary.requests == len(model.calls) > 0
    assert summary.input_tokens is None and summary.output_tokens is None
    assert any("token usage unknown" in w for w in summary.warnings)


def test_duplicate_callbacks_for_one_run_are_counted_once():
    counter = UsageCounter(clock=ReplayClock(T))
    rid = uuid4()
    for _ in range(2):  # the same handler attached at model and graph level
        counter.on_chat_model_start({"name": "m"}, [[]], run_id=rid, metadata={"langgraph_node": "Trader"})
    assert counter.summary().requests == 1


def test_times_come_from_the_injected_clock():
    clock = ReplayClock(T)
    counter = UsageCounter(clock=clock)
    rid = uuid4()
    counter.on_chat_model_start({"name": "m"}, [[]], run_id=rid, metadata={})
    clock.advance_by(timedelta(seconds=5))
    counter.on_llm_end(type("R", (), {"generations": [], "llm_output": None})(), run_id=rid)
    (call,) = counter.calls()
    assert (call.started_at, call.ended_at) == (T, T + timedelta(seconds=5))
