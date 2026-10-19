"""The shared broker contract run against the test double too, so the double used across the tests behaves like a
broker wherever the contract speaks (docs/tasks/M4-06.md rule 10; Codex M4 review B12)."""

import pytest

from investment_engine.execution import broker_contract
from tests.engine.broker_doubles import ScriptedBroker
from tests.engine.test_simulated_broker import BEFORE, CAL, CLOSE, order


@pytest.mark.unit
@pytest.mark.parametrize("case", broker_contract.CASES, ids=lambda c: c.__name__)
def test_the_double_meets_the_contract(case):
    case(lambda: ScriptedBroker(calendar=CAL), order, BEFORE)


@pytest.mark.unit
@pytest.mark.parametrize("case", broker_contract.CASES_AFTER_A_FILL, ids=lambda c: c.__name__)
def test_the_double_meets_the_contract_after_a_fill(case):
    def fill(broker, o):
        broker.send("FILL", o.client_order_id, CLOSE, quantity=str(o.quantity))
        return CLOSE

    case(lambda: ScriptedBroker(calendar=CAL), order, BEFORE, fill=fill)
