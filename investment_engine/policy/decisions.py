"""Policy decision contracts (docs/tasks/M3-08.md; filled in by the policy checks, M3-10).

Defined with the intent contract so the intent store (M3-09) can hold them. A
CheckResult always carries a reason, also when it passed. Registered with the
canonical codec, so decisions are stored, hashed and audited exactly.
"""

from dataclasses import dataclass
from datetime import datetime

from investment_engine.lineage.records import register
from investment_engine.market.availability import check_utc


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    reason: str  # always set, also when passed

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("a check needs a name")
        if not isinstance(self.passed, bool):
            raise TypeError("passed is a bool")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError(f"check {self.name} needs a reason, also when it passed")


@dataclass(frozen=True)
class PolicyDecision:
    intent_id: str
    intent_version: int
    passed: bool
    checks: tuple[CheckResult, ...]
    policy_version: str
    autonomy_level: int
    decided_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        check_utc(self.decided_at, "decided_at")
        if self.passed != all(c.passed for c in self.checks):
            raise ValueError("a policy decision passes exactly when every check passes")


register(CheckResult)
register(PolicyDecision)
