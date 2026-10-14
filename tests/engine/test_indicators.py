"""Indicators for the first strategies (docs/tasks/M2-02.md).

SMA(50), SMA(200), RSI(14) with Wilder's smoothing, and the distance of the
close from SMA(200), all on the split-adjusted view as of T.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, ex_date_start
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
)
from investment_engine.quant.adjusted import (
    AdjustedBasis,
    VerificationEvidence,
    adjusted_daily,
    establish_coverage,
)
from investment_engine.quant.indicators import (
    DEFINITIONS,
    DIST_SMA200,
    RSI14,
    SMA50,
    SMA200,
    distance_from,
    evaluate,
    registry,
    rsi,
    sma,
)

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()


# ------------------------------------------------------------------ SMA


@pytest.mark.unit
def test_sma_is_the_mean_of_the_last_window_values():
    assert sma([1.0, 2.0, 3.0], 3) == 2.0
    assert sma([1.0, 2.0, 3.0, 10.0], 3) == 5.0


@pytest.mark.unit
def test_sma_is_none_until_exactly_window_values():
    assert sma([1.0, 2.0], 3) is None
    assert sma([1.0, 2.0, 3.0], 3) is not None


# ------------------------------------------------------------------ RSI


@pytest.mark.unit
def test_rsi_seed_and_recurrence_by_hand():
    closes = [10.0, 11.0, 12.0, 11.0, 13.0]  # changes +1, +1, -1, +2
    # Seed over the first 3 changes: gain 2/3, loss 1/3, RS 2, RSI 66.67.
    assert rsi(closes[:4], 3) == pytest.approx(100 - 100 / 3)
    # Next: gain (2/3*2 + 2)/3 = 10/9, loss (1/3*2 + 0)/3 = 2/9, RS 5, RSI 83.33.
    assert rsi(closes, 3) == pytest.approx(100 - 100 / 6)


@pytest.mark.unit
def test_rsi_gains_only_losses_only_and_flat():
    assert rsi([1.0, 2.0, 3.0, 4.0], 3) == 100.0
    assert rsi([4.0, 3.0, 2.0, 1.0], 3) == 0.0
    assert rsi([2.0, 2.0, 2.0, 2.0], 3) == 50.0


@pytest.mark.unit
def test_rsi_needs_window_plus_one_values():
    assert rsi([1.0] * 14, 14) is None
    assert rsi([1.0] * 15, 14) == 50.0


@pytest.mark.unit
def test_rsi_after_the_seed_follows_wilders_recurrence_on_a_longer_series():
    closes = [44.0, 44.25, 44.5, 43.75, 44.5, 45.0, 44.75, 45.5, 46.0, 45.75, 46.25, 47.0, 46.5, 46.25, 47.0,
              47.5, 47.25]
    changes = [b - a for a, b in zip(closes, closes[1:], strict=False)]
    gain = sum(max(c, 0) for c in changes[:14]) / 14
    loss = sum(max(-c, 0) for c in changes[:14]) / 14
    for c in changes[14:]:
        gain = (gain * 13 + max(c, 0)) / 14
        loss = (loss * 13 + max(-c, 0)) / 14
    assert rsi(closes, 14) == pytest.approx(100 - 100 / (1 + gain / loss))


# ------------------------------------------------------------------ distance and invalid input


@pytest.mark.unit
def test_distance_from_the_average():
    assert distance_from(110.0, 100.0) == pytest.approx(0.10)
    assert distance_from(90.0, 100.0) == pytest.approx(-0.10)


@pytest.mark.unit
@pytest.mark.parametrize("call", [
    lambda: sma([Decimal("1")], 1), lambda: sma([1], 1), lambda: sma([float("nan")], 1),
    lambda: sma([1.0, -1.0], 2), lambda: sma([1.0], 0), lambda: sma([1.0], True),
    lambda: rsi([1.0, 0.0], 1), lambda: rsi([1.0, 2.0], 0), lambda: rsi([1.0, float("inf")], 1),
    lambda: sma([1e308, 1e308], 2), lambda: distance_from(1e308, 1e-308),
    lambda: distance_from(1.0, 0.0), lambda: distance_from(1.0, -5.0), lambda: distance_from(Decimal("1"), 1.0),
])
def test_invalid_inputs_raise(call):
    with pytest.raises((TypeError, ValueError)):
        call()


# ------------------------------------------------------------------ definitions


@pytest.mark.unit
def test_each_definition_is_registered_with_its_warmup_on_the_split_adjusted_view():
    reg = registry()
    expected = [(SMA50, ("sma", 50, 50)), (SMA200, ("sma", 200, 200)), (RSI14, ("rsi", 14, 200)),
                (DIST_SMA200, ("dist_sma", 200, 200))]
    assert [d.key for d in DEFINITIONS] == [d.key for d, _ in expected]
    for d, (name, window, warmup) in expected:
        assert reg.get(d.key) == d
        assert (d.name, d.params["window"], d.warmup_sessions) == (name, window, warmup)
        assert d.input_basis is AdjustedBasis.SPLIT_ADJUSTED_AS_OF


@pytest.mark.unit
def test_evaluate_is_none_during_warmup_and_never_a_partial_window():
    closes = [float(i) for i in range(1, 200)]  # 199 values
    assert evaluate(SMA200, closes) is None
    assert evaluate(DIST_SMA200, closes) is None
    assert evaluate(SMA50, closes) == pytest.approx(sum(closes[-50:]) / 50)
    assert evaluate(SMA200, closes + [200.0]) == pytest.approx(100.5)
    assert evaluate(DIST_SMA200, closes + [200.0]) == pytest.approx(200.0 / 100.5 - 1)
    assert evaluate(RSI14, closes[:14]) is None


@pytest.mark.unit
def test_rsi14_uses_exactly_its_declared_seeding_window():
    closes = [100.0 + (i % 7) - (i % 3) for i in range(260)]
    assert RSI14.params["seed_sessions"] == 200 and RSI14.warmup_sessions == 200
    assert evaluate(RSI14, closes[:199]) is None
    assert evaluate(RSI14, closes) == rsi(closes[-200:], 14)
    assert evaluate(RSI14, [50.0] * 40 + closes) == evaluate(RSI14, closes)  # earlier history never matters


@pytest.mark.unit
def test_values_at_t_do_not_change_when_later_bars_exist():
    closes = [100.0 + (i % 7) - (i % 3) for i in range(260)]
    for definition in DEFINITIONS:
        assert evaluate(definition, closes[:230]) == evaluate(definition, closes[:230])
        assert evaluate(definition, list(closes[:230])) == evaluate(definition, closes[:231][:230])


# ------------------------------------------------------------------ across a synthetic 10-for-1 split


def _bar(d, close):
    s = CAL.session(d)
    received = s.close + timedelta(minutes=5)
    close = Decimal(close)
    return CandleObservation(
        source="yfinance", instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=close, high=close, low=close, close=close, currency="USD", volume=Decimal("1000"),
        state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received, processed_at=received,
        backfill_available_from=s.close)


@pytest.mark.unit
def test_adjusted_closes_have_no_artificial_discontinuity_and_sma200_matches_a_manual_reference(tmp_path):
    root = tmp_path / "market"
    writer, reader = MarketDataWriter(root), MarketDataReader(root)
    sessions = [s.date for s in CAL.sessions_between(date(2023, 6, 1), date(2024, 6, 21))]
    ex = date(2024, 6, 10)
    raw = {d: (Decimal("1000") + Decimal(i % 9)) / (10 if d >= ex else 1) for i, d in enumerate(sessions)}
    writer.write_candles([_bar(d, f"{raw[d]:.4f}") for d in sessions], import_id="bars")
    writer.write_corporate_actions([ActionObservation(
        source="yfinance", instrument_id=NVDA, currency="USD", exchange_timezone="America/New_York",
        action_type=ActionType.SPLIT, ex_date=ex, ratio=Decimal("10"), amount=None, amount_basis=None,
        new_symbol=None, source_version="1.7.0", received_at=datetime(2026, 10, 12, 20, tzinfo=UTC),
        processed_at=datetime(2026, 10, 12, 20, tzinfo=UTC),
        backfill_available_from=ex_date_start(ex, "America/New_York"))], import_id="a")
    at = CAL.session(date(2024, 6, 21)).close + timedelta(hours=1)
    ev = VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                              date(2019, 1, 1), date(2026, 10, 12), "test-verification", "COMPLETE")
    cov = establish_coverage([ev], source="yfinance", instrument_id=NVDA, types=[ActionType.SPLIT],
                             first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=at, reason="test")
    bars = adjusted_daily(reader, "yfinance", NVDA, sessions[0], sessions[-1], at=at, calendar=CAL, coverage=cov)
    adjusted = [b.close for b in bars]
    raw_closes = [float(raw[d]) for d in sessions]
    i = sessions.index(ex)
    assert raw_closes[i] / raw_closes[i - 1] - 1 < -0.85  # raw: an artificial ~90% drop
    assert abs(adjusted[i] / adjusted[i - 1] - 1) < 0.01  # adjusted: continuous
    manual = [float(raw[d] / (10 if d < ex else 1)) for d in sessions]
    assert evaluate(SMA200, adjusted) == pytest.approx(sum(manual[-200:]) / 200)
