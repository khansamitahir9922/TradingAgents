"""Labelled returns and completed prediction outcomes (docs/tasks/M2-08.md)."""

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.evaluation.returns import (
    LabelConfig,
    ReturnBasis,
    ReturnObservation,
    outcome_at,
    session_returns,
    training_eligible,
)
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, AmountBasis, ex_date_start
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
)
from investment_engine.money import Money
from investment_engine.quant.adjusted import VerificationEvidence, establish_coverage

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
TZ = "America/New_York"
PRICE, TOTAL = ReturnBasis.SPLIT_ADJUSTED_PRICE_RETURN, ReturnBasis.TOTAL_RETURN_CLOSE_REINVESTED
D1, D2, D3, D4 = date(2024, 3, 4), date(2024, 3, 5), date(2024, 3, 6), date(2024, 3, 7)
LATE = datetime(2026, 10, 12, 20, tzinfo=UTC)


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def bar(d, close, *, source="yfinance", received_at=None):
    s = CAL.session(d)
    received = received_at or s.close
    close = Decimal(close)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=close, high=close, low=close, close=close, currency="USD", volume=Decimal("1000"),
        state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received, processed_at=received,
        backfill_available_from=s.close)


def action(ex, *, ratio=None, dividend=None, source="yfinance", received_at=LATE, backfill=True,
           action_type=None):
    action_type = action_type or (ActionType.SPLIT if ratio is not None else ActionType.DIVIDEND)
    return ActionObservation(
        source=source, instrument_id=NVDA, currency="USD", exchange_timezone=TZ, action_type=action_type,
        ex_date=ex, ratio=None if ratio is None else Decimal(ratio),
        amount=None if dividend is None else Money(Decimal(dividend), "USD"),
        amount_basis=None if dividend is None else AmountBasis.AS_REPORTED,
        new_symbol="NVDX" if action_type is ActionType.SYMBOL_CHANGE else None, source_version="1.7.0",
        received_at=received_at, processed_at=received_at,
        backfill_available_from=ex_date_start(ex, TZ) if backfill else None)


def coverage(at, types=(ActionType.SPLIT, ActionType.DIVIDEND), source="yfinance"):
    evidence = [VerificationEvidence(source, NVDA, t, date(2019, 1, 1), date(2026, 10, 12), date(2019, 1, 1),
                                     date(2026, 10, 12), "test-verification", "COMPLETE") for t in types]
    return establish_coverage(evidence, source=source, instrument_id=NVDA, types=types, first=date(2019, 1, 1),
                              last=date(2026, 10, 12), as_of=at, reason="test")


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "market"
    return {"writer": MarketDataWriter(root), "reader": MarketDataReader(root), "root": root}


def one_day(store, basis, *, at=None, start=D1, cov=None):
    at = at or utc(2024, 3, 8, 22)
    [obs] = session_returns(store["reader"], "yfinance", NVDA, start, CAL.next_session(start).date, at=at,
                            calendar=CAL, coverage=cov or coverage(at), basis=basis)
    return obs


# ------------------------------------------------------------------ hand-calculated examples


@pytest.mark.unit
def test_a_split_alone_is_a_zero_price_and_total_return(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "50")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, ratio="2")], import_id="a")
    assert one_day(store, PRICE).value == 0.0
    assert one_day(store, TOTAL).value == 0.0


@pytest.mark.unit
def test_a_dividend_of_one_per_new_share_on_the_split_date_is_a_two_percent_total_return(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "50")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, ratio="2"), action(D2, dividend="1")], import_id="a")
    assert one_day(store, PRICE).value == 0.0
    assert one_day(store, TOTAL).value == pytest.approx(0.02)


@pytest.mark.unit
def test_a_plain_dividend_separates_price_and_total_return(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, dividend="1")], import_id="a")
    assert one_day(store, PRICE).value == pytest.approx(-0.01)
    assert one_day(store, TOTAL).value == 0.0


@pytest.mark.unit
def test_multi_day_total_return_chains_daily_gross_returns_reinvesting_at_the_close(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99"), bar(D3, "110"), bar(D4, "55")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, dividend="1"), action(D4, ratio="2")], import_id="a")
    at = utc(2024, 3, 8, 22)
    total = outcome_at(store["reader"], "yfinance", NVDA, D1, config=LabelConfig(3, TOTAL, "t-1"), at=at,
                       calendar=CAL, coverage=coverage(at))
    # Day 1: (99 + 1)/100 = 1.0; day 2: 110/99; day 3: 2*55/110 = 1.0.
    assert total.value == pytest.approx(110 / 99 - 1)
    price = outcome_at(store["reader"], "yfinance", NVDA, D1, config=LabelConfig(3, PRICE, "p-1"), at=at,
                       calendar=CAL, coverage=coverage(at, types=(ActionType.SPLIT,)))
    assert price.value == pytest.approx((55 * 2) / 100 - 1)
    assert (total.start_session, total.end_session) == (D1, D4)
    assert total.outcome_end == CAL.session(D4).close


@pytest.mark.unit
def test_session_returns_give_one_observation_per_adjacent_pair(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "110"), bar(D3, "99")], import_id="b")
    at = utc(2024, 3, 8, 22)
    obs = session_returns(store["reader"], "yfinance", NVDA, D1, D3, at=at, calendar=CAL,
                          coverage=coverage(at, types=(ActionType.SPLIT,)), basis=PRICE)
    assert [(o.start_session, o.end_session) for o in obs] == [(D1, D2), (D2, D3)]
    assert [o.value for o in obs] == [pytest.approx(0.1), pytest.approx(-0.1)]


# ------------------------------------------------------------------ point in time and providers


@pytest.mark.unit
def test_a_future_split_does_not_count_at_an_earlier_t(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "101")], import_id="b")
    store["writer"].write_corporate_actions([action(D3, ratio="2")], import_id="a")
    obs = one_day(store, PRICE, at=utc(2024, 3, 5, 22))
    assert obs.value == pytest.approx(0.01) and obs.action_refs == ()


@pytest.mark.unit
def test_a_late_dividend_correction_is_excluded_at_an_earlier_t(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, dividend="1", received_at=utc(2024, 3, 5, 12))], import_id="a1")
    store["writer"].write_corporate_actions([action(D2, dividend="2", received_at=utc(2024, 3, 20, 12))], import_id="a2")
    early = one_day(store, TOTAL, at=utc(2024, 3, 8, 22))
    later = one_day(store, TOTAL, at=utc(2024, 3, 21, 22))
    assert early.value == 0.0 and later.value == pytest.approx(0.01)
    assert [a.revision for a in early.action_refs] == [1] and [a.revision for a in later.action_refs] == [2]


@pytest.mark.unit
def test_another_providers_actions_never_apply(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "50")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, ratio="2", source="testvendor")], import_id="tv")
    assert one_day(store, PRICE).value == pytest.approx(-0.5)


@pytest.mark.unit
def test_full_references_and_backfill_labels_are_preserved(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "50")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, ratio="2")], import_id="a")
    obs = one_day(store, PRICE)
    assert [(r.start_time, r.revision, r.import_id) for r in obs.bar_refs] == [
        (CAL.session(D1).open, 1, "b"), (CAL.session(D2).open, 1, "b")]
    assert all(r.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED for r in obs.bar_refs)
    [split] = obs.action_refs
    assert split.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED and split.ex_date == D2
    assert obs.available_from == max(CAL.session(D2).close, ex_date_start(D2, TZ))
    assert obs.coverage.established


# ------------------------------------------------------------------ unavailable, never zero


@pytest.mark.unit
def test_a_missing_internal_session_is_unavailable_not_compressed(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99"), bar(D4, "120")], import_id="b")
    at = utc(2024, 3, 8, 22)
    obs = outcome_at(store["reader"], "yfinance", NVDA, D1, config=LabelConfig(3, PRICE, "p"), at=at, calendar=CAL,
                     coverage=coverage(at))
    assert obs.value is None and str(D3) in obs.unavailable_reason


@pytest.mark.unit
def test_a_missing_previous_close_is_unavailable(store):
    store["writer"].write_candles([bar(D2, "99")], import_id="b")
    obs = one_day(store, TOTAL)
    assert obs.value is None and str(D1) in obs.unavailable_reason


@pytest.mark.unit
def test_unestablished_dividend_coverage_makes_total_return_unavailable_but_not_price_return(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99")], import_id="b")
    at = utc(2024, 3, 8, 22)
    splits_only = coverage(at, types=(ActionType.SPLIT,))
    total = one_day(store, TOTAL, cov=splits_only)
    assert total.value is None and "DIVIDEND" in total.unavailable_reason
    assert one_day(store, PRICE, cov=splits_only).value == pytest.approx(-0.01)


@pytest.mark.unit
def test_an_unsupported_action_type_makes_the_outcome_unavailable(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, action_type=ActionType.SYMBOL_CHANGE)], import_id="a")
    obs = one_day(store, PRICE)
    assert obs.value is None and "SYMBOL_CHANGE" in obs.unavailable_reason


@pytest.mark.unit
def test_an_outcome_not_complete_at_t_is_unavailable(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99")], import_id="b")
    at = utc(2024, 3, 5, 22)
    obs = outcome_at(store["reader"], "yfinance", NVDA, D1, config=LabelConfig(5, PRICE, "p"), at=at, calendar=CAL,
                     coverage=coverage(at))
    assert obs.value is None and "complete" in obs.unavailable_reason


# ------------------------------------------------------------------ horizons and eligibility


@pytest.mark.unit
def test_the_horizon_counts_sessions_across_holidays_and_half_days(store):
    days = [s.date for s in CAL.sessions_between(date(2024, 6, 14), date(2024, 7, 10))]
    store["writer"].write_candles([bar(d, "100") for d in days], import_id="b")
    at = utc(2024, 7, 11, 22)
    obs = outcome_at(store["reader"], "yfinance", NVDA, date(2024, 6, 14), config=LabelConfig(5, PRICE, "p"),
                     at=at, calendar=CAL, coverage=coverage(at))
    assert obs.end_session == date(2024, 6, 24)  # 17, 18, (19 holiday), 20, 21, 24
    half = outcome_at(store["reader"], "yfinance", NVDA, date(2024, 7, 2), config=LabelConfig(1, PRICE, "p"), at=at,
                      calendar=CAL, coverage=coverage(at))
    assert half.end_session == date(2024, 7, 3) and half.outcome_end == CAL.session(date(2024, 7, 3)).close


@pytest.mark.unit
def test_labels_ending_after_or_observed_after_or_computed_after_the_cutoff_are_not_eligible(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99")], import_id="b")
    at = utc(2024, 3, 8, 22)
    obs = one_day(store, PRICE, at=at)
    assert training_eligible(obs, at)
    assert not training_eligible(obs, CAL.session(D2).close - timedelta(seconds=1))  # ends after the cutoff
    late_input = replace(obs, available_from=at + timedelta(days=1))
    assert not training_eligible(late_input, at)  # an input observed after the cutoff
    assert not training_eligible(obs, at - timedelta(hours=1))  # computed (as_of) after the cutoff
    assert not training_eligible(replace(obs, value=None, unavailable_reason="x"), at)


@pytest.mark.unit
def test_a_correction_after_the_cutoff_cannot_leak_into_the_label_computed_at_the_cutoff(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "99")], import_id="b")
    store["writer"].write_candles([bar(D2, "200", received_at=utc(2024, 3, 20))], import_id="fix")
    cutoff = utc(2024, 3, 8, 22)
    at_cutoff = one_day(store, PRICE, at=cutoff)
    assert at_cutoff.value == pytest.approx(-0.01) and training_eligible(at_cutoff, cutoff)
    today = one_day(store, PRICE, at=utc(2024, 3, 21))
    assert today.value == pytest.approx(1.0) and not training_eligible(today, cutoff)


@pytest.mark.unit
def test_label_config_is_validated():
    for bad in ({"horizon_sessions": 0}, {"horizon_sessions": True}, {"basis": "LOG_RETURN"}, {"version": ""}):
        values = {"horizon_sessions": 5, "basis": PRICE, "version": "labels-0.1.0", **bad}
        with pytest.raises((TypeError, ValueError)):
            LabelConfig(**values)


@pytest.mark.unit
def test_stored_files_are_unchanged_and_invalid_inputs_refused(store):
    store["writer"].write_candles([bar(D1, "100"), bar(D2, "50")], import_id="b")
    store["writer"].write_corporate_actions([action(D2, ratio="2")], import_id="a")

    def tree():
        digest = hashlib.sha256()
        for path in sorted(p for p in store["root"].rglob("*") if p.is_file()):
            digest.update(path.read_bytes())
        return digest.hexdigest()

    before = tree()
    one_day(store, TOTAL)
    assert tree() == before
    at = utc(2024, 3, 8, 22)
    with pytest.raises(ValueError):
        session_returns(store["reader"], "yfinance", NVDA, D2, D1, at=at, calendar=CAL, coverage=coverage(at),
                        basis=PRICE)
    with pytest.raises(ValueError):
        session_returns(store["reader"], "yfinance", NVDA, D1, D2, at=datetime(2024, 3, 8), calendar=CAL,
                        coverage=coverage(at), basis=PRICE)
    assert isinstance(one_day(store, PRICE), ReturnObservation)
