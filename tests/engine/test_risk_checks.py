"""The deterministic risk checks: approve, reject or reduce (docs/tasks/M3-11.md)."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from investment_engine.decision.market_view import ViewDirection
from investment_engine.oms.intents import Side
from investment_engine.portfolio.snapshot import PortfolioSnapshot, PositionValue, SnapshotSource
from investment_engine.risk.checks import RiskInputs, check_risk, reduced_version
from investment_engine.risk.decisions import RiskOutcome
from investment_engine.risk.limits import Halt
from tests.engine.test_sizer import BAR, LIMITS, NVDA, T, lineage, reference, sized, snap, view

BIG_ADV = Decimal("10000000")


def inputs(s=None, *, ref=None, v=None, adv=BIG_ADV, halt=None, admitted=0, already=False, limits=LIMITS):
    return RiskInputs(snapshot=s or snap(), limits=limits, halt=halt, reference=ref or reference(), adv=adv,
                      adv_refs=(), admitted_buys_excluding_self=admitted, already_admitted=already,
                      view=v or view(), view_lineage=lineage(), adv_missing="" if adv is not None else
                      "volume history unavailable: 2024-05-31 not known")


def decide(intent=None, **kw):
    i = intent or sized().intent
    s = kw.pop("s", None) or snap()
    return check_risk(replace(i, snapshot_id=s.snapshot_id), inputs(s, **kw), at=T)


def failed(decision):
    return [c.name for c in decision.checks if not c.passed]


def other_holding(cash, amd_value, peak=None):
    amd = PositionValue("EQ_US_AMD", Decimal(1), Decimal(amd_value), replace(BAR, instrument_id="EQ_US_AMD"),
                        Decimal(amd_value))
    equity = Decimal(cash) + Decimal(amd_value)
    return PortfolioSnapshot("R1", T, SnapshotSource.DECLARED_STARTING_STATE, "USD", Decimal(cash), (amd,), equity, T,
                             Decimal(peak) if peak else equity, "sst-x")


@pytest.mark.unit
def test_a_sized_first_buy_is_approved_and_every_check_reports():
    decision, halt = decide()
    assert decision.outcome is RiskOutcome.APPROVE and halt is None and decision.reduced_quantity is None
    assert [c.name for c in decision.checks] == ["fresh_data", "halt", "drawdown", "min_price", "position", "cash",
                                                 "liquidity", "daily_buys"]
    assert all(c.reason for c in decision.checks) and decision.risk_version == "risk-1"


@pytest.mark.unit
def test_exactly_at_the_position_limit_passes():
    s = snap(cash="12120")  # 10% = 1,212.00 = 10 x 121.20 exactly
    intent = sized(s=s).intent
    assert intent.quantity == Decimal(10)
    assert decide(intent, s=s)[0].outcome is RiskOutcome.APPROVE


@pytest.mark.unit
def test_each_reducible_check_alone_reduces_to_its_hand_calculated_quantity():
    big = replace(sized().intent, quantity=Decimal(100))  # 100 x 121.20 = 12,120 > 10,000
    position, _ = decide(big)
    assert failed(position) == ["position"] and position.outcome is RiskOutcome.REDUCE
    assert position.reduced_quantity == Decimal(82)  # floor(10,000 / 121.20)
    assert "reduce 100 -> 82" in next(c.reason for c in position.checks if c.name == "position")
    cash, _ = decide(s=other_holding("1000", "99000"))  # 82 x 121.20 > 1,000 cash; gross room 1,000
    assert failed(cash) == ["cash"] and cash.reduced_quantity == Decimal(8)  # floor(1,000 / 121.20)
    liquidity, _ = decide(adv=Decimal("500000"))  # cap 5,000; 82 x 120 = 9,840
    assert failed(liquidity) == ["liquidity"] and liquidity.reduced_quantity == Decimal(41)  # floor(5,000 / 120)


@pytest.mark.unit
def test_several_reducible_failures_reduce_to_the_smallest_and_below_one_share_rejects():
    big = replace(sized().intent, quantity=Decimal(100))
    both, _ = decide(big, adv=Decimal("500000"))
    assert failed(both) == ["position", "liquidity"] and both.reduced_quantity == Decimal(41)
    tiny, _ = decide(adv=Decimal("5000"))  # cap 50 < one share at 120
    assert tiny.outcome is RiskOutcome.REJECT and "below 1 share" in tiny.checks[-1].reason


@pytest.mark.unit
def test_a_reduction_is_a_new_version_and_its_recheck_approves_but_a_second_reduction_rejects():
    big = replace(sized().intent, quantity=Decimal(100), snapshot_id=snap().snapshot_id)
    decision, _ = check_risk(big, inputs(), at=T)
    v2 = reduced_version(big, decision, at=T + timedelta(seconds=1))
    assert (v2.intent_id, v2.version, v2.supersedes, v2.quantity) == (big.intent_id, 2, 1, Decimal(82))
    assert all(getattr(v2, n) == getattr(big, n) for n in big.MATERIAL if n != "quantity")
    assert check_risk(v2, inputs(), at=T)[0].outcome is RiskOutcome.APPROVE
    forced, _ = check_risk(replace(v2, quantity=Decimal(100)), inputs(), at=T)
    assert forced.outcome is RiskOutcome.REJECT and "did not converge" in forced.checks[-1].reason
    approve, _ = check_risk(replace(big, quantity=Decimal(1)), inputs(), at=T)
    with pytest.raises(ValueError, match="REDUCE"):  # only a REDUCE decision makes a new version
        reduced_version(big, approve, at=T)


@pytest.mark.unit
def test_a_halt_rejects_buys_and_passes_sells_and_a_drawdown_at_the_threshold_requests_one():
    halt = Halt("R1", True, T - timedelta(days=1), "core-engine", "drawdown", "risk-1", None)
    buy, _ = decide(halt=halt)
    assert buy.outcome is RiskOutcome.REJECT and "halt" in failed(buy)
    held = snap(cash="0", held="25")
    sell_intent = sized(view("BEARISH"), s=held).intent
    sell, _ = decide(sell_intent, s=held, halt=halt)
    assert sell.outcome is RiskOutcome.APPROVE and sell_intent.side is Side.SELL
    falling = other_holding("84999", "1", peak="100000")  # equity 85,000: exactly 15% below the peak
    decision, request = decide(s=falling)
    assert decision.outcome is RiskOutcome.REJECT and "drawdown" in failed(decision)
    assert request is not None and request.limits_version == "risk-1" and request.account_id == "R1"
    assert decide(s=falling, halt=halt)[1] is None  # already halted: no second request


@pytest.mark.unit
def test_stale_or_unhealthy_views_missing_volume_and_cheap_stocks_reject():
    from investment_engine.market.data_health import Applicability, DataHealth

    abstain = replace(view(), direction=ViewDirection.ABSTAIN, strength=0.0, abstain_reason="required data not OK")
    unhealthy = replace(view(), data_health=DataHealth(NVDA, T, Applicability(True, ""), (), False))
    for v in (abstain, unhealthy):
        assert decide(v=v)[0].outcome is RiskOutcome.REJECT
    expired, _ = check_risk(replace(sized().intent, snapshot_id=snap().snapshot_id), inputs(), at=view().valid_until)
    assert "fresh_data" in failed(expired)
    missing, _ = decide(adv=None)
    assert missing.outcome is RiskOutcome.REJECT and "2024-05-31" in next(c.reason for c in missing.checks
                                                                          if c.name == "liquidity")
    cheap = sized(ref=reference("4.99")).intent
    assert "min_price" in failed(decide(cheap, ref=reference("4.99"))[0])


@pytest.mark.unit
def test_the_daily_buy_cap_counts_only_new_admissions():
    assert failed(decide(admitted=5)[0]) == ["daily_buys"]
    assert decide(admitted=5, already=True)[0].outcome is RiskOutcome.APPROVE  # already holds its slot
    v2 = replace(sized().intent, version=2, supersedes=1)
    assert failed(decide(v2, admitted=5)[0]) == ["daily_buys"]  # a v2 never admitted needs a slot (S3)
    assert decide(admitted=4)[0].outcome is RiskOutcome.APPROVE


@pytest.mark.unit
def test_a_large_holding_sells_down_to_the_volume_limit_partial_selling_d18():
    held = snap(cash="0", held="1000", price="100.00")  # $100,000 in one stock, far above the 10% cap
    ref = reference("100.00")
    sell = sized(view("BEARISH"), ref=ref, s=held).intent
    decision, _ = decide(sell, s=held, ref=ref, adv=Decimal("1000000"))  # liquidity cap $10,000
    assert decision.outcome is RiskOutcome.REDUCE and decision.reduced_quantity == Decimal(100)
    assert failed(decision) == ["liquidity"]  # position and cash don't apply to a sell


@pytest.mark.unit
def test_decisions_are_deterministic_and_inconsistent_inputs_raise():
    assert decide() == decide()
    with pytest.raises(ValueError, match="sized under"):
        decide(limits=replace(LIMITS, version="risk-2"))
    with pytest.raises(ValueError, match="snapshot"):
        check_risk(sized().intent, inputs(snap(cash="1")), at=T)


# ---------------------------------------------------------------- the caller's decimal context never matters (B6)

AMBIENT = [  # (precision, rounding, extra traps): what a caller might have set
    (6, "ROUND_FLOOR", ()), (6, "ROUND_CEILING", ()), (9, "ROUND_HALF_UP", ("Inexact",)),
    (50, "ROUND_DOWN", ("Rounded",)), (28, "ROUND_05UP", ("Inexact", "Rounded")),
]


def _ambient(prec, rounding, traps):
    import decimal

    context = decimal.Context(prec=prec, rounding=getattr(decimal, rounding))
    for trap in traps:
        context.traps[getattr(decimal, trap)] = True
    return context


def _risk_cases():
    from investment_engine.lineage.records import canonical_json

    big = replace(sized().intent, quantity=Decimal(100), snapshot_id=snap().snapshot_id)
    decision, _ = check_risk(big, inputs(adv=Decimal("500000")), at=T)  # position and liquidity both reduce
    v2 = reduced_version(big, decision, at=T + timedelta(seconds=1))
    approve = decide()
    drawdown = decide(s=other_holding("85000", "1000", peak="101000"))  # at the threshold: REJECT and a halt
    return canonical_json([approve, decision, v2, check_risk(v2, inputs(adv=Decimal("500000")), at=T), drawdown])


@pytest.mark.unit
@pytest.mark.parametrize("prec, rounding, traps", AMBIENT)
def test_risk_results_ignore_the_callers_decimal_context(prec, rounding, traps):
    """Codex B6: ambient rounding changed recorded reasons, and precision 6 raised InvalidOperation."""
    import decimal

    expected = _risk_cases()
    with decimal.localcontext(_ambient(prec, rounding, traps)) as caller:
        before = (caller.prec, caller.rounding, dict(caller.traps))
        assert _risk_cases() == expected  # identical quantities, decisions, reasons and identities
        assert (caller.prec, caller.rounding, dict(caller.traps)) == before  # the caller's context is untouched
