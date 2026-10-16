"""Walk-forward folds and leakage guards (docs/tasks/M2-11.md rules 1-4 and 6; M2-11a).

Folds are calendar months aligned to the first covered session. Each fold's
training cutoff is the close of the last session before its test start, so
it is strictly earlier; test windows are half-open and never overlap. Only
complete test windows (every session of them within the data's last date)
are folds.

M2's strategies are fixed rules: training history is used only for warm-up,
nothing is fitted, and an unsupported fit step or imputation of a required
source is refused rather than silently accepted. Test decisions are the
replay's own views, each made with historical point-in-time reads at its T;
they are only filtered by the test window, never recomputed with later data.

Per fold:
- training labels are counted as eligible only when complete and fully
  available by the cutoff, computed at the cutoff (M2-08); the rest are purged
  and counted. They're reported, not fitted;
- test outcomes are realised evaluation data, read at the evaluation time;
- direction metrics and a SIMULATED research run starting from fresh cash;
- warm-up and abstentions are counted, and a terminal outcome missing its
  full horizon is unavailable, not truncated.
Fold metrics stay separate. The stitched summary is a labelled normalized
series of per-fold returns, not a continuous portfolio's P&L. No output
promotes anything: OPEN-09 thresholds are unaccepted.
"""

import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from investment_engine.decision.market_view import ViewDirection
from investment_engine.evaluation.metrics import (
    DirectionEvaluation,
    PredictionView,
    evaluate_direction,
)
from investment_engine.evaluation.returns import LabelConfig, outcome_at, training_eligible
from investment_engine.evaluation.simulation import (
    EvaluationConfig,
    EvaluationRun,
    simulate_research,
)
from investment_engine.lineage.records import register
from investment_engine.market.availability import check_utc
from investment_engine.market.calendar.base import CalendarRangeError
from investment_engine.market.candles import Candle, Timeframe
from investment_engine.market.corporate_actions import ActionType, CorporateAction
from investment_engine.quant.adjusted import VerificationEvidence, establish_coverage, local_date

PROMOTION_STATUS = "PROMOTION NOT ASSESSED: thresholds pending approval"
STITCHED_LABEL = ("Normalized stitched fold returns: each fold's net return from fresh cash, listed in order; "
                  "not a continuous portfolio's dollar P&L")


class UnsupportedFitStep(ValueError):
    """M2 fits nothing: a preprocessing, tuning or calibration step, or required-source imputation, is refused."""


def _months(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{what} must be an int")
    if value < 1:
        raise ValueError(f"{what} must be positive")
    return value


@dataclass(frozen=True)
class WalkForwardConfig:
    train_months: int  # provisional 24
    test_months: int  # provisional 6, non-overlapping
    step_months: int  # provisional 6
    label_config: LabelConfig
    version: str

    def __post_init__(self) -> None:
        for name in ("train_months", "test_months", "step_months"):
            _months(getattr(self, name), name)
        if self.step_months < self.test_months:
            raise ValueError("a step shorter than the test window would overlap test observations")
        if not isinstance(self.label_config, LabelConfig):
            raise TypeError("label_config must be a LabelConfig")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("a walk-forward configuration is versioned")


@dataclass(frozen=True)
class Fold:
    train_start: datetime
    train_cutoff: datetime
    test_start: datetime
    test_end: datetime  # all UTC; half-open test interval
    label_config: LabelConfig
    config_version: str

    def __post_init__(self) -> None:
        for name in ("train_start", "train_cutoff", "test_start", "test_end"):
            check_utc(getattr(self, name), name)
        if not self.train_start < self.train_cutoff < self.test_start < self.test_end:
            raise ValueError("a fold needs train_start < train_cutoff < test_start < test_end")


@dataclass(frozen=True)
class FoldResult:
    fold: Fold
    train_views: int
    train_labels_eligible: int
    train_labels_purged: int
    test_views: int
    warmup_views: int
    direction: DirectionEvaluation
    run: EvaluationRun


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple[FoldResult, ...]
    stitched: tuple[tuple[datetime, float | None], ...]
    stitched_label: str
    promotion: str
    limitations: tuple[str, ...]


for _cls in (WalkForwardConfig, Fold, FoldResult, WalkForwardResult, LabelConfig):
    register(_cls)


class RevisionCache:
    """Every stored revision of one provider and instrument, answering point-in-time reads in memory.

    Same semantics as the store reader's visible_at views: per record, the
    highest revision with available_from <= at. Loaded once from the store's
    revision histories, so an evaluation doesn't repeat thousands of store
    reads; it is a read-only projection, never written back.
    """

    def __init__(self, candles: Sequence[Candle], actions: Sequence[CorporateAction]) -> None:
        self._candles: dict[tuple, list[tuple[datetime, list[Candle]]]] = {}
        grouped: dict[tuple, dict[datetime, list[Candle]]] = {}
        for c in candles:
            grouped.setdefault((c.source, c.instrument_id, c.timeframe), {}).setdefault(c.start_time, []).append(c)
        for key, by_start in grouped.items():
            self._candles[key] = sorted((start, sorted(revs, key=lambda c: c.revision))
                                        for start, revs in by_start.items())
        self._actions: dict[tuple, list[CorporateAction]] = {}
        for a in actions:
            self._actions.setdefault((a.source, a.instrument_id, a.action_type, a.ex_date), []).append(a)
        for revs in self._actions.values():
            revs.sort(key=lambda a: a.revision)

    @classmethod
    def load(cls, reader, source: str, instrument_id: str, timeframes=(Timeframe.D1,)) -> "RevisionCache":
        lo, hi = datetime(1900, 1, 1, tzinfo=UTC), datetime(2200, 1, 1, tzinfo=UTC)
        candles = [c for tf in timeframes for c in reader.candle_revision_history(source, instrument_id, tf, lo, hi)]
        actions = reader.action_revision_history(source, instrument_id, date(1900, 1, 1), date(2200, 1, 1))
        return cls(candles, actions)

    def candles_visible_at(self, source, instrument_id, timeframe, start, end, at):
        rows = self._candles.get((source, instrument_id, Timeframe(timeframe)), [])
        lo = bisect.bisect_left(rows, start, key=lambda row: row[0])
        hi = bisect.bisect_left(rows, end, key=lambda row: row[0])
        out = []
        for _, revisions in rows[lo:hi]:
            visible = [c for c in revisions if c.available_from <= at]
            if visible:
                out.append(visible[-1])
        return out

    def actions_visible_at(self, source, instrument_id, start, end, at, types=None):
        wanted = None if types is None else {ActionType(t) for t in types}
        out = []
        for (s, i, action_type, ex_date), revisions in self._actions.items():
            if (s, i) != (source, instrument_id) or not start <= ex_date < end:
                continue
            if wanted is not None and action_type not in wanted:
                continue
            visible = [a for a in revisions if a.available_from <= at]
            if visible:
                out.append(visible[-1])
        return sorted(out, key=lambda a: (a.ex_date, list(ActionType).index(a.action_type)))


def _add_months(d: date, months: int) -> date:
    year, month = divmod(d.month - 1 + months, 12)
    year, month = d.year + year, month + 1
    for day in range(d.day, 27, -1):  # clamp to the month's last day
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, min(d.day, 28))


def _session_on_or_after(calendar, d: date):
    return calendar.session(d) if calendar.is_session(d) else calendar.next_session(d)


def make_folds(first: date, last: date, *, calendar, config: WalkForwardConfig) -> tuple[Fold, ...]:
    """Every complete fold between the first covered session on or after `first` and `last`."""
    anchor = _session_on_or_after(calendar, first).date
    folds = []
    k = 0
    while True:
        start_date = _add_months(anchor, k * config.step_months)
        test_date = _add_months(start_date, config.train_months)
        end_date = _add_months(test_date, config.test_months)
        try:
            test_session = _session_on_or_after(calendar, test_date)
            end_session = _session_on_or_after(calendar, end_date)
        except CalendarRangeError:
            break
        if calendar.previous_session(end_session.date).date > last:
            break
        folds.append(Fold(
            train_start=_session_on_or_after(calendar, start_date).open,
            train_cutoff=calendar.previous_session(test_session.date).close,
            test_start=test_session.open, test_end=end_session.open,
            label_config=config.label_config, config_version=config.version))
        k += 1
    return tuple(folds)


def walk_forward(folds: Sequence[Fold], *, views: Sequence[PredictionView], reader, calendar, source: str,
                 instrument_id: str, coverage_evidence: Sequence[VerificationEvidence], coverage_first: date,
                 coverage_last: date, coverage_reason: str, evaluation_config: EvaluationConfig, at: datetime,
                 fit_steps: Sequence[str] = (), impute_required_sources: bool = False) -> WalkForwardResult:
    if fit_steps:
        raise UnsupportedFitStep(f"M2 runs fixed rules; fit steps {tuple(fit_steps)} are not supported")
    if impute_required_sources:
        raise UnsupportedFitStep("required sources are never imputed (Law 9): missing data abstains")
    at = check_utc(at, "at")
    folds = tuple(folds)
    for f in folds:
        if not isinstance(f, Fold):
            raise TypeError("folds must be Fold records")
    for a_fold, b_fold in zip(folds, folds[1:], strict=False):
        if b_fold.test_start < a_fold.test_end:
            raise ValueError("fold test windows must be in order and must not repeat or overlap: "
                             f"{a_fold.test_start}..{a_fold.test_end} then {b_fold.test_start}..{b_fold.test_end}")
    views = sorted(views, key=lambda pv: pv.view.generated_at)

    def cover(t: datetime, types):
        return establish_coverage(coverage_evidence, source=source, instrument_id=instrument_id, types=types,
                                  first=coverage_first, last=coverage_last, as_of=t, reason=coverage_reason)

    def outcome(session: date, config: LabelConfig, t: datetime):
        types = ("SPLIT",) if config.basis.value.startswith("SPLIT") else ("SPLIT", "DIVIDEND")
        return outcome_at(reader, source, instrument_id, session, config=config, at=t, calendar=calendar,
                          coverage=cover(t, types))

    results = []
    for fold in folds:
        config = fold.label_config
        train = [pv for pv in views if fold.train_start <= pv.view.generated_at <= fold.train_cutoff]
        eligible = sum(training_eligible(outcome(pv.prediction_session, config, fold.train_cutoff), fold.train_cutoff)
                       for pv in train)
        # Only views that exist by the evaluation cutoff; an unfinished fold's run is reported incomplete.
        test = [pv for pv in views if fold.test_start <= pv.view.generated_at < fold.test_end
                and pv.view.generated_at <= at]
        outcomes = [outcome(pv.prediction_session, config, at) for pv in test]
        trailing = []
        for pv in test:
            start = pv.prediction_session
            try:
                for _ in range(config.horizon_sessions):
                    start = calendar.previous_session(start).date
            except CalendarRangeError:
                continue
            trailing.append(outcome(start, config, pv.view.generated_at))
        direction = evaluate_direction(test, outcomes, config=config, calendar=calendar, trailing=trailing)
        first_session = local_date(fold.test_start, calendar)
        last_session = calendar.previous_session(local_date(fold.test_end, calendar)).date
        run = simulate_research([pv.view for pv in test], reader=reader, calendar=calendar, source=source,
                                instrument_id=instrument_id, first=first_session, last=last_session, at=at,
                                coverage=cover(at, ("SPLIT", "DIVIDEND")), config=evaluation_config)
        warmup = sum(pv.view.direction is ViewDirection.ABSTAIN and pv.view.abstain_reason == "warm-up"
                     for pv in test)
        results.append(FoldResult(fold, len(train), eligible, len(train) - eligible, len(test), warmup, direction,
                                  run))

    stitched = tuple((r.fold.test_start, next(m.value for m in r.run.metrics if m.key == "net_return"))
                     for r in results)
    limitations = (
        STITCHED_LABEL + ".",
        "Fixed rules: training history is used only for warm-up; nothing is fitted or tuned.",
        "Training labels are counted at each cutoff and purged unless complete and available by it; they are not "
        "fitted.",
        "Views in warm-up or abstaining are counted, never dropped; terminal outcomes without a full horizon are "
        "unavailable.",
        f"{PROMOTION_STATUS}.",
    )
    return WalkForwardResult(tuple(results), stitched, STITCHED_LABEL, PROMOTION_STATUS, limitations)
