"""Capture every prompt, response and tool payload of a run as untrusted text (M6-04).

Texts are kept verbatim apart from two explicit edits: the loaded secrets are
replaced by a marker, and anything beyond MAX_TEXT characters is cut with the
cut length recorded. Nothing is parsed or acted on here.
"""

from __future__ import annotations

import json
import threading

from langchain_core.callbacks import BaseCallbackHandler

from investment_engine.research.contracts import MAX_TEXT, CapturedText
from investment_engine.research.usage import _agent

REDACTED = "[REDACTED SECRET]"


class Redactor:
    def __init__(self, secrets=()) -> None:
        # Longest first, so a secret containing another is replaced whole.
        self._secrets = tuple(sorted({s for s in secrets if isinstance(s, str) and len(s) >= 4}, key=len, reverse=True))

    def __call__(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text


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
