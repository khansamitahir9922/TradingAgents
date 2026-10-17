"""The position sizer: a view and a snapshot become intent version 1 (G1 step 6; docs/tasks/M3-08.md).

Long only (D2). BULLISH targets `max_position_fraction` of equity (D1);
BEARISH targets zero, so it sells everything held and does nothing when flat;
NEUTRAL holds; ABSTAIN or an expired view proposes nothing, with the view's
reason (Law 9). Strength isn't used to scale size: it's a heuristic scale, not
a probability (M2-04).

Prices come only from the RawReference (M3-07, Codex B1): the limit is the
reference moved by `limit_band_fraction` (D13), rounded to the cent toward the
safer side (down for buys, up for sells). A holding is valued at the same raw
close, and the snapshot must have used that same bar revision. Quantities are
whole shares, floored; less than one share proposes nothing. Deterministic and
Decimal throughout; no clock is read (`created_at = at`).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_FLOOR, ROUND_UP, Decimal, getcontext
from zoneinfo import ZoneInfo

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.market.availability import check_utc
from investment_engine.market.candles import Timeframe
from investment_engine.oms.intents import OrderIntent, Side, intent_id_for
from investment_engine.policy.rules import PolicyRules
from investment_engine.portfolio.reference import RawReference
from investment_engine.portfolio.snapshot import PortfolioSnapshot
from investment_engine.risk.decisions import exact
from investment_engine.risk.limits import RiskLimits

SIZER_VERSION = "sizer-target-weight-1"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class SizingResult:
    intent: OrderIntent | None
    reason: str  # why there is no intent, or what was sized


def _check_reference(view: MarketView, view_lineage, reference: RawReference, snapshot: PortfolioSnapshot) -> None:
    snap = view_lineage.snapshot
    if (reference.source, reference.instrument_id) != (snap.source, snap.instrument_id) \
            or reference.instrument_id != view.instrument_id or reference.bar not in tuple(view_lineage.bar_refs):
        raise ValueError("the reference doesn't come from the view's lineage (its provider, instrument and bar)")
    held = next((p for p in snapshot.positions if p.instrument_id == reference.instrument_id), None)
    if held is not None and held.price_ref != reference.bar:
        raise ValueError(f"the snapshot valued {reference.instrument_id} from another bar revision than the "
                         "reference; size from one revision only")


@exact
def size(view: MarketView, *, view_lineage, reference: RawReference, snapshot: PortfolioSnapshot,
         limits: RiskLimits, rules: PolicyRules, calendar, at: datetime, sizer_version: str) -> SizingResult:
    at = check_utc(at, "at")
    if view.direction is ViewDirection.ABSTAIN:
        return SizingResult(None, f"ABSTAIN: {view.abstain_reason or 'no reason given'}")
    if at >= view.valid_until:
        return SizingResult(None, f"view expired at {view.valid_until.isoformat()}")
    if view.direction is ViewDirection.NEUTRAL:
        return SizingResult(None, "NEUTRAL: hold, no intent")
    if Timeframe(reference.bar.timeframe).value not in rules.view_timeframes:
        return SizingResult(None, f"{reference.bar.timeframe} views aren't allowed (D12)")
    _check_reference(view, view_lineage, reference, snapshot)
    ctx = getcontext()  # the fresh calculation context `exact` set up (Codex M3 review B6)
    held = snapshot.held(reference.instrument_id)
    current = ctx.multiply(held, reference.close)
    if view.direction is ViewDirection.BULLISH:
        side = Side.BUY
        limit = ctx.multiply(reference.close, ctx.add(Decimal(1), rules.limit_band_fraction)).quantize(
            CENT, rounding=ROUND_DOWN)
        target = ctx.multiply(limits.max_position_fraction, snapshot.equity)
        if target <= current:
            return SizingResult(None, f"already at or above the target ({current} >= {target})")
        quantity = ctx.divide(ctx.subtract(target, current), limit).to_integral_value(rounding=ROUND_FLOOR)
        if quantity < 1:
            return SizingResult(None, f"below one share (room {ctx.subtract(target, current)} at {limit})")
    else:
        side = Side.SELL
        if held <= 0:
            return SizingResult(None, "BEARISH: nothing held (long only)")
        limit = ctx.multiply(reference.close, ctx.subtract(Decimal(1), rules.limit_band_fraction)).quantize(
            CENT, rounding=ROUND_UP)
        quantity = held
    zone = ZoneInfo(calendar.timezone)
    target_session = calendar.next_session(view.generated_at.astimezone(zone).date()).date
    intent = OrderIntent(
        intent_id=intent_id_for(snapshot.account_id, view_lineage.lineage_id, reference.instrument_id,
                                sizer_version),
        version=1, account_id=snapshot.account_id, instrument_id=reference.instrument_id, side=side,
        quantity=quantity, order_type=rules.order_type, limit_price=limit, time_in_force=rules.time_in_force,
        reference_price=reference.close, reference_bar=reference.bar, target_session=target_session,
        view_lineage_id=view_lineage.lineage_id, view_valid_until=view.valid_until,
        snapshot_id=snapshot.snapshot_id, sizer_version=sizer_version, policy_version=rules.version,
        risk_version=limits.version, created_at=at, supersedes=None)
    return SizingResult(intent, f"{side} {quantity} at limit {limit}")
