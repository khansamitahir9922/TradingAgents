"""The deterministic risk checks: approve, reject or reduce (architecture G1 step 8; Laws 3, 12; docs/tasks/M3-11.md).

Checks, in order, all reported:
1. fresh_data: the view isn't ABSTAIN, is still valid (D10), its required
   sources were OK, and the reference is the view's decision bar;
2. halt: an active drawdown halt rejects BUYs; SELLs pass;
3. drawdown (D3, BUY): at or past the halt fraction below the peak, the BUY is
   rejected and a HaltRequest is returned for the pipeline to latch;
4. min_price (D6, BUY);
5. position (D1, BUY only): the holding after the buy, at the limit price,
   stays within the cap; a SELL only lowers a position (S6);
6. cash (D2, BUY only): paid from cash, with gross exposure within its cap;
7. liquidity (D4, BUY and SELL): within the fraction of the average daily
   traded value over the last N sessions; a missing session rejects;
8. daily_buys (D5, BUY): a new BUY intent fails when the account's admitted
   count for the session is at the cap; one already admitted never needs a
   second slot, and a version above 1 is not evidence of admission (S3).

Failures of 1-4 or 8 reject. Failures of only 5-7 reduce to the largest whole
quantity satisfying all three (for a SELL, liquidity only: partial selling,
D18), unless that is below `min_quantity` (D9), which rejects. A reduction is
a new version (`reduced_version`), never an edit. A second reduction of a
reduced version is a defect and rejects ("reduction did not converge").
Deterministic and Decimal; comparisons exactly at a limit pass.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import ROUND_FLOOR, Context, Decimal

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.lineage.records import register
from investment_engine.market.availability import check_utc
from investment_engine.oms.intents import OrderIntent, Side
from investment_engine.policy.decisions import CheckResult
from investment_engine.portfolio.reference import RawReference
from investment_engine.portfolio.snapshot import PortfolioSnapshot
from investment_engine.quant.adjusted import BarRef
from investment_engine.risk.decisions import RiskDecision, RiskOutcome
from investment_engine.risk.limits import Halt, RiskLimits

CTX = Context(prec=34)


@dataclass(frozen=True)
class RiskInputs:
    snapshot: PortfolioSnapshot
    limits: RiskLimits
    halt: Halt | None
    reference: RawReference
    adv: Decimal | None  # mean raw close x volume over the last N sessions ending at the decision session
    adv_refs: tuple[BarRef, ...]
    admitted_buys_excluding_self: int  # read under the admission lock (M3-12 rule 4)
    already_admitted: bool
    view: MarketView
    view_lineage: object
    adv_missing: str = ""  # why adv is None


@dataclass(frozen=True)
class HaltRequest:
    account_id: str
    at: datetime
    limits_version: str
    reason: str


register(HaltRequest)


def average_daily_value(knowledge, calendar, source: str, instrument_id: str, session: date, sessions: int, *,
                        at: datetime) -> tuple[Decimal | None, tuple[BarRef, ...], str]:
    """Mean raw close x volume of the bars of the `sessions` regular sessions ending at `session`, all known at T.

    Any expected session without a known CLOSED bar gives (None, refs so far, reason); older bars are never used
    in its place (Codex re-review S2)."""
    days, d = [], session
    for _ in range(sessions):
        days.append(d)
        d = calendar.previous_session(d).date
    total, refs = Decimal(0), []
    for day in reversed(days):
        bar = knowledge.latest_closed(source, instrument_id, day, at=at, calendar=calendar)
        if bar is None:
            return None, tuple(refs), f"volume history unavailable: {day} not known at {at.isoformat()}"
        refs.append(BarRef(bar.source, bar.instrument_id, bar.timeframe, bar.start_time, bar.revision, bar.import_id,
                           bar.available_from, bar.availability_basis))
        total = CTX.add(total, CTX.multiply(bar.close, bar.volume))
    return CTX.divide(total, Decimal(sessions)), tuple(refs), ""


def _floor(x: Decimal) -> Decimal:
    return x.to_integral_value(rounding=ROUND_FLOOR)


def _pct(x: Decimal) -> str:
    return f"{CTX.multiply(x, Decimal(100)).quantize(Decimal('0.1'))}%"


def check_risk(intent: OrderIntent, inputs: RiskInputs, *, at: datetime) -> tuple[RiskDecision, HaltRequest | None]:
    at = check_utc(at, "at")
    s, limits, ref, view = inputs.snapshot, inputs.limits, inputs.reference, inputs.view
    if limits.version != intent.risk_version:
        raise ValueError(f"the intent was sized under {intent.risk_version}, not {limits.version}")
    if s.snapshot_id != intent.snapshot_id:
        raise ValueError("the snapshot isn't the one the intent was sized from")
    buy = intent.side is Side.BUY
    qty, limit = intent.quantity, intent.limit_price
    checks, halt_request = [], None
    reject, reducible = [], {}

    problems = []
    if view.direction is ViewDirection.ABSTAIN:
        problems.append(f"the view is ABSTAIN ({view.abstain_reason})")
    if at >= view.valid_until:
        problems.append(f"the view expired at {view.valid_until.isoformat()}")
    if not view.data_health.required_sources_ok:
        problems.append("the view's required sources were not OK")
    if intent.reference_bar != ref.bar or ref.bar not in tuple(inputs.view_lineage.bar_refs):
        problems.append("the reference isn't the view's decision bar")
    checks.append(CheckResult("fresh_data", not problems, "; ".join(problems) or
                              f"view valid until {view.valid_until.isoformat()}; reference {ref.session} rev "
                              f"{ref.bar.revision}"))
    if problems:
        reject.append("fresh_data")

    halted = inputs.halt is not None and inputs.halt.halted
    ok = not (halted and buy)
    checks.append(CheckResult("halt", ok, f"drawdown halt since {inputs.halt.at.isoformat()}" if not ok
                              else ("halted, but a sell reduces risk" if halted else "no halt")))
    if not ok:
        reject.append("halt")

    if buy and s.peak_equity > 0:
        threshold = CTX.multiply(s.peak_equity, CTX.subtract(Decimal(1), limits.drawdown_halt_fraction))
        drawdown = CTX.divide(CTX.subtract(s.peak_equity, s.equity), s.peak_equity)
        ok = s.equity > threshold
        checks.append(CheckResult("drawdown", ok, f"drawdown {_pct(drawdown)} < {_pct(limits.drawdown_halt_fraction)}"
                                  f" ({limits.version})" if ok else
                                  f"drawdown {_pct(drawdown)} >= {_pct(limits.drawdown_halt_fraction)} "
                                  f"({limits.version}): halt"))
        if not ok:
            reject.append("drawdown")
            if not halted:
                halt_request = HaltRequest(s.account_id, at, limits.version,
                                           f"drawdown {_pct(drawdown)} >= {_pct(limits.drawdown_halt_fraction)}")
    else:
        checks.append(CheckResult("drawdown", True, "a sell reduces risk" if not buy else "no peak yet"))

    ok = not buy or ref.close >= limits.min_price
    checks.append(CheckResult("min_price", ok, f"{ref.close} >= {limits.min_price} USD" if ok
                              else f"{ref.close} < {limits.min_price} USD minimum (D6)"))
    if not ok:
        reject.append("min_price")

    held = s.held(intent.instrument_id)
    if buy:
        cap = CTX.multiply(limits.max_position_fraction, s.equity)
        after = CTX.multiply(CTX.add(held, qty), limit)
        ok = after <= cap
        allowed = max(_floor(CTX.subtract(CTX.divide(cap, limit), held)), Decimal(0))
        share = CTX.divide(after, s.equity) if s.equity > 0 else Decimal(0)
        checks.append(CheckResult("position", ok, f"position {_pct(share)} <= {_pct(limits.max_position_fraction)} "
                                  f"({limits.version})" if ok else
                                  f"position {_pct(share)} > {_pct(limits.max_position_fraction)} ({limits.version}): "
                                  f"reduce {qty} -> {allowed}"))
        if not ok:
            reducible["position"] = allowed
        gross_now = sum((p.value for p in s.positions), Decimal(0))
        cost = CTX.multiply(qty, limit)
        room = min(s.cash, CTX.subtract(CTX.multiply(limits.max_gross_exposure_fraction, s.equity), gross_now))
        ok = cost <= room
        allowed = max(_floor(CTX.divide(room, limit)), Decimal(0)) if room > 0 else Decimal(0)
        checks.append(CheckResult("cash", ok, f"cost {cost} <= {room} available" if ok else
                                  f"cost {cost} > {room} available (no borrowing, D2): reduce {qty} -> {allowed}"))
        if not ok:
            reducible["cash"] = allowed
    else:
        checks.append(CheckResult("position", True, "a sell only lowers the position"))
        checks.append(CheckResult("cash", True, "a sell needs no cash"))

    if inputs.adv is None:
        checks.append(CheckResult("liquidity", False, inputs.adv_missing or "volume history unavailable"))
        reject.append("liquidity")
    else:
        cap = CTX.multiply(limits.max_order_adv_fraction, inputs.adv)
        value = CTX.multiply(qty, ref.close)
        ok = value <= cap
        allowed = _floor(CTX.divide(cap, ref.close))
        checks.append(CheckResult("liquidity", ok, f"order {value} <= {_pct(limits.max_order_adv_fraction)} of "
                                  f"{limits.adv_sessions}-session ADV {inputs.adv.quantize(Decimal('0.01'))}" if ok else
                                  f"order {value} > {_pct(limits.max_order_adv_fraction)} of {limits.adv_sessions}-"
                                  f"session ADV {inputs.adv.quantize(Decimal('0.01'))}: reduce {qty} -> {allowed}"))
        if not ok:
            reducible["liquidity"] = allowed

    if buy:
        count, already = inputs.admitted_buys_excluding_self, inputs.already_admitted
        ok = already or count < limits.max_new_buys_per_session
        checks.append(CheckResult("daily_buys", ok, f"already admitted (one slot of {limits.max_new_buys_per_session})"
                                  if already else f"{count} of {limits.max_new_buys_per_session} new buys admitted "
                                  f"for {intent.target_session}" + ("" if ok else ": cap reached (D5)")))
        if not ok:
            reject.append("daily_buys")
    else:
        checks.append(CheckResult("daily_buys", True, "a sell isn't a new buy"))

    reduced = None
    if reject:
        outcome = RiskOutcome.REJECT
    elif reducible:
        target = min(reducible.values())
        if intent.supersedes is not None:
            checks.append(CheckResult("reduction", False, "reduction did not converge: a reduced version needed a "
                                                          "second reduction"))
            outcome = RiskOutcome.REJECT
        elif target < limits.min_quantity:
            checks.append(CheckResult("reduction", False, f"the reduced quantity {target} is below "
                                                          f"{limits.min_quantity} share (D9)"))
            outcome = RiskOutcome.REJECT
        else:
            outcome, reduced = RiskOutcome.REDUCE, target
    else:
        outcome = RiskOutcome.APPROVE
    return (RiskDecision(intent.intent_id, intent.version, outcome, tuple(checks), limits.version, s.snapshot_id,
                         reduced, at), halt_request)


def reduced_version(intent: OrderIntent, decision: RiskDecision, *, at: datetime) -> OrderIntent:
    """The next version: the same intent with the reduced quantity (Law 12: a new version, never an edit)."""
    if decision.outcome is not RiskOutcome.REDUCE or (decision.intent_id, decision.intent_version) != (
            intent.intent_id, intent.version):
        raise ValueError("only this intent version's REDUCE decision makes a reduced version")
    return replace(intent, version=intent.version + 1, quantity=decision.reduced_quantity, supersedes=intent.version,
                   created_at=check_utc(at, "at"))
