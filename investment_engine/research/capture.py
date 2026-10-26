"""Capture every prompt, response and tool payload of a run as untrusted text (M6-04).

Texts are kept verbatim apart from two explicit edits: the loaded secrets are
replaced by a marker, and anything beyond MAX_TEXT characters is cut with the
cut length recorded. Nothing is parsed or acted on here.
"""

from __future__ import annotations

import json
import re
import threading

from langchain_core.callbacks import BaseCallbackHandler

from investment_engine.research.contracts import MAX_TEXT, CapturedText
from investment_engine.research.usage import _agent

REDACTED = "[REDACTED SECRET]"


class Redactor:
    """Replaces every configured secret, and its JSON-escaped forms, in one pass.

    One regular-expression pass (longest alternative first) means a replacement
    marker is never itself matched again, however short a secret is. Escaped forms
    cover text that was serialized before it reached the redactor.
    """

    def __init__(self, secrets=()) -> None:
        forms = set()
        for secret in secrets:
            if isinstance(secret, str) and secret:
                forms |= {secret, json.dumps(secret)[1:-1], json.dumps(secret, ensure_ascii=False)[1:-1]}
        ordered = sorted(forms, key=len, reverse=True)
        self._pattern = re.compile("|".join(re.escape(f) for f in ordered)) if ordered else None

    def __call__(self, text: str) -> str:
        return text if self._pattern is None else self._pattern.sub(REDACTED, text)

    def deep(self, value):
        """A copy of plain JSON-like data (str, dict, list, tuple) with every string redacted."""
        if isinstance(value, str):
            return self(value)
        if isinstance(value, dict):
            return {self.deep(k): self.deep(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return type(value)(self.deep(v) for v in value)
        return value


def _message_text(message) -> str:
    content = getattr(message, "content", message)
    parts = [f"[{getattr(message, 'type', 'message')}] " + (content if isinstance(content, str)
                                                             else json.dumps(content, default=str, sort_keys=True))]
    calls = getattr(message, "tool_calls", None)
    if calls:
        parts.append("[tool_calls] " + json.dumps(calls, default=str, sort_keys=True))
    return "\n".join(parts)


class TextCapture(BaseCallbackHandler):
    raise_error = True  # a capture failure must surface, never leave a silently incomplete record

    def __init__(self, *, redact: Redactor) -> None:
        self._redact = redact
        self._lock = threading.Lock()
        self._texts: list[CapturedText] = []
        self._seen: set[tuple[str, str]] = set()

    def _add(self, run_id, metadata, role: str, text: str) -> None:
        key = (str(run_id), role)
        text = self._redact(text)
        cut = max(0, len(text) - MAX_TEXT)
        with self._lock:
            if key in self._seen:  # the same handler attached at model and graph level
                return
            self._seen.add(key)
            self._texts.append(CapturedText(str(run_id), _agent(metadata), role, text[:MAX_TEXT], cut))

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs) -> None:
        self._add(run_id, metadata, "prompt", "\n\n".join(_message_text(m) for batch in messages for m in batch))

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs) -> None:
        self._add(run_id, metadata, "prompt", "\n\n".join(prompts))

    def on_llm_end(self, response, *, run_id, metadata=None, **kwargs) -> None:
        texts = [_message_text(g.message) if getattr(g, "message", None) is not None else g.text
                 for generations in response.generations for g in generations]
        self._add(run_id, metadata, "response", "\n\n".join(texts))

    def on_tool_start(self, serialized, input_str, *, run_id, metadata=None, **kwargs) -> None:
        self._add(run_id, metadata, "tool_input", f"[{(serialized or {}).get('name', 'tool')}] {input_str}")

    def on_tool_end(self, output, *, run_id, metadata=None, **kwargs) -> None:
        self._add(run_id, metadata, "tool_output", str(getattr(output, "content", output)))

    def texts(self) -> tuple[CapturedText, ...]:
        with self._lock:
            return tuple(self._texts)


__all__ = ["REDACTED", "Redactor", "TextCapture"]
