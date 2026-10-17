"""Risk decision contracts (docs/tasks/M3-08.md; filled in by the risk checks, M3-11).

A RiskDecision is APPROVE, REJECT or REDUCE; only a REDUCE carries the reduced
quantity, which becomes a new intent version (Law 12). NotRun records a check
that was never executed, with its reason; it is never shown or counted as a
pass or a failure (Codex M3 review B3).
"""

import functools
from dataclasses import dataclass
from datetime import datetime
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from enum import StrEnum

from investment_engine.lineage.records import register
from investment_engine.market.availability import check_utc
from investment_engine.policy.decisions import CheckResult


def calculation_context() -> Context:
    """A fresh, fully specified decimal context for sizing and risk (M3-11 rule 4; Codex M3 review B6)."""
    return Context(prec=34, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def exact(fn):
    """Run `fn` in a fresh calculation context: every Decimal operation inside it, unqualified `quantize`, `sum` and
    reason formatting included, ignores the caller's precision, rounding and traps, and the caller's context is
    left untouched."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with localcontext(calculation_context()):
            return fn(*args, **kwargs)
    return run


class RiskOutcome(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REDUCE = "REDUCE"


@dataclass(frozen=True)
class RiskDecision:
    intent_id: str
    intent_version: int
    outcome: RiskOutcome
    checks: tuple[CheckResult, ...]
    risk_version: str
    snapshot_id: str
    reduced_quantity: Decimal | None  # only for REDUCE
    decided_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", RiskOutcome(self.outcome))
        object.__setattr__(self, "checks", tuple(self.checks))
        check_utc(self.decided_at, "decided_at")
        if (self.outcome is RiskOutcome.REDUCE) != (self.reduced_quantity is not None):
            raise ValueError("a reduced quantity is set exactly for a REDUCE outcome")
        if self.reduced_quantity is not None and (
                not isinstance(self.reduced_quantity, Decimal) or self.reduced_quantity <= 0
                or self.reduced_quantity != self.reduced_quantity.to_integral_value()):
            raise ValueError("a reduced quantity is a positive whole number of shares")


@dataclass(frozen=True)
class NotRun:
    """A check stage that was not executed, and why."""

    stage: str  # "policy" or "risk"
    reason: str

    def __post_init__(self) -> None:
        if self.stage not in ("policy", "risk"):
            raise ValueError("NotRun is for the policy or risk stage")
        if not self.reason.strip():
            raise ValueError("NotRun needs a reason")


for _cls in (RiskOutcome, RiskDecision, NotRun):
    register(_cls)
