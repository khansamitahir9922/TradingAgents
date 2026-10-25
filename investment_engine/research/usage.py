"""Count what one TradingAgents run actually asks of the provider (M6-00; OPEN-10).

A LangChain callback handler records every model request and tool call with the
agent node that made it. Token counts are taken only from what the provider
reports: a call without reported usage makes the run's tokens unknown, never 0.
The same handler can be attached at model and graph level; each run ID counts once.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime

from langchain_core.callbacks import BaseCallbackHandler

from investment_engine.market.availability import check_utc


@dataclass(frozen=True)
class LlmCall:
    run_id: str
    node: str | None
    model: str | None
    started_at: datetime
    ended_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None


@dataclass(frozen=True)
class ToolCall:
    run_id: str
    node: str | None
    name: str
    input_sha256: str
    result_chars: int | None
    started_at: datetime
    ended_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class UsageSummary:
    requests: int
    input_tokens: int | None  # None: at least one call's usage was not reported
    output_tokens: int | None
    tool_calls: int
    per_agent: tuple[tuple[str, int], ...]  # (node, model requests)
    warnings: tuple[str, ...]


def _reported_usage(response) -> tuple[int | None, int | None]:
    for generations in getattr(response, "generations", None) or ():
        for generation in generations:
            usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
            if usage and "input_tokens" in usage and "output_tokens" in usage:
                return int(usage["input_tokens"]), int(usage["output_tokens"])
    token_usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
    for prompt, completion in (("prompt_tokens", "completion_tokens"), ("input_tokens", "output_tokens")):
        if prompt in token_usage and completion in token_usage:
            return int(token_usage[prompt]), int(token_usage[completion])
    return None, None


def _agent(metadata) -> str | None:
    """The top-level graph node: an analyst's sub-graph reports its inner node ("agent"),
    while its checkpoint namespace starts with the analyst's own node name."""
    metadata = metadata or {}
    namespace = metadata.get("langgraph_checkpoint_ns") or metadata.get("checkpoint_ns")
    if namespace:
        return namespace.split("|", 1)[0].split(":", 1)[0]
    return metadata.get("langgraph_node")


class UsageCounter(BaseCallbackHandler):
    """Thread-safe: the analysts run concurrently. Errors in the counter are raised,
    never swallowed, so a broken count cannot pass as a small one."""

    raise_error = True

    def __init__(self, *, clock) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._calls: dict[str, dict] = {}
        self._tools: dict[str, dict] = {}

    def _now(self) -> datetime:
        return check_utc(self._clock.now(), "callback time")

    def _start_call(self, serialized, run_id, metadata, kwargs) -> None:
        metadata = metadata or {}
        params = kwargs.get("invocation_params") or {}
        model = params.get("model") or params.get("model_name") or metadata.get("ls_model_name") or \
            (serialized or {}).get("name")
        with self._lock:
            self._calls.setdefault(str(run_id), {
                "node": _agent(metadata), "model": model, "started_at": self._now(),
                "ended_at": None, "input_tokens": None, "output_tokens": None, "error": None})

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs) -> None:
        self._start_call(serialized, run_id, metadata, kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs) -> None:
        self._start_call(serialized, run_id, metadata, kwargs)

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        tokens_in, tokens_out = _reported_usage(response)
        with self._lock:
            call = self._calls.get(str(run_id))
            if call is not None and call["ended_at"] is None:
                call.update(ended_at=self._now(), input_tokens=tokens_in, output_tokens=tokens_out)

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        with self._lock:
            call = self._calls.get(str(run_id))
            if call is not None and call["ended_at"] is None:
                call.update(ended_at=self._now(), error=type(error).__name__)

    def on_tool_start(self, serialized, input_str, *, run_id, metadata=None, **kwargs) -> None:
        with self._lock:
            self._tools.setdefault(str(run_id), {
                "node": _agent(metadata), "name": (serialized or {}).get("name") or "unknown",
                "input_sha256": hashlib.sha256(str(input_str).encode("utf-8")).hexdigest(),
                "result_chars": None, "started_at": self._now(), "ended_at": None, "error": None})

    def on_tool_end(self, output, *, run_id, **kwargs) -> None:
        with self._lock:
            tool = self._tools.get(str(run_id))
            if tool is not None and tool["ended_at"] is None:
                content = getattr(output, "content", output)
                tool.update(ended_at=self._now(), result_chars=len(str(content)))

    def on_tool_error(self, error, *, run_id, **kwargs) -> None:
        with self._lock:
            tool = self._tools.get(str(run_id))
            if tool is not None and tool["ended_at"] is None:
                tool.update(ended_at=self._now(), error=type(error).__name__)

    def calls(self) -> tuple[LlmCall, ...]:
        with self._lock:
            return tuple(LlmCall(rid, **values) for rid, values in self._calls.items())

    def tools(self) -> tuple[ToolCall, ...]:
        with self._lock:
            return tuple(ToolCall(rid, **values) for rid, values in self._tools.items())

    def summary(self) -> UsageSummary:
        calls, tools = self.calls(), self.tools()
        warnings = []
        known = all(c.input_tokens is not None and c.output_tokens is not None for c in calls)
        if calls and not known:
            missing = sum(c.input_tokens is None or c.output_tokens is None for c in calls)
            warnings.append(f"token usage unknown for {missing} of {len(calls)} requests")
        unfinished = sum(c.ended_at is None for c in calls) + sum(t.ended_at is None for t in tools)
        if unfinished:
            warnings.append(f"{unfinished} calls did not finish")
        failed = sum(c.error is not None for c in calls)
        if failed:
            warnings.append(f"{failed} model requests failed")
        per_agent: dict[str, int] = {}
        for call in calls:
            per_agent[call.node or "unattributed"] = per_agent.get(call.node or "unattributed", 0) + 1
        return UsageSummary(len(calls), sum(c.input_tokens for c in calls) if known else None,
                            sum(c.output_tokens for c in calls) if known else None, len(tools),
                            tuple(sorted(per_agent.items())), tuple(warnings))


__all__ = ["LlmCall", "ToolCall", "UsageCounter", "UsageSummary"]
