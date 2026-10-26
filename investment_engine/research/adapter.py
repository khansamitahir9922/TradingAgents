"""Run one TradingAgents propagation behind a port and capture it (M6-04; ADR-001; Part I).

Only the Research Worker imports this module. It holds LLM settings, never
broker credentials. A run is advisory: the adapter returns a ResearchRecord
(reconstructable, not reproducible) and the raw final state for M6-05's parser.
It never writes to the database; the worker saves the result.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import logging
import os
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from langchain_core.callbacks import BaseCallbackHandler

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
from investment_engine.research.secrets import ambient_switches
from investment_engine.research.usage import UsageCounter

EXCHANGE_ZONE = ZoneInfo("America/New_York")
STATE_KEYS = ("company_of_interest", "trade_date", "market_report", "sentiment_report", "news_report",
              "fundamentals_report", "investment_debate_state", "investment_plan", "trader_investment_plan",
              "trader_proposal_structured", "risk_debate_state", "final_trade_decision", "final_rating",
              "final_decision_structured", "past_context", "memory_note")
FAILURE_CHARS = 500
PROVIDERS = frozenset({"google"})  # D45: Gemini only in M6
RECORDED_CONFIG = ("llm_provider", "quick_think_provider", "deep_think_provider", "quick_think_llm",
                   "deep_think_llm", "backend_url", "quick_think_backend_url", "deep_think_backend_url",
                   "max_debate_rounds", "max_risk_discuss_rounds", "max_tool_rounds", "max_recur_limit",
                   "temperature", "max_tokens", "llm_max_retries", "checkpoint_enabled", "output_language",
                   "google_thinking_level", "openai_reasoning_effort", "anthropic_effort", "benchmark_ticker",
                   "data_vendors", "tool_vendors")


class ProviderCallRefused(RuntimeError):
    """Raised before a model request once the provider has failed in this run (D46: no retries)."""


class ProviderFailureGuard(BaseCallbackHandler):
    """After the provider's first error, refuse every later model call before it is sent.

    Upstream catches a failed structured call and asks the plain model again; with
    `llm_max_retries=0` that is still a second paid request after a quota/429 error.
    Raising in the start callback stops that request before the provider sees it,
    and the run is recorded FAILED. Malformed structured output is a parser error,
    not a provider error, so upstream's free-text fallback for it is untouched.
    """

    raise_error = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.first_error: BaseException | None = None

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        with self._lock:
            if self.first_error is None and not isinstance(error, ProviderCallRefused):
                self.first_error = error

    def _refuse_if_failed(self) -> None:
        with self._lock:
            failed = self.first_error
        if failed is not None:
            raise ProviderCallRefused(f"provider failed earlier in this run ({type(failed).__name__}); "
                                      "no further model calls are made")

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs) -> None:
        self._refuse_if_failed()

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs) -> None:
        self._refuse_if_failed()


CACHE_NOTE = ("data sources record each vendor function that ran; whether it answered from upstream's disk cache "
              "under the run's cache directory, or the instrument identity from the in-process cache, is not "
              "distinguished")


class SourceRecorder:
    """Records the research-data fetch that actually served each call (Codex M6 review B6).

    Upstream routes every data tool through `router.VENDOR_METHODS` (looked up per call, with fallbacks); the
    sentiment node also calls its social fetchers directly, and the run resolves the instrument identity before
    the graph starts. Each of these functions is wrapped for the run only, in this dedicated process, and
    restored afterwards. Arguments are hashed, results measured; nothing is altered.
    """

    def __init__(self, clock) -> None:
        self._clock, self._lock = clock, threading.Lock()
        self._refs: list[DataSourceRef] = []
        self._restore: list = []

    def _wrap(self, vendor: str, method: str, func):
        recorder = self

        def recorded(*args, **kwargs):
            started = check_utc(recorder._clock.now(), "fetch start")
            digest = hashlib.sha256(repr((args, sorted(kwargs.items()))).encode("utf-8", "replace")).hexdigest()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                recorder._add(DataSourceRef(vendor, method, started, digest, recorder._clock.now(),
                                            type(exc).__name__, None))
                raise
            recorder._add(DataSourceRef(vendor, method, started, digest, recorder._clock.now(), None,
                                        len(str(result))))
            return result

        return recorded

    def _add(self, ref: DataSourceRef) -> None:
        with self._lock:
            self._refs.append(ref)

    def _replace(self, owner, name, value) -> None:
        self._restore.append((owner, name, owner[name] if isinstance(owner, dict) else getattr(owner, name)))
        if isinstance(owner, dict):
            owner[name] = value
        else:
            setattr(owner, name, value)

    def __enter__(self):
        from tradingagents.agents import context
        from tradingagents.agents.analysts import sentiment_analyst
        from tradingagents.dataflows import router

        for method, vendors in router.VENDOR_METHODS.items():
            for vendor, impl in list(vendors.items()):
                if isinstance(impl, list):
                    self._replace(vendors, vendor, [self._wrap(vendor, method, impl[0]), *impl[1:]])
                else:
                    self._replace(vendors, vendor, self._wrap(vendor, method, impl))
        self._replace(sentiment_analyst, "fetch_stocktwits_messages",
                      self._wrap("stocktwits", "stocktwits_messages", sentiment_analyst.fetch_stocktwits_messages))
        self._replace(sentiment_analyst, "fetch_reddit_posts",
                      self._wrap("reddit", "reddit_posts", sentiment_analyst.fetch_reddit_posts))
        self._replace(context, "_identity", self._wrap("yfinance", "instrument_identity", context._identity))
        return self

    def __exit__(self, *exc) -> None:
        for owner, name, original in reversed(self._restore):
            if isinstance(owner, dict):
                owner[name] = original
            else:
                setattr(owner, name, original)
        self._restore.clear()

    def refs(self) -> tuple[DataSourceRef, ...]:
        with self._lock:
            return tuple(self._refs)


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
        # Every run-shaping key is set here, never inherited: both tiers on the job's provider, no endpoint
        # overrides, provider knobs at their defaults, upstream's own tool/recursion limits (B4).
        cfg.update(llm_provider=s.provider, quick_think_provider=s.provider, deep_think_provider=s.provider,
                   quick_think_llm=s.quick_model, deep_think_llm=s.deep_model, backend_url=None,
                   quick_think_backend_url=None, deep_think_backend_url=None,
                   max_debate_rounds=s.max_debate_rounds, max_risk_discuss_rounds=s.max_risk_rounds,
                   max_tool_rounds=20, max_recur_limit=100,
                   temperature=None if s.temperature is None else float(s.temperature),  # LLM setting, not money
                   max_tokens=None, google_thinking_level=None, openai_reasoning_effort=None, anthropic_effort=None,
                   benchmark_ticker=None, output_language=s.output_language, llm_max_retries=0,
                   checkpoint_enabled=False, results_dir=str(self.work_dir / "results"),
                   data_cache_dir=str(self.work_dir / "cache"),
                   memory_log_path=str(self.work_dir / "memory" / "trading_memory.md"))
        return cfg

    @staticmethod
    def effective(cfg: dict) -> str:
        return json.dumps({k: cfg.get(k) for k in RECORDED_CONFIG}, sort_keys=True, default=str)

    def run(self, job: ResearchJob, *, attempt: int, clock) -> RunOutput:
        started = check_utc(clock.now(), "start")
        counter, capture = UsageCounter(clock=clock), TextCapture(redact=self._redact)
        guard = ProviderFailureGuard()
        handlers = [guard, counter, capture]  # the guard first: a refused call never reaches the others
        today = started.astimezone(EXCHANGE_ZONE).date()
        cfg = self.config(job)
        log_factory = logging.getLogRecordFactory()
        logging.setLogRecordFactory(self._redacting_records(log_factory))
        sources = SourceRecorder(clock)
        self._live = (counter, capture, sources)
        try:
            with sources:
                failure, final_state, state_text = self._run_graph(job, cfg, handlers, guard, today)
        finally:
            logging.setLogRecordFactory(log_factory)
        return self._output(job, attempt, clock, started, counter, capture, cfg, failure, final_state, state_text,
                            sources.refs())

    def partial(self):
        """What the current (or last) run has captured so far: (calls, tools, texts, data sources).

        Thread-safe snapshot, for a worker abandoning a run at its deadline (Codex M6 review N2)."""
        live = getattr(self, "_live", None)
        if live is None:
            return (), (), (), ()
        counter, capture, sources = live
        calls = tuple(CallRecord(c.run_id, c.node, c.model, c.started_at, c.ended_at, c.input_tokens,
                                 c.output_tokens, c.error) for c in counter.calls())
        tools = tuple(ToolRecord(t.run_id, t.node, t.name, t.input_sha256, t.result_chars, t.started_at, t.ended_at,
                                 t.error) for t in counter.tools())
        return calls, tools, capture.texts(), sources.refs()

    def _redacting_records(self, make):
        """Every log record created during a run (upstream's warnings included) carries redacted text only."""
        redact = self._redact

        def factory(*args, **kwargs):
            record = make(*args, **kwargs)
            try:
                message = record.getMessage()
            except Exception:  # a malformed log call keeps its own error path
                return record
            record.msg, record.args = redact(message), ()
            if record.exc_info and record.exc_info[1] is not None:
                record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)))
                record.exc_info = None
            return record

        return factory

    def _run_graph(self, job, cfg, handlers, guard, today):
        failure, final_state, state_text = None, None, "{}"
        switches = ambient_switches(os.environ)
        if job.settings.provider not in PROVIDERS:
            failure = f"provider {job.settings.provider} is not approved: M6 runs Google only (D45)"
        elif switches:
            failure = ("refused before any call: set variables would change upstream providers, endpoints or "
                       "integrations: " + ", ".join(switches))
        elif job.research_date != today:
            failure = (f"research date {job.research_date.isoformat()} is not the current exchange date "
                       f"{today.isoformat()}: historical research is refused (D50)")
        else:
            try:
                graph = self._graph_factory(selected_analysts=job.settings.analysts, config=cfg,
                                            callbacks=handlers)
                state = graph.create_run_state(job.ticker, job.research_date.isoformat())
                result = graph.graph.invoke(state, **graph.propagator.get_graph_args(callbacks=handlers))
                # Upstream writes its state log and memory entry from what it is given: the redacted state.
                safe = {k: self._redact.deep(v) if isinstance(v, str | dict | list | tuple) else v
                        for k, v in result.items()}
                graph.record_decision(job.ticker, job.research_date.isoformat(), safe)
                final_state, state_text = _state_json(safe)
                state_text = self._redact(state_text)
                final_state = json.loads(state_text)
            except Exception as exc:  # recorded as a failed run, never a partial context
                failure, final_state = _failure(exc, self._redact), None
            if guard.first_error is not None:  # even when upstream swallowed it and carried on
                failure = self._redact(f"provider error: {type(guard.first_error).__name__}: {guard.first_error}; "
                                       "no further model calls were made")[:FAILURE_CHARS]
                final_state = None
        return failure, final_state, state_text

    def _output(self, job, attempt, clock, started, counter, capture, cfg, failure, final_state, state_text,
                sources):
        summary = counter.summary()
        warnings = list(summary.warnings)
        calls = tuple(CallRecord(c.run_id, c.node, c.model, c.started_at, c.ended_at, c.input_tokens, c.output_tokens,
                                 c.error) for c in counter.calls())
        tools = tuple(ToolRecord(t.run_id, t.node, t.name, t.input_sha256, t.result_chars, t.started_at, t.ended_at,
                                 t.error) for t in counter.tools())
        if sources:
            warnings.append(CACHE_NOTE)
        record = ResearchRecord(job.job_id, attempt, job.settings, importlib.metadata.version("tradingagents"),
                                self.code_version, calls, tools, capture.texts(), sources, state_text,
                                UsageTotals.of(calls, len(tools)), tuple(warnings), started,
                                max(started, check_utc(clock.now(), "finish")),
                                RunOutcome.FAILED if failure else RunOutcome.SUCCEEDED, failure,
                                self.effective(cfg))
        return RunOutput(record, final_state)


__all__ = ["EXCHANGE_ZONE", "ResearchPort", "RunOutput", "TradingAgentsAdapter"]
