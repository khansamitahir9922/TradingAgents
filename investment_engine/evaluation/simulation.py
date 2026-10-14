"""Cost-inclusive SIMULATED research at next-open raw prices (docs/tasks/M2-10.md).

Initial evaluation, not execution replay: no broker port, OrderIntent, order,
ledger, outbox or new process. All money, prices and quantities are Decimal;
return metrics cross the float64 boundary once.

- Each view (from replay, with its lineage id) may trade at the next regular
  session open strictly after its generated_at, and only if it is still valid
  at that open. BULLISH targets long; BEARISH and NEUTRAL target cash; ABSTAIN
  schedules nothing and keeps the current exposure. If several valid
  decisions target one open, the latest wins. Unchanged exposure doesn't trade.
- Raw as-traded prices. Before an ex-date's open, a split multiplies the
  shares (no fictitious loss or turnover) and a dividend pays cash per
  post-split share on its ex-date: a research assumption that differs from
  payment-date broker cash and ledger accounting. Split and dividend coverage
  must be established; an empty query proves nothing.
- Start in cash. Buys take the most whole shares (SHARE_QUANTUM) the cash
  covers including costs; costs are one combined per-side research assumption
  in basis points, quantized to 0.0001. Residual cash stays; cash earns no
  interest.
- Buy-and-hold enters at the same first eligible open with the same cash,
  costs, actions and valuation data; a cash benchmark holds the initial cash.
  Ending equity is marked at the last close without forced liquidation.
- A session without a completed bar makes the run incomplete: no trade or
  valuation is invented for it, and return metrics are unavailable.
"""

import dataclasses
import decimal
import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.evaluation.metrics import MetricValue
from investment_engine.lineage.records import canonical_json, register
from investment_engine.market.availability import check_instrument_id, check_provider, check_utc
from investment_engine.market.corporate_actions import ActionType
from investment_engine.money import PRICE_QUANTUM, SHARE_QUANTUM, quantize, to_float64
from investment_engine.quant.adjusted import (
    ActionCoverage,
    ActionRef,
    BarRef,
    action_ref,
    bar_ref,
    completed_daily_bars,
    local_date,
    require_coverage,
    visible_actions,
)

LABEL = "SIMULATED / REPLAY · historical research"
_CURRENCY = re.compile(r"[A-Z]{3}")
_EXPOSURES = ("LONG_OR_CASH",)
_DIVIDENDS = ("CASH_ON_EX_DATE_RESEARCH_ASSUMPTION",)


@dataclass(frozen=True)
class EvaluationConfig:
    version: str
    initial_cash: Decimal
    currency: str
    costs_bps_per_side: Decimal  # provisional 5; stress run 10
    exposure: str  # LONG_OR_CASH in the first research experiment
    dividend_treatment: str  # CASH_ON_EX_DATE_RESEARCH_ASSUMPTION

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("an evaluation configuration is versioned")
        for name in ("initial_cash", "costs_bps_per_side"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise TypeError(f"{name} must be a finite Decimal")
        if self.initial_cash <= 0:
            raise ValueError("initial cash must be positive")
        if self.costs_bps_per_side < 0:
            raise ValueError("costs can't be negative")
        if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency):
            raise ValueError(f"currency must be an ISO 4217 code, not {self.currency!r}")
        if self.exposure not in _EXPOSURES:
            raise ValueError(f"exposure must be one of {_EXPOSURES}")
        if self.dividend_treatment not in _DIVIDENDS:
            raise ValueError(f"dividend treatment must be one of {_DIVIDENDS}")


@dataclass(frozen=True)
class SimulatedTrade:
    decision_lineage_id: str
    decision_time: datetime
    simulated_time: datetime
    side: str  # BUY or SELL
    quantity: Decimal
    raw_price: Decimal
    costs: Decimal
    bar_ref: BarRef
    label: str = "SIMULATED"


@dataclass(frozen=True)
class Benchmark:
    name: str  # buy_and_hold or cash
    entry_time: datetime | None
    shares: Decimal  # held at the end
    equity_curve: tuple[tuple[date, Decimal], ...]
    metrics: tuple[MetricValue, ...]


@dataclass(frozen=True)
class EvaluationRun:
    config: EvaluationConfig
    label: str
    source: str
    instrument_id: str
    first: date
    last: date
    as_of: datetime
    trades: tuple[SimulatedTrade, ...]
    equity_curve: tuple[tuple[date, Decimal], ...]  # marked at each valued close
    cash_curve: tuple[tuple[date, Decimal], ...]
    ending_shares: Decimal
    complete: bool
    metrics: tuple[MetricValue, ...]
    benchmarks: tuple[Benchmark, ...]
    lineage_refs: tuple[str, ...]  # decision lineage ids
    input_refs: tuple[BarRef | ActionRef, ...]  # realised-outcome revisions read at as_of
    limitations: tuple[str, ...]
    run_id: str = field(init=False)

    def __post_init__(self) -> None:
        content = canonical_json({f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init})
        object.__setattr__(self, "run_id", "run-" + hashlib.sha256(content.encode()).hexdigest())


for _cls in (EvaluationConfig, SimulatedTrade, Benchmark, EvaluationRun, MetricValue):
    register(_cls)


def _first_open_after(calendar, t: datetime):
    d = local_date(t, calendar)
    if calendar.is_session(d) and calendar.session(d).open > t:
        return calendar.session(d)
    return calendar.next_session(d)


class _Book:
    """One simulated cash-and-shares position, all in Decimal."""

    def __init__(self, cash: Decimal, bps: Decimal) -> None:
        self.cash, self.shares, self.rate = cash, Decimal(0), bps / Decimal(10000)

    def cost(self, quantity: Decimal, price: Decimal) -> Decimal:
        return quantize(quantity * price * self.rate, PRICE_QUANTUM)

    def apply(self, splits: Sequence, dividends: Sequence) -> None:
        for a in splits:
            self.shares *= a.ratio
        for a in dividends:
            self.cash += self.shares * a.amount.amount

    def buy(self, price: Decimal) -> Decimal:
        with decimal.localcontext() as ctx:
            ctx.prec = 60
            quantity = (self.cash / (price * (1 + self.rate))).quantize(SHARE_QUANTUM, rounding=decimal.ROUND_FLOOR)
        while quantity > 0 and quantity * price + self.cost(quantity, price) > self.cash:
            quantity -= SHARE_QUANTUM
        if quantity > 0:
            self.cash -= quantity * price + self.cost(quantity, price)
            self.shares += quantity
        return quantity

    def sell(self, price: Decimal) -> Decimal:
        quantity = self.shares
        self.cash += quantity * price - self.cost(quantity, price)
        self.shares = Decimal(0)
        return quantity

    def equity(self, close: Decimal) -> Decimal:
        return self.cash + self.shares * close


def _return_metrics(curve, initial: Decimal, incomplete: str) -> tuple[MetricValue, ...]:
    keys = ("net_return", "max_drawdown", "sharpe_daily_annualized")
    if incomplete:
        return tuple(MetricValue(k, None, 0, f"incomplete run: {incomplete}") for k in keys)
    if not curve:
        return tuple(MetricValue(k, None, 0, "no valued session") for k in keys)
    values = [to_float64(v) for _, v in curve]
    base = to_float64(initial)
    peak, drawdown = base, 0.0
    for v in values:
        peak = max(peak, v)
        drawdown = min(drawdown, v / peak - 1)
    returns = [b / a - 1 for a, b in zip(values, values[1:], strict=False)]
    sharpe, reason = None, ""
    if len(returns) < 2:
        reason = "fewer than two daily returns"
    else:
        mean = sum(returns) / len(returns)
        sd = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
        if sd == 0:
            reason = "zero variance of daily returns"
        else:
            sharpe = mean / sd * math.sqrt(252)
    return (MetricValue("net_return", values[-1] / base - 1, len(values), ""),
            MetricValue("max_drawdown", drawdown, len(values), ""),
            MetricValue("sharpe_daily_annualized", sharpe, len(returns) if sharpe is not None else 0, reason))


def simulate_research(views: Sequence[MarketView], *, reader, calendar, source: str, instrument_id: str,
                      first: date, last: date, at: datetime, coverage: ActionCoverage,
                      config: EvaluationConfig) -> EvaluationRun:
    check_provider(source)
    check_instrument_id(instrument_id)
    at = check_utc(at, "at")
    if last < first:
        raise ValueError(f"the range {first}..{last} runs backwards")
    for action_type in (ActionType.SPLIT, ActionType.DIVIDEND):
        require_coverage(coverage, source=source, instrument_id=instrument_id, action_type=action_type,
                         first=first, last=max(last, local_date(at, calendar)), at=at)
    views = sorted(views, key=lambda v: v.generated_at)
    for v in views:
        if not isinstance(v, MarketView) or v.instrument_id != instrument_id:
            raise ValueError("views must be MarketViews of the evaluated instrument")
        if v.generated_at > at:
            raise ValueError(f"a view generated at {v.generated_at} is after the evaluation time {at}")
        if len(v.evidence_refs) != 1:
            raise ValueError("each view needs exactly its lineage id (run it through the M2-07 pipeline)")

    sessions = [s for s in calendar.sessions_between(first, last) if s.close <= at]
    by_open = {s.open: s for s in sessions}
    schedule: dict[datetime, MarketView] = {}
    expired = outside = 0
    for v in views:
        target = _first_open_after(calendar, v.generated_at)
        if v.valid_until < target.open:
            expired += 1
        elif target.open not in by_open:
            outside += 1
        else:
            schedule[target.open] = v  # later views overwrite earlier ones: the latest valid decision wins
    start_index = min((sessions.index(by_open[o]) for o in schedule), default=0)
    window = sessions[start_index:]

    bars = completed_daily_bars(reader, source, instrument_id, window, at=at)
    actions = []
    if window:
        for action_type in ActionType:
            actions += [a for a in visible_actions(reader, source, instrument_id, action_type, window[0].date, at=at,
                                                   calendar=calendar) if a.ex_date <= window[-1].date]
    unsupported = sorted({str(a.action_type) for a in actions
                          if a.action_type not in (ActionType.SPLIT, ActionType.DIVIDEND)})
    if any(a.currency != config.currency for a in actions) or any(c.currency != config.currency
                                                                  for c in bars.values()):
        raise ValueError(f"bars and actions must be in the configured currency {config.currency}")

    book, hold, cash_book = _Book(config.initial_cash, config.costs_bps_per_side), \
        _Book(config.initial_cash, config.costs_bps_per_side), _Book(config.initial_cash, Decimal(0))
    trades, curve, cash_curve, hold_curve, flat_curve, missing = [], [], [], [], [], []
    hold_entry = None
    for s in window:
        today = [a for a in actions if a.ex_date == s.date]
        splits = [a for a in today if a.action_type is ActionType.SPLIT]
        dividends = [a for a in today if a.action_type is ActionType.DIVIDEND]
        book.apply(splits, dividends)
        hold.apply(splits, dividends)
        candle = bars.get(s.date)
        if candle is None:
            missing.append(s.date)
            continue
        if hold_entry is None and hold.buy(candle.open) > 0:
            hold_entry = s.open
        decision = schedule.get(s.open)
        if decision is not None and decision.direction is not ViewDirection.ABSTAIN:
            want_long = decision.direction is ViewDirection.BULLISH
            if want_long and book.shares == 0:
                quantity = book.buy(candle.open)
                side = "BUY"
            elif not want_long and book.shares > 0:
                quantity = book.sell(candle.open)
                side = "SELL"
            else:
                quantity = Decimal(0)
            if quantity > 0:
                trades.append(SimulatedTrade(decision.evidence_refs[0], decision.generated_at, s.open, side,
                                             quantity, candle.open, book.cost(quantity, candle.open),
                                             bar_ref(candle)))
        curve.append((s.date, book.equity(candle.close)))
        cash_curve.append((s.date, book.cash))
        hold_curve.append((s.date, hold.equity(candle.close)))
        flat_curve.append((s.date, cash_book.cash))

    problems = []
    if missing:
        problems.append("no completed bar for " + ", ".join(str(d) for d in missing))
    if unsupported:
        problems.append("unsupported corporate actions: " + ", ".join(unsupported))
    incomplete = "; ".join(problems)
    entries = sum(t.side == "BUY" for t in trades)
    counts = (
        ("trades", len(trades)), ("entries", entries), ("round_trips", sum(t.side == "SELL" for t in trades)),
        ("abstain_views", sum(v.direction is ViewDirection.ABSTAIN for v in views)),
        ("expired_decisions", expired), ("decisions_outside_window", outside),
    )
    metrics = _return_metrics(curve, config.initial_cash, incomplete) + tuple(
        MetricValue(k, float(n), n, "") for k, n in counts)
    benchmarks = (
        Benchmark("buy_and_hold", hold_entry, hold.shares, tuple(hold_curve),
                  _return_metrics(hold_curve, config.initial_cash, incomplete)),
        Benchmark("cash", None, Decimal(0), tuple(flat_curve),
                  _return_metrics(flat_curve, config.initial_cash, incomplete)),
    )
    limitations = [
        "SIMULATED research: not execution replay; no orders, fills, portfolio cash or ledger P&L exist.",
        "Next-open raw prices with whole-share quantities; costs are one combined per-side assumption "
        f"({config.costs_bps_per_side} bps).",
        "Dividends are credited as cash on the ex-date (research assumption; brokers pay on the payment date).",
        "Cash earns no interest.",
        f"Ending exposure is marked at the last close and not liquidated ({book.shares} shares held).",
    ]
    if problems:
        limitations.append("Run incomplete: " + incomplete)
    input_refs = tuple(sorted({bar_ref(c) for c in bars.values()}, key=lambda r: r.start_time)) + tuple(
        action_ref(a) for a in sorted(actions, key=lambda a: (a.ex_date, list(ActionType).index(a.action_type))))
    return EvaluationRun(
        config=config, label=LABEL, source=source, instrument_id=instrument_id, first=first, last=last, as_of=at,
        trades=tuple(trades), equity_curve=tuple(curve), cash_curve=tuple(cash_curve), ending_shares=book.shares,
        complete=not problems, metrics=metrics, benchmarks=benchmarks,
        lineage_refs=tuple(dict.fromkeys(v.evidence_refs[0] for v in views)), input_refs=input_refs,
        limitations=tuple(limitations))
