"""The rule-strategy interface (Law 9; Part H; docs/tasks/M2-04.md).

A strategy declares its required sources, actions and features, reads only
its declared features through a guarded snapshot, and returns a direction and
a strength in [0, 1] that is never a probability, or None during warm-up.
"""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType

import pytest

from investment_engine.market.candles import Timeframe
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import Applicability, DataHealth, SourceKey
from investment_engine.quant.adjusted import AdjustedBasis, VerificationEvidence, establish_coverage
from investment_engine.quant.features import FeatureDefinition
from investment_engine.quant.indicators import RSI14, SMA50, SMA200
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import (
    Direction,
    RuleStrategy,
    StrategySignal,
    UndeclaredFeature,
    declared_snapshot,
)

NVDA = "EQ_US_NVDA"
AT = datetime(2024, 6, 21, 21, tzinfo=UTC)


def snapshot(values=None):
    values = values if values is not None else {SMA50.key: 101.0, SMA200.key: 100.0, RSI14.key: 55.0}
    ev = VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                              date(2019, 1, 1), date(2026, 10, 12), "v", "COMPLETE")
    cov = establish_coverage([ev], source="yfinance", instrument_id=NVDA, types=[ActionType.SPLIT],
                             first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=AT, reason="t")
    health = DataHealth(NVDA, AT, Applicability(True, ""), (), True)
    return FeatureSnapshot(NVDA, "yfinance", AT, date(2024, 6, 21), MappingProxyType(dict(values)),
                           MappingProxyType({SMA50.key: "1.0.0", SMA200.key: "1.0.0", RSI14.key: "1.0.0"}), (), (),
                           cov, "", AdjustedBasis.SPLIT_ADJUSTED_AS_OF, health, (), 102.0)


@dataclass(frozen=True)
class Dummy:
    name: str = "dummy"
    version: str = "0.1.0"
    required_sources: tuple = (SourceKey("yfinance", Timeframe.D1),)
    required_actions: tuple = (ActionType.SPLIT,)
    features: tuple = (SMA50, SMA200)

    def evaluate(self, snap):
        view = declared_snapshot(snap, self.features)
        fast, slow = view.values[SMA50.key], view.values[SMA200.key]
        if fast is None or slow is None:
            return None
        direction = Direction.BULLISH if fast > slow else Direction.BEARISH
        return StrategySignal(self.name, self.version, direction, 0.5, ("fast above slow",),
                              (SMA50.key, SMA200.key))


@pytest.mark.unit
def test_a_conforming_strategy_passes_the_contract():
    s = Dummy()
    assert isinstance(s, RuleStrategy)
    signal = s.evaluate(snapshot())
    assert signal.direction is Direction.BULLISH and signal.strength == 0.5
    assert signal.feature_keys == (SMA50.key, SMA200.key)


@pytest.mark.unit
@pytest.mark.parametrize("strength", [-0.01, 1.01, float("nan"), float("inf"), True, Decimal("0.5"), 1])
def test_strength_must_be_a_finite_float_in_zero_to_one(strength):
    with pytest.raises((TypeError, ValueError)):
        StrategySignal("s", "0.1.0", Direction.BULLISH, strength, ("r",), ("k",))


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"strategy": ""}, {"strategy_version": ""}, {"strategy_version": "1"}, {"direction": "ABSTAIN"},
    {"reasons": ("",)}, {"reasons": "text"}, {"feature_keys": ()},
])
def test_signal_identity_direction_and_reasons_are_validated(change):
    fields = {"strategy": "s", "strategy_version": "0.1.0", "direction": Direction.NEUTRAL, "strength": 0.0,
              "reasons": ("r",), "feature_keys": ("k",)}
    with pytest.raises((TypeError, ValueError)):
        StrategySignal(**{**fields, **change})


@pytest.mark.unit
def test_abstain_is_not_a_strategy_direction():
    assert {d.value for d in Direction} == {"BULLISH", "BEARISH", "NEUTRAL"}


@pytest.mark.unit
def test_reading_an_undeclared_feature_raises():
    view = declared_snapshot(snapshot(), (SMA50,))
    assert view.values[SMA50.key] == 101.0
    with pytest.raises(UndeclaredFeature):
        view.values[RSI14.key]
    with pytest.raises(UndeclaredFeature):
        view.values.get(RSI14.key)
    assert list(view.values) == [SMA50.key]


@pytest.mark.unit
def test_the_guarded_view_is_an_immutable_copy():
    snap = snapshot()
    view = declared_snapshot(snap, (SMA50,))
    with pytest.raises(TypeError):
        view.values[SMA50.key] = 0.0
    assert snap.values[RSI14.key] == 55.0  # the original is untouched
    assert view.as_of == snap.as_of and view.data_health == snap.data_health


@pytest.mark.unit
def test_declared_features_must_match_the_snapshots_definitions():
    other_version = FeatureDefinition("sma", "1.0.1", {"window": 50}, AdjustedBasis.SPLIT_ADJUSTED_AS_OF, 50)
    other_params = FeatureDefinition("sma", "1.0.0", {"window": 20}, AdjustedBasis.SPLIT_ADJUSTED_AS_OF, 20)
    for d in (other_version, other_params):
        with pytest.raises(UndeclaredFeature):
            declared_snapshot(snapshot(), (d,))
    snap = snapshot()
    mismatched = replace(snap, feature_versions=MappingProxyType({**snap.feature_versions, SMA50.key: "2.0.0"}))
    with pytest.raises(ValueError):
        declared_snapshot(mismatched, (SMA50,))


@pytest.mark.unit
def test_warmup_gives_none():
    assert Dummy().evaluate(snapshot({SMA50.key: 101.0, SMA200.key: None, RSI14.key: None})) is None


@pytest.mark.unit
def test_the_same_snapshot_gives_an_identical_signal():
    snap = snapshot()
    assert Dummy().evaluate(snap) == Dummy().evaluate(snap)
