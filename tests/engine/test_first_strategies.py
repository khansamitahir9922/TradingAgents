"""The first rule strategies, OPEN-06 option A (docs/tasks/M2-05.md)."""

from datetime import UTC, date, datetime
from types import MappingProxyType

import pytest

from investment_engine.market.candles import Timeframe
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import Applicability, DataHealth, SourceKey
from investment_engine.quant.adjusted import AdjustedBasis, VerificationEvidence, establish_coverage
from investment_engine.quant.indicators import DEFINITIONS, DIST_SMA200, RSI14, SMA50, SMA200
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import Direction, RuleStrategy, StrategySignal
from investment_engine.quant.strategies.pullback import PullbackStrategy
from investment_engine.quant.strategies.trend import TrendStrategy

NVDA = "EQ_US_NVDA"
AT = datetime(2024, 6, 21, 21, tzinfo=UTC)


def snap(*, sma50=101.0, sma200=100.0, dist=0.05, rsi=50.0):
    ev = VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                              date(2019, 1, 1), date(2026, 10, 12), "v", "COMPLETE")
    cov = establish_coverage([ev], source="yfinance", instrument_id=NVDA, types=[ActionType.SPLIT],
                             first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=AT, reason="t")
    values = {SMA50.key: sma50, SMA200.key: sma200, RSI14.key: rsi, DIST_SMA200.key: dist}
    return FeatureSnapshot(NVDA, "yfinance", AT, date(2024, 6, 21), MappingProxyType(values),
                           MappingProxyType({d.key: d.version for d in DEFINITIONS}), (), (), cov, "",
                           AdjustedBasis.SPLIT_ADJUSTED_AS_OF, DataHealth(NVDA, AT, Applicability(True, ""), (), True),
                           (), 105.0)


TREND, PULLBACK = TrendStrategy(), PullbackStrategy()


# ------------------------------------------------------------------ A1, trend


@pytest.mark.unit
@pytest.mark.parametrize(("kwargs", "direction"), [
    ({"dist": 0.05, "sma50": 101.0, "sma200": 100.0}, Direction.BULLISH),
    ({"dist": -0.05, "sma50": 99.0, "sma200": 100.0}, Direction.BEARISH),
    ({"dist": 0.05, "sma50": 99.0, "sma200": 100.0}, Direction.NEUTRAL),  # above SMA200, SMA50 below
    ({"dist": -0.05, "sma50": 101.0, "sma200": 100.0}, Direction.NEUTRAL),  # below SMA200, SMA50 above
    ({"dist": 0.0, "sma50": 101.0, "sma200": 100.0}, Direction.NEUTRAL),  # close equals SMA200
    ({"dist": 0.05, "sma50": 100.0, "sma200": 100.0}, Direction.NEUTRAL),  # SMA50 equals SMA200
])
def test_trend_table(kwargs, direction):
    assert TREND.evaluate(snap(**kwargs)).direction is direction


@pytest.mark.unit
@pytest.mark.parametrize(("dist", "strength"), [(0.0, 0.0), (0.042, 0.42), (0.10, 1.0), (-0.25, 1.0)])
def test_trend_strength_is_a_distance_scale(dist, strength):
    signal = TREND.evaluate(snap(dist=dist, sma50=101.0 if dist >= 0 else 99.0))
    assert signal.strength == pytest.approx(strength)
    assert "not a probability" in TrendStrategy.strength_scale


@pytest.mark.unit
def test_trend_reasons_name_the_rule_and_values():
    signal = TREND.evaluate(snap(dist=0.042))
    assert signal.reasons == ("close 4.2% above SMA200; SMA50 above SMA200",)
    assert set(signal.feature_keys) == {SMA50.key, SMA200.key, DIST_SMA200.key}


# ------------------------------------------------------------------ A2, pullback


@pytest.mark.unit
@pytest.mark.parametrize(("kwargs", "direction"), [
    ({"dist": 0.05, "rsi": 25.0}, Direction.BULLISH),
    ({"dist": 0.05, "rsi": 30.0}, Direction.BULLISH),  # inclusive
    ({"dist": -0.05, "rsi": 75.0}, Direction.BEARISH),
    ({"dist": -0.05, "rsi": 70.0}, Direction.BEARISH),  # inclusive
    ({"dist": 0.05, "rsi": 30.01}, Direction.NEUTRAL),
    ({"dist": 0.05, "rsi": 75.0}, Direction.NEUTRAL),  # overbought in an uptrend: not a signal
    ({"dist": -0.05, "rsi": 25.0}, Direction.NEUTRAL),  # oversold in a downtrend: not a signal
    ({"dist": 0.0, "rsi": 20.0}, Direction.NEUTRAL),  # close equals SMA200
])
def test_pullback_table(kwargs, direction):
    assert PULLBACK.evaluate(snap(**kwargs)).direction is direction


@pytest.mark.unit
@pytest.mark.parametrize(("rsi", "strength"), [(50.0, 0.0), (30.0, 0.4), (0.0, 1.0), (100.0, 1.0)])
def test_pullback_strength_is_an_rsi_distance_scale(rsi, strength):
    assert PULLBACK.evaluate(snap(rsi=rsi)).strength == pytest.approx(strength)
    assert "not a probability" in PullbackStrategy.strength_scale


@pytest.mark.unit
def test_pullback_reads_only_rsi_and_distance():
    signal = PULLBACK.evaluate(snap(dist=0.05, rsi=28.0))
    assert set(signal.feature_keys) == {RSI14.key, DIST_SMA200.key}
    assert signal.reasons == ("close 5.0% above SMA200; RSI 28.0 at or below 30",)


# ------------------------------------------------------------------ shared


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["sma200", "dist", "sma50"])
def test_trend_warmup_gives_none(missing):
    assert TREND.evaluate(snap(**{missing: None})) is None


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["rsi", "dist"])
def test_pullback_warmup_gives_none(missing):
    assert PULLBACK.evaluate(snap(**{missing: None})) is None


@pytest.mark.unit
def test_declared_sources_actions_features_and_identity():
    for strategy, name, features in ((TREND, "daily-trend", (SMA50, SMA200, DIST_SMA200)),
                                     (PULLBACK, "daily-pullback", (RSI14, DIST_SMA200))):
        assert isinstance(strategy, RuleStrategy)
        assert (strategy.name, strategy.version) == (name, "0.1.0")
        assert strategy.required_sources == (SourceKey("yfinance", Timeframe.D1),)
        assert strategy.required_actions == (ActionType.SPLIT,)
        assert {d.key for d in strategy.features} == {d.key for d in features}
        assert all(d.input_basis is AdjustedBasis.SPLIT_ADJUSTED_AS_OF for d in strategy.features)
        signal = strategy.evaluate(snap())
        assert isinstance(signal, StrategySignal)
        assert (signal.strategy, signal.strategy_version) == (name, "0.1.0")
        assert 0.0 <= signal.strength <= 1.0


@pytest.mark.unit
def test_strategies_are_deterministic():
    s = snap(dist=-0.03, sma50=98.0, rsi=71.0)
    assert TREND.evaluate(s) == TREND.evaluate(s)
    assert PULLBACK.evaluate(s) == PULLBACK.evaluate(s)
