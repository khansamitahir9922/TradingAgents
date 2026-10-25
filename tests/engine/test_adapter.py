"""M6-04: one TradingAgents run behind the port, fully captured, offline."""
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.research.adapter import TradingAgentsAdapter
from investment_engine.research.capture import REDACTED
from investment_engine.research.contracts import RunOutcome
from tests.engine.research_fakes import (
    ScriptedModel,
    offline,  # noqa: F401  (fixture, applied with usefixtures)
    use_model,
)
from tests.engine.test_research_contracts import job, settings
from tradingagents.dataflows import router
from tradingagents.graph import trading_graph

T = datetime(2026, 1, 9, 15, tzinfo=UTC)  # 10:00 in New York on the job's research date
SECRET = "AIzaFAKE-research-key-0123456789"
pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("offline")]


class FailingModel(ScriptedModel):
    fail_at: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if len(self.calls) + 1 == self.fail_at:
            self.calls.append(1)
            raise RuntimeError(f"provider unavailable for key {SECRET}")
        return super()._generate(messages, stop, run_manager, **kwargs)


def adapter(tmp_path):
    return TradingAgentsAdapter(work_dir=tmp_path / "work", code_version="abc123", secrets=(SECRET,))


def test_a_full_run_is_captured_and_reconstructable(tmp_path, monkeypatch):
    model = ScriptedModel(structured=True, usage={"input_tokens": 7, "output_tokens": 2, "total_tokens": 9})
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    rec = out.record
    assert rec.outcome is RunOutcome.SUCCEEDED and rec.failure is None
    assert rec.usage.requests == len(model.calls) == len(rec.calls)
    assert rec.usage.input_tokens == 7 * len(model.calls)
    assert rec.usage.tool_calls == len(rec.tools) == len(rec.data_sources) >= 12
    prompts = [t for t in rec.texts if t.role == "prompt"]
    assert len(prompts) == len(model.calls)  # every agent's prompt, once
    assert {t.node for t in prompts} >= {"Market Analyst", "Trader", "Portfolio Manager"}
    assert {"prompt", "response", "tool_input", "tool_output"} == {t.role for t in rec.texts}
    assert out.final_state["final_decision_structured"]["rating"] == "Overweight"
    assert out.final_state["trader_proposal_structured"]["entry_price"] == 120.5
    assert json.loads(rec.final_state_json) == out.final_state
    assert rec.upstream_version == "0.6.0" and rec.code_version == "abc123" and rec.run_id


def test_settings_are_pinned_without_retries_or_checkpoints(tmp_path, monkeypatch):
    seen = {}
    real = trading_graph.TradingAgentsGraph

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    use_model(monkeypatch, ScriptedModel(structured=True))
    TradingAgentsAdapter(work_dir=tmp_path / "w", code_version="abc", graph_factory=spy).run(
        job(), attempt=1, clock=ReplayClock(T))
    cfg = seen["config"]
    assert (cfg["llm_provider"], cfg["quick_think_llm"], cfg["deep_think_llm"]) == (
        "google", "gemini-quick-001", "gemini-deep-001")
    assert cfg["llm_max_retries"] == 0 and cfg["checkpoint_enabled"] is False
    assert Path(cfg["results_dir"]).is_relative_to(tmp_path / "w")
    assert seen["selected_analysts"] == settings().analysts


@pytest.mark.parametrize("day", [date(2026, 1, 8), date(2026, 1, 12)])
def test_a_date_other_than_the_current_exchange_date_is_refused_before_any_model_call(tmp_path, monkeypatch, day):
    model = ScriptedModel(structured=True)
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(research_date=day), attempt=1, clock=ReplayClock(T))
    assert out.record.outcome is RunOutcome.FAILED and "historical research is refused" in out.record.failure
    assert model.calls == [] and out.record.calls == () and out.final_state is None


def test_the_exchange_date_is_new_york_not_utc(tmp_path, monkeypatch):
    use_model(monkeypatch, ScriptedModel(structured=True))
    late_utc = datetime(2026, 1, 10, 2, tzinfo=UTC)  # still Jan 9 in New York
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(late_utc))
    assert out.record.outcome is RunOutcome.SUCCEEDED


def test_a_provider_error_is_a_failed_record_without_context_or_secret(tmp_path, monkeypatch):
    model = FailingModel(structured=True, fail_at=9)
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    rec = out.record
    assert rec.outcome is RunOutcome.FAILED and out.final_state is None
    assert rec.failure.startswith("RuntimeError") and SECRET not in rec.failure and REDACTED in rec.failure
    assert len(rec.calls) == len(model.calls)  # the failed call is counted too
    assert any(c.error for c in rec.calls)


def test_a_secret_reaching_prompts_or_tool_output_is_redacted_everywhere(tmp_path, monkeypatch):
    for vendors in router.VENDOR_METHODS.values():
        for vendor in vendors:
            monkeypatch.setitem(vendors, vendor, lambda *a, **k: f"vendor echoed {SECRET}")
    use_model(monkeypatch, ScriptedModel(structured=True))
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    blob = json.dumps([t.text for t in out.record.texts]) + out.record.final_state_json
    assert SECRET not in blob and REDACTED in blob


def test_run_times_come_from_the_injected_clock(tmp_path, monkeypatch):
    use_model(monkeypatch, ScriptedModel(structured=True))
    clock = ReplayClock(T)
    out = adapter(tmp_path).run(job(), attempt=2, clock=clock)
    assert out.record.started_at == T == out.record.finished_at and out.record.attempt == 2
    assert out.record.finished_at - out.record.started_at == timedelta(0)
