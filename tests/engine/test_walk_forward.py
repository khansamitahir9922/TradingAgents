"""Walk-forward folds and leakage guards (docs/tasks/M2-11.md rules 1-4 and 6; M2-11a)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.clock import ReplayClock
from investment_engine.decision.pipeline import run_views
from investment_engine.evaluation.metrics import PredictionView
from investment_engine.evaluation.returns import LabelConfig, ReturnBasis
from investment_engine.evaluation.simulation import EvaluationConfig
from investment_engine.evaluation.walk_forward import (
    PROMOTION_STATUS,
    Fold,
    RevisionCache,
    UnsupportedFitStep,
    WalkForwardConfig,
    make_folds,
    walk_forward,
)
from investment_engine.lineage.records import LineageStore
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import BarState, PriceBasis, Timeframe, VolumeBasis
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.instruments import AssetClass, Instrument, InstrumentStatus
from investment_engine.market.replay import ReplayFeed
from investment_engine.market.store.reader import MarketDataReader
from investment_engine.market.store.writer import CandleObservation, MarketDataWriter
from investment_engine.market.symbols import SymbolMapping
from investment_engine.quant.adjusted import VerificationEvidence
from investment_engine.quant.strategies.pullback import PullbackStrategy
from investment_engine.quant.strategies.trend import TrendStrategy
from investment_engine.storage.database import SqliteDatabase
from investment_engine.storage.sqlite import (
    SqliteInstrumentRepository,
    SqliteSymbolResolver,
    apply_schema,
    open_operational_db,
)

NVDA = "EQ_US_NVDA"
CAL = load_us_equities_calendar()
LABELS = LabelConfig(5, ReturnBasis.SPLIT_ADJUSTED_PRICE_RETURN, "labels-test")
SMALL = WalkForwardConfig(train_months=10, test_months=2, step_months=2, label_config=LABELS, version="wf-test")
EVAL = EvaluationConfig("eval-test", Decimal("10000"), "USD", Decimal("5"), "LONG_OR_CASH",
                        "CASH_ON_EX_DATE_RESEARCH_ASSUMPTION")
TYPES = (ActionType.SPLIT, ActionType.DIVIDEND)
EVIDENCE = tuple(VerificationEvidence("yfinance", NVDA, t, date(2019, 1, 1), date(2026, 10, 12), date(2019, 1, 1),
                                      date(2026, 10, 12), "test-verification", "COMPLETE") for t in TYPES)


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


# ------------------------------------------------------------------ folds


@pytest.mark.unit
def test_folds_align_to_the_first_session_and_never_overlap_their_tests():
    config = WalkForwardConfig(24, 6, 6, LABELS, "wf")
    folds = make_folds(date(2019, 1, 1), date(2026, 10, 9), calendar=CAL, config=config)
    first = folds[0]
    assert first.train_start == CAL.session(date(2019, 1, 2)).open  # 1 January is a holiday
    assert first.test_start == CAL.session(date(2021, 1, 4)).open  # 2 January 2021 is a Saturday
    assert first.train_cutoff == CAL.session(date(2020, 12, 31)).close
    assert first.train_cutoff < first.test_start
    assert first.test_end == CAL.session(date(2021, 7, 2)).open  # half-open: 2 July 2021 belongs to the next fold
    for a, b in zip(folds, folds[1:], strict=False):
        assert a.test_end <= b.test_start  # non-overlapping test observations
        assert b.train_start > a.train_start
    assert all(f.test_end <= CAL.session(date(2026, 10, 9)).close for f in folds)
    assert {f.label_config for f in folds} == {LABELS} and {f.config_version for f in folds} == {"wf"}
    assert len(folds) == 11  # 2021-01 .. 2026-07, complete six-month windows only


@pytest.mark.unit
def test_overlapping_test_windows_or_invalid_months_are_refused():
    with pytest.raises(ValueError):
        WalkForwardConfig(24, 6, 3, LABELS, "wf")
    for bad in ((0, 6, 6), (24, True, 6), (24, 6, 0)):
        with pytest.raises((TypeError, ValueError)):
            WalkForwardConfig(*bad, LABELS, "wf")


# ------------------------------------------------------------------ a synthetic history run through the pipeline

SESSIONS = [s.date for s in CAL.sessions_between(date(2023, 1, 3), date(2024, 7, 2))]


def bar(d, close, received_at=None):
    s = CAL.session(d)
    received = received_at or s.close
    return CandleObservation(
        source="yfinance", instrument_id=NVDA, timeframe=Timeframe.D1, start_time=s.open, end_time=s.close,
        open=close, high=close, low=close, close=close, currency="USD", volume=Decimal("1000"),
        state=BarState.CLOSED, source_version="1.7.0", price_basis=PriceBasis.RAW_AS_REPORTED,
        volume_basis=VolumeBasis.RAW_AS_REPORTED, event_time=s.close, received_at=received, processed_at=received,
        backfill_available_from=s.close)


def price(i):
    return (Decimal(100) + Decimal(i) / 5 + Decimal((i * 7) % 11) - 5).quantize(Decimal("0.0001"))


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wf")
    conn = open_operational_db(tmp / "op.sqlite3")
    apply_schema(conn)
    db = SqliteDatabase(conn)
    instruments, resolver = SqliteInstrumentRepository(db), SqliteSymbolResolver(db)
    instruments.add(Instrument(NVDA, AssetClass.EQUITY, "USD", "XNAS", "America/New_York",
                               InstrumentStatus.ACTIVE, date(1999, 1, 22), None))
    resolver.add(SymbolMapping(NVDA, "yfinance", "NVDA", date(1999, 1, 22), None))
    writer, reader = MarketDataWriter(tmp / "market"), MarketDataReader(tmp / "market")
    writer.write_candles([bar(d, price(i)) for i, d in enumerate(SESSIONS)], import_id="bars")
    start, end = CAL.session(SESSIONS[0]).open - timedelta(days=1), CAL.session(SESSIONS[-1]).close + timedelta(days=5)
    lineage = LineageStore(db)
    feed = ReplayFeed(reader, ReplayClock(start), sources=["yfinance"], instrument_ids=[NVDA],
                      timeframes=[Timeframe.D1], start=start, end=end)
    views = list(run_views(feed, instrument_id=NVDA, source="yfinance", strategies=(TrendStrategy(), PullbackStrategy()),
                           policy_version="0.1.0", calendar=CAL, instruments=instruments, resolver=resolver,
                           lineage_store=lineage, coverage_evidence=EVIDENCE, coverage_first=SESSIONS[0],
                           coverage_last=date(2026, 10, 12), coverage_reason="test", calendar_version="cal",
                           code_version="code"))
    predictions = tuple(PredictionView("yfinance", lineage.get(v.evidence_refs[0]).snapshot.session_date, v)
                        for v in views)
    yield {"conn": conn, "reader": RevisionCache.load(reader, "yfinance", NVDA), "store": reader, "writer": writer,
           "views": predictions, "end": end, "lineage": lineage}
    conn.close()


def run(history, folds=None, **kwargs):
    folds = folds if folds is not None else make_folds(SESSIONS[0], SESSIONS[-1], calendar=CAL, config=SMALL)
    at = history["end"]
    return walk_forward(folds, views=history["views"], reader=history["reader"], calendar=CAL, source="yfinance",
                        instrument_id=NVDA, coverage_evidence=EVIDENCE, coverage_first=SESSIONS[0],
                        coverage_last=date(2026, 10, 12), coverage_reason="test", evaluation_config=EVAL, at=at,
                        **kwargs)


@pytest.mark.unit
def test_each_fold_evaluates_only_its_test_views_with_fresh_cash(history):
    result = run(history)
    assert len(result.folds) == 4  # tests from 3 Nov 2023, 3 Jan, 3 Mar and 3 May 2024, two months each
    for f in result.folds:
        assert f.test_views == len([v for v in history["views"]
                                    if f.fold.test_start <= v.view.generated_at < f.fold.test_end])
        assert f.run.equity_curve[0][1] <= EVAL.initial_cash or f.run.trades
        assert f.run.config == EVAL and CAL.session(f.run.first).open == f.fold.test_start
        assert all(f.fold.test_start <= t.decision_time < f.fold.test_end for t in f.run.trades)
    assert result.promotion == PROMOTION_STATUS == "PROMOTION NOT ASSESSED: thresholds pending approval"


@pytest.mark.unit
def test_training_labels_are_purged_unless_complete_and_available_by_the_cutoff(history):
    result = run(history)
    f = result.folds[0]
    assert f.train_labels_purged >= LABELS.horizon_sessions  # the last five sessions' labels end after the cutoff
    assert f.train_labels_eligible > 0
    assert f.train_labels_eligible + f.train_labels_purged == f.train_views


@pytest.mark.unit
def test_a_correction_arriving_after_the_cutoff_cannot_change_training_labels(history, tmp_path):
    folds = make_folds(SESSIONS[0], SESSIONS[-1], calendar=CAL, config=SMALL)
    before = run(history, folds[:1])
    # Copy the store, then correct a training-period bar after the fold's cutoff.
    import shutil
    root = tmp_path / "market"
    shutil.copytree(history["store"].root, root)
    late = folds[0].test_end + timedelta(days=1)
    target = SESSIONS[100]
    MarketDataWriter(root).write_candles([bar(target, price(100) + 50, received_at=late)], import_id="late")
    after_history = {**history, "reader": RevisionCache.load(MarketDataReader(root), "yfinance", NVDA)}
    after = run(after_history, folds[:1])
    assert (after.folds[0].train_labels_eligible, after.folds[0].train_labels_purged) == (
        before.folds[0].train_labels_eligible, before.folds[0].train_labels_purged)
    assert after.folds[0].direction.metrics == before.folds[0].direction.metrics


@pytest.mark.unit
def test_fit_steps_and_required_source_imputation_are_rejected(history):
    with pytest.raises(UnsupportedFitStep):
        run(history, fit_steps=("global_scaler",))
    with pytest.raises(UnsupportedFitStep):
        run(history, impute_required_sources=True)


@pytest.mark.unit
def test_fit_free_runs_are_deterministic(history):
    assert run(history) == run(history)


@pytest.mark.unit
def test_counts_and_limitations_show_warmup_abstentions_and_terminal_horizons(history):
    result = run(history)
    last = result.folds[-1]
    # The last test window ends at the data's end: its final five views can't have complete 5-session outcomes.
    assert last.direction.unavailable_outcomes >= LABELS.horizon_sessions
    assert last.direction.eligible_views == last.test_views
    first = result.folds[0]
    assert first.direction.abstain_views >= 0 and first.warmup_views >= 0
    assert any("stitched" in s for s in result.limitations)
    assert any("warm-up" in s for s in result.limitations)


@pytest.mark.unit
def test_stitched_returns_are_labelled_as_a_normalized_summary(history):
    result = run(history)
    assert result.stitched_label.startswith("Normalized stitched fold returns")
    assert len(result.stitched) == len(result.folds)


@pytest.mark.unit
def test_views_outside_every_fold_are_never_test_observations(history):
    result = run(history)
    counted = sum(f.test_views for f in result.folds)
    assert counted < len(history["views"])  # the first ten months are training/warm-up only


@pytest.mark.unit
def test_a_fold_carries_its_boundaries_and_versions():
    f = make_folds(SESSIONS[0], SESSIONS[-1], calendar=CAL, config=SMALL)[0]
    assert isinstance(f, Fold) and f.config_version == "wf-test" and f.label_config == LABELS
    with pytest.raises(ValueError):
        replace(f, train_cutoff=f.test_start)



@pytest.mark.unit
def test_the_revision_cache_answers_exactly_like_the_store_reader(history):
    store, cache = history["store"], history["reader"]
    times = [CAL.session(d).close + timedelta(seconds=s) for d in SESSIONS[::37] for s in (-1, 0, 1)]
    for at in times:
        for start_d, end_d in ((SESSIONS[0], SESSIONS[-1]), (SESSIONS[50], SESSIONS[60])):
            start, end = CAL.session(start_d).open, CAL.session(end_d).close
            assert cache.candles_visible_at("yfinance", NVDA, Timeframe.D1, start, end, at) ==                 store.candles_visible_at("yfinance", NVDA, Timeframe.D1, start, end, at)
        assert cache.actions_visible_at("yfinance", NVDA, date(2019, 1, 1), date(2027, 1, 1), at) ==             store.actions_visible_at("yfinance", NVDA, date(2019, 1, 1), date(2027, 1, 1), at)


@pytest.mark.unit
def test_an_unfinished_fold_is_reported_incomplete_not_complete(history):
    folds = make_folds(SESSIONS[0], SESSIONS[-1], calendar=CAL, config=SMALL)
    last = folds[-1]
    cutoff = last.test_start + timedelta(days=20)
    result = walk_forward([last], views=history["views"], reader=history["reader"], calendar=CAL, source="yfinance",
                          instrument_id=NVDA, coverage_evidence=EVIDENCE, coverage_first=SESSIONS[0],
                          coverage_last=date(2026, 10, 12), coverage_reason="test", evaluation_config=EVAL,
                          at=cutoff)
    [fold] = result.folds
    assert not fold.run.complete
    assert fold.test_views == len([v for v in history["views"] if last.test_start <= v.view.generated_at <= cutoff])
    assert result.stitched[0][1] is None


# ------------------------------------------------------------------ S2: the fold collection is validated


@pytest.mark.unit
@pytest.mark.parametrize("arrangement", ["duplicate", "overlap", "out_of_order"])
def test_duplicate_overlapping_or_unordered_folds_are_refused(history, arrangement):
    folds = make_folds(SESSIONS[0], SESSIONS[-1], calendar=CAL, config=SMALL)
    if arrangement == "duplicate":
        folds = (folds[0], folds[0])
    elif arrangement == "overlap":
        folds = (folds[0], replace(folds[1], test_start=folds[0].test_end - timedelta(days=5),
                                   train_cutoff=folds[0].test_end - timedelta(days=6)))
    else:
        folds = (folds[1], folds[0])
    with pytest.raises(ValueError, match="fold"):
        run(history, folds)
