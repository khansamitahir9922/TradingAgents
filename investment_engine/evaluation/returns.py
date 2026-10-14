"""Labelled returns and completed prediction outcomes (docs/tasks/M2-08.md).

Two separately labelled bases, both read explicitly as visible at T from one
provider, with exact Decimal arithmetic until a single float64 conversion:

- SPLIT_ADJUSTED_PRICE_RETURN: the end close over the start close on one
  split basis, i.e. raw_end * (product of split ratios effective in
  (start, end]) / raw_start - 1. Splits after the end cancel out.
- TOTAL_RETURN_CLOSE_REINVESTED: a close-to-close index, not adjusted OHLC.
  For each adjacent session, hold one share bought at the preceding raw close;
  effective splits multiply its quantity; a dividend on that date is the
  stored as-paid amount per post-split share, paid in cash; gross =
  (quantity * close + dividend cash) / preceding close. Dividend cash is
  reinvested at that close and the daily gross returns are chained.

Every session from start to end must have a completed bar; a missing one, an
outcome not complete at T, unestablished coverage of the needed action types
(SPLIT, and DIVIDEND for total return) or an unsupported action type gives an
unavailable observation with its reason, never a zero. These are research
results, not ledger P&L.
"""

import decimal
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from investment_engine.market.availability import check_instrument_id, check_provider, check_utc
from investment_engine.market.candles import Candle
from investment_engine.market.corporate_actions import ActionType, CorporateAction
from investment_engine.money import to_float64
from investment_engine.quant.adjusted import (
    ActionCoverage,
    ActionRef,
    AdjustmentUnavailable,
    BarRef,
    action_ref,
    bar_ref,
    completed_daily_bars,
    local_date,
    require_coverage,
    visible_actions,
)


class ReturnBasis(StrEnum):
    SPLIT_ADJUSTED_PRICE_RETURN = "SPLIT_ADJUSTED_PRICE_RETURN"
    TOTAL_RETURN_CLOSE_REINVESTED = "TOTAL_RETURN_CLOSE_REINVESTED"


_NEEDS = {
    ReturnBasis.SPLIT_ADJUSTED_PRICE_RETURN: (ActionType.SPLIT,),
    ReturnBasis.TOTAL_RETURN_CLOSE_REINVESTED: (ActionType.SPLIT, ActionType.DIVIDEND),
}
_UNSUPPORTED = (ActionType.SYMBOL_CHANGE, ActionType.DELISTING)


@dataclass(frozen=True)
class ReturnObservation:
    source: str
    instrument_id: str
    start_session: date
    end_session: date
    basis: ReturnBasis
    value: float | None
    outcome_end: datetime  # the end session's close
    available_from: datetime  # the latest availability of any input used
    as_of: datetime  # T: when it was computed
    bar_refs: tuple[BarRef, ...]
    action_refs: tuple[ActionRef, ...]
    coverage: ActionCoverage
    unavailable_reason: str  # "" when value is not None


@dataclass(frozen=True)
class LabelConfig:
    horizon_sessions: int  # provisional baseline 5 (OPEN-09), never inferred from a model
    basis: ReturnBasis
    version: str

    def __post_init__(self) -> None:
        h = self.horizon_sessions
        if isinstance(h, bool) or not isinstance(h, int):
            raise TypeError("horizon_sessions must be an int")
        if h < 1:
            raise ValueError("horizon_sessions must be positive")
        object.__setattr__(self, "basis", ReturnBasis(self.basis))
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("a label configuration is versioned")


def _context() -> decimal.Context:
    return decimal.Context(prec=60, rounding=decimal.ROUND_HALF_EVEN)


def _value(sessions, bars: dict[date, Candle], actions: Sequence[CorporateAction], basis: ReturnBasis) -> Decimal:
    ctx = _context()
    splits = {a.ex_date: a.ratio for a in actions if a.action_type is ActionType.SPLIT}
    dividends = {a.ex_date: a for a in actions if a.action_type is ActionType.DIVIDEND}
    currency = bars[sessions[0].date].currency
    if basis is ReturnBasis.SPLIT_ADJUSTED_PRICE_RETURN:
        factor = Decimal(1)
        for s in sessions[1:]:
            factor = ctx.multiply(factor, splits.get(s.date, Decimal(1)))
        start, end = bars[sessions[0].date].close, bars[sessions[-1].date].close
        return ctx.subtract(ctx.divide(ctx.multiply(end, factor), start), Decimal(1))
    growth = Decimal(1)
    for previous, current in zip(sessions, sessions[1:], strict=False):
        quantity = splits.get(current.date, Decimal(1))
        cash = Decimal(0)
        if current.date in dividends:
            amount = dividends[current.date].amount
            if amount.currency != currency or dividends[current.date].amount_basis is None:
                raise AdjustmentUnavailable(f"dividend on {current.date} has an unknown convention or currency")
            cash = ctx.multiply(quantity, amount.amount)
        gross = ctx.divide(ctx.add(ctx.multiply(quantity, bars[current.date].close), cash),
                           bars[previous.date].close)
        growth = ctx.multiply(growth, gross)
    return ctx.subtract(growth, Decimal(1))


def _observation(reader, source: str, instrument_id: str, sessions, *, at: datetime, calendar,
                 coverage: ActionCoverage, basis: ReturnBasis) -> ReturnObservation:
    start, end = sessions[0], sessions[-1]

    def result(value=None, reason="", bars=(), actions=()):
        refs = tuple(bar_ref(c) for c in bars)
        arefs = tuple(action_ref(a) for a in actions)
        times = [r.available_from for r in refs] + [r.available_from for r in arefs]
        return ReturnObservation(source, instrument_id, start.date, end.date, basis, value, end.close,
                                 max(times) if times else at, at, refs, arefs, coverage, reason)

    if end.close > at:
        return result(reason=f"outcome not complete at T: {end.date} closes at {end.close}")
    try:
        for action_type in _NEEDS[basis]:
            require_coverage(coverage, source=source, instrument_id=instrument_id, action_type=action_type,
                             first=start.date, last=max(end.date, local_date(at, calendar)), at=at)
    except AdjustmentUnavailable as exc:
        return result(reason=str(exc))
    bars = completed_daily_bars(reader, source, instrument_id, sessions, at=at)
    missing = [s.date for s in sessions if s.date not in bars]
    used_bars = [bars[s.date] for s in sessions if s.date in bars]
    if missing:
        return result(reason="missing sessions: " + ", ".join(str(d) for d in missing), bars=used_bars)
    actions = []
    for action_type in (*_NEEDS[basis], *_UNSUPPORTED):
        actions += [a for a in visible_actions(reader, source, instrument_id, action_type, start.date, at=at,
                                               calendar=calendar) if start.date < a.ex_date <= end.date]
    unsupported = sorted({str(a.action_type) for a in actions if a.action_type in _UNSUPPORTED})
    if unsupported:
        return result(reason=f"unsupported corporate action in the window: {', '.join(unsupported)}",
                      bars=used_bars, actions=actions)
    if any(a.currency != used_bars[0].currency for a in actions):
        raise ValueError("actions and bars disagree on the instrument's currency")
    actions.sort(key=lambda a: (a.ex_date, list(ActionType).index(a.action_type)))
    try:
        value = to_float64(_value(sessions, bars, actions, basis))
    except AdjustmentUnavailable as exc:
        return result(reason=str(exc), bars=used_bars, actions=actions)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("the return is not finite")
    return result(value=value, bars=used_bars, actions=actions)


def _check(source, instrument_id, at):
    check_provider(source)
    check_instrument_id(instrument_id)
    return check_utc(at, "at")


def session_returns(reader, source: str, instrument_id: str, first: date, last: date, *, at: datetime, calendar,
                    coverage: ActionCoverage, basis: ReturnBasis) -> tuple[ReturnObservation, ...]:
    """One-session returns for each adjacent pair of sessions in first..last."""
    at, basis = _check(source, instrument_id, at), ReturnBasis(basis)
    if last < first:
        raise ValueError(f"the range {first}..{last} runs backwards")
    sessions = calendar.sessions_between(first, last)
    return tuple(_observation(reader, source, instrument_id, pair, at=at, calendar=calendar, coverage=coverage,
                              basis=basis) for pair in zip(sessions, sessions[1:], strict=False))


def outcome_at(reader, source: str, instrument_id: str, prediction_session: date, *, config: LabelConfig,
               at: datetime, calendar, coverage: ActionCoverage) -> ReturnObservation:
    """The h-session outcome from the prediction session's close to the h-th later session's close."""
    at = _check(source, instrument_id, at)
    sessions = [calendar.session(prediction_session)]
    for _ in range(config.horizon_sessions):
        sessions.append(calendar.next_session(sessions[-1].date))
    return _observation(reader, source, instrument_id, sessions, at=at, calendar=calendar, coverage=coverage,
                        basis=config.basis)


def training_eligible(outcome: ReturnObservation, training_cutoff: datetime) -> bool:
    """Usable in a fold trained up to the cutoff: complete, computed and fully available by then."""
    cutoff = check_utc(training_cutoff, "training_cutoff")
    return (outcome.value is not None and outcome.outcome_end <= cutoff and outcome.available_from <= cutoff
            and outcome.as_of <= cutoff)
