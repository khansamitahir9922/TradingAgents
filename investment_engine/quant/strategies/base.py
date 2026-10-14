"""The rule-strategy interface (Law 9; Part H; docs/tasks/M2-04.md).

A strategy states what it needs (required sources, actions and features) and
what it returns: a direction and a strength in [0, 1]. Strength is a
documented per-strategy scale, never a probability; `probability_up` exists
only for calibrated models (M9). ABSTAIN is the policy's decision (M2-06),
never a strategy's. Strategies are pure functions of the snapshot: no hidden
state, randomness or clock reads, and they read features only through
declared_snapshot(), whose values mapping refuses any undeclared key.
"""

import math
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, runtime_checkable

from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import SourceKey
from investment_engine.quant.features import FeatureDefinition
from investment_engine.quant.snapshot import FeatureSnapshot

_VERSION = re.compile(r"\d+\.\d+\.\d+")


class Direction(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class UndeclaredFeature(KeyError):
    """A strategy read, or declared, a feature the snapshot doesn't provide as declared."""


def _text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{what} must be non-empty text, not {value!r}")
    return value


@dataclass(frozen=True)
class StrategySignal:
    strategy: str
    strategy_version: str
    direction: Direction
    strength: float  # 0 – 1; NOT a probability (Part H; design principles §6.4)
    reasons: tuple[str, ...]  # plain-language, from the rule that fired
    feature_keys: tuple[str, ...]  # exactly the features read

    def __post_init__(self) -> None:
        _text(self.strategy, "strategy")
        if not isinstance(self.strategy_version, str) or not _VERSION.fullmatch(self.strategy_version):
            raise ValueError(f"strategy_version must be semantic, not {self.strategy_version!r}")
        object.__setattr__(self, "direction", Direction(self.direction))
        if isinstance(self.strength, bool) or not isinstance(self.strength, float):
            raise TypeError(f"strength must be a float, not {type(self.strength).__name__}")
        if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"strength must be within [0, 1], not {self.strength}")
        for name in ("reasons", "feature_keys"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple")
            for item in value:
                _text(item, name)
        if not self.feature_keys:
            raise ValueError("a signal names the features it read")


@runtime_checkable
class RuleStrategy(Protocol):
    name: str
    version: str
    required_sources: tuple[SourceKey, ...]  # Law 9: e.g. (yfinance D1,)
    required_actions: tuple[ActionType, ...]  # e.g. (SPLIT,) for the adjusted view
    features: tuple[FeatureDefinition, ...]

    def evaluate(self, snapshot: FeatureSnapshot) -> StrategySignal | None:  # None while any feature warms up
        ...


class _DeclaredValues(Mapping):
    """A read-only mapping exposing only the declared feature keys; any other key raises."""

    def __init__(self, values: Mapping[str, float | None], keys: Sequence[str]) -> None:
        self._values = {k: values[k] for k in keys}

    def __getitem__(self, key: str) -> float | None:
        if key not in self._values:
            raise UndeclaredFeature(f"feature {key} was not declared by this strategy")
        return self._values[key]

    def get(self, key, default=None):  # an undeclared read raises; it never quietly returns a default
        return self[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _DeclaredValues) and self._values == other._values

    __hash__ = None


def declared_snapshot(snapshot: FeatureSnapshot, definitions: Sequence[FeatureDefinition]) -> FeatureSnapshot:
    """An immutable copy of `snapshot` whose values expose only `definitions`' keys."""
    keys = []
    for d in definitions:
        if not isinstance(d, FeatureDefinition):
            raise TypeError(f"definitions must be FeatureDefinitions, not {type(d).__name__}")
        if d.key not in snapshot.values:
            raise UndeclaredFeature(f"the snapshot has no feature {d.key}")
        if snapshot.feature_versions.get(d.key) != d.version:
            raise ValueError(f"the snapshot computed {d.key} at version {snapshot.feature_versions.get(d.key)}, "
                             f"not {d.version}")
        if d.input_basis is not snapshot.adjusted_basis:
            raise ValueError(f"{d.key} reads {d.input_basis}, the snapshot holds {snapshot.adjusted_basis}")
        keys.append(d.key)
    return replace(snapshot, values=_DeclaredValues(snapshot.values, keys))
