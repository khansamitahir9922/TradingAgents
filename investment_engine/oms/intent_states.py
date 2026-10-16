"""The OrderIntent state machine (architecture G2; ADR-004; docs/tasks/M3-09.md).

`ALLOWED` is G2 exactly as frozen: nothing else is accepted, and the final
states have no way out. It is the one shared definition every caller uses.
M3 additionally refuses APPROVED -> CONVERTED, a legal G2 edge, because orders
arrive only in M4; that guard has its own error, distinct from an illegal
transition, and M4's spec removes it through a reviewed change.
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
    """APPROVED -> CONVERTED is a G2 edge, but orders arrive in M4; nothing was written."""


def check(from_state: S, to_state: S) -> None:
    from_state, to_state = S(from_state), S(to_state)
    if to_state not in ALLOWED.get(from_state, frozenset()):
        raise IllegalTransition(f"{from_state} -> {to_state} is not an intent transition (G2)")
    if to_state is S.CONVERTED:
        raise OrdersNotBuilt("APPROVED -> CONVERTED creates an Order; orders arrive in M4")
