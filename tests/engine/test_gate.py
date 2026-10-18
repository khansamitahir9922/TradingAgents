"""The Pre-Execution Gate's checks, as a pure function (docs/tasks/M4-05.md rules 1, 2, 3, 5)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from investment_engine.execution.gate import (
    ACCEPTED_PROMOTION,
    GateInputs,
    Missing,
    SessionWindow,
    check_gate,
)
from investment_engine.killswitch.flag import FlagReading, FlagState
from investment_engine.oms.intent_store import StoredIntent
from investment_engine.oms.intents import IntentState, Side
from investment_engine.oms.order_states import OrderState
from investment_engine.oms.orders import Order, OrderStatus, order_ids
from investment_engine.policy.accounts import AccountKind
from tests.engine.test_sizer import sized

AT = datetime(2026, 10, 19, 10, tzinfo=UTC)
NAMES = ["kill_switch", "intent_version", "approval", "view", "controls", "positions", "session", "cancel"]
INTENT = replace(sized().intent, intent_id="int-g", account_id="R1")
ORDER = Order(*order_ids("int-g", 1), "int-g", 1, "content-1", "pfp-1", "R1", AccountKind.RESEARCH, INTENT.instrument_id,
              Side.BUY, Decimal(10), "LIMIT", Decimal("101.00"), "DAY", date(2026, 10, 19), AT - timedelta(hours=1))
STATUS = OrderStatus(ORDER.order_id, OrderState.NEW, 1, Decimal(0), None, None, 0)
STORED = StoredIntent(INTENT, IntentState.CONVERTED, 4, None, None, None, "core", AT, AT + timedelta(hours=8), AT, "ilin")
ENABLED = FlagReading(True, FlagState(True, 3, AT, "owner", True, "go"), None)
GOOD = GateInputs(
    latest_version=1, intent_state=IntentState.CONVERTED, intent_content_id="content-1",
    approval_expires_at=AT + timedelta(hours=8), view_valid_until=AT + timedelta(hours=8),
    reference_current=True, action_since_reference=False, risk_version=INTENT.risk_version,
    policy_version=INTENT.policy_version, autonomy_setting="aut-1", pinned_autonomy_setting="aut-1",
    halted=False, restricted=False, promotion=None, fingerprint_now="pfp-1", pending_cancel=False,
    session=SessionWindow(AT - timedelta(hours=14), AT + timedelta(minutes=30), AT + timedelta(hours=7)))


def decide(inputs=GOOD, *, order=ORDER, kill=ENABLED, at=AT):
    return check_gate(order, STATUS, at=at, inputs=inputs, intent=STORED, kill_switch=kill)


def failed(decision):
    return [c.name for c in decision.checks if not c.passed]


@pytest.mark.unit
def test_a_good_order_passes_with_all_eight_checks_recorded():
    decision = decide()
    assert decision.passed and [c.name for c in decision.checks] == NAMES


@pytest.mark.unit
@pytest.mark.parametrize("change, name", [
    ({"latest_version": 2}, "intent_version"),
    ({"intent_state": IntentState.EXPIRED}, "intent_version"),
    ({"intent_content_id": "content-other"}, "intent_version"),
    ({"approval_expires_at": AT}, "approval"),
    ({"view_valid_until": AT}, "view"),
    ({"reference_current": False}, "view"),
    ({"action_since_reference": True}, "view"),
    ({"risk_version": "risk-9"}, "controls"),
    ({"policy_version": "policy-9"}, "controls"),
    ({"autonomy_setting": "aut-2"}, "controls"),
    ({"halted": True}, "controls"),
    ({"restricted": True}, "controls"),
    ({"fingerprint_now": "pfp-2"}, "positions"),
    ({"pending_cancel": True}, "cancel"),
])
def test_each_check_fails_alone_with_its_reason(change, name):
    decision = decide(replace(GOOD, **change))
    assert failed(decision) == [name] and not decision.passed
    assert all(c.reason for c in decision.checks)


@pytest.mark.unit
@pytest.mark.parametrize("field", [f for f in GOOD.__dataclass_fields__ if f != "promotion"])
def test_a_missing_read_fails_its_check_as_unavailable(field):
    decision = decide(replace(GOOD, **{field: Missing("not read")}))
    (check,) = [c for c in decision.checks if not c.passed]
    assert check.reason.startswith("unavailable: not read")


@pytest.mark.unit
@pytest.mark.parametrize("reading, reason", [
    (FlagReading(False, None, "missing"), "trading disabled: missing"),
    (FlagReading(False, None, "bad checksum"), "trading disabled: bad checksum"),
    (FlagReading(False, FlagState(False, 4, AT, "owner", True, "stop"), None), "trading disabled (halted, sequence 4)"),
])
def test_every_kill_switch_problem_fails_the_gate(reading, reason):
    decision = decide(kill=reading)
    assert failed(decision) == ["kill_switch"] and decision.checks[0].reason == reason


@pytest.mark.unit
def test_boundaries_are_exclusive_one_microsecond_before_passes():
    tick = timedelta(microseconds=1)
    session = GOOD.session
    for field, value in (("approval_expires_at", AT), ("view_valid_until", AT)):
        assert not decide(replace(GOOD, **{field: value})).passed
        assert decide(replace(GOOD, **{field: value + tick})).passed
    at_open = replace(GOOD, session=replace(session, target_open=AT))
    assert failed(decide(at_open)) == ["session"]
    assert decide(replace(GOOD, session=replace(session, target_open=AT + tick))).passed
    assert failed(decide(replace(GOOD, session=replace(session, decision_close=AT)))) == ["session"]


@pytest.mark.unit
def test_a_halt_blocks_a_buy_but_not_a_sell_and_paper_needs_an_accepted_promotion():
    sell = replace(ORDER, side=Side.SELL)
    assert decide(replace(GOOD, halted=True), order=sell).passed
    assert decide(replace(GOOD, halted=Missing("not read")), order=sell).passed  # a halt never matters to a sell
    paper = replace(ORDER, account_kind=AccountKind.PAPER)
    assert failed(decide(replace(GOOD, promotion="PROMOTION NOT ASSESSED"), order=paper)) == ["controls"]
    assert failed(decide(GOOD, order=paper)) == ["controls"]  # not read at all
    assert decide(replace(GOOD, promotion=ACCEPTED_PROMOTION), order=paper).passed


@pytest.mark.unit
def test_the_same_inputs_give_the_same_decision_byte_for_byte():
    assert decide() == decide()
    assert decide().inputs == decide().inputs
