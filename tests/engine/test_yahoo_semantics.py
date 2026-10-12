"""Yahoo field semantics, decided from evidence (docs/tasks/M1-12.md).

Each field (daily and hourly prices and volume, dividend amounts, split
ratios) is decided separately from independent, cited references in
fixtures/reference/nvda_reference.json, compared with the recorded yfinance
responses in fixtures/yfinance/. The decisions must match the committed
YAHOO_VERIFICATION record. Synthetic cases cover each outcome, including the
volume counterexample: dollar-volume continuity alone never decides.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.corporate_actions import (
    ActionType,
    AmountBasis,
    CorporateAction,
    ex_date_start,
)
from investment_engine.market.importers.yahoo_semantics import (
    PROVENANCE_DOCUMENT,
    YAHOO_VERIFICATION,
    DividendAnchor,
    FieldBlocked,
    FieldKey,
    OutsideVerifiedRange,
    PriceAnchor,
    Semantics,
    SplitHistoryMismatch,
    Transformation,
    VersionMismatch,
    VolumeAnchor,
    check_cited_splits,
    check_same_split_history,
    close_is_dividend_adjusted,
    decide_daily_volume,
    decide_dividends,
    decide_hourly_prices,
    decide_hourly_volume,
    decide_prices,
    decide_split_ratios,
    dollar_volume_continuity,
    hourly_differences,
    in_range_splits,
    load_recording,
    reconstruct_price,
    reconstruct_volume,
    recorded_series,
    split_factor,
    transformation_for,
    transformation_of,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
REFERENCE = json.loads((FIXTURES / "reference" / "nvda_reference.json").read_text(encoding="utf-8"))
DOWNLOAD = date(2026, 10, 12)
FETCHED = datetime(2026, 10, 12, 8, 25, tzinfo=UTC)


def recording(name: str):
    return load_recording(FIXTURES / "yfinance" / name)


def split(ex_date: date, ratio: str) -> CorporateAction:
    return CorporateAction(
        source="yfinance", instrument_id="EQ_US_NVDA", currency="USD", exchange_timezone="America/New_York",
        action_type=ActionType.SPLIT, ex_date=ex_date, ratio=Decimal(ratio), amount=None, amount_basis=None,
        new_symbol=None, source_version="1.7.0", import_id="test", received_at=FETCHED, processed_at=FETCHED,
        revision=1, available_from=ex_date_start(ex_date, "America/New_York"),
        availability_basis=AvailabilityBasis.BACKFILL_ASSUMED,
    )


CITED = [split(date(2021, 7, 20), "4"), split(date(2024, 6, 10), "10")]


def recorded_splits() -> list[tuple[date, Decimal]]:
    return recorded_series(recording("nvda_splits_before.json"), "Stock Splits")


def daily_rows() -> dict[date, dict]:
    rec = recording("nvda_1d_2019_2026.json")
    return {d: dict(zip(rec.columns, values, strict=True)) for d, values in rec.by_date()}


def factor(d: date) -> Decimal:
    return split_factor(CITED, d, DOWNLOAD)


# ------------------------------------------------------------------ the record


@pytest.mark.unit
def test_the_record_states_its_range_and_cited_splits():
    assert YAHOO_VERIFICATION.instrument_id == "EQ_US_NVDA"
    assert YAHOO_VERIFICATION.yfinance_version == "1.7.0"
    assert YAHOO_VERIFICATION.verified_from == date(2019, 1, 1)
    assert YAHOO_VERIFICATION.cited_splits == ((date(2021, 7, 20), Decimal("4")), (date(2024, 6, 10), Decimal("10")))
    assert YAHOO_VERIFICATION.split_history_call == "Ticker(symbol).splits"
    assert set(YAHOO_VERIFICATION.fields) == set(FieldKey)


@pytest.mark.unit
def test_the_cited_splits_are_the_reference_files_in_range_splits():
    cited = tuple(
        (date.fromisoformat(s["ex_date"]), Decimal(s["ratio"]))
        for s in REFERENCE["splits"]
        if s["ex_date"] is not None and date.fromisoformat(s["ex_date"]) >= YAHOO_VERIFICATION.verified_from
    )
    assert cited == YAHOO_VERIFICATION.cited_splits
    for s in REFERENCE["splits"]:
        assert s["covered_range"] == (s["ex_date"] is not None and s["ex_date"] >= "2019-01-01")


@pytest.mark.unit
def test_the_provenance_document_mirrors_the_record():
    text = (ROOT / PROVENANCE_DOCUMENT).read_text(encoding="utf-8")
    assert YAHOO_VERIFICATION.document == PROVENANCE_DOCUMENT
    for key, field in YAHOO_VERIFICATION.fields.items():
        assert f"| `{key}` | `{field.semantics}` | `{field.transformation}` |" in text
    assert "verified_from" in text and "2019-01-01" in text


@pytest.mark.unit
def test_every_cited_source_is_defined_and_counted():
    sources = REFERENCE["sources"]
    assert len(sources) == 17
    cited = {
        s
        for group in ("splits", "dividends", "price_anchors", "volume_anchors")
        for entry in REFERENCE[group]
        for s in entry["sources"]
    }
    assert cited <= set(sources)


# ------------------------------------------------------------------ recordings


@pytest.mark.unit
def test_recordings_read_back_exactly():
    rec = recording("nvda_1d_2019_2026.json")
    assert rec.columns == ("Open", "High", "Low", "Close", "Adj Close", "Volume")
    assert len(rec.rows) == rec.metadata["rows"] == 1954
    first_date, first = rec.by_date()[0]
    assert first_date == date(2019, 1, 2)
    assert first[3] == 3.4054999351501465  # Close, exactly as recorded
    assert rec.metadata["yfinance_version"] == "1.7.0"


@pytest.mark.unit
def test_recorded_split_history_is_full_and_unchanged_across_the_run():
    before = recorded_splits()
    after = recorded_series(recording("nvda_splits_after.json"), "Stock Splits")
    assert [d for d, _ in before] == [
        date(2000, 6, 27), date(2001, 9, 12), date(2006, 4, 7), date(2007, 9, 11), date(2021, 7, 20), date(2024, 6, 10)
    ]
    check_same_split_history(before, after)  # no exception


@pytest.mark.unit
def test_a_date_filtered_response_has_no_later_splits():
    # The 2021-Q1 request with actions=True: splits followed on 2021-07-20 and
    # 2024-06-10, yet the response reports none. It must never be the split history.
    rec = recording("nvda_1d_2021q1_with_actions.json")
    assert rec.metadata["parameters"]["actions"] is True
    assert recorded_series(rec, "Stock Splits") == []
    with pytest.raises(SplitHistoryMismatch, match="missing"):
        check_cited_splits(recorded_series(rec, "Stock Splits"))


# ------------------------------------------------------------------ split factor


@pytest.mark.unit
@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2021, 7, 19), "40"),  # last session before the 4:1 split
        (date(2021, 7, 20), "10"),  # its ex-date: only the later 10:1 split remains
        (date(2024, 6, 7), "10"),
        (date(2024, 6, 10), "1"),
        (date(2026, 10, 9), "1"),
    ],
)
def test_split_factor_around_each_ex_date(d, expected):
    assert split_factor(CITED, d, DOWNLOAD) == Decimal(expected)


@pytest.mark.unit
def test_a_bar_years_before_still_receives_every_later_split():
    assert split_factor(CITED, date(2019, 1, 2), DOWNLOAD) == Decimal("40")


@pytest.mark.unit
def test_only_splits_up_to_the_download_date_count():
    assert split_factor(CITED, date(2021, 7, 19), date(2024, 6, 9)) == Decimal("4")
    assert split_factor(CITED, date(2021, 7, 19), date(2024, 6, 10)) == Decimal("40")


@pytest.mark.unit
def test_a_request_window_that_excludes_a_later_split_does_not_change_f():
    # F has no window: a bar in a window ending 2021-03-31 still gets both later splits.
    for d in (date(2021, 1, 4), date(2021, 3, 30)):
        assert split_factor(CITED, d, DOWNLOAD) == Decimal("40")


@pytest.mark.unit
def test_split_factor_refuses_dates_before_the_verified_range():
    with pytest.raises(OutsideVerifiedRange):
        split_factor(CITED, date(2018, 12, 31), DOWNLOAD)


@pytest.mark.unit
def test_split_factor_refuses_splits_before_the_verified_range():
    with pytest.raises(OutsideVerifiedRange):
        split_factor([split(date(2007, 9, 11), "1.5"), *CITED], date(2021, 1, 4), DOWNLOAD)


@pytest.mark.unit
def test_split_factor_takes_only_split_actions():
    dividend = replace(
        CITED[0], action_type=ActionType.DIVIDEND, ratio=None,
        amount=__import__("investment_engine.money", fromlist=["Money"]).Money(Decimal("0.16"), "USD"),
        amount_basis=AmountBasis.AS_REPORTED,
    )
    with pytest.raises(ValueError, match="SPLIT"):
        split_factor([dividend], date(2021, 1, 4), DOWNLOAD)


# ------------------------------------------------------------------ split-history checks


@pytest.mark.unit
def test_the_recorded_history_matches_the_cited_splits_in_range():
    assert check_cited_splits(recorded_splits()) == YAHOO_VERIFICATION.cited_splits


@pytest.mark.unit
def test_a_before_and_after_mismatch_aborts():
    before = recorded_splits()
    with pytest.raises(SplitHistoryMismatch, match="mid-run"):
        check_same_split_history(before, [*before, (date(2026, 10, 12), Decimal("2"))])


@pytest.mark.unit
@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: [*s, (date(2025, 3, 3), Decimal("2"))], "extra"),  # a planted 2025 split
        (lambda s: [x for x in s if x[0] != date(2021, 7, 20)], "missing"),
        (lambda s: [(d, Decimal("5") if d == date(2024, 6, 10) else r) for d, r in s], "ratio"),
        (lambda s: [(date(2024, 6, 11) if d == date(2024, 6, 10) else d, r) for d, r in s], "missing"),
    ],
    ids=["extra", "missing", "different-ratio", "shifted-ex-date"],
)
def test_an_in_range_difference_from_the_cited_splits_aborts(change, message):
    with pytest.raises(SplitHistoryMismatch, match=message):
        check_cited_splits(change(recorded_splits()))


@pytest.mark.unit
def test_pre_range_splits_are_ignored():
    moved = [(date(2001, 9, 17) if d == date(2001, 9, 12) else d, r) for d, r in recorded_splits()]
    assert check_cited_splits(moved) == check_cited_splits(recorded_splits())
    assert in_range_splits(moved) == in_range_splits(recorded_splits())
    assert [d for d, _ in in_range_splits(moved)] == [date(2021, 7, 20), date(2024, 6, 10)]


# ------------------------------------------------------------------ determination on the fixtures


def _price_anchors() -> list[PriceAnchor]:
    rows = daily_rows()
    column = {"close": "Close", "high": "High", "low": "Low", "open": "Open"}
    anchors = []
    for a in REFERENCE["price_anchors"]:
        if any(s.startswith("MW-ARCHIVE-") for s in a["sources"]):
            continue  # retained supporting evidence; the approved test uses the July citation
        d = date.fromisoformat(a["date"])
        anchors.append(PriceAnchor(d, Decimal(repr(rows[d][column[a["field"]]])), factor(d), Decimal(a["value"])))
    return anchors


def _volume_anchors(role: str) -> list[VolumeAnchor]:
    rows = daily_rows()
    return [
        VolumeAnchor(date.fromisoformat(a["date"]), Decimal(rows[date.fromisoformat(a["date"])]["Volume"]),
                     factor(date.fromisoformat(a["date"])), Decimal(a["shares"]))
        for a in REFERENCE["volume_anchors"]
        if a["role"].startswith(role)
    ]


def _dividend_anchors() -> list[DividendAnchor]:
    vendor = dict(recorded_series(recording("nvda_dividends.json"), "Dividends"))
    return [
        DividendAnchor(date.fromisoformat(a["ex_date"]), vendor[date.fromisoformat(a["ex_date"])],
                       factor(date.fromisoformat(a["ex_date"])), Decimal(a["declared_per_share"]))
        for a in REFERENCE["dividends"]
    ]


def _expected(key: FieldKey):
    return YAHOO_VERIFICATION.fields[key]


@pytest.mark.unit
def test_split_ratios_are_as_cited():
    semantics = decide_split_ratios(in_range_splits(recorded_splits()), YAHOO_VERIFICATION.cited_splits)
    assert semantics is _expected(FieldKey.SPLIT_RATIO).semantics is Semantics.UNADJUSTED
    assert transformation_of(FieldKey.SPLIT_RATIO, semantics) is _expected(FieldKey.SPLIT_RATIO).transformation


@pytest.mark.unit
def test_daily_prices_are_split_adjusted_and_reconstruct_exactly():
    anchors = _price_anchors()
    # One cited as-traded value per split epoch in range.
    assert {a.factor for a in anchors} == {Decimal("40"), Decimal("10"), Decimal("1")}
    rows = [r for d, r in daily_rows().items() if d < date(2026, 6, 4)]
    adjusted = close_is_dividend_adjusted([r["Close"] for r in rows], [r["Adj Close"] for r in rows])
    decision = decide_prices(anchors, dividend_adjusted=adjusted)
    assert adjusted is False
    assert decision.semantics is _expected(FieldKey.D1_PRICE).semantics is Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD
    assert decision.max_error == _expected(FieldKey.D1_PRICE).max_error
    assert decision.max_error <= Decimal("0.01")
    assert transformation_of(FieldKey.D1_PRICE, decision.semantics) is Transformation.SPLIT_RECONSTRUCTION
    for a in anchors:
        assert abs(reconstruct_price(a.vendor, a.factor) - a.cited) <= Decimal("0.01")


@pytest.mark.unit
def test_daily_volume_is_split_adjusted_under_the_daily_rule():
    decision = decide_daily_volume(_volume_anchors("decisive"), _volume_anchors("control"))
    assert decision.semantics is _expected(FieldKey.D1_VOLUME).semantics is Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD
    errors = decision.errors[Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD]
    assert [round(e, 4) for e in errors] == [Decimal("0.0114"), Decimal("0.0169")]
    assert all(e >= Decimal("9") for e in decision.errors[Semantics.UNADJUSTED])  # about 900% off
    assert [round(g, 4) for g in decision.control_gaps] == [Decimal("0.0207"), Decimal("0.0163")]
    assert round(decision.max_error, 4) == _expected(FieldKey.D1_VOLUME).max_error
    assert transformation_of(FieldKey.D1_VOLUME, decision.semantics) is Transformation.SPLIT_RECONSTRUCTION


@pytest.mark.unit
def test_dividends_are_split_adjusted_and_reconstruct_to_the_declared_amounts():
    anchors = _dividend_anchors()
    decision = decide_dividends(anchors)
    assert decision.semantics is _expected(FieldKey.DIVIDEND_AMOUNT).semantics
    assert decision.semantics is Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD
    assert [a.ex_date for a in anchors if a.factor > 1] == [date(2021, 6, 9), date(2024, 3, 5)]
    for a in anchors:
        assert reconstruct_price(a.vendor, a.factor) == a.declared


@pytest.mark.unit
def test_hourly_prices_stay_undetermined_with_unexplained_differences():
    hourly = recording("nvda_1h_730d.json")
    daily = recording("nvda_1d_2019_2026.json")
    in_vendor_units = hourly_differences(hourly, daily)
    as_traded = hourly_differences(hourly, daily, factor=factor)
    assert len({d.session for d in in_vendor_units}) == 169
    assert len({d.session for d in as_traded}) == 181
    worst = max(in_vendor_units, key=lambda d: d.difference)
    assert (worst.session, worst.extreme) == (date(2026, 2, 9), "high")
    assert worst.difference == Decimal("198.72500610351562") - Decimal("193.66000366210938")

    semantics = decide_hourly_prices(in_vendor_units, explained=False,
                                     split_method=Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD)
    assert semantics is _expected(FieldKey.H1_PRICE).semantics is Semantics.UNDETERMINED
    assert _expected(FieldKey.H1_PRICE).transformation is Transformation.BLOCKED
    assert transformation_of(FieldKey.H1_PRICE, semantics) is Transformation.BLOCKED


@pytest.mark.unit
def test_hourly_volume_is_blocked_without_comparable_hourly_references():
    assert REFERENCE["hourly_volume_anchors"] == []
    decision = decide_hourly_volume([], hourly_sum_ratios=(Decimal("0.967"), Decimal("0.954")))
    assert decision.semantics is _expected(FieldKey.H1_VOLUME).semantics is Semantics.UNDETERMINED
    assert decision.supporting == (Decimal("0.967"), Decimal("0.954"))  # recorded only
    assert transformation_of(FieldKey.H1_VOLUME, decision.semantics) is Transformation.BLOCKED
    assert _expected(FieldKey.H1_VOLUME).transformation is Transformation.BLOCKED


# ------------------------------------------------------------------ synthetic outcomes


@pytest.mark.unit
def test_unadjusted_volume_established_by_an_anchor_with_adjusted_prices():
    prices = decide_prices([PriceAnchor(date(2021, 7, 19), Decimal("18.7798"), Decimal("40"), Decimal("751.19"))],
                           dividend_adjusted=False)
    volume = decide_daily_volume([VolumeAnchor(date(2021, 7, 19), Decimal("1000"), Decimal("40"), Decimal("1000"))],
                                 [])
    assert transformation_of(FieldKey.D1_PRICE, prices.semantics) is Transformation.SPLIT_RECONSTRUCTION
    assert transformation_of(FieldKey.D1_VOLUME, volume.semantics) is Transformation.IDENTITY


@pytest.mark.unit
def test_a_dividend_adjusted_close_is_other_and_blocked():
    assert close_is_dividend_adjusted([10.0, 11.0], [10.0, 11.0]) is True
    decision = decide_prices([PriceAnchor(date(2021, 7, 19), Decimal("18.7798"), Decimal("40"), Decimal("751.19"))],
                             dividend_adjusted=True)
    assert decision.semantics is Semantics.OTHER
    assert transformation_of(FieldKey.D1_PRICE, decision.semantics) is Transformation.BLOCKED


@pytest.mark.unit
def test_prices_matching_both_or_neither_interpretation_are_undetermined():
    both = PriceAnchor(date(2024, 6, 10), Decimal("121.79"), Decimal("1"), Decimal("121.79"))
    neither = PriceAnchor(date(2021, 7, 19), Decimal("20"), Decimal("40"), Decimal("751.19"))
    assert decide_prices([both], dividend_adjusted=False).semantics is Semantics.UNDETERMINED
    assert decide_prices([neither], dividend_adjusted=False).semantics is Semantics.UNDETERMINED


@pytest.mark.unit
def test_volume_without_primary_evidence_is_blocked_even_where_f_is_1():
    decision = decide_daily_volume([], [])
    assert decision.semantics is Semantics.UNDETERMINED
    for key in (FieldKey.D1_VOLUME, FieldKey.H1_VOLUME):
        # never the F == 1 identity exception: volume needs primary evidence
        assert transformation_of(key, Semantics.UNDETERMINED) is Transformation.BLOCKED


@pytest.mark.unit
def test_prices_consistent_with_daily_may_use_identity_only_where_f_is_1():
    assert transformation_of(FieldKey.H1_PRICE, Semantics.UNDETERMINED, at_most_split_adjusted=True) is (
        Transformation.IDENTITY_IF_NO_LATER_SPLIT
    )
    assert transformation_of(FieldKey.H1_PRICE, Semantics.UNDETERMINED) is Transformation.BLOCKED


@pytest.mark.unit
def test_a_decisive_volume_anchor_must_have_f_above_1():
    with pytest.raises(ValueError, match="F > 1"):
        decide_daily_volume([VolumeAnchor(date(2024, 6, 10), Decimal("1"), Decimal("1"), Decimal("1"))], [])


@pytest.mark.unit
def test_a_control_gap_above_3_percent_keeps_volume_undetermined():
    decisive = [VolumeAnchor(date(2024, 6, 6), Decimal("10000"), Decimal("10"), Decimal("1000"))]
    control = [VolumeAnchor(date(2024, 6, 10), Decimal("1100"), Decimal("1"), Decimal("1000"))]
    assert decide_daily_volume(decisive, []).semantics is Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD
    assert decide_daily_volume(decisive, control).semantics is Semantics.UNDETERMINED


@pytest.mark.unit
def test_documentation_establishes_volume():
    decision = decide_daily_volume([], [], documented=Semantics.UNADJUSTED)
    assert decision.semantics is Semantics.UNADJUSTED
    assert decide_hourly_volume([], documented=Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD).semantics is (
        Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD
    )


@pytest.mark.unit
def test_dividends_with_only_f_1_anchors_are_undetermined():
    anchors = [DividendAnchor(date(2024, 6, 11), Decimal("0.01"), Decimal("1"), Decimal("0.01"))]
    assert decide_dividends(anchors).semantics is Semantics.UNDETERMINED


@pytest.mark.unit
def test_split_ratios_that_differ_from_the_citations_are_undetermined():
    vendor = ((date(2021, 7, 20), Decimal("4")), (date(2024, 6, 10), Decimal("5")))
    assert decide_split_ratios(vendor, YAHOO_VERIFICATION.cited_splits) is Semantics.UNDETERMINED
    assert transformation_of(FieldKey.SPLIT_RATIO, Semantics.UNDETERMINED) is Transformation.BLOCKED


# ------------------------------------------------------------------ the volume counterexample (Codex finding)

# A 4:1 split with real activity rising around it: as traded, 1,000 shares at
# 40 before and 16,000 at 10 after; the vendor's split-adjusted volume before
# is 4,000. Continuity favours identity (ratio 1.0) and would store 4,000.
BEFORE = VolumeAnchor(date(2021, 7, 19), Decimal("4000"), Decimal("4"), Decimal("1000"))


@pytest.mark.unit
def test_continuity_alone_never_decides():
    ratio_identity = dollar_volume_continuity([Decimal("40")], [Decimal("4000")], [Decimal("10")], [Decimal("16000")])
    ratio_reconstructed = dollar_volume_continuity([Decimal("40")], [Decimal("1000")], [Decimal("10")],
                                                   [Decimal("16000")])
    assert ratio_identity == Decimal("1")
    assert ratio_reconstructed == Decimal("4")
    decision = decide_daily_volume([], [], continuity_ratio=ratio_identity)
    assert decision.semantics is Semantics.UNDETERMINED
    assert decision.supporting == (ratio_identity,)
    transformation = transformation_of(FieldKey.D1_VOLUME, decision.semantics)
    assert transformation is Transformation.BLOCKED
    assert transformation is not Transformation.IDENTITY


@pytest.mark.unit
def test_a_cited_1000_share_anchor_establishes_reconstruction():
    decision = decide_daily_volume([BEFORE], [], continuity_ratio=Decimal("1"))
    assert decision.semantics is Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD
    assert decision.supporting == (Decimal("1"),)  # recorded, no effect
    assert reconstruct_volume(BEFORE.vendor, BEFORE.factor) == Decimal("1000")


@pytest.mark.unit
def test_a_cited_4000_share_anchor_establishes_identity():
    decision = decide_daily_volume([replace(BEFORE, cited=Decimal("4000"))], [], continuity_ratio=Decimal("1"))
    assert decision.semantics is Semantics.UNADJUSTED
    assert decision.supporting == (Decimal("1"),)


# ------------------------------------------------------------------ transformation_for


@pytest.mark.unit
def test_transformation_for_verified_daily_fields():
    assert transformation_for(FieldKey.D1_PRICE, "1.7.0") is Transformation.SPLIT_RECONSTRUCTION
    assert transformation_for(FieldKey.D1_VOLUME, "1.7.0") is Transformation.SPLIT_RECONSTRUCTION
    assert transformation_for(FieldKey.DIVIDEND_AMOUNT, "1.7.0") is Transformation.SPLIT_RECONSTRUCTION
    assert transformation_for(FieldKey.SPLIT_RATIO, "1.7.0") is Transformation.IDENTITY


@pytest.mark.unit
@pytest.mark.parametrize("key", [FieldKey.H1_PRICE, FieldKey.H1_VOLUME])
def test_transformation_for_raises_for_a_blocked_field(key):
    with pytest.raises(FieldBlocked, match=str(key)):
        transformation_for(key, "1.7.0")


@pytest.mark.unit
def test_transformation_for_raises_for_a_different_yfinance_version():
    with pytest.raises(VersionMismatch, match="1.7.1"):
        transformation_for(FieldKey.D1_PRICE, "1.7.1")


# ------------------------------------------------------------------ reconstruction arithmetic


@pytest.mark.unit
def test_reconstruction_quantizes_half_even():
    assert reconstruct_price(Decimal("14.92650032043457"), Decimal("40")) == Decimal("597.0600")
    assert reconstruct_price(Decimal("0.00000125"), Decimal("1")) == Decimal("0.0000")
    assert reconstruct_price(Decimal("0.00015"), Decimal("1")) == Decimal("0.0002")
    assert reconstruct_volume(Decimal("10"), Decimal("4")) == Decimal("2")  # 2.5 → 2, half-even
    assert reconstruct_volume(Decimal("14"), Decimal("4")) == Decimal("4")  # 3.5 → 4
