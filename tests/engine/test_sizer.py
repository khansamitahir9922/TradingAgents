"""The OrderIntent contract and the position sizer (docs/tasks/M3-08.md)."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from investment_engine.decision.market_view import MarketView, ViewDirection
from investment_engine.market.availability import AvailabilityBasis
from investment_engine.market.calendar.us_equities import load_us_equities_calendar
from investment_engine.market.candles import Timeframe
from investment_engine.market.data_health import Applicability, DataHealth
from investment_engine.oms.intents import IntentState, OrderIntent, Side, intent_id_for
from investment_engine.policy.decisions import CheckResult, PolicyDecision
from investment_engine.policy.rules import PolicyRules
from investment_engine.portfolio.reference import RawReference
from investment_engine.portfolio.sizer import SIZER_VERSION, size
from investment_engine.portfolio.snapshot import PortfolioSnapshot, PositionValue, SnapshotSource
from investment_engine.quant.adjusted import BarRef
from investment_engine.risk.decisions import NotRun, RiskDecision, RiskOutcome
from investment_engine.risk.limits import RiskLimits

CAL = load_us_equities_calendar()
NVDA = "EQ_US_NVDA"
DAY = date(2024, 6, 3)
T = CAL.session(DAY).close + timedelta(minutes=5)
BAR = BarRef("yfinance", NVDA, Timeframe.D1, CAL.session(DAY).open, 1, "bars", CAL.session(DAY).close,
             AvailabilityBasis.BACKFILL_ASSUMED)
LIMITS = RiskLimits("risk-1", Decimal("0.10"), Decimal("1.00"), True, Decimal("0.15"), Decimal("0.01"), 20, 5,
                    Decimal("5"), Decimal("1"))
RULES = PolicyRules("policy-1", (), "REGULAR_ONLY", "LIMIT", "DAY", Decimal("0.01"), ("D1",))


def view(direction="BULLISH", at=T, valid_until=None, reason=""):
    health = DataHealth(NVDA, at, Applicability(True, ""), (), True)
    strength = 0.5 if direction in ("BULLISH", "BEARISH") else 0.0
    return MarketView(NVDA, ViewDirection(direction), strength, None, "5 sessions", at,
                      valid_until or CAL.session(date(2024, 6, 4)).close, None, health, ("lin-view",), "0.1.0",
                      reason or ("warm-up" if direction == "ABSTAIN" else ""), ())


def lineage(bar=BAR):
    return SimpleNamespace(lineage_id="lin-view", bar_refs=(bar,),
                           snapshot=SimpleNamespace(source="yfinance", instrument_id=NVDA, session_date=DAY))


def reference(close="120.00", bar=BAR):
    return RawReference("yfinance", NVDA, DAY, bar, Decimal(close), "USD", T)


def snap(cash="100000", held=None, price="120.00", bar=BAR):
    positions = () if held is None else (PositionValue(NVDA, Decimal(held), Decimal(price), bar,
                                                       Decimal(held) * Decimal(price)),)
    equity = Decimal(cash) + sum((p.value for p in positions), Decimal(0))
    return PortfolioSnapshot("R1", T, SnapshotSource.DECLARED_STARTING_STATE, "USD", Decimal(cash), positions, equity,
                             T, equity, "sst-x")


def sized(v=None, *, ref=None, s=None, limits=LIMITS, at=T):
    return size(v or view(), view_lineage=lineage(), reference=ref or reference(), snapshot=s or snap(),
                limits=limits, rules=RULES, calendar=CAL, at=at, sizer_version=SIZER_VERSION)


@pytest.mark.unit
def test_the_first_buy_of_a_cash_only_account_is_sized_from_the_raw_reference_alone():
    result = sized()
    intent = result.intent
    assert intent is not None and intent.side is Side.BUY and intent.version == 1 and intent.supersedes is None
    assert intent.limit_price == Decimal("121.20")  # 120.00 x 1.01, rounded down for a buy
    assert intent.quantity == Decimal("82")  # floor(10,000 / 121.20)
    assert intent.reference_price == Decimal("120.00") and intent.reference_bar == BAR
    assert intent.target_session == date(2024, 6, 4) and intent.created_at == T
    assert (intent.order_type, intent.time_in_force) == ("LIMIT", "DAY")
    assert (intent.policy_version, intent.risk_version, intent.snapshot_id) == ("policy-1", "risk-1",
                                                                              snap().snapshot_id)


@pytest.mark.unit
@pytest.mark.parametrize("cash, close, expected", [
    ("100000", "120.00", "82"),
    ("50000", "33.33", "148"),  # floor(5,000 / 33.66)
    ("1213", "120.00", "1"),  # target 121.30 buys exactly one share at 121.20
])
def test_hand_calculated_buy_sizes(cash, close, expected):
    assert sized(ref=reference(close), s=snap(cash=cash)).intent.quantity == Decimal(expected)


@pytest.mark.unit
def test_below_one_share_already_at_target_neutral_abstain_and_expired_give_no_intent_with_reasons():
    cases = {
        "below one share": sized(s=snap(cash="1000")),  # target 100 < one share at 121.20
        "already at": sized(s=snap(cash="0", held="100")),  # 12,000 held >= 10% of 12,000
        "NEUTRAL": sized(view("NEUTRAL")),
        "ABSTAIN": sized(view("ABSTAIN", reason="required data not OK")),
        "expired": sized(at=view().valid_until),
    }
    for reason, result in cases.items():
        assert result.intent is None and reason in result.reason, (reason, result.reason)


@pytest.mark.unit
def test_bearish_sells_everything_held_and_does_nothing_when_flat():
    flat = sized(view("BEARISH"))
    assert flat.intent is None and "nothing held" in flat.reason
    sell = sized(view("BEARISH"), s=snap(cash="0", held="25")).intent
    assert sell.side is Side.SELL and sell.quantity == Decimal("25")
    assert sell.limit_price == Decimal("118.80")  # 120.00 x 0.99, rounded up for a sell
    odd = sized(view("BEARISH"), ref=reference("33.333"), s=snap(cash="0", held="3", price="33.333")).intent
    assert odd.limit_price == Decimal("33.00")  # 32.99967 rounded up to the cent


@pytest.mark.unit
def test_a_reference_that_disagrees_with_the_lineage_or_the_holding_raises():
    other = replace(BAR, revision=2)
    with pytest.raises(ValueError, match="lineage"):
        sized(ref=reference(bar=other))
    with pytest.raises(ValueError, match="lineage"):
        sized(ref=replace(reference(), source="testvendor"))
    with pytest.raises(ValueError, match="revision"):
        sized(s=snap(cash="0", held="10", bar=other))  # a holding valued from another bar revision


@pytest.mark.unit
def test_the_same_inputs_give_the_same_intent_and_the_id_depends_on_the_sizer_version():
    a, b = sized().intent, sized().intent
    assert a == b and a.intent_id == intent_id_for("R1", "lin-view", NVDA, SIZER_VERSION)
    assert intent_id_for("R1", "lin-view", NVDA, "sizer-other") != a.intent_id


@pytest.mark.unit
def test_order_intents_refuse_bad_values():
    good = sized().intent
    for change in ({"quantity": Decimal("1.5")}, {"quantity": Decimal("0")}, {"quantity": 5.0},
                   {"limit_price": 121.2}, {"created_at": datetime(2024, 6, 3)}, {"version": 0},
                   {"order_type": "MARKET"}, {"time_in_force": "GTC"}):
        with pytest.raises((TypeError, ValueError)):
            replace(good, **change)
    with pytest.raises(AttributeError):
        good.quantity = Decimal("1")  # frozen
    assert set(OrderIntent.MATERIAL) == {"account_id", "instrument_id", "side", "quantity", "order_type",
                                         "limit_price", "time_in_force"}
    assert len(IntentState) == 9 and IntentState.CONVERTED in IntentState


@pytest.mark.unit
def test_decision_contracts_and_not_run_are_registered_values():
    from investment_engine.lineage.records import canonical_json, decode, encode

    decision = PolicyDecision("int-x", 1, True, (CheckResult("autonomy", True, "Level 1"),), "policy-1", 1, T)
    risk = RiskDecision("int-x", 1, RiskOutcome.REDUCE, (CheckResult("position", False, "12% > 10%"),), "risk-1",
                        "psn-x", Decimal("64"), T)
    not_run = NotRun("risk", "policy rejected: risk not evaluated")
    for value in (decision, risk, not_run, sized().intent):
        assert decode(encode(value)) == value and canonical_json(value)
    with pytest.raises(ValueError):
        RiskDecision("int-x", 1, RiskOutcome.APPROVE, (), "risk-1", "psn-x", Decimal("1"), T)  # quantity only for REDUCE
    with pytest.raises(ValueError):
        RiskDecision("int-x", 1, RiskOutcome.REDUCE, (), "risk-1", "psn-x", None, T)
    with pytest.raises(ValueError):
        CheckResult("autonomy", True, "")  # a reason is always set
