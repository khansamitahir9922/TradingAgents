"""The gate's read provider: every input read fresh, inside the gate transaction (docs/tasks/M4-05.md rule 4).

Each read that can't be made becomes `Missing` with its reason, never a
default (Law 9). The provider never decides anything; `check_gate` does.
Promotion for PAPER accounts reads a fixed "not assessed" status: the execution
package imports no evaluation module (M4-03 layering), and no PAPER account can
be ACCEPTED in M4 anyway (D22). The proposal-time policy check reports the
recorded assessment (M4-10). A later milestone that lets PAPER trade must inject
the status through this provider's `promotion` callable.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from investment_engine.execution.gate import GateInputs, Missing, SessionWindow
from investment_engine.market.corporate_actions import ActionType
from investment_engine.oms.orders import CancelProgress, Order
from investment_engine.policy.accounts import AccountKind

_ACTIONS = (ActionType.SPLIT, ActionType.DIVIDEND)


def _read(fn, what: str):
    try:
        value = fn()
    except Exception as exc:  # any failure to read is Missing, with its reason (Law 9)
        return Missing(f"{what} ({type(exc).__name__}: {exc})"[:300])
    return Missing(f"{what}: none") if value is None else value


class StoreGateReads:
    def __init__(self, stores, orders, *, knowledge, calendar, fingerprints, promotion=None) -> None:
        self.stores, self.orders = stores, orders
        self.knowledge, self.calendar, self.fingerprints = knowledge, calendar, fingerprints
        self.promotion = promotion or (lambda order, intent, at: "PROMOTION NOT ASSESSED (OPEN-09)")

    def read(self, order: Order, *, at: datetime):
        s = self.stores
        intent = s.intents.get(order.intent_id, order.intent_version)
        version = intent.intent
        ref = version.reference_bar
        zone = ZoneInfo(self.calendar.timezone)
        decision_day = ref.start_time.astimezone(zone).date()

        def latest_version():
            return s.intents.get(order.intent_id).intent.version

        def content_id():
            from investment_engine.oms.conversion import intent_content_id

            return intent_content_id(s.intents.get(order.intent_id, order.intent_version).intent)

        def reference_current():
            bar = self.knowledge.latest_closed(ref.source, ref.instrument_id, decision_day, at=at, calendar=self.calendar)
            if bar is None:
                raise LookupError("the decision bar isn't known at this time")
            return bar.revision == ref.revision

        def action_since_reference():
            actions = self.knowledge.actions_between(ref.source, ref.instrument_id, decision_day + timedelta(days=1),
                                                     version.target_session, at=at)
            return any(a.action_type in _ACTIONS for a in actions)

        def autonomy_now():
            return s.accounts.autonomy_at(order.account_id, at).setting_id

        def autonomy_pinned():
            if intent.lineage_id is None:
                raise LookupError("the intent has no lineage record")
            return s.intent_lineage.get(intent.lineage_id).autonomy.setting_id

        def halted():
            halt = s.limits.halt_at(order.account_id, at)
            return halt is not None and halt.halted

        def restricted():
            return order.instrument_id in s.limits.policy_at(order.account_id, at).restricted

        def fingerprint():
            value = self.fingerprints.at(order.account_id, at, excluding_order=order.order_id)
            if not isinstance(value, str):
                raise LookupError(getattr(value, "reason", str(value)))
            return value

        def pending_cancel():
            return any(r.order_id == order.order_id and p is not CancelProgress.CLOSED
                       for r, p, _ in self.orders.open_cancels())

        def session():
            target = self.calendar.session(version.target_session)
            return SessionWindow(self.calendar.session(decision_day).close, target.open, target.close)

        inputs = GateInputs(
            latest_version=_read(latest_version, "latest intent version"),
            intent_state=_read(lambda: s.intents.get(order.intent_id, order.intent_version).state, "intent state"),
            intent_content_id=_read(content_id, "intent content"),
            approval_expires_at=_read(lambda: intent.approval_expires_at, "approval expiry"),
            view_valid_until=_read(lambda: version.view_valid_until, "view validity"),
            reference_current=_read(reference_current, "reference bar"),
            action_since_reference=_read(action_since_reference, "corporate actions"),
            risk_version=_read(lambda: s.limits.risk_at(order.account_id, at).version, "risk limits"),
            policy_version=_read(lambda: s.limits.policy_at(order.account_id, at).version, "policy rules"),
            autonomy_setting=_read(autonomy_now, "autonomy setting"),
            pinned_autonomy_setting=_read(autonomy_pinned, "the intent's autonomy setting"),
            halted=_read(halted, "halt state"),
            restricted=_read(restricted, "restricted list"),
            promotion=(_read(lambda: self.promotion(order, intent, at), "promotion")
                       if order.account_kind is AccountKind.PAPER else None),
            fingerprint_now=_read(fingerprint, "positions"),
            pending_cancel=_read(pending_cancel, "cancel requests"),
            session=_read(session, "sessions"),
        )
        return inputs, intent


__all__ = ["StoreGateReads"]
