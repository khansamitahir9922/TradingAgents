"""The Pre-Execution Gate (Law 13; ADR-004 section 4; architecture G1 step 11; docs/tasks/M4-05.md).

`check_gate` is pure: no I/O, no clock, no randomness. Every check runs and
is recorded with its reason, passed or failed, in this order:

    1 kill_switch   2 intent_version   3 approval   4 view   5 controls
    6 positions     7 session          8 cancel

Inputs are typed: a read that couldn't be made is `Missing`, never confused
with an observed False, and fails its check as "unavailable" (Law 9). The
gate never reruns the strategy, never resizes or reprices, and cancels never
pass through it (Law 15).

`gate_order` is the worker's gate transaction (rule 4): take the
account-control lock, lock the order row, and only then read every input
fresh, decide, and write the decision with its edge (NEW -> SUBMITTING or
GATE_REJECTED) by compare-and-set, all before committing. Every writer that
can change an input takes the same lock first, so a change commits wholly
before the reads, which then see it, or wholly after the decision.
"""

from dataclasses import asdict, dataclass
from datetime import datetime

from investment_engine.killswitch.flag import FlagReading
from investment_engine.lineage.records import canonical_json, register
from investment_engine.oms.intent_store import StoredIntent
from investment_engine.oms.intents import IntentState, Side
from investment_engine.oms.order_states import OrderState
from investment_engine.oms.orders import GateDecision, Order, OrderStatus
from investment_engine.policy.accounts import AccountKind
from investment_engine.policy.decisions import CheckResult

ACCEPTED_PROMOTION = "ACCEPTED"


@dataclass(frozen=True)
class Missing:
    """A read that couldn't be made; it fails its check (Law 9)."""

    reason: str


@dataclass(frozen=True)
class SessionWindow:
    decision_close: datetime  # the decision bar's session close
    target_open: datetime
    target_close: datetime


@dataclass(frozen=True)
class GateInputs:
    latest_version: int | Missing
    intent_state: IntentState | Missing
    intent_content_id: str | Missing
    approval_expires_at: datetime | Missing
    view_valid_until: datetime | Missing
    reference_current: bool | Missing  # True: the decision bar is still its latest known revision
    action_since_reference: bool | Missing  # True: a split or dividend ex-date in (decision session, target session]
    risk_version: str | Missing
    policy_version: str | Missing
    autonomy_setting: str | Missing  # the setting effective now
    pinned_autonomy_setting: str | Missing  # the setting the intent was proposed under (its lineage)
    halted: bool | Missing
    restricted: bool | Missing
    promotion: str | Missing | None  # PAPER only; None for RESEARCH (D23)
    fingerprint_now: str | Missing  # excluding this order
    pending_cancel: bool | Missing
    session: SessionWindow | Missing


for _cls in (Missing, SessionWindow, GateInputs):
    register(_cls)


def _unavailable(*values) -> str | None:
    missing = [v.reason for v in values if isinstance(v, Missing)]
    return f"unavailable: {'; '.join(missing)}" if missing else None


def _check(name: str, ok: bool, reason: str) -> CheckResult:
    return CheckResult(name, bool(ok), reason)


def check_gate(order: Order, status: OrderStatus, *, at: datetime, inputs: GateInputs, intent: StoredIntent,
               kill_switch: FlagReading) -> GateDecision:
    i, checks = inputs, []

    # 1 kill switch (ADR-006)
    if kill_switch.enabled:
        checks.append(_check("kill_switch", True, f"trading enabled (sequence {kill_switch.state.sequence})"))
    elif kill_switch.state is not None:
        checks.append(_check("kill_switch", False, f"trading disabled (halted, sequence {kill_switch.state.sequence})"))
    else:
        checks.append(_check("kill_switch", False, f"trading disabled: {kill_switch.problem}"))

    # 2 the intent version (Law 12)
    missing = _unavailable(i.latest_version, i.intent_state, i.intent_content_id)
    if missing:
        checks.append(_check("intent_version", False, missing))
    else:
        problems = []
        if i.latest_version != order.intent_version:
            problems.append(f"latest version is {i.latest_version}, the order's is {order.intent_version}")
        if i.intent_state is not IntentState.CONVERTED:
            problems.append(f"intent is {i.intent_state}, not CONVERTED")
        if i.intent_content_id != order.intent_content_id:
            problems.append("the intent version's content changed since conversion")
        checks.append(_check("intent_version", not problems, "; ".join(problems) or "unchanged and CONVERTED"))

    # 3 approval expiry
    missing = _unavailable(i.approval_expires_at)
    checks.append(_check("approval", False, missing) if missing else
                  _check("approval", at < i.approval_expires_at,
                         f"approval valid until {i.approval_expires_at.isoformat()}" if at < i.approval_expires_at
                         else f"approval expired at {i.approval_expires_at.isoformat()}"))

    # 4 the view and its raw reference
    missing = _unavailable(i.view_valid_until, i.reference_current, i.action_since_reference)
    if missing:
        checks.append(_check("view", False, missing))
    else:
        problems = []
        if not at < i.view_valid_until:
            problems.append(f"view expired at {i.view_valid_until.isoformat()}")
        if i.reference_current is not True:
            problems.append("a newer revision of the decision bar is known")
        if i.action_since_reference is not False:
            problems.append("a split or dividend falls between the decision bar and the target session")
        checks.append(_check("view", not problems, "; ".join(problems) or "view and reference current"))

    # 5 policy, risk and autonomy controls
    buy = order.side is Side.BUY
    values = [i.risk_version, i.policy_version, i.autonomy_setting, i.pinned_autonomy_setting, i.restricted]
    if buy:
        values.append(i.halted)
    if order.account_kind is AccountKind.PAPER:
        values.append(i.promotion if i.promotion is not None else Missing("promotion status not read"))
    missing = _unavailable(*values)
    if missing:
        checks.append(_check("controls", False, missing))
    else:
        problems = []
        if i.risk_version != intent.intent.risk_version:
            problems.append(f"risk limits are {i.risk_version}, the intent's are {intent.intent.risk_version}")
        if i.policy_version != intent.intent.policy_version:
            problems.append(f"policy rules are {i.policy_version}, the intent's are {intent.intent.policy_version}")
        if i.autonomy_setting != i.pinned_autonomy_setting:
            problems.append("the autonomy setting changed since the proposal")
        if buy and i.halted is not False:
            problems.append("the account is halted for new buys")
        if i.restricted is not False:
            problems.append(f"{order.instrument_id} is restricted")
        if order.account_kind is AccountKind.PAPER and i.promotion != ACCEPTED_PROMOTION:
            problems.append(f"promotion not accepted: {i.promotion}")
        checks.append(_check("controls", not problems, "; ".join(problems) or "controls unchanged since approval"))

    # 6 no position change since the proposal (Law 13)
    missing = _unavailable(i.fingerprint_now)
    checks.append(_check("positions", False, missing) if missing else
                  _check("positions", i.fingerprint_now == order.position_fingerprint,
                         "positions and reservations unchanged since the proposal"
                         if i.fingerprint_now == order.position_fingerprint
                         else "positions or reservations changed since the proposal"))

    # 7 the session allows the time in force (D7, D25: orders rest from the open)
    missing = _unavailable(i.session)
    if missing:
        checks.append(_check("session", False, missing))
    else:
        s = i.session
        if order.time_in_force != "DAY":
            ok, reason = False, f"time in force {order.time_in_force} isn't DAY"
        elif not at > s.decision_close:
            ok, reason = False, f"before the decision bar's close {s.decision_close.isoformat()}"
        elif not at < s.target_open:
            ok, reason = False, (f"at or after the target session's open {s.target_open.isoformat()}: the daily "
                                 "fill model needs an order resting from the open (D25)")
        else:
            ok, reason = True, f"before the target session's open {s.target_open.isoformat()}"
        checks.append(_check("session", ok, reason))

    # 8 no pending cancel (G3 has no NEW -> CANCELLED: the gate rejects instead)
    missing = _unavailable(i.pending_cancel)
    checks.append(_check("cancel", False, missing) if missing else
                  _check("cancel", i.pending_cancel is False,
                         "no cancel pending" if i.pending_cancel is False else "a cancel was requested before submission"))

    record = {"at": at.isoformat(), "order": order.order_id, "status_version": status.aggregate_version,
              "inputs": asdict(i), "kill_switch": {"enabled": kill_switch.enabled, "problem": kill_switch.problem,
                                                   "sequence": None if kill_switch.state is None
                                                   else kill_switch.state.sequence}}
    return GateDecision(order.order_id, 1, all(c.passed for c in checks), tuple(checks), at,
                        canonical_json(_plain(record)))


def _plain(value):
    """asdict() leaves enums, datetimes and nested Missing values; canonical_json encodes them deterministically."""
    if isinstance(value, dict):
        if set(value) == {"reason"}:
            return {"missing": value["reason"]}
        return {k: _plain(v) for k, v in value.items()}
    return value


def gate_order(order_id: str, *, at: datetime, orders, reads, kill_switch) -> GateDecision | None:
    """The gate transaction (rule 4). Returns the decision, or None if the order is no longer NEW."""
    db = orders._db
    with db.transaction():
        order, _ = orders.get(order_id)
        db.lock(f"account-control|{order.account_id}")
        db.execute("SELECT 1 FROM orders WHERE order_id = :id FOR UPDATE", {"id": order_id})
        order, status = orders.get(order_id)
        if status.state is not OrderState.NEW:
            return None
        inputs, intent = reads.read(order, at=at)
        decision = check_gate(order, status, at=at, inputs=inputs, intent=intent, kill_switch=kill_switch.read())
        to = OrderState.SUBMITTING if decision.passed else OrderState.GATE_REJECTED
        failed = [f"{c.name}: {c.reason}" for c in decision.checks if not c.passed]
        orders.transition(order_id, to, expected_aggregate_version=status.aggregate_version, at=at,
                          reason="gate passed" if decision.passed else "gate failed: " + "; ".join(failed),
                          gate=decision)
    return decision


__all__ = ["ACCEPTED_PROMOTION", "GateInputs", "Missing", "SessionWindow", "check_gate", "gate_order"]
