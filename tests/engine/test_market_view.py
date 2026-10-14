"""MarketView and the decision policy (Law 9; Part H; docs/tasks/M2-06.md)."""

from dataclasses import replace
from datetime import date, timedelta
from types import MappingProxyType

import pytest

from investment_engine.decision.market_view import MarketView, ViewDirection, decide
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import Timeframe
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import (
    Applicability,
    DataHealth,
    HealthStatus,
    SourceHealth,
    SourceKey,
)
from investment_engine.quant.adjusted import AdjustedBasis, VerificationEvidence, establish_coverage
from investment_engine.quant.indicators import DEFINITIONS
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import Direction, StrategySignal
from investment_engine.quant.strategies.pullback import PullbackStrategy
from investment_engine.quant.strategies.trend import TrendStrategy

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
AT = CAL.session(date(2024, 6, 21)).close + timedelta(hours=1)  # Friday after the close
YF_D1 = SourceKey("yfinance", Timeframe.D1)
TREND, PULLBACK = TrendStrategy(), PullbackStrategy()
STRATEGIES = (TREND, PULLBACK)


def source_health(status=HealthStatus.OK, key=YF_D1, at=AT):
    return SourceHealth(key, status, at, at - timedelta(hours=1), timedelta(hours=1), 0, (),
                        "" if status is HealthStatus.OK else f"{status} detail")


def health(*entries, applicable=True, at=AT):
    entries = entries if entries else (source_health(at=at),)
    if not applicable:
        return DataHealth(NVDA, at, Applicability(False, "not listed yet"), (), False)
    return DataHealth(NVDA, at, Applicability(True, ""), tuple(entries),
                      all(e.status is HealthStatus.OK for e in entries))


def coverage(at=AT, established=True):
    ev = VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                              date(2019, 1, 1), date(2026, 10, 12), "v", "COMPLETE")
    return establish_coverage([ev] if established else [], source="yfinance", instrument_id=NVDA,
                              types=[ActionType.SPLIT], first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=at,
                              reason="t")


def snapshot(*, h=None, cov=None, reason="", at=AT):
    values = {d.key: 1.0 for d in DEFINITIONS}
    return FeatureSnapshot(NVDA, "yfinance", at, date(2024, 6, 21), MappingProxyType(values),
                           MappingProxyType({d.key: d.version for d in DEFINITIONS}), (), (),
                           cov or coverage(at), reason, AdjustedBasis.SPLIT_ADJUSTED_AS_OF, h or health(at=at), (),
                           100.0)


def signal(strategy, direction, strength=0.5, reason="rule fired"):
    return StrategySignal(strategy.name, strategy.version, direction, strength, (reason,),
                          tuple(d.key for d in strategy.features))


def view(signals=None, snap=None, strategies=STRATEGIES, **kwargs):
    signals = signals if signals is not None else (signal(TREND, Direction.BULLISH, 0.4),
                                                   signal(PULLBACK, Direction.NEUTRAL, 0.1))
    return decide(signals, snap or snapshot(), strategies, policy_version="0.1.0", calendar=CAL, **kwargs)


# ------------------------------------------------------------------ Law 9


@pytest.mark.unit
def test_all_ok_and_applicable_gives_a_directional_view():
    v = view()
    assert isinstance(v, MarketView)
    assert v.direction is ViewDirection.BULLISH and v.strength == 0.4 and v.abstain_reason == ""


@pytest.mark.unit
@pytest.mark.parametrize("status", [HealthStatus.STALE, HealthStatus.MISSING, HealthStatus.DEGRADED])
def test_any_non_ok_required_source_abstains_and_is_named(status):
    v = view(snap=snapshot(h=health(source_health(status))))
    assert v.direction is ViewDirection.ABSTAIN and v.strength == 0.0
    assert "yfinance D1" in v.abstain_reason and str(status) in v.abstain_reason


@pytest.mark.unit
def test_every_non_ok_source_is_named():
    tv = SourceKey("testvendor", Timeframe.D1)
    v = view(snap=snapshot(h=health(source_health(HealthStatus.STALE), source_health(HealthStatus.MISSING, tv))))
    assert v.direction is ViewDirection.ABSTAIN and "yfinance D1: STALE" in v.abstain_reason


@pytest.mark.unit
def test_a_not_applicable_instrument_abstains():
    v = view(snap=snapshot(h=health(applicable=False)))
    assert v.direction is ViewDirection.ABSTAIN and "not applicable" in v.abstain_reason


@pytest.mark.unit
def test_a_missing_required_health_entry_abstains_rather_than_passing_an_empty_check():
    tv_only = health(source_health(key=SourceKey("testvendor", Timeframe.D1)))
    v = view(snap=snapshot(h=tv_only))
    assert v.direction is ViewDirection.ABSTAIN and "no health entry" in v.abstain_reason


@pytest.mark.unit
def test_unestablished_coverage_or_an_unavailable_snapshot_abstains():
    assert view(snap=snapshot(cov=coverage(established=False))).direction is ViewDirection.ABSTAIN
    v = view(snap=snapshot(reason="missing sessions in the feature window: 2024-03-01"))
    assert v.direction is ViewDirection.ABSTAIN and "2024-03-01" in v.abstain_reason


@pytest.mark.unit
def test_established_coverage_with_no_splits_is_not_a_missing_source():
    assert view().direction is ViewDirection.BULLISH  # the default coverage holds no actions at all


@pytest.mark.unit
def test_warmup_abstains():
    v = view((signal(TREND, Direction.BULLISH), None))
    assert v.direction is ViewDirection.ABSTAIN and v.abstain_reason == "warm-up"


# ------------------------------------------------------------------ combination policy v0.1


@pytest.mark.unit
@pytest.mark.parametrize(("a1", "a2", "direction", "strength"), [
    ((Direction.BULLISH, 0.3), (Direction.NEUTRAL, 0.0), ViewDirection.BULLISH, 0.3),
    ((Direction.BULLISH, 0.3), (Direction.BULLISH, 0.8), ViewDirection.BULLISH, 0.8),
    ((Direction.BEARISH, 0.6), (Direction.BEARISH, 0.2), ViewDirection.BEARISH, 0.6),
    ((Direction.NEUTRAL, 0.2), (Direction.NEUTRAL, 0.0), ViewDirection.NEUTRAL, 0.0),
    ((Direction.NEUTRAL, 0.2), (Direction.BULLISH, 0.9), ViewDirection.NEUTRAL, 0.0),
    ((Direction.BULLISH, 0.3), (Direction.BEARISH, 0.9), ViewDirection.NEUTRAL, 0.0),  # consistency check
])
def test_combination_table(a1, a2, direction, strength):
    v = view((signal(TREND, *a1), signal(PULLBACK, *a2)))
    assert v.direction is direction and v.strength == strength
    assert v.regime == str(a1[0])


@pytest.mark.unit
def test_consistency_neutral_keeps_its_reasons_visible():
    v = view((signal(TREND, Direction.BULLISH, 0.3, "trend up"), signal(PULLBACK, Direction.BEARISH, 0.9, "rsi high")))
    assert "trend up" in v.reasons and "rsi high" in v.reasons
    assert any("against" in r for r in v.reasons)


@pytest.mark.unit
def test_with_a1_only_the_direction_is_a1s():
    v = view((signal(TREND, Direction.BEARISH, 0.7),), strategies=(TREND,))
    assert v.direction is ViewDirection.BEARISH and v.strength == 0.7


# ------------------------------------------------------------------ fields


@pytest.mark.unit
def test_probability_up_is_always_none_and_horizon_and_versions_are_set():
    for v in (view(), view((signal(TREND, Direction.BULLISH), None))):
        assert v.probability_up is None
        assert v.horizon == "5 sessions" and v.policy_version == "0.1.0"
        assert v.generated_at == AT and v.data_health == snapshot().data_health
        assert 0.0 <= v.strength <= 1.0


@pytest.mark.unit
@pytest.mark.parametrize(("at", "expected"), [
    (CAL.session(date(2024, 6, 21)).close + timedelta(hours=1), date(2024, 6, 24)),  # Friday: next is Monday
    (CAL.session(date(2024, 6, 18)).close + timedelta(hours=1), date(2024, 6, 20)),  # Juneteenth holiday skipped
])
def test_valid_until_is_the_next_sessions_close(at, expected):
    v = view(snap=snapshot(at=at))
    assert v.valid_until == CAL.session(expected).close


@pytest.mark.unit
def test_the_same_inputs_give_an_identical_view():
    assert view() == view()


@pytest.mark.unit
def test_evidence_refs_are_carried():
    assert view(evidence_refs=("lineage:abc",)).evidence_refs == ("lineage:abc",)


# ------------------------------------------------------------------ refused inputs


@pytest.mark.unit
@pytest.mark.parametrize("signals", [
    (signal(PULLBACK, Direction.NEUTRAL), signal(TREND, Direction.BULLISH)),  # slots out of order
    (signal(TREND, Direction.BULLISH),),  # a slot missing
    (replace(signal(TREND, Direction.BULLISH), strategy_version="9.9.9"), signal(PULLBACK, Direction.NEUTRAL)),
])
def test_mismatched_signal_identities_versions_or_counts_raise(signals):
    with pytest.raises(ValueError):
        view(signals)


@pytest.mark.unit
def test_the_strategy_set_must_be_non_empty_and_distinct():
    with pytest.raises(ValueError):
        view((), strategies=())
    with pytest.raises(ValueError):
        view((signal(TREND, Direction.BULLISH),) * 2, strategies=(TREND, TREND))


@pytest.mark.unit
def test_a_snapshot_whose_health_is_for_another_time_or_instrument_raises():
    snap = snapshot()
    with pytest.raises(ValueError):
        view(snap=replace(snap, data_health=replace(snap.data_health, as_of=AT + timedelta(seconds=1))))
    with pytest.raises(ValueError):
        view(snap=replace(snap, data_health=replace(snap.data_health, instrument_id="EQ_US_MSFT")))


@pytest.mark.unit
@pytest.mark.parametrize("strength", [1.5, -0.1, float("nan")])
def test_a_view_with_an_invalid_strength_raises(strength):
    with pytest.raises(ValueError):
        replace(view(), strength=strength)


@pytest.mark.unit
def test_an_abstain_view_must_have_zero_strength_and_a_reason():
    with pytest.raises(ValueError):
        replace(view(), direction=ViewDirection.ABSTAIN)
    with pytest.raises(ValueError):
        replace(view(), probability_up=0.6)
