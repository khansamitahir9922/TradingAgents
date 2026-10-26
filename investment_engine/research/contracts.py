"""Immutable research records (M6-01; ADR-001; architecture Part H).

Research is advisory, untrusted evidence (Law 4). Nothing here converts to an
order, a limit, a size or a probability. These records import no LangChain or
TradingAgents code, so any process can decode them; the Research Worker's
adapter converts its own run output into them.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from investment_engine.ledger.contracts import identity
from investment_engine.lineage.records import register
from investment_engine.market.availability import check_instrument_id, check_name, check_utc

MAX_TEXT = 1_000_000  # characters per captured text; longer text is cut explicitly, never silently
UNTRUSTED_LABEL = "LLM suggestion: not a price used by the system"
TEXT_ROLES = frozenset({"prompt", "response", "tool_input", "tool_output"})


def _content(record, *, exclude=()):
    return {f.name: getattr(record, f.name) for f in fields(record) if f.init and f.name not in exclude}


def _date(value, what):
    if type(value) is not date:
        raise TypeError(f"{what} must be a date, not {type(value).__name__}")
    return value


def _count(value, what, *, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{what} must be a {'positive' if positive else 'nonnegative'} integer")
    return value


def _optional_count(value, what):
    return None if value is None else _count(value, what)


def _optional_text(value, what):
    return None if value is None else check_name(value, what)


class Rating(StrEnum):
    """Upstream's 5-tier Portfolio Manager rating, mirrored (no upstream import)."""
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(StrEnum):
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class JobState(StrEnum):
    REQUESTED = "REQUESTED"
    CLAIMED = "CLAIMED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BUDGET_REFUSED = "BUDGET_REFUSED"
    EXPIRED_UNCLAIMED = "EXPIRED_UNCLAIMED"


class RunOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ContextSource(StrEnum):
    TYPED = "TYPED"  # from the parsed PortfolioDecision / TraderProposal (upstream change U1)
    FREE_TEXT_FALLBACK = "FREE_TEXT_FALLBACK"  # upstream's own text rating parser


JOB_EDGES: dict[JobState | None, frozenset[JobState]] = {
    None: frozenset({JobState.REQUESTED}),
    JobState.REQUESTED: frozenset({JobState.CLAIMED, JobState.EXPIRED_UNCLAIMED}),
    # CLAIMED -> CLAIMED: a new lease after the previous one expired (a crashed run).
    JobState.CLAIMED: frozenset({JobState.CLAIMED, JobState.SUCCEEDED, JobState.FAILED, JobState.BUDGET_REFUSED}),
}


def check_job_edge(current: JobState | None, target: JobState) -> None:
    if JobState(target) not in JOB_EDGES.get(current, frozenset()):
        raise ValueError(f"research job edge {current} -> {target} is not allowed")


@dataclass(frozen=True)
class ResearchSettings:
    """Everything that shapes a run, frozen at request time. Retries are not a setting:
    the adapter pins upstream llm_max_retries to 0 (C4)."""
    provider: str
    quick_model: str
    deep_model: str
    max_debate_rounds: int
    max_risk_rounds: int
    analysts: tuple[str, ...]
    temperature: Decimal | None
    output_language: str

    def __post_init__(self) -> None:
        for name in ("provider", "quick_model", "deep_model", "output_language"):
            check_name(getattr(self, name), name)
        _count(self.max_debate_rounds, "max_debate_rounds", positive=True)
        _count(self.max_risk_rounds, "max_risk_rounds", positive=True)
        object.__setattr__(self, "analysts", tuple(self.analysts))
        if not self.analysts or len(set(self.analysts)) != len(self.analysts):
            raise ValueError("analysts must be a nonempty list without duplicates")
        for analyst in self.analysts:
            check_name(analyst, "analyst")
        if self.temperature is not None and (not isinstance(self.temperature, Decimal) or not self.temperature.is_finite()):
            raise TypeError("temperature must be a finite Decimal or None")

    @property
    def settings_hash(self) -> str:
        return identity(_content(self))


@dataclass(frozen=True)
class ResearchJob:
    instrument_id: str
    ticker: str
    research_date: date
    requested_by: str
    requested_at: datetime  # command time: a separate request is a separate job
    reason: str
    settings: ResearchSettings

    def __post_init__(self) -> None:
        check_instrument_id(self.instrument_id)
        check_name(self.ticker, "ticker")
        _date(self.research_date, "research_date")
        check_name(self.requested_by, "requested_by")
        check_utc(self.requested_at, "requested_at")
        check_name(self.reason, "reason")
        if not isinstance(self.settings, ResearchSettings):
            raise TypeError("ResearchSettings required")

    @property
    def job_id(self) -> str:
        """The request's identity; the free-text reason is provenance, not identity."""
        return "rjb-" + identity((self.instrument_id, self.ticker, self.research_date, self.requested_by,
                                  self.requested_at, self.settings.settings_hash))


@dataclass(frozen=True)
class JobVersion:
    job_id: str
    version: int
    state: JobState
    at: datetime
    actor: str  # operator ID for REQUESTED, worker ID afterwards
    lease_until: datetime | None
    run_id: str | None
    reason: str

    def __post_init__(self) -> None:
        check_name(self.job_id, "job_id")
        _count(self.version, "version", positive=True)
        object.__setattr__(self, "state", JobState(self.state))
        check_utc(self.at, "at")
        check_name(self.actor, "actor")
        if (self.state is JobState.CLAIMED) != (self.lease_until is not None):
            raise ValueError("exactly a CLAIMED version carries a lease")
        if self.lease_until is not None and check_utc(self.lease_until, "lease_until") <= self.at:
            raise ValueError("a lease must end after it starts")
        _optional_text(self.run_id, "run_id")
        check_name(self.reason, "reason")


@dataclass(frozen=True)
class CallRecord:
    call_id: str
    node: str | None
    model: str | None
    started_at: datetime
    ended_at: datetime | None
    input_tokens: int | None  # None: the provider did not report it
    output_tokens: int | None
    error: str | None

    def __post_init__(self) -> None:
        check_name(self.call_id, "call_id")
        _optional_text(self.node, "node")
        _optional_text(self.model, "model")
        check_utc(self.started_at, "started_at")
        if self.ended_at is not None and check_utc(self.ended_at, "ended_at") < self.started_at:
            raise ValueError("a call cannot end before it starts")
        _optional_count(self.input_tokens, "input_tokens")
        _optional_count(self.output_tokens, "output_tokens")
        _optional_text(self.error, "error")


@dataclass(frozen=True)
class ToolRecord:
    call_id: str
    node: str | None
    name: str
    input_sha256: str
    result_chars: int | None
    started_at: datetime
    ended_at: datetime | None
    error: str | None

    def __post_init__(self) -> None:
        check_name(self.call_id, "call_id")
        _optional_text(self.node, "node")
        check_name(self.name, "name")
        if len(self.input_sha256) != 64:
            raise ValueError("input_sha256 must be a SHA-256 hex digest")
        _optional_count(self.result_chars, "result_chars")
        check_utc(self.started_at, "started_at")
        if self.ended_at is not None and check_utc(self.ended_at, "ended_at") < self.started_at:
            raise ValueError("a call cannot end before it starts")
        _optional_text(self.error, "error")


@dataclass(frozen=True)
class UsageTotals:
    requests: int
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: int

    def __post_init__(self) -> None:
        _count(self.requests, "requests")
        _optional_count(self.input_tokens, "input_tokens")
        _optional_count(self.output_tokens, "output_tokens")
        _count(self.tool_calls, "tool_calls")

    @classmethod
    def of(cls, calls, tool_calls: int) -> UsageTotals:
        known = all(c.input_tokens is not None and c.output_tokens is not None for c in calls)
        return cls(len(calls), sum(c.input_tokens for c in calls) if known else None,
                   sum(c.output_tokens for c in calls) if known else None, tool_calls)


@dataclass(frozen=True)
class CapturedText:
    """One prompt, response or tool payload, stored verbatim as untrusted text."""
    call_id: str
    node: str | None
    role: str
    text: str
    truncated_chars: int  # characters cut beyond MAX_TEXT, recorded rather than hidden

    def __post_init__(self) -> None:
        check_name(self.call_id, "call_id")
        _optional_text(self.node, "node")
        if self.role not in TEXT_ROLES:
            raise ValueError(f"role must be one of {sorted(TEXT_ROLES)}")
        if not isinstance(self.text, str) or len(self.text) > MAX_TEXT:
            raise ValueError(f"captured text must be a string of at most {MAX_TEXT} characters")
        _count(self.truncated_chars, "truncated_chars")


@dataclass(frozen=True)
class DataSourceRef:
    vendor: str
    method: str
    fetched_at: datetime
    args_sha256: str

    def __post_init__(self) -> None:
        check_name(self.vendor, "vendor")
        check_name(self.method, "method")
        check_utc(self.fetched_at, "fetched_at")
        if len(self.args_sha256) != 64:
            raise ValueError("args_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True)
class ResearchRecord:
    """Everything needed to reconstruct a run (not reproduce it: LLM output varies)."""
    job_id: str
    attempt: int
    settings: ResearchSettings
    upstream_version: str
    code_version: str
    calls: tuple[CallRecord, ...]
    tools: tuple[ToolRecord, ...]
    texts: tuple[CapturedText, ...]
    data_sources: tuple[DataSourceRef, ...]
    final_state_json: str
    usage: UsageTotals
    warnings: tuple[str, ...]
    started_at: datetime
    finished_at: datetime
    outcome: RunOutcome
    failure: str | None
    effective_config_json: str = "{}"  # the upstream configuration actually used (Codex M6 review B4)

    def __post_init__(self) -> None:
        check_name(self.job_id, "job_id")
        _count(self.attempt, "attempt", positive=True)
        if not isinstance(self.effective_config_json, str) or len(self.effective_config_json) > MAX_TEXT:
            raise ValueError("effective_config_json must be bounded text")
        if not isinstance(self.settings, ResearchSettings):
            raise TypeError("ResearchSettings required")
        check_name(self.upstream_version, "upstream_version")
        check_name(self.code_version, "code_version")
        for name, kind in (("calls", CallRecord), ("tools", ToolRecord), ("texts", CapturedText),
                           ("data_sources", DataSourceRef)):
            object.__setattr__(self, name, tuple(getattr(self, name)))
            if not all(isinstance(v, kind) for v in getattr(self, name)):
                raise TypeError(f"{name} must hold {kind.__name__} records")
        if not isinstance(self.final_state_json, str) or len(self.final_state_json) > 10 * MAX_TEXT:
            raise ValueError("final_state_json must be bounded text")
        if not isinstance(self.usage, UsageTotals):
            raise TypeError("UsageTotals required")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        for warning in self.warnings:
            check_name(warning, "warning")
        if check_utc(self.finished_at, "finished_at") < check_utc(self.started_at, "started_at"):
            raise ValueError("a run cannot finish before it starts")
        object.__setattr__(self, "outcome", RunOutcome(self.outcome))
        if (self.outcome is RunOutcome.FAILED) != (self.failure is not None):
            raise ValueError("exactly a FAILED run records its failure")
        _optional_text(self.failure, "failure")

    @property
    def run_id(self) -> str:
        return "rrn-" + identity((self.job_id, self.attempt))


@dataclass(frozen=True)
class UntrustedLevels:
    """LLM-suggested levels: display only. Deliberately offers no conversion to any order type."""
    entry: Decimal | None
    stop: Decimal | None

    def __post_init__(self) -> None:
        for name in ("entry", "stop"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value <= 0):
                raise ValueError(f"{name} must be a positive finite Decimal or None")

    @property
    def label(self) -> str:
        return UNTRUSTED_LABEL


@dataclass(frozen=True)
class ResearchContext:
    run_id: str
    instrument_id: str
    rating: Rating
    trader_action: TraderAction | None
    suggested_levels: UntrustedLevels
    horizon_sessions: int
    generated_at: datetime
    valid_until: datetime
    warnings: tuple[str, ...]
    source: ContextSource

    def __post_init__(self) -> None:
        check_name(self.run_id, "run_id")
        check_instrument_id(self.instrument_id)
        object.__setattr__(self, "rating", Rating(self.rating))
        if self.trader_action is not None:
            object.__setattr__(self, "trader_action", TraderAction(self.trader_action))
        if not isinstance(self.suggested_levels, UntrustedLevels):
            raise TypeError("UntrustedLevels required")
        _count(self.horizon_sessions, "horizon_sessions", positive=True)
        if check_utc(self.valid_until, "valid_until") <= check_utc(self.generated_at, "generated_at"):
            raise ValueError("research must be valid for some time after it is generated")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        for warning in self.warnings:
            check_name(warning, "warning")
        object.__setattr__(self, "source", ContextSource(self.source))

    def status(self, at: datetime) -> str:
        if check_utc(at, "at") < self.generated_at:
            raise ValueError("research cannot be assessed before it was generated")
        return "VALID" if at < self.valid_until else "EXPIRED"


@dataclass(frozen=True)
class BudgetPolicy:
    """Daily caps (D46), versioned; set only by a current Admin (M6-06)."""
    version: int
    daily_requests: int
    daily_tokens: int
    daily_usd: Decimal | None
    reserve_requests: int  # per-run reservation before measured usage replaces it
    reserve_tokens: int
    set_by: str
    set_at: datetime
    reason: str

    def __post_init__(self) -> None:
        _count(self.version, "version", positive=True)
        for name in ("daily_requests", "daily_tokens", "reserve_requests", "reserve_tokens"):
            _count(getattr(self, name), name, positive=True)
        if self.daily_usd is not None and (not isinstance(self.daily_usd, Decimal) or not self.daily_usd.is_finite()
                                           or self.daily_usd < 0):
            raise ValueError("daily_usd must be a nonnegative finite Decimal or None")
        check_name(self.set_by, "set_by")
        check_utc(self.set_at, "set_at")
        check_name(self.reason, "reason")


@dataclass(frozen=True)
class BudgetUsage:
    day: date  # UTC day
    run_id: str
    kind: str  # RESERVED before a run, ACTUAL after it
    requests: int
    tokens: int
    usd: Decimal | None
    at: datetime

    def __post_init__(self) -> None:
        _date(self.day, "day")
        check_name(self.run_id, "run_id")
        if self.kind not in ("RESERVED", "ACTUAL"):
            raise ValueError("budget usage kind must be RESERVED or ACTUAL")
        _count(self.requests, "requests")
        _count(self.tokens, "tokens")
        if self.usd is not None and (not isinstance(self.usd, Decimal) or not self.usd.is_finite() or self.usd < 0):
            raise ValueError("usd must be a nonnegative finite Decimal or None")
        check_utc(self.at, "at")


for _type in (Rating, TraderAction, JobState, RunOutcome, ContextSource, ResearchSettings, ResearchJob, JobVersion,
              CallRecord, ToolRecord, UsageTotals, CapturedText, DataSourceRef, ResearchRecord, UntrustedLevels,
              ResearchContext, BudgetPolicy, BudgetUsage):
    register(_type)
