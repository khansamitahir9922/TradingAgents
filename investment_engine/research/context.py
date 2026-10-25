"""Build a ResearchContext from one run's typed output (M6-05; D51, D53).

The rating comes from the parsed Portfolio Manager decision (upstream change U1).
Without it, the rating upstream itself parsed from the decision text is used and
labelled a free-text fallback. Levels come only from the parsed Trader proposal
and are untrusted. Report text is never read for fields: an instruction inside a
report changes nothing here.
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from investment_engine.market.availability import check_utc
from investment_engine.research.contracts import (
    ContextSource,
    Rating,
    ResearchContext,
    RunOutcome,
    TraderAction,
    UntrustedLevels,
)

HORIZON_SESSIONS = 5  # D51: M2's five-session prediction horizon
REPORT_KEYS = ("market_report", "sentiment_report", "news_report", "fundamentals_report")


class NoResearchContext(ValueError):
    """The run produced nothing usable; the job is recorded as FAILED with this reason."""


def valid_until(generated_at: datetime, *, calendar, sessions: int = HORIZON_SESSIONS) -> datetime:
    """The close of the `sessions`-th session that opens after `generated_at`."""
    generated_at = check_utc(generated_at, "generated_at")
    day = generated_at.astimezone(ZoneInfo(calendar.timezone)).date()
    current = calendar.session(day) if calendar.is_session(day) and calendar.session(day).open > generated_at \
        else calendar.next_session(day)
    for _ in range(sessions - 1):
        current = calendar.next_session(current.date)
    return current.close


def _level(value, name: str, warnings: list[str]) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        warnings.append(f"suggested {name} is not a number and was dropped")
        return None
    if isinstance(value, float) and not math.isfinite(value):
        warnings.append(f"suggested {name} is not finite and was dropped")
        return None
    try:
        level = Decimal(str(value))  # the exact decimal form the model wrote, not the binary float
    except InvalidOperation:
        warnings.append(f"suggested {name} could not be read and was dropped")
        return None
    if level <= 0:
        warnings.append(f"suggested {name} is not positive and was dropped")
        return None
    return level


def _rating(value) -> Rating | None:
    try:
        return Rating(value)
    except ValueError:
        return None


def build_context(output, *, instrument_id: str, calendar, override_until: datetime | None = None) -> ResearchContext:
    record, state = output.record, output.final_state
    if record.outcome is not RunOutcome.SUCCEEDED or state is None:
        raise NoResearchContext("the run failed; it has no research context")
    warnings: list[str] = []
    decision = state.get("final_decision_structured")
    if isinstance(decision, dict) and _rating(decision.get("rating")) is not None:
        rating, source = _rating(decision["rating"]), ContextSource.TYPED
    else:
        rating, source = _rating(state.get("final_rating")), ContextSource.FREE_TEXT_FALLBACK
        if rating is None:
            raise NoResearchContext("no rating: neither a typed decision nor a parsed 5-tier rating")
        warnings.append("rating read from upstream's free-text parser, not a typed decision")
    proposal = state.get("trader_proposal_structured")
    action, entry, stop = None, None, None
    if isinstance(proposal, dict):
        try:
            action = TraderAction(proposal.get("action"))
        except ValueError:
            warnings.append("trader action is not Buy/Hold/Sell and was dropped")
        entry = _level(proposal.get("entry_price"), "entry", warnings)
        stop = _level(proposal.get("stop_loss"), "stop", warnings)
    else:
        warnings.append("no typed trader proposal: action and levels unavailable")
    for key in REPORT_KEYS:
        if key in state and not str(state.get(key) or "").strip():
            warnings.append(f"{key} empty")
    failed_tools = sorted({t.name for t in record.tools if t.error})
    if failed_tools:
        warnings.append("tool errors: " + ", ".join(failed_tools))
    if record.usage.input_tokens is None:
        warnings.append("token usage unknown")
    warnings.extend(w for w in record.warnings if w not in warnings)
    generated = record.finished_at
    until = valid_until(generated, calendar=calendar)
    if override_until is not None:
        if check_utc(override_until, "override_until") > until:
            raise ValueError("a validity override can only shorten the default validity")
        until = override_until
    return ResearchContext(record.run_id, instrument_id, rating, action, UntrustedLevels(entry, stop),
                           HORIZON_SESSIONS, generated, until, tuple(dict.fromkeys(warnings)), source)


__all__ = ["HORIZON_SESSIONS", "NoResearchContext", "build_context", "valid_until"]
