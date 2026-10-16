"""The deterministic policy checks (docs/tasks/M3-10.md)."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType, SimpleNamespace

import pytest

from investment_engine.market.instruments import Instrument, InstrumentStatus
from investment_engine.oms.intents import Side
from investment_engine.policy.accounts import Account, AccountKind, AutonomySetting
from investment_engine.policy.checks import check_policy
from tests.engine.test_sizer import CAL, NVDA, RULES, T, sized, snap

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
LINEAGE = SimpleNamespace(strategy_versions=MappingProxyType({"pullback": "1.0.0", "trend": "1.0.0"}))


def account(kind=AccountKind.RESEARCH):
    return Account("R1", kind, "USD", datetime(2019, 1, 2, tzinfo=UTC), NOW)


def autonomy(level=1):
    return AutonomySetting("R1", level, datetime(2019, 1, 2, tzinfo=UTC), NOW, 2, "owner", "demo")


def instrument(**changes):
    values = {"instrument_id": NVDA, "asset_class": "EQUITY", "currency": "USD", "exchange": "XNAS",
              "timezone": "America/New_York", "status": "ACTIVE", "active_from": date(1999, 1, 22), "active_to": None}
    values.update(changes)
    return Instrument(**values)


def decide(intent=None, *, kind=AccountKind.RESEARCH, level=1, rules=RULES, inst=None, snapshot=None):
    i = intent or sized().intent
    return check_policy(i, account=account(kind), autonomy=autonomy(level), rules=rules, instrument=inst or instrument(),
                        snapshot=snapshot or snap(), view_lineage=LINEAGE, calendar=CAL, at=T)


def failed(decision):
    return [c.name for c in decision.checks if not c.passed]


@pytest.mark.unit
def test_all_checks_run_in_order_and_pass_for_a_research_account_at_level_1():
    d = decide()
    assert d.passed and [c.name for c in d.checks] == ["autonomy", "promotion", "instrument", "restricted",
                                                       "long_only", "trading_window"]
    assert all(c.reason for c in d.checks) and d.policy_version == "policy-1" and d.autonomy_level == 1
    assert d.decided_at == T


@pytest.mark.unit
def test_each_check_failing_alone_with_its_reason():
    cases = [
        (decide(level=0), "autonomy", "advisory account (Level 0)"),
        (decide(kind=AccountKind.PAPER), "promotion", "PROMOTION NOT ASSESSED: strategy versions pullback=1.0.0, "
                                                      "trend=1.0.0 have no accepted promotion (OPEN-09)"),
        (decide(inst=instrument(status=InstrumentStatus.SUSPENDED)), "instrument", "SUSPENDED"),
        (decide(rules=replace(RULES, restricted=(NVDA,))), "restricted", "restricted list"),
        (decide(replace(sized().intent, target_session=date(2024, 6, 8))), "trading_window", "not a regular session"),
    ]
    for decision, name, reason in cases:
        assert failed(decision) == [name], (name, failed(decision))
        assert reason in next(c.reason for c in decision.checks if c.name == name)


@pytest.mark.unit
def test_several_failures_are_all_reported_and_paper_fails_promotion_at_levels_1_and_2():
    d = decide(kind=AccountKind.PAPER, level=0, rules=replace(RULES, restricted=(NVDA,)))
    assert failed(d) == ["autonomy", "promotion", "restricted"] and not d.passed
    for level in (1, 2):
        assert failed(decide(kind=AccountKind.PAPER, level=level)) == ["promotion"]


@pytest.mark.unit
def test_a_sell_larger_than_the_holding_fails_long_only():
    from tests.engine.test_sizer import view

    sell = sized(view("BEARISH"), s=snap(cash="0", held="25")).intent
    assert decide(sell, snapshot=snap(cash="0", held="25")).passed
    too_big = replace(sell, quantity=Decimal("26"))
    d = decide(too_big, snapshot=snap(cash="0", held="25"))
    assert failed(d) == ["long_only"] and "no short selling" in d.checks[4].reason
    assert sell.side is Side.SELL


@pytest.mark.unit
def test_an_instrument_outside_its_active_dates_fails():
    delisted = instrument(status=InstrumentStatus.DELISTED, active_to=date(2024, 6, 4))
    assert failed(decide(inst=delisted)) == ["instrument"]
    later = instrument(active_from=date(2024, 6, 5))
    assert failed(decide(inst=later)) == ["instrument"]


@pytest.mark.unit
def test_an_older_restricted_version_does_not_apply_after_a_newer_one_removes_it():
    newer = replace(RULES, version="policy-2", restricted=())
    intent = replace(sized().intent, policy_version="policy-2")
    assert decide(intent, rules=newer).passed
    with pytest.raises(ValueError, match="sized under"):  # the decision uses exactly the intent's version
        decide(sized().intent, rules=newer)


@pytest.mark.unit
def test_same_inputs_give_equal_decisions_and_inconsistent_inputs_raise():
    assert decide() == decide()
    with pytest.raises(ValueError, match="same account"):
        decide(replace(sized().intent, account_id="R2"))
    with pytest.raises(ValueError, match="instrument"):
        decide(inst=instrument(instrument_id="EQ_US_AMD"))
