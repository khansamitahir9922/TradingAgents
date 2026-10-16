"""Versioned policy rules (architecture Part F "Policy rules (versioned)"; docs/tasks/M3-06.md).

One account's restricted list (D8) and its order-shape rules: regular session
only, LIMIT orders, DAY time-in-force (D7), the limit band around the
reference price (D13) and the view timeframes allowed (D12: daily only;
hourly isn't decided, so it's refused). Set-valued fields are sorted,
de-duplicated tuples, so the M2-07 codec encodes them without change and the
same rules always give the same bytes (Codex M3 review B2).
"""

from dataclasses import dataclass
from decimal import Decimal

from investment_engine.lineage.records import register

SESSIONS = ("REGULAR_ONLY",)
ORDER_TYPES = ("LIMIT",)
TIMES_IN_FORCE = ("DAY",)
TIMEFRAMES = ("D1",)  # D12: hourly views are refused until decided


def sorted_unique(values, what: str) -> tuple[str, ...]:
    items = tuple(values)
    if any(not isinstance(v, str) or not v.strip() for v in items):
        raise ValueError(f"{what} holds non-empty text only")
    return tuple(sorted(set(items)))


def fraction(value: object, name: str, *, upper: Decimal = Decimal(1)) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite() or not Decimal(0) < value <= upper:
        raise ValueError(f"{name} must be in (0, {upper}], not {value}")
    return value


@dataclass(frozen=True)
class PolicyRules:
    version: str  # "policy-<n>" per account, assigned on publish
    restricted: tuple[str, ...]  # D8: instrument ids
    session: str  # D7
    order_type: str  # D7, D13
    time_in_force: str  # D7
    limit_band_fraction: Decimal  # D13
    view_timeframes: tuple[str, ...]  # D12

    def __post_init__(self) -> None:
        object.__setattr__(self, "restricted", sorted_unique(self.restricted, "restricted"))
        object.__setattr__(self, "view_timeframes", sorted_unique(self.view_timeframes, "view_timeframes"))
        for name, allowed in (("session", SESSIONS), ("order_type", ORDER_TYPES), ("time_in_force", TIMES_IN_FORCE)):
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name} must be one of {allowed} in v1, not {getattr(self, name)!r}")
        fraction(self.limit_band_fraction, "limit_band_fraction")
        unsupported = [t for t in self.view_timeframes if t not in TIMEFRAMES]
        if unsupported or not self.view_timeframes:
            raise ValueError(f"view timeframes must be {TIMEFRAMES} in v1; {unsupported or 'none'} refused "
                             "(D12: hourly isn't decided)")


register(PolicyRules)
