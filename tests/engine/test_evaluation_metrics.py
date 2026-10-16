"""Honest direction metrics and matched baselines (docs/tasks/M2-09.md)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.evaluation.metrics import PredictionView, evaluate_direction, spearman
from investment_engine.evaluation.returns import LabelConfig, ReturnBasis, ReturnObservation
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import Applicability, DataHealth
from investment_engine.quant.adjusted import VerificationEvidence, establish_coverage

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
DAYS = [s.date for s in CAL.sessions_between(date(2024, 3, 1), date(2024, 4, 30))]
CONFIG = LabelConfig(1, ReturnBasis.SPLIT_ADJUSTED_PRICE_RETURN, "labels-test")


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def at(d):
    return CAL.session(d).close


def pv(d, direction, strength=0.5, source="yfinance"):
    t = at(d)
    health = DataHealth(NVDA, t, Applicability(True, ""), (), True)
    strength = 0.0 if direction in ("NEUTRAL", "ABSTAIN") else strength
    view = MarketView(NVDA, ViewDirection(direction), strength, None, "1 sessions", t, t + timedelta(days=1), None,
                      health, (), "0.1.0", "warm-up" if direction == "ABSTAIN" else "", ())
    return PredictionView(source, d, view)


def outcome(d, value, *, horizon=1, source="yfinance", available_from=None, basis=CONFIG.basis):
    end = CAL.session(d)
    for _ in range(horizon):
        end = CAL.next_session(end.date)
    ev = VerificationEvidence("yfinance", NVDA, ActionType.SPLIT, date(2019, 1, 1), date(2026, 10, 12),
                              date(2019, 1, 1), date(2026, 10, 12), "v", "COMPLETE")
    cov = establish_coverage([ev], source="yfinance", instrument_id=NVDA, types=[ActionType.SPLIT],
                             first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=utc(2026, 1, 1), reason="t")
    return ReturnObservation(source, NVDA, d, end.date, basis, value, end.close, available_from or end.close,
                             utc(2026, 1, 1), (), (), cov, "" if value is not None else "missing")


def trailing(d, value, available_from=None):
    """The same-basis h-session return ending at d's close, read at d's T."""
    start = CAL.previous_session(d)
    o = outcome(start.date, value)
    return ReturnObservation(o.source, NVDA, start.date, d, o.basis, value, at(d), available_from or at(d), at(d),
                             (), (), o.coverage, "" if value is not None else "missing")


def metric(result, key):
    [m] = [m for m in result.metrics if m.key == key]
    return m


def table():
    # Day:     0      1      2      3      4      5        6         7
    views = [pv(DAYS[0], "BULLISH", 0.9), pv(DAYS[1], "BULLISH", 0.2), pv(DAYS[2], "BEARISH", 0.6),
             pv(DAYS[3], "BEARISH", 0.4), pv(DAYS[4], "NEUTRAL"), pv(DAYS[5], "ABSTAIN"),
             pv(DAYS[6], "BULLISH", 0.5), pv(DAYS[7], "BULLISH", 0.7)]
    outcomes = [outcome(DAYS[0], 0.03), outcome(DAYS[1], -0.01), outcome(DAYS[2], -0.02), outcome(DAYS[3], 0.01),
                outcome(DAYS[4], 0.02), outcome(DAYS[5], 0.05), outcome(DAYS[6], 0.0), outcome(DAYS[7], None)]
    return views, outcomes


@pytest.mark.unit
def test_counts_accuracy_base_rate_and_matched_always_up():
    views, outcomes = table()
    r = evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL)
    assert (r.eligible_views, r.directional_views, r.neutral_views, r.abstain_views, r.unavailable_outcomes) == (
        8, 6, 1, 1, 1)
    # Scored: directional, available, non-zero outcome -> days 0, 1, 2, 3. Correct on 0 and 2.
    assert metric(r, "direction_accuracy").value == pytest.approx(0.5) and metric(r, "direction_accuracy").n == 4
    assert metric(r, "zero_outcome_exclusions").value == 1  # day 6
    # Always-up on exactly the scored dates: positive on days 0 and 3.
    assert metric(r, "always_up_accuracy_matched").value == pytest.approx(0.5)
    assert metric(r, "paired_accuracy_difference").value == pytest.approx(0.0)
    # Full eligible population (every available non-zero outcome): days 0-5 -> positive on 0, 3, 4, 5.
    assert metric(r, "always_up_accuracy_full").value == pytest.approx(4 / 6) and metric(r, "always_up_accuracy_full").n == 6
    assert metric(r, "positive_base_rate").value == pytest.approx(4 / 7)  # zero counts as not positive
    assert r.config_version == "labels-test" and r.horizon_sessions == 1


@pytest.mark.unit
def test_selective_abstention_is_exposed_by_the_full_population_baseline():
    views = [pv(DAYS[i], "BULLISH" if i < 2 else "ABSTAIN") for i in range(6)]
    outcomes = [outcome(DAYS[i], v) for i, v in enumerate([0.01, 0.02, -0.01, -0.02, -0.03, -0.01])]
    r = evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL)
    assert metric(r, "direction_accuracy").value == 1.0 and metric(r, "direction_accuracy").n == 2
    assert metric(r, "always_up_accuracy_matched").value == 1.0
    assert metric(r, "always_up_accuracy_full").value == pytest.approx(2 / 6)
    assert r.abstain_views == 4


@pytest.mark.unit
def test_last_period_baseline_uses_only_completed_available_trailing_returns():
    views, outcomes = table()
    trail = [trailing(DAYS[0], 0.01), trailing(DAYS[1], 0.02),
             trailing(DAYS[2], -0.01, available_from=at(DAYS[2]) + timedelta(seconds=1)),  # not available at T
             trailing(DAYS[3], -0.02)]
    r = evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL, trailing=trail)
    lp = metric(r, "last_period_accuracy_matched")
    # Paired sample: days 0, 1, 3 (day 2's trailing return wasn't available). Last-period predicts up, up, down.
    assert lp.n == 3 and lp.value == pytest.approx(1 / 3)  # day 0 right (+), day 1 wrong (-), day 3 wrong (+)
    model = metric(r, "direction_accuracy_on_last_period_sample")
    assert model.n == 3 and model.value == pytest.approx(1 / 3)  # day 0 right, 1 wrong, 3 wrong
    assert metric(r, "last_period_unavailable").value == 1


@pytest.mark.unit
def test_information_coefficient_uses_signed_strength_with_zero_outcomes_included():
    views, outcomes = table()
    r = evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL)
    ic = metric(r, "information_coefficient")
    # Directional with available outcomes: days 0, 1, 2, 3, 6 (zero included, day 7 unavailable).
    scores = [0.9, 0.2, -0.6, -0.4, 0.5]
    returns = [0.03, -0.01, -0.02, 0.01, 0.0]
    assert ic.n == 5 and ic.value == pytest.approx(spearman(scores, returns))


@pytest.mark.unit
def test_spearman_perfect_ties_and_constant():
    assert spearman([1.0, 2.0, 3.0], [10.0, 20.0, 30.0]) == pytest.approx(1.0)
    assert spearman([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    # Ties get average ranks: x ranks (1.5, 1.5, 3), y ranks (1, 2, 3) -> r = 0.8660...
    assert spearman([1.0, 1.0, 2.0], [1.0, 2.0, 3.0]) == pytest.approx(0.8660254, rel=1e-6)
    assert spearman([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


@pytest.mark.unit
def test_unavailable_metrics_are_none_with_a_reason_never_zero_or_nan():
    views = [pv(DAYS[0], "NEUTRAL"), pv(DAYS[1], "ABSTAIN")]
    outcomes = [outcome(DAYS[0], 0.01), outcome(DAYS[1], 0.02)]
    r = evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL)
    for key in ("direction_accuracy", "information_coefficient", "paired_accuracy_difference"):
        m = metric(r, key)
        assert m.value is None and m.unavailable_reason and m.n == 0


@pytest.mark.unit
def test_every_metric_reports_its_sample_size():
    views, outcomes = table()
    for m in evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL).metrics:
        assert isinstance(m.n, int) and m.n >= 0


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["duplicate_view", "duplicate_outcome", "horizon", "provider", "basis", "missing"])
def test_mismatched_or_duplicate_inputs_are_rejected(bad):
    views, outcomes = table()
    if bad == "duplicate_view":
        views.append(views[0])
    elif bad == "duplicate_outcome":
        outcomes.append(outcomes[0])
    elif bad == "horizon":
        outcomes[0] = outcome(DAYS[0], 0.03, horizon=2)
    elif bad == "provider":
        outcomes[0] = outcome(DAYS[0], 0.03, source="testvendor")
    elif bad == "basis":
        outcomes[0] = outcome(DAYS[0], 0.03, basis=ReturnBasis.TOTAL_RETURN_CLOSE_REINVESTED)
    else:
        outcomes.pop(0)
    with pytest.raises(ValueError):
        evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL)


@pytest.mark.unit
def test_outcome_refs_are_the_observations_used():
    views, outcomes = table()
    r = evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL)
    assert set(r.outcome_refs) == set(outcomes)


# ------------------------------------------------------------------ S3: the last-period sample is auditable


@pytest.mark.unit
def test_the_last_period_sample_and_its_trailing_returns_are_kept():
    views, outcomes = table()
    trail = [trailing(DAYS[0], 0.01), trailing(DAYS[1], 0.02),
             trailing(DAYS[2], -0.01, available_from=at(DAYS[2]) + timedelta(seconds=1)),
             trailing(DAYS[3], -0.02)]
    r = evaluate_direction(views, outcomes, config=CONFIG, calendar=CAL, trailing=trail)
    assert r.last_period_sample == (DAYS[0], DAYS[1], DAYS[3])
    assert r.last_period_excluded == (DAYS[2],)
    assert set(r.trailing_refs) == {trail[0], trail[1], trail[3]}
