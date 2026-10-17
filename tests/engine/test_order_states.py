"""The Order state machine and its owners (architecture G3; docs/tasks/M4-00.md rules 1 and 2)."""

import pytest

from investment_engine.oms import order_states
from investment_engine.oms.order_states import OrderState as S, ProcessRole

# G3, written out independently of EDGES (architecture Part G3; M4-00 rule 4: a complete fill goes SUBMITTED -> FILLED)
G3 = {
    (S.NEW, S.GATE_REJECTED), (S.NEW, S.SUBMITTING),
    (S.SUBMITTING, S.SUBMITTED), (S.SUBMITTING, S.REJECTED), (S.SUBMITTING, S.EXPIRED), (S.SUBMITTING, S.UNKNOWN),
    (S.SUBMITTED, S.PARTIALLY_FILLED), (S.SUBMITTED, S.FILLED), (S.SUBMITTED, S.CANCEL_PENDING),
    (S.SUBMITTED, S.REJECTED), (S.SUBMITTED, S.EXPIRED),
    (S.PARTIALLY_FILLED, S.FILLED), (S.PARTIALLY_FILLED, S.CANCEL_PENDING),
    (S.CANCEL_PENDING, S.CANCELLED), (S.CANCEL_PENDING, S.PARTIALLY_FILLED), (S.CANCEL_PENDING, S.FILLED),
    (S.UNKNOWN, S.SUBMITTED), (S.UNKNOWN, S.PARTIALLY_FILLED), (S.UNKNOWN, S.FILLED), (S.UNKNOWN, S.CANCELLED),
    (S.UNKNOWN, S.REJECTED), (S.UNKNOWN, S.EXPIRED),
}


@pytest.mark.unit
def test_edges_are_exactly_g3_with_no_extensions():
    assert {(a, b) for a, targets in order_states.EDGES.items() for b in targets} == G3
    assert (S.PARTIALLY_FILLED, S.EXPIRED) not in G3  # D19: OPEN-16 (a) left out
    assert {S.GATE_REJECTED, S.FILLED, S.CANCELLED, S.REJECTED, S.EXPIRED} == order_states.FINAL
    assert all(b is not S.SUBMITTING for a, b in G3 if a is S.UNKNOWN)  # never resent (Law 14)


@pytest.mark.unit
@pytest.mark.parametrize("a", [None, *S])
@pytest.mark.parametrize("b", list(S))
def test_every_pair_is_legal_for_its_owner_only(a, b):
    owner = ProcessRole.CORE if (a, b) == (None, S.NEW) else ProcessRole.EXECUTION
    if (a, b) in G3 or (a, b) == (None, S.NEW):
        order_states.check(a, b, owner)
        other = ProcessRole.EXECUTION if owner is ProcessRole.CORE else ProcessRole.CORE
        with pytest.raises(order_states.WrongProcess):
            order_states.check(a, b, other)
    else:
        for role in ProcessRole:
            with pytest.raises(order_states.IllegalTransition):
                order_states.check(a, b, role)
