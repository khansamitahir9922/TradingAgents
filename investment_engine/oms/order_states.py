"""The Order state machine and who owns each transition (architecture G3; ADR-004 sections 1 and 3; Law 10;
docs/tasks/M4-00.md).

`EDGES` is G3 exactly as frozen. The chain "NEW -> SUBMITTING -> SUBMITTED ->
PARTIALLY_FILLED -> FILLED" is read as the order fills in steps, so a single
complete fill moves SUBMITTED -> FILLED directly, as CANCEL_PENDING may (the
accepted M4-00 rule 4). UNKNOWN resolves only to a state the broker reports,
never back to SUBMITTING, and nothing leaves UNKNOWN without that report (D20).
There is no PARTIALLY_FILLED -> EXPIRED (D19). The final states have no way out.

`OWNER` gives each edge its only writer: the Core Engine creates NEW; the
Execution Worker writes every other edge (G3 table). Both processes use this
one module; the order store refuses any other edge or writer, and the schema
(0011) checks both again.
"""

from enum import StrEnum

from investment_engine.lineage.records import register


class OrderState(StrEnum):
    NEW = "NEW"
    GATE_REJECTED = "GATE_REJECTED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class ProcessRole(StrEnum):
    CORE = "core-engine"
    EXECUTION = "execution-worker"
    RESEARCH = "research-worker"  # M6: writes research tables only; owns no order edge


register(OrderState)
register(ProcessRole)

S = OrderState
EDGES: dict[S, frozenset[S]] = {
    S.NEW: frozenset({S.GATE_REJECTED, S.SUBMITTING}),
    S.SUBMITTING: frozenset({S.SUBMITTED, S.REJECTED, S.EXPIRED, S.UNKNOWN}),
    S.SUBMITTED: frozenset({S.PARTIALLY_FILLED, S.FILLED, S.CANCEL_PENDING, S.REJECTED, S.EXPIRED}),
    S.PARTIALLY_FILLED: frozenset({S.FILLED, S.CANCEL_PENDING}),
    S.CANCEL_PENDING: frozenset({S.CANCELLED, S.PARTIALLY_FILLED, S.FILLED}),
    S.UNKNOWN: frozenset({S.SUBMITTED, S.PARTIALLY_FILLED, S.FILLED, S.CANCELLED, S.REJECTED, S.EXPIRED}),
}
FINAL = frozenset(set(S) - set(EDGES))  # GATE_REJECTED, FILLED, CANCELLED, REJECTED, EXPIRED
OPEN = frozenset(set(S) - FINAL)  # NEW, SUBMITTING, SUBMITTED, PARTIALLY_FILLED, CANCEL_PENDING, UNKNOWN
FILL_STATES = frozenset({S.PARTIALLY_FILLED, S.FILLED})  # reached only through a recorded fill

OWNER: dict[tuple[S | None, S], ProcessRole] = {(None, S.NEW): ProcessRole.CORE}
OWNER.update({(a, b): ProcessRole.EXECUTION for a, targets in EDGES.items() for b in targets})


class IllegalTransition(ValueError):
    """Not a G3 edge; nothing was written."""


class WrongProcess(PermissionError):
    """The edge belongs to another process (G3 ownership); nothing was written."""


def check(from_state: S | None, to_state: S, role: ProcessRole) -> None:
    to_state = S(to_state)
    from_state = None if from_state is None else S(from_state)
    owner = OWNER.get((from_state, to_state))
    if owner is None:
        raise IllegalTransition(f"{from_state} -> {to_state} is not an order transition (G3)")
    if ProcessRole(role) is not owner:
        raise WrongProcess(f"{from_state} -> {to_state} is written only by the {owner.value}, not the {role}")


__all__ = ["EDGES", "FILL_STATES", "FINAL", "OPEN", "OWNER", "IllegalTransition", "OrderState", "ProcessRole",
           "WrongProcess", "check"]
