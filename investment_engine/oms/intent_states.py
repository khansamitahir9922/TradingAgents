"""The OrderIntent state machine (architecture G2; ADR-004; docs/tasks/M3-09.md).

`ALLOWED` is G2 exactly as frozen: nothing else is accepted, and the final
states have no way out. It is the one shared definition every caller uses.
APPROVED -> CONVERTED, a legal G2 edge, is refused unless it is written together
with its Order: only `oms.conversion` passes `converting=True` (M4-02 rule 6).
That guard has its own error, distinct from an illegal transition.
"""

from investment_engine.oms.intents import IntentState as S

ALLOWED: dict[S, frozenset[S]] = {
    S.PROPOSED: frozenset({S.POLICY_REJECTED, S.RISK_REJECTED, S.SUPERSEDED, S.AWAITING_APPROVAL, S.APPROVED}),
    S.AWAITING_APPROVAL: frozenset({S.APPROVED, S.DECLINED, S.EXPIRED}),
    S.APPROVED: frozenset({S.CONVERTED, S.EXPIRED, S.SUPERSEDED}),
}
FINAL = frozenset(set(S) - set(ALLOWED))  # POLICY_REJECTED, RISK_REJECTED, SUPERSEDED, DECLINED, EXPIRED, CONVERTED


class IllegalTransition(ValueError):
    """Not a G2 edge; nothing was written."""


class OrdersNotBuilt(ValueError):
    """APPROVED -> CONVERTED is written only with its Order (M4-02); nothing was written."""


def check(from_state: S, to_state: S, *, converting: bool = False) -> None:
    from_state, to_state = S(from_state), S(to_state)
    if to_state not in ALLOWED.get(from_state, frozenset()):
        raise IllegalTransition(f"{from_state} -> {to_state} is not an intent transition (G2)")
    if to_state is S.CONVERTED and not converting:
        raise OrdersNotBuilt("APPROVED -> CONVERTED is written only with its Order, by oms.conversion (M4-02)")
