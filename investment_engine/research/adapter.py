"""Run one TradingAgents propagation behind a port and capture it (M6-04; ADR-001; Part I).

Only the Research Worker imports this module. It holds LLM settings, never
broker credentials. A run is advisory: the adapter returns a ResearchRecord
(reconstructable, not reproducible) and the raw final state for M6-05's parser.
It never writes to the database; the worker saves the result.
"""

from __future__ import annotations

import copy
import importlib.metadata
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from investment_engine.market.availability import check_utc
from investment_engine.research.capture import Redactor, TextCapture
from investment_engine.research.contracts import (
    CallRecord,
    DataSourceRef,
    ResearchJob,
    ResearchRecord,
    RunOutcome,
    ToolRecord,
    UsageTotals,
)
from investment_engine.research.usage import UsageCounter

EXCHANGE_ZONE = ZoneInfo("America/New_York")
ROUTER_VENDOR = "tradingagents-router"  # upstream routes each tool to its configured vendor
STATE_KEYS = ("company_of_interest", "trade_date", "market_report", "sentiment_report", "news_report",
              "fundamentals_report", "investment_debate_state", "investment_plan", "trader_investment_plan",
              "trader_proposal_structured", "risk_debate_state", "final_trade_decision", "final_rating",
              "final_decision_structured", "past_context", "memory_note")
FAILURE_CHARS = 500


@dataclass(frozen=True)
class RunOutput:
    record: ResearchRecord
    final_state: dict | None  # the JSON-safe selected state, None when the run failed


class ResearchPort(Protocol):
    def run(self, job: ResearchJob, *, attempt: int, clock) -> RunOutput: ...


def _state_json(state) -> tuple[dict, str]:
    selected = {key: state.get(key) for key in STATE_KEYS if key in state}
    text = json.dumps(selected, sort_keys=True, default=str, ensure_ascii=True)
    return json.loads(text), text


def _failure(exc: BaseException, redact: Redactor) -> str:
    return redact(f"{type(exc).__name__}: {exc}")[:FAILURE_CHARS] or type(exc).__name__


class TradingAgentsAdapter:
    def __init__(self, *, work_dir: Path, code_version: str, secrets=(), graph_factory=None) -> None:
        self.work_dir, self.code_version = Path(work_dir), code_version
        self._redact = Redactor(secrets)
        if graph_factory is None:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            graph_factory = TradingAgentsGraph
        self._graph_factory = graph_factory

    def config(self, job: ResearchJob) -> dict:
        from tradingagents.default_config import DEFAULT_CONFIG

        s = job.settings
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg.update(llm_provider=s.provider, quick_think_llm=s.quick_model, deep_think_llm=s.deep_model,
                   max_debate_rounds=s.max_debate_rounds, max_risk_discuss_rounds=s.max_risk_rounds,
                   temperature=None if s.temperature is None else float(s.temperature),  # LLM setting, not money
                   output_language=s.output_language, llm_max_retries=0, checkpoint_enabled=False,
                   results_dir=str(self.work_dir / "results"), data_cache_dir=str(self.work_dir / "cache"),
                   memory_log_path=str(self.work_dir / "memory" / "trading_memory.md"))
        return cfg

    def run(self, job: ResearchJob, *, attempt: int, clock) -> RunOutput:
        started = check_utc(clock.now(), "start")
        counter, capture = UsageCounter(clock=clock), TextCapture(redact=self._redact)
        final_state, state_text, failure, warnings = None, "{}", None, []
        today = started.astimezone(EXCHANGE_ZONE).date()
        if job.research_date != today:
            failure = (f"research date {job.research_date.isoformat()} is not the current exchange date "
                       f"{today.isoformat()}: historical research is refused (D50)")
        else:
            try:
                graph = self._graph_factory(selected_analysts=job.settings.analysts, config=self.config(job),
                                            callbacks=[counter, capture])
                state = graph.create_run_state(job.ticker, job.research_date.isoformat())
                result = graph.graph.invoke(state, **graph.propagator.get_graph_args(callbacks=[counter, capture]))
                graph.record_decision(job.ticker, job.research_date.isoformat(), result)
                final_state, state_text = _state_json(result)
                state_text = self._redact(state_text)
                final_state = json.loads(state_text)
            except Exception as exc:  # recorded as a failed run, never a partial context
                failure, final_state = _failure(exc, self._redact), None
        summary = counter.summary()
        warnings.extend(summary.warnings)
        calls = tuple(CallRecord(c.run_id, c.node, c.model, c.started_at, c.ended_at, c.input_tokens, c.output_tokens,
                                 c.error) for c in counter.calls())
        tools = tuple(ToolRecord(t.run_id, t.node, t.name, t.input_sha256, t.result_chars, t.started_at, t.ended_at,
                                 t.error) for t in counter.tools())
        sources = tuple(DataSourceRef(ROUTER_VENDOR, t.name, t.started_at, t.input_sha256) for t in tools)
        record = ResearchRecord(job.job_id, attempt, job.settings, importlib.metadata.version("tradingagents"),
                                self.code_version, calls, tools, capture.texts(), sources, state_text,
                                UsageTotals.of(calls, len(tools)), tuple(warnings), started,
                                max(started, check_utc(clock.now(), "finish")),
                                RunOutcome.FAILED if failure else RunOutcome.SUCCEEDED, failure)
        return RunOutput(record, final_state)


__all__ = ["EXCHANGE_ZONE", "ResearchPort", "RunOutput", "TradingAgentsAdapter"]
