"""MarketView and the decision policy (Law 9; Part H; docs/tasks/M2-06.md).

Policy 0.1.0, deterministic and versioned. In order:
1. Law 9, stricter than its minimum: the view is ABSTAIN unless the instrument
   is applicable and every source required by any strategy has a health entry
   with status OK. DEGRADED abstains too, because holes distort indicators.
   The reason names every non-OK source.
2. An unavailable snapshot (holes, missing decision bar, adjustment) or
   unestablished coverage of a required action type abstains. Established
   coverage with no actions is valid.
3. Warm-up: if any strategy returns None, the view is ABSTAIN ("warm-up").
4. Combination: the first strategy (A1) sets the regime and the direction. A
   later strategy firing in the same direction raises the strength to the
   maximum of the two; one firing against A1 gives NEUTRAL with a consistency
   reason. NEUTRAL has strength 0.
`valid_until` is provisionally the close of the next session after T (OPEN-08
decides it by M3). `probability_up` is always None: strength is a scale, not a
probability.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from investment_engine.market.data_health import DataHealth, HealthStatus
from investment_engine.quant.adjusted import local_date
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import Direction, RuleStrategy, StrategySignal

HORIZON = "5 sessions"  # OPEN-09 provisional research horizon (owner, 2026-10-14)


class ViewDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class MarketView:  # Part H fields
    instrument_id: str
    direction: ViewDirection
    strength: float  # 0 – 1, not a probability; 0 when ABSTAIN or NEUTRAL
    probability_up: float | None  # always None for rule strategies
    horizon: str
    generated_at: datetime  # T
    valid_until: datetime
    regime: str | None  # A1's direction, as context
    data_health: DataHealth
    evidence_refs: tuple[str, ...]  # lineage id(s) (M2-07)
    policy_version: str
    abstain_reason: str  # "" unless ABSTAIN
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", ViewDirection(self.direction))
        if isinstance(self.strength, bool) or not isinstance(self.strength, float):
            raise TypeError("strength must be a float")
        if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"strength must be within [0, 1], not {self.strength}")
        if self.probability_up is not None:
            raise ValueError("rule-strategy views carry no probability (M9 calibrated models only)")
        if self.direction in (ViewDirection.ABSTAIN, ViewDirection.NEUTRAL) and self.strength != 0.0:
            raise ValueError(f"a {self.direction} view has zero strength")
        if (self.direction is ViewDirection.ABSTAIN) != bool(self.abstain_reason):
            raise ValueError("an ABSTAIN view needs a reason, and only an ABSTAIN view has one")
        if not self.valid_until > self.generated_at:
            raise ValueError("a view must be valid after it is generated")


def _check_slots(signals: Sequence[StrategySignal | None], strategies: Sequence[RuleStrategy]) -> None:
    if not strategies:
        raise ValueError("the policy needs at least one strategy")
    if len({(s.name, s.version) for s in strategies}) != len(strategies) or len({s.name for s in strategies}) != len(
            strategies):
        raise ValueError("strategies must be distinct")
    if len(signals) != len(strategies):
        raise ValueError(f"{len(signals)} signals for {len(strategies)} strategies: one slot per strategy")
    for sig, strategy in zip(signals, strategies, strict=True):
        if sig is None:
            continue
        if not isinstance(sig, StrategySignal):
            raise TypeError(f"expected a StrategySignal or None, not {type(sig).__name__}")
        if (sig.strategy, sig.strategy_version) != (strategy.name, strategy.version):
            raise ValueError(f"signal from {sig.strategy} {sig.strategy_version} in the slot of "
                             f"{strategy.name} {strategy.version}")


def _law9(snapshot: FeatureSnapshot, strategies: Sequence[RuleStrategy]) -> str:
    health = snapshot.data_health
    if not health.applicability.applicable:
        return f"instrument not applicable: {health.applicability.reason}"
    by_key = {s.source: s for s in health.sources}
    problems = []
    required = []
    for strategy in strategies:
        for key in strategy.required_sources:
            if key not in required:
                required.append(key)
    for key in required:
        entry = by_key.get(key)
        if entry is None:
            problems.append(f"{key.provider} {key.timeframe}: no health entry")
        elif entry.status is not HealthStatus.OK:
            problems.append(f"{key.provider} {key.timeframe}: {entry.status}"
                            + (f" ({entry.detail})" if entry.detail else ""))
    if problems:
        return "required data not OK: " + "; ".join(problems)
    coverage = snapshot.action_coverage
    for strategy in strategies:
        for action_type in strategy.required_actions:
            if not coverage.established or action_type not in coverage.types:
                return f"action coverage for {action_type} not established: {coverage.reason}"
    if snapshot.unavailable_reason:
        return f"snapshot unavailable: {snapshot.unavailable_reason}"
    return ""


def decide(strategy_signals: Sequence[StrategySignal | None], snapshot: FeatureSnapshot,
           strategies: Sequence[RuleStrategy], *, policy_version: str, calendar,
           evidence_refs: tuple[str, ...] = ()) -> MarketView:
    signals, strategies = tuple(strategy_signals), tuple(strategies)
    _check_slots(signals, strategies)
    health = snapshot.data_health
    if health.as_of != snapshot.as_of or health.instrument_id != snapshot.instrument_id:
        raise ValueError("the snapshot's DataHealth is for another time or instrument")
    at = snapshot.as_of
    valid_until = calendar.next_session(local_date(at, calendar)).close
    a1 = signals[0]
    regime = None if a1 is None else str(a1.direction)
    reasons = tuple(r for sig in signals if sig is not None for r in sig.reasons)

    def make(direction: ViewDirection, strength: float, abstain_reason: str = "", extra=()) -> MarketView:
        return MarketView(snapshot.instrument_id, direction, strength, None, HORIZON, at, valid_until, regime, health,
                          tuple(evidence_refs), policy_version, abstain_reason, reasons + tuple(extra))

    reason = _law9(snapshot, strategies)
    if reason:
        return make(ViewDirection.ABSTAIN, 0.0, reason)
    if any(sig is None for sig in signals):
        return make(ViewDirection.ABSTAIN, 0.0, "warm-up")

    direction, strength = a1.direction, a1.strength
    for sig, strategy in zip(signals[1:], strategies[1:], strict=True):
        if sig.direction is Direction.NEUTRAL:
            continue
        if direction is not Direction.NEUTRAL and sig.direction is not direction:
            return make(ViewDirection.NEUTRAL, 0.0,
                        extra=(f"consistency: {strategy.name} fired {sig.direction} against the {direction} regime",))
        if sig.direction is direction:
            strength = max(strength, sig.strength)
    if direction is Direction.NEUTRAL:
        return make(ViewDirection.NEUTRAL, 0.0)
    return make(ViewDirection(str(direction)), strength)
