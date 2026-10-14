"""The point-in-time split-adjusted daily view (ADR-007, ADR-009; docs/tasks/M2-00.md).

Stored prices stay raw. The view divides each bar's prices by the product of
the split ratios that were available and effective at T and whose ex-date is
after the bar, using only what was visible at T and only established action
coverage. It is never stored and is not a Candle.
"""

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, Candle, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType, ex_date_start
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import (
    ActionObservation,
    CandleObservation,
    MarketDataWriter,
)
from investment_engine.quant.adjusted import (
    ActionCoverage,
    AdjustedBar,
    AdjustedBasis,
    AdjustmentUnavailable,
    VerificationEvidence,
    adjusted_daily,
    establish_coverage,
)

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
TZ = "America/New_York"
VERSION = "yahoo-verification-2026-10-12/yfinance-1.7.0"


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def bar(d, close, *, source="yfinance", received_at=None, volume="1000", currency="USD"):
    s = CAL.session(d)
    close = Decimal(close)
    received_at = received_at or s.close + timedelta(minutes=5)
    return CandleObservation(
        source=source, instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=close, high=close, low=close, close=close, currency=currency, volume=Decimal(volume),
        state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received_at,
        processed_at=received_at, backfill_available_from=s.close,
    )


def split(ex, ratio, *, source="yfinance", received_at=None, backfill=True):
    received_at = received_at or utc(2026, 10, 12, 20)
    return ActionObservation(
        source=source, instrument_id=NVDA, currency="USD", exchange_timezone=TZ, action_type=ActionType.SPLIT,
        ex_date=ex, ratio=Decimal(ratio), amount=None, amount_basis=None, new_symbol=None, source_version="1.7.0",
        received_at=received_at, processed_at=received_at,
        backfill_available_from=ex_date_start(ex, TZ) if backfill else None,
    )


def evidence(*, source="yfinance", first=date(2019, 1, 1), last=date(2026, 10, 12), status="COMPLETE",
             action_type=ActionType.SPLIT):
    return VerificationEvidence(
        provider=source, instrument_id=NVDA, action_type=action_type, first=first, last=last,
        request_first=first, request_last=last, verification=VERSION, status=status)


def coverage(at, *, source="yfinance", first=date(2019, 1, 1), last=date(2026, 10, 12), ev=None):
    return establish_coverage(
        ev if ev is not None else (evidence(source=source),), source=source, instrument_id=NVDA,
        types=(ActionType.SPLIT,), first=first, last=last, as_of=at,
        reason="verified Yahoo split history; research assumption, not a historical observation")


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "market"
    return {"writer": MarketDataWriter(root), "reader": MarketDataReader(root), "root": root}


def view(store, first, last, at, *, source="yfinance", cov=None):
    return adjusted_daily(store["reader"], source, NVDA, first, last, at=at, calendar=CAL,
                          coverage=cov if cov is not None else coverage(at, source=source))


def closes(bars):
    return {b.session_date: b.close for b in bars}


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


# ------------------------------------------------------------------ the NVDA 2024 split


JUN_06, JUN_07, JUN_10, JUN_11 = date(2024, 6, 6), date(2024, 6, 7), date(2024, 6, 10), date(2024, 6, 11)


@pytest.fixture
def nvda_2024(store):
    store["writer"].write_candles([bar(JUN_06, "1209.98"), bar(JUN_07, "1208.88"), bar(JUN_10, "121.79"),
                                   bar(JUN_11, "120.91")], import_id="bars")
    store["writer"].write_corporate_actions([split(JUN_10, "10")], import_id="actions")
    return store


@pytest.mark.unit
def test_after_the_ex_date_earlier_bars_are_divided_by_ten_and_closes_are_continuous(nvda_2024):
    at = utc(2024, 6, 11, 21)
    bars = view(nvda_2024, JUN_06, JUN_11, at)
    c = closes(bars)
    assert c[JUN_07] == pytest.approx(120.888)
    assert c[JUN_10] == pytest.approx(121.79)
    assert abs(c[JUN_10] / c[JUN_07] - 1) < 0.01  # the day's real move, not a 90% crash
    by_day = {b.session_date: b for b in bars}
    assert by_day[JUN_07].factor == Decimal("10") and by_day[JUN_10].factor == Decimal("1")
    assert by_day[JUN_07].volume == pytest.approx(10000.0)  # volume is multiplied by the factor
    assert all(isinstance(b, AdjustedBar) and not isinstance(b, Candle) for b in bars)
    assert all(b.basis is AdjustedBasis.SPLIT_ADJUSTED_AS_OF and b.as_of == at for b in bars)


@pytest.mark.unit
def test_before_the_ex_date_no_adjustment_is_applied(nvda_2024):
    at = utc(2024, 6, 7, 21)
    c = closes(view(nvda_2024, JUN_06, JUN_07, at))
    assert c == {JUN_06: pytest.approx(1209.98), JUN_07: pytest.approx(1208.88)}


@pytest.mark.unit
def test_a_split_after_the_last_requested_bar_but_effective_by_t_still_counts(nvda_2024):
    at = utc(2024, 6, 11, 21)
    c = closes(view(nvda_2024, JUN_06, JUN_07, at))
    assert c[JUN_07] == pytest.approx(120.888)


@pytest.mark.unit
def test_a_split_effective_only_after_t_does_not_count(store):
    store["writer"].write_candles([bar(JUN_07, "1208.88")], import_id="bars")
    # Announced and observed before T, but its ex-date is after T's session date.
    store["writer"].write_corporate_actions([split(JUN_10, "10", received_at=utc(2024, 5, 22, 21), backfill=False)],
                                            import_id="announced")
    at = utc(2024, 6, 7, 21)
    assert closes(view(store, JUN_07, JUN_07, at)) == {JUN_07: pytest.approx(1208.88)}


# ------------------------------------------------------------------ point in time


@pytest.mark.unit
def test_a_split_revision_available_only_after_t_is_not_applied(store):
    store["writer"].write_candles([bar(JUN_07, "1208.88"), bar(JUN_10, "121.79")], import_id="bars")
    # Observed on 12 June, so revision 1 is backfilled to the ex-date start; a later
    # import with a changed ratio is an OBSERVED revision 2, available only from its receipt.
    store["writer"].write_corporate_actions([split(JUN_10, "10", received_at=utc(2024, 6, 10, 12))], import_id="a1")
    store["writer"].write_corporate_actions([split(JUN_10, "5", received_at=utc(2024, 6, 20, 12))], import_id="a2")
    early = utc(2024, 6, 11, 21)
    later = utc(2024, 6, 21, 21)
    assert closes(view(store, JUN_07, JUN_10, early))[JUN_07] == pytest.approx(120.888)
    assert closes(view(store, JUN_07, JUN_10, later))[JUN_07] == pytest.approx(241.776)
    # The view at the earlier T is unchanged by the later correction.
    assert closes(view(store, JUN_07, JUN_10, early))[JUN_07] == pytest.approx(120.888)


@pytest.mark.unit
def test_a_bar_correction_after_t_does_not_change_the_view_at_t(store):
    store["writer"].write_candles([bar(JUN_07, "1208.88")], import_id="b1")
    store["writer"].write_candles([bar(JUN_07, "1300.00", received_at=utc(2024, 6, 20, 12))], import_id="b2")
    store["writer"].write_corporate_actions([split(JUN_10, "10")], import_id="a")
    at = utc(2024, 6, 11, 21)
    [only] = view(store, JUN_07, JUN_07, at)
    assert only.close == pytest.approx(120.888)
    assert only.raw_ref.revision == 1


@pytest.mark.unit
def test_the_factor_is_exact_decimal_until_the_single_float_conversion(store):
    store["writer"].write_candles([bar(JUN_07, "100.0000")], import_id="bars")
    store["writer"].write_corporate_actions([split(JUN_10, "3")], import_id="a")
    [only] = view(store, JUN_07, JUN_07, utc(2024, 6, 11, 21))
    assert only.factor == Decimal("3")
    assert only.close == float(Decimal("100") / Decimal("3"))


@pytest.mark.unit
def test_two_splits_multiply(store):
    store["writer"].write_candles([bar(date(2021, 7, 19), "751.19")], import_id="bars")
    store["writer"].write_corporate_actions([split(date(2021, 7, 20), "4"), split(JUN_10, "10")], import_id="a")
    [only] = view(store, date(2021, 7, 19), date(2021, 7, 19), utc(2024, 6, 11, 21))
    assert only.factor == Decimal("40")
    assert only.close == pytest.approx(751.19 / 40)


# ------------------------------------------------------------------ providers, gaps, references


@pytest.mark.unit
def test_a_testvendor_split_never_adjusts_yfinance_bars(store):
    store["writer"].write_candles([bar(JUN_07, "1208.88")], import_id="bars")
    store["writer"].write_corporate_actions([split(JUN_10, "10", source="testvendor")], import_id="tv")
    assert closes(view(store, JUN_07, JUN_07, utc(2024, 6, 11, 21)))[JUN_07] == pytest.approx(1208.88)


@pytest.mark.unit
def test_a_missing_session_stays_missing(store):
    store["writer"].write_candles([bar(JUN_06, "100"), bar(JUN_10, "100")], import_id="bars")
    bars = view(store, JUN_06, JUN_10, utc(2024, 6, 11, 21))
    assert [b.session_date for b in bars] == [JUN_06, JUN_10]


@pytest.mark.unit
def test_full_references_and_backfill_labels_survive(nvda_2024):
    at = utc(2024, 6, 11, 21)
    by_day = {b.session_date: b for b in view(nvda_2024, JUN_06, JUN_11, at)}
    ref = by_day[JUN_07].raw_ref
    assert (ref.source, ref.instrument_id, ref.timeframe, ref.start_time) == (
        "yfinance", NVDA, Timeframe.D1, CAL.session(JUN_07).open)
    assert ref.revision == 1 and ref.import_id == "bars"
    assert ref.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED
    [action] = by_day[JUN_07].action_refs
    assert (action.action_type, action.ex_date, action.revision, action.import_id) == (
        ActionType.SPLIT, JUN_10, 1, "actions")
    assert action.availability_basis is AvailabilityBasis.BACKFILL_ASSUMED
    assert by_day[JUN_10].action_refs == ()  # no split after 10 June applies to it


@pytest.mark.unit
def test_stored_files_are_unchanged_by_successful_and_failed_calls(nvda_2024):
    before = tree_hash(nvda_2024["root"])
    at = utc(2024, 6, 11, 21)
    view(nvda_2024, JUN_06, JUN_11, at)
    with pytest.raises(AdjustmentUnavailable):
        view(nvda_2024, JUN_06, JUN_11, at, cov=replace(coverage(at), established=False))
    assert tree_hash(nvda_2024["root"]) == before


# ------------------------------------------------------------------ coverage evidence


@pytest.mark.unit
def test_established_coverage_with_zero_splits_succeeds(store):
    store["writer"].write_candles([bar(JUN_07, "1208.88")], import_id="bars")
    [only] = view(store, JUN_07, JUN_07, utc(2024, 6, 11, 21))
    assert only.factor == Decimal("1") and only.action_refs == ()


@pytest.mark.unit
def test_unestablished_coverage_raises_so_the_policy_can_abstain(nvda_2024):
    at = utc(2024, 6, 11, 21)
    unestablished = establish_coverage((), source="yfinance", instrument_id=NVDA, types=(ActionType.SPLIT,),
                                       first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=at, reason="none")
    assert not unestablished.established
    with pytest.raises(AdjustmentUnavailable, match="coverage"):
        view(nvda_2024, JUN_06, JUN_11, at, cov=unestablished)


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"source": "testvendor"}, {"instrument_id": "EQ_US_MSFT"}, {"types": (ActionType.DIVIDEND,)},
    {"first": date(2024, 6, 7)}, {"last": date(2024, 6, 10)}, {"as_of": utc(2024, 6, 12, 21)},
])
def test_coverage_for_another_provider_instrument_type_time_or_short_range_is_refused(nvda_2024, change):
    at = utc(2024, 6, 11, 21)
    with pytest.raises(AdjustmentUnavailable):
        view(nvda_2024, JUN_06, JUN_11, at, cov=replace(coverage(at), **change))


@pytest.mark.unit
@pytest.mark.parametrize("status", ["PARTIAL", "FAILED"])
def test_partial_or_failed_verification_cannot_establish_zero_splits(store, status):
    at = utc(2024, 6, 11, 21)
    cov = coverage(at, ev=(evidence(status=status),))
    assert not cov.established
    store["writer"].write_candles([bar(JUN_07, "1208.88")], import_id="bars")
    with pytest.raises(AdjustmentUnavailable):
        view(store, JUN_07, JUN_07, at, cov=cov)


@pytest.mark.unit
@pytest.mark.parametrize("ev", [
    (), (evidence(source="testvendor"),), (evidence(action_type=ActionType.DIVIDEND),),
    (evidence(first=date(2024, 1, 2)),),
])
def test_coverage_without_matching_completed_verification_is_not_established(ev):
    assert not coverage(utc(2024, 6, 11, 21), ev=ev).established


@pytest.mark.unit
@pytest.mark.parametrize("refs", [("trust me",), ()])
def test_hand_made_established_coverage_without_verification_references_is_refused(store, refs):
    at = utc(2024, 6, 11, 21)
    store["writer"].write_candles([bar(JUN_07, "1208.88")], import_id="bars")
    forged = ActionCoverage(source="yfinance", instrument_id=NVDA, types=(ActionType.SPLIT,),
                            first=date(2019, 1, 1), last=date(2026, 10, 12), as_of=at, established=True,
                            evidence_refs=refs, reason="forged")
    with pytest.raises(AdjustmentUnavailable, match="evidence"):
        view(store, JUN_07, JUN_07, at, cov=forged)


@pytest.mark.unit
def test_evidence_references_round_trip_and_survive_into_the_coverage():
    ev = evidence()
    assert VerificationEvidence.parse(ev.ref) == ev
    cov = coverage(utc(2024, 6, 11, 21))
    assert cov.evidence_refs == (ev.ref,)


@pytest.mark.unit
def test_evidence_whose_range_ends_after_its_request_is_refused():
    with pytest.raises(ValueError):
        replace(evidence(), request_last=date(2026, 1, 1))


# ------------------------------------------------------------------ completed bars only (correction 5)


@pytest.mark.unit
def test_a_bar_received_before_it_ended_is_refused_as_malformed(store):
    s = CAL.session(JUN_07)
    early = s.close - timedelta(hours=1)
    store["writer"].write_candles([replace(bar(JUN_07, "1208.88"), received_at=early, processed_at=early)],
                                  import_id="bars")
    with pytest.raises(ValueError, match="received"):
        view(store, JUN_07, JUN_07, utc(2024, 6, 11, 21))


class _Reader:
    """A stand-in reader that returns exactly the given rows, to probe validation."""

    def __init__(self, candles=(), actions=()):
        self.candles, self.actions = list(candles), list(actions)

    def candles_visible_at(self, source, instrument_id, timeframe, start, end, at):
        return list(self.candles)

    def actions_visible_at(self, source, instrument_id, start, end, at, types=None):
        return list(self.actions)


def stored(observation, revision=1):
    o = observation
    return Candle(o.source, o.instrument_id, o.timeframe, o.start_time, o.end_time, o.open, o.high, o.low,
                  o.close, o.currency, o.volume, o.state, o.source_version, o.price_basis, o.volume_basis, "imp",
                  o.event_time, o.received_at, o.processed_at, revision, o.backfill_available_from,
                  AvailabilityBasis.BACKFILL_ASSUMED)


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"state": BarState.FORMING},
    {"source": "testvendor"},
    {"instrument_id": "EQ_US_MSFT"},
    {"timeframe": Timeframe.H1},
    {"currency": "EUR"},
])
def test_rows_for_another_identity_forming_or_another_currency_are_refused(change):
    at = utc(2024, 6, 11, 21)
    good = stored(bar(JUN_06, "100"))
    rows = [good, replace(stored(bar(JUN_07, "100")), **change)]
    with pytest.raises(ValueError):
        adjusted_daily(_Reader(rows), "yfinance", NVDA, JUN_06, JUN_07, at=at, calendar=CAL, coverage=coverage(at))


@pytest.mark.unit
def test_a_bar_ending_after_t_or_available_after_t_is_refused():
    at = utc(2024, 6, 7, 18)  # during the 7 June session
    open_bar = stored(bar(JUN_07, "100"))
    with pytest.raises(ValueError):
        adjusted_daily(_Reader([open_bar]), "yfinance", NVDA, JUN_07, JUN_07, at=at, calendar=CAL,
                       coverage=coverage(at))


@pytest.mark.unit
def test_a_bar_off_the_session_boundaries_or_duplicated_is_refused():
    at = utc(2024, 6, 11, 21)
    good = stored(bar(JUN_07, "100"))
    shifted = replace(good, end_time=good.end_time - timedelta(minutes=1), event_time=good.end_time - timedelta(minutes=1))
    for rows in ([shifted], [good, good]):
        with pytest.raises(ValueError):
            adjusted_daily(_Reader(rows), "yfinance", NVDA, JUN_07, JUN_07, at=at, calendar=CAL,
                           coverage=coverage(at))


@pytest.mark.unit
def test_a_split_row_from_another_provider_or_not_yet_available_is_refused(nvda_2024):
    at = utc(2024, 6, 11, 21)
    actions = nvda_2024["reader"].actions_visible_at("yfinance", NVDA, date(2019, 1, 1), date(2027, 1, 1), at)
    candles = nvda_2024["reader"].candles_visible_at("yfinance", NVDA, Timeframe.D1, utc(2024, 6, 1),
                                                     utc(2024, 6, 12), at)
    for bad in (replace(actions[0], source="testvendor"),
                replace(actions[0], available_from=at + timedelta(seconds=1),
                        received_at=at + timedelta(seconds=1), processed_at=at + timedelta(seconds=1),
                        availability_basis=AvailabilityBasis.OBSERVED)):
        with pytest.raises(ValueError):
            adjusted_daily(_Reader(candles, [bad]), "yfinance", NVDA, JUN_06, JUN_11, at=at, calendar=CAL,
                           coverage=coverage(at))


@pytest.mark.unit
def test_arguments_are_checked():
    at = utc(2024, 6, 11, 21)
    with pytest.raises(ValueError):
        adjusted_daily(_Reader(), "yfinance", NVDA, JUN_11, JUN_06, at=at, calendar=CAL, coverage=coverage(at))
    with pytest.raises(ValueError):
        adjusted_daily(_Reader(), "yfinance", NVDA, JUN_06, JUN_11, at=datetime(2024, 6, 11, 21),
                       calendar=CAL, coverage=coverage(at))
    with pytest.raises(ValueError):
        adjusted_daily(_Reader(), "yfinance", NVDA, JUN_06, JUN_11, at=at, calendar=CAL, coverage=coverage(at),
                       basis="TOTAL_RETURN")


@pytest.mark.unit
def test_there_is_no_write_path():
    import investment_engine.quant.adjusted as module

    assert not any(name.startswith(("write", "store", "save")) for name in dir(module))
