"""Level 1 approval and decline of one exact intent version (architecture G1 step 9; docs/tasks/M3-13.md).

A named Admin or Trader (D17) approves or declines exactly the latest version
of an intent waiting for approval, before its deadline (D11: the target
session's open). Two times, never merged (Codex re-review R2): who may act is
checked at the real command time `command_at`; everything about the intent
(deadline, autonomy setting, limits and rules, halt) at the business time
`at`, which is the replay time for a RESEARCH account and the live time for a
PAPER one (where the two must be equal). Approval records `approved_at = at`
and `approval_recorded_at = command_at`, and expires at the target session's
close, never later than the view's validity.

The account-control lock is taken first (S4), so a change to autonomy, limits
or a halt commits either before the approval, which then sees it and refuses,
or after it. The autonomy setting must be the very setting the intent was
proposed under (its setting id, so 1 -> 2 -> 1 is caught), and the limits and
rules versions must be the intent's. The command acts on the intent as it read
it before taking the lock: if expiry or another approval changed it meanwhile,
the compare-and-set (M3-09) reports "intent changed meanwhile; nothing
approved". Every refusal is audited in its own transaction. No order is
created in M3.
"""

from datetime import datetime

from investment_engine.audit.events import Actor, ActorKind, AuditEvent
from investment_engine.market.availability import check_utc
from investment_engine.oms.intent_store import StaleWrite, StoredIntent
from investment_engine.oms.intents import IntentState, Side
from investment_engine.policy.accounts import AccountKind, NotAuthorized, Role
from investment_engine.risk.limits import NoLimits

APPROVERS = (Role.ADMIN, Role.TRADER)


class ApprovalRefused(ValueError):
    """The approval or decline was refused; nothing changed (the refusal itself is audited)."""


def _operator(stores, operator_id: str, command_at: datetime):
    try:
        operator = stores.accounts.operator(operator_id, command_at)
    except KeyError:
        raise NotAuthorized(f"{operator_id} is not a registered operator") from None
    if not operator.active:
        raise NotAuthorized(f"{operator_id} is not an active operator now")
    if operator.role not in APPROVERS:
        raise NotAuthorized(f"{operator_id} ({operator.role}) may not approve or decline; an Admin or Trader may")
    return operator


def _check(stores, current: StoredIntent, seen: StoredIntent, version: int, at: datetime, account) -> None:
    intent = current.intent
    if current.aggregate_version != seen.aggregate_version:
        raise StaleWrite(f"{intent.intent_id} changed since it was read")
    if version != intent.version:
        raise ApprovalRefused(f"version {version} is not the latest version ({intent.version}) of {intent.intent_id}")
    if current.state is not IntentState.AWAITING_APPROVAL:
        raise ApprovalRefused(f"{intent.intent_id} v{version} is {current.state}, not AWAITING_APPROVAL")
    if account.kind is AccountKind.RESEARCH and at < intent.created_at:
        raise ApprovalRefused("a replay time can't be earlier than the proposal")
    if at >= current.approval_deadline:
        raise ApprovalRefused(f"the approval deadline {current.approval_deadline.isoformat()} has passed")
    lineage = stores.intent_lineage.get(current.lineage_id)
    try:
        setting = stores.accounts.autonomy_at(intent.account_id, at)
    except LookupError:
        setting = None
    if setting is None or setting.setting_id != lineage.autonomy.setting_id or setting.level != 1:
        raise ApprovalRefused("autonomy changed since proposal")
    try:
        risk, rules = stores.limits.risk_at(intent.account_id, at), stores.limits.policy_at(intent.account_id, at)
    except NoLimits:
        raise ApprovalRefused("controls changed since proposal; propose again") from None
    halt = stores.limits.halt_at(intent.account_id, at)
    if (risk.version, rules.version) != (intent.risk_version, intent.policy_version) or (
            intent.side is Side.BUY and halt is not None and halt.halted):
        raise ApprovalRefused("controls changed since proposal; propose again")


def _refusal(stores, action: str, intent_id: str, operator_id: str, command_at: datetime, at: datetime,
             reason: str, os_user: str | None) -> None:
    try:
        role = stores.accounts.operator(operator_id, command_at).role.value
        actor = Actor(ActorKind.OPERATOR, operator_id, role, os_user)
    except KeyError:
        actor = Actor(ActorKind.PROCESS, "admin-cli", None, os_user)
    try:
        account_id = stores.intents.get(intent_id).intent.account_id
        business = at if stores.accounts.account(account_id).kind is AccountKind.RESEARCH else None
    except KeyError:
        business = None
    with stores.db.transaction():
        stores.audit.append(AuditEvent(actor, f"{action}_refused", "intent", intent_id, None, None, command_at,
                                       business, f"{operator_id}: {reason}"[:1000],
                                       f"{action}:{intent_id}:{command_at.isoformat()}",
                                       f"{action}_refused:{intent_id}:{operator_id}:{command_at.isoformat()}"))


def record_refusal(stores, action: str, intent_id: str, operator_id: str, command_at: datetime, at: datetime,
                   reason: str, os_user: str | None = None) -> None:
    """Audit a refusal decided by the caller (the Admin CLI refuses --at for a PAPER account), in its own
    transaction."""
    _refusal(stores, action, intent_id, operator_id, check_utc(command_at, "command_at"), check_utc(at, "at"),
             reason, os_user)


def _act(stores, action: str, intent_id: str, version: int, operator_id: str, at: datetime, command_at: datetime,
         reason: str, os_user: str | None, decide, *, needs_reason: bool = False) -> StoredIntent:
    at, command_at = check_utc(at, "at"), check_utc(command_at, "command_at")
    try:
        if needs_reason and (not isinstance(reason, str) or not reason.strip()):
            raise ApprovalRefused("a decline needs a reason")
        try:
            seen = stores.intents.get(intent_id)
        except KeyError:
            raise ApprovalRefused(f"unknown intent {intent_id}") from None
        account = stores.accounts.account(seen.intent.account_id)
        if account.kind is AccountKind.PAPER and at != command_at:
            raise ApprovalRefused("a PAPER account acts at live time only; a replay time is refused")
        with stores.db.transaction():
            stores.db.lock(f"account-control|{account.account_id}")
            operator = _operator(stores, operator_id, command_at)
            _check(stores, stores.intents.get(intent_id), seen, version, at, account)
            return decide(seen, operator)
    except StaleWrite:
        _refusal(stores, action, intent_id, operator_id, command_at, at, "intent changed meanwhile", os_user)
        raise ApprovalRefused("intent changed meanwhile; nothing approved") from None
    except (ApprovalRefused, NotAuthorized) as exc:
        _refusal(stores, action, intent_id, operator_id, command_at, at, str(exc), os_user)
        raise


def approve(intent_id: str, version: int, *, operator_id: str, at: datetime, command_at: datetime, stores, calendar,
            reason: str = "", os_user: str | None = None) -> StoredIntent:
    def decide(seen: StoredIntent, operator):
        intent = seen.intent
        expires = min(calendar.session(intent.target_session).close, intent.view_valid_until)
        actor = Actor(ActorKind.OPERATOR, operator.operator_id, operator.role.value, os_user)
        return stores.intents.transition(
            intent.intent_id, intent.version, IntentState.APPROVED,
            expected_aggregate_version=seen.aggregate_version, at=at, by=actor,
            reason=reason or f"approved by {operator.operator_id}", approved_by=operator.operator_id,
            approved_at=at, approval_expires_at=expires, approval_recorded_at=command_at)
    return _act(stores, "intent.approve", intent_id, version, operator_id, at, command_at, reason, os_user, decide)


def decline(intent_id: str, version: int, *, operator_id: str, at: datetime, command_at: datetime, stores,
            reason: str, os_user: str | None = None) -> StoredIntent:
    def decide(seen: StoredIntent, operator):
        intent = seen.intent
        actor = Actor(ActorKind.OPERATOR, operator.operator_id, operator.role.value, os_user)
        return stores.intents.transition(intent.intent_id, intent.version, IntentState.DECLINED,
                                         expected_aggregate_version=seen.aggregate_version, at=at, by=actor,
                                         reason=reason)
    return _act(stores, "intent.decline", intent_id, version, operator_id, at, command_at, reason, os_user, decide,
                needs_reason=True)
