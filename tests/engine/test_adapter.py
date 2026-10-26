"""M6-04: one TradingAgents run behind the port, fully captured, offline."""
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import ClassVar

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
    assert "RuntimeError" in rec.failure and SECRET not in rec.failure and REDACTED in rec.failure
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


def test_tier_providers_and_endpoints_are_pinned_whatever_the_ambient_defaults(tmp_path, monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG

    for key, value in (("deep_think_provider", "openai"), ("quick_think_provider", "anthropic"),
                       ("backend_url", "https://elsewhere.example/v1"), ("deep_think_backend_url", "https://x.example"),
                       ("google_thinking_level", "high"), ("max_tool_rounds", 3)):
        monkeypatch.setitem(DEFAULT_CONFIG, key, value)  # what inherited TRADINGAGENTS_* variables would do
    seen = []
    real = trading_graph.create_tier_client
    use_model(monkeypatch, ScriptedModel(structured=True))
    fake = trading_graph.create_tier_client

    def spy(config, tier, **k):
        seen.append((tier, config[f"{tier}_think_provider"], config.get(f"{tier}_think_backend_url"),
                     config.get("backend_url"), config.get("google_thinking_level"), config["max_tool_rounds"]))
        return fake(config, tier, **k)

    monkeypatch.setattr(trading_graph, "create_tier_client", spy)
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    assert real is not None and out.record.outcome is RunOutcome.SUCCEEDED
    assert sorted(seen) == [("deep", "google", None, None, None, 20), ("quick", "google", None, None, None, 20)]
    effective = json.loads(out.record.effective_config_json)
    assert effective["deep_think_provider"] == effective["quick_think_provider"] == "google"
    assert effective["backend_url"] is None and effective["llm_max_retries"] == 0


def test_a_provider_other_than_google_is_refused_before_any_call(tmp_path, monkeypatch):
    model = ScriptedModel(structured=True)
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(settings=settings(provider="openai")), attempt=1, clock=ReplayClock(T))
    assert out.record.outcome is RunOutcome.FAILED and "D45" in out.record.failure and model.calls == []


@pytest.mark.parametrize("name", ["TYPESAFE_API_KEY", "TRADINGAGENTS_DEEP_THINK_PROVIDER", "GOOGLE_GENAI_USE_VERTEXAI"])
def test_an_ambient_upstream_switch_refuses_the_run_before_any_call(tmp_path, monkeypatch, name):
    monkeypatch.setenv(name, "ambient-value-xyz")
    model = ScriptedModel(structured=True)
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    assert out.record.outcome is RunOutcome.FAILED and name in out.record.failure
    assert "ambient-value-xyz" not in out.record.failure and model.calls == []


class QuotaOnce(ScriptedModel):
    """The Trader's structured call hits one 429; any later call would have succeeded."""

    raise_quota: bool = False
    failed_at: list = []
    message: str = "429 RESOURCE_EXHAUSTED: quota exceeded"

    def with_structured_output(self, schema, **kwargs):
        from langchain_core.runnables import RunnableLambda

        from tests.engine.research_fakes import STRUCTURED
        from tradingagents.agents import schemas

        plain = self.model_copy(update={"tools": ()})

        def call(value, config):
            if schema is schemas.TraderProposal and not self.failed_at:
                return plain.model_copy(update={"raise_quota": True}).invoke(value, config=config)
            plain.invoke(value, config=config)
            return STRUCTURED[schema]

        return RunnableLambda(call)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.raise_quota:
            self.calls.append(1)
            self.failed_at.append(len(self.calls))
            raise RuntimeError(self.message)
        return super()._generate(messages, stop, run_manager, **kwargs)


def test_a_quota_error_is_never_retried_by_the_upstream_fallback(tmp_path, monkeypatch):
    model = QuotaOnce(structured=True, failed_at=[])
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    assert model.failed_at, "the scenario must reach the Trader's structured call"
    assert len(model.calls) == model.failed_at[0]  # no model call reached the provider after the 429
    assert out.record.outcome is RunOutcome.FAILED and out.final_state is None
    assert "RESOURCE_EXHAUSTED" in out.record.failure and "no further" in out.record.failure


def test_malformed_structured_output_still_falls_back_to_free_text(tmp_path, monkeypatch):
    model = ScriptedModel(structured=False)  # structured output unsupported: upstream's allowed fallback
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    assert out.record.outcome is RunOutcome.SUCCEEDED


ESCAPED_SECRET = 'AIzaFAKE"quote\\back-0123456789'  # a quote and a backslash: escaped forms differ from the literal


def _every_output(tmp_path, capsys, caplog):
    texts = [path.read_text(encoding="utf-8", errors="replace") for path in (tmp_path / "work").rglob("*")
             if path.is_file()]
    captured = capsys.readouterr()
    return "\n".join(texts + [captured.out, captured.err, caplog.text])


@pytest.mark.parametrize("secret", [SECRET, ESCAPED_SECRET])
def test_an_echoed_secret_reaches_no_file_log_or_stream(tmp_path, monkeypatch, capsys, caplog, secret):
    import logging

    caplog.set_level(logging.DEBUG)
    for vendors in router.VENDOR_METHODS.values():
        for vendor in vendors:
            monkeypatch.setitem(vendors, vendor, lambda *a, _s=secret, **k: f"vendor echoed {_s}")
    use_model(monkeypatch, EchoModel(structured=True))  # reports quote the tool output, as real models do
    out = TradingAgentsAdapter(work_dir=tmp_path / "work", code_version="abc", secrets=(secret,)).run(
        job(), attempt=1, clock=ReplayClock(T))
    assert secret in "".join(EchoModel.echoed), "the scenario must put the secret into model output"
    assert out.record.outcome is RunOutcome.SUCCEEDED
    escaped = json.dumps(secret)[1:-1]
    stored = json.dumps([t.text for t in out.record.texts]) + out.record.final_state_json
    everywhere = _every_output(tmp_path, capsys, caplog) + stored
    assert secret not in everywhere and escaped not in everywhere
    assert any(p.suffix == ".json" for p in (tmp_path / "work").rglob("*")), "upstream wrote its state log"


def test_a_secret_in_a_provider_error_is_never_logged(tmp_path, monkeypatch, capsys, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    model = QuotaOnce(structured=True, failed_at=[], message=f"429 quota exceeded for key {SECRET}")
    use_model(monkeypatch, model)
    out = adapter(tmp_path).run(job(), attempt=1, clock=ReplayClock(T))
    assert out.record.outcome is RunOutcome.FAILED and model.failed_at
    assert "structured-output invocation failed" in caplog.text  # upstream did log the error
    assert SECRET not in _every_output(tmp_path, capsys, caplog) + out.record.failure


def test_redaction_is_single_pass_and_covers_escaped_forms():
    from investment_engine.research.capture import Redactor

    redact = Redactor(("abcd1234", "zz"))
    assert redact("x abcd1234 y") == f"x {REDACTED} y"
    assert "zz" not in redact("zz and zz") and redact("zz").count("REDACTED") == 1
    tricky = 'k"q\\x-123456'
    assert tricky not in redact(json.dumps({"v": tricky})) and json.dumps(tricky)[1:-1] not in Redactor((tricky,))(
        json.dumps({"v": tricky}))


def test_secrets_too_short_to_redact_safely_are_refused(tmp_path):
    from investment_engine.research.secrets import ResearchSecretsError, load_research_secrets

    path = tmp_path / "research_worker.env"
    path.write_text("GOOGLE_API_KEY=abc\n", encoding="utf-8")
    with pytest.raises(ResearchSecretsError, match="too short"):
        load_research_secrets(path)


class EchoModel(ScriptedModel):
    """Like a real model, its answer after a tool call quotes the tool's output into the report."""

    echoed: ClassVar[list] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        if messages and isinstance(messages[-1], ToolMessage):
            quoted = " ".join(str(m.content) for m in messages if isinstance(m, ToolMessage))
            EchoModel.echoed.append(quoted)
            self.calls.append(1)
            message = AIMessage(content=f"Report quoting sources: {quoted}\n\n**Rating**: Overweight\n\n"
                                        "FINAL TRANSACTION PROPOSAL: **BUY**")
            return ChatResult(generations=[ChatGeneration(message=message)])
        return super()._generate(messages, stop, run_manager, **kwargs)
