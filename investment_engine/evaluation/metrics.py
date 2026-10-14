"""Honest direction metrics and matched baselines (docs/tasks/M2-09.md).

Views are joined to completed outcomes by provider, instrument, prediction
session, horizon and basis; duplicates and mismatched targets raise.

- Directional accuracy scores BULLISH/BEARISH views with available, non-zero
  outcomes. NEUTRAL and ABSTAIN are not predictions of a flat market; they,
  unavailable outcomes and zero-outcome exclusions are counted separately.
- Always-up is reported on exactly the scored dates (the paired comparison)
  and on the full eligible population, so selective abstention can't quietly
  improve the comparison.
- Last-period direction is the sign of the same-basis h-session return ending
  at the prediction session's close, which must be complete and available at
  the view's T. Dates without it shrink and are identified in its paired
  sample.
- The information coefficient is Spearman's rank correlation (average ranks
  for ties) between the signed strength (+ for BULLISH, - for BEARISH) and the
  realised return, zeros included. Strength is a heuristic scale, not a
  probability.
A metric that can't be computed is None with its reason, never NaN or zero.
Overlapping multi-session outcomes are disclosed; no significance is claimed.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.evaluation.returns import LabelConfig, ReturnBasis, ReturnObservation


@dataclass(frozen=True)
class PredictionView:
    """A view with the provider and prediction session it was made from (from its lineage snapshot)."""

    source: str
    prediction_session: date
    view: MarketView


@dataclass(frozen=True)
class MetricValue:
    key: str
    value: float | None
    n: int
    unavailable_reason: str


@dataclass(frozen=True)
class DirectionEvaluation:
    config_version: str
    basis: ReturnBasis
    horizon_sessions: int
    eligible_views: int
    directional_views: int
    neutral_views: int
    abstain_views: int
    unavailable_outcomes: int
    metrics: tuple[MetricValue, ...]
    outcome_refs: tuple[ReturnObservation, ...]
    disclosures: tuple[str, ...]


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman's rank correlation with average ranks for ties; None if undefined."""
    if len(x) != len(y):
        raise ValueError("samples differ in length")
    if len(x) < 2:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _rate(hits: int, n: int, key: str, empty: str) -> MetricValue:
    return MetricValue(key, hits / n if n else None, n, "" if n else empty)


def _diff(a: MetricValue, b: MetricValue, key: str) -> MetricValue:
    if a.value is None or b.value is None:
        return MetricValue(key, None, 0, "no paired sample")
    return MetricValue(key, a.value - b.value, a.n, "")


def _horizon_end(calendar, start: date, h: int) -> date:
    d = start
    for _ in range(h):
        d = calendar.next_session(d).date
    return d


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def evaluate_direction(views: Sequence[PredictionView], outcomes: Sequence[ReturnObservation], *,
                       config: LabelConfig, calendar,
                       trailing: Sequence[ReturnObservation] = ()) -> DirectionEvaluation:
    h, basis = config.horizon_sessions, config.basis

    def check(o: ReturnObservation, what: str) -> None:
        if not isinstance(o, ReturnObservation):
            raise TypeError(f"{what} must be ReturnObservations")
        if o.basis is not basis:
            raise ValueError(f"{what} on {o.basis}, not the declared {basis}")
        if _horizon_end(calendar, o.start_session, h) != o.end_session:
            raise ValueError(f"{what} {o.start_session}..{o.end_session} is not a {h}-session horizon")

    by_view: dict[tuple, PredictionView] = {}
    for v in views:
        key = (v.source, v.view.instrument_id, v.prediction_session)
        if key in by_view:
            raise ValueError(f"duplicate view for {key}")
        by_view[key] = v
    by_outcome: dict[tuple, ReturnObservation] = {}
    for o in outcomes:
        check(o, "outcome")
        key = (o.source, o.instrument_id, o.start_session)
        if key in by_outcome:
            raise ValueError(f"duplicate outcome for {key}")
        by_outcome[key] = o
    by_trailing: dict[tuple, ReturnObservation] = {}
    for o in trailing:
        check(o, "trailing return")
        key = (o.source, o.instrument_id, o.end_session)
        if key in by_trailing:
            raise ValueError(f"duplicate trailing return for {key}")
        by_trailing[key] = o

    joined = []
    for key in sorted(by_view, key=lambda k: (k[2], k[0], k[1])):
        if key not in by_outcome:
            raise ValueError(f"no outcome for the view at {key}: every view needs its declared target")
        joined.append((by_view[key], by_outcome[key]))

    directional = [(v, o) for v, o in joined if v.view.direction in (ViewDirection.BULLISH, ViewDirection.BEARISH)]
    available = [(v, o) for v, o in joined if o.value is not None]
    scored = [(v, o) for v, o in directional if o.value is not None and o.value != 0]

    def correct(v: PredictionView, value: float) -> bool:
        return (v.view.direction is ViewDirection.BULLISH) == (value > 0)

    accuracy = _rate(sum(correct(v, o.value) for v, o in scored), len(scored), "direction_accuracy",
                     "no directional view with an available non-zero outcome")
    up_matched = _rate(sum(o.value > 0 for _, o in scored), len(scored), "always_up_accuracy_matched",
                       "no scored dates")
    nonzero = [(v, o) for v, o in available if o.value != 0]
    up_full = _rate(sum(o.value > 0 for _, o in nonzero), len(nonzero), "always_up_accuracy_full",
                    "no available non-zero outcome")
    base = _rate(sum(o.value > 0 for _, o in available), len(available), "positive_base_rate",
                 "no available outcome")
    zero_excluded = sum(1 for _, o in directional if o.value == 0)

    paired, lp_missing = [], 0
    for v, o in scored:
        t = by_trailing.get((v.source, v.view.instrument_id, v.prediction_session))
        at = v.view.generated_at
        if (t is None or t.value is None or t.value == 0 or t.outcome_end > at or t.available_from > at
                or t.as_of > at):
            lp_missing += 1
            continue
        paired.append((v, o, _sign(t.value)))
    lp = _rate(sum((s > 0) == (o.value > 0) for _, o, s in paired), len(paired), "last_period_accuracy_matched",
               "no scored date has a completed, available trailing return")
    model_on_lp = _rate(sum(correct(v, o.value) for v, o, _ in paired), len(paired),
                        "direction_accuracy_on_last_period_sample", "no paired last-period sample")

    ic_sample = [(v, o) for v, o in directional if o.value is not None]
    scores = [(1 if v.view.direction is ViewDirection.BULLISH else -1) * v.view.strength for v, _ in ic_sample]
    ic_value = spearman(scores, [o.value for _, o in ic_sample]) if len(ic_sample) >= 3 else None
    ic_reason = ("" if ic_value is not None else
                 "fewer than 3 directional views with available outcomes" if len(ic_sample) < 3 else
                 "constant scores or returns")
    ic = MetricValue("information_coefficient", ic_value, len(ic_sample) if ic_value is not None else 0, ic_reason)

    metrics = (
        accuracy, up_matched, _diff(accuracy, up_matched, "paired_accuracy_difference"), up_full, base,
        MetricValue("zero_outcome_exclusions", float(zero_excluded), zero_excluded, ""),
        lp, model_on_lp, _diff(model_on_lp, lp, "paired_last_period_difference"),
        MetricValue("last_period_unavailable", float(lp_missing), lp_missing, ""),
        ic,
    )
    disclosures = ["Strength is a heuristic scale, not a calibrated probability.",
                   "No statistical significance is claimed."]
    if h > 1:
        disclosures.append(f"{h}-session outcomes of consecutive views overlap; samples are not independent.")
    return DirectionEvaluation(
        config_version=config.version, basis=basis, horizon_sessions=h, eligible_views=len(joined),
        directional_views=len(directional),
        neutral_views=sum(v.view.direction is ViewDirection.NEUTRAL for v, _ in joined),
        abstain_views=sum(v.view.direction is ViewDirection.ABSTAIN for v, _ in joined),
        unavailable_outcomes=sum(o.value is None for _, o in joined),
        metrics=metrics, outcome_refs=tuple(o for _, o in joined), disclosures=tuple(disclosures))
