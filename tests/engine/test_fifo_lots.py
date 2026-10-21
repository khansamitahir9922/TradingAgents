"""M5-03: exact cumulative half-even FIFO, including adversarial rounding."""
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal, Inexact, Rounded, localcontext
from fractions import Fraction

import pytest

from investment_engine.ledger.contracts import AccountingUnavailable, SourceConflict
from investment_engine.ledger.lots import FifoBook, allocate_cost

T = datetime(2024, 1, 2, tzinfo=UTC)
NVDA = "EQ_US_NVDA"


def book(quantity="6", cost=".0004"):
    value = FifoBook("R1", at=T)
    value.acquire(NVDA, Decimal(quantity), Decimal(cost), "buy", at=T)
    return value


def test_six_share_counterexample_and_final_exact_residual():
    value = book()
    costs = [value.consume(NVDA, Decimal(1), f"sell-{i}")[0].cost for i in range(6)]
    assert costs == list(map(Decimal, [".0001", "0", ".0001", ".0001", "0", ".0001"]))
    lot = value.lots()[0]
    assert lot.remaining_quantity == lot.remaining_cost == 0
    value = book("2", ".00015")
    assert value.consume(NVDA, Decimal(1), "s1")[0].cost == Decimal(".0001")
    assert value.consume(NVDA, Decimal(1), "s2")[0].cost == Decimal(".00005")


def test_grouping_invariance_and_conservation_for_400_cases():
    for quantity in range(1, 21):
        for units in range(1, 21):
            cost = Decimal(units).scaleb(-5)
            value = book(str(quantity), str(cost))
            allocated = Fraction()
            for disposed in range(1, quantity + 1):
                chunk = value.consume(NVDA, Decimal(1), f"s-{disposed}")[0].cost
                assert chunk >= 0
                allocated += Fraction(chunk)
                grouped = book(str(quantity), str(cost)).consume(NVDA, Decimal(disposed), "group")[0].cost
                assert allocated == Fraction(grouped)
                assert Fraction(value.lots()[0].remaining_cost) + allocated == Fraction(cost)
            assert allocated == Fraction(cost)


def test_fifo_across_lots_and_equal_time_stable_acquisition_ids():
    value = FifoBook("R1", at=T + timedelta(days=1))
    value.acquire(NVDA, Decimal(3), Decimal(600), "b", at=T)
    value.acquire(NVDA, Decimal(2), Decimal(200), "a", at=T)
    matches = value.consume(NVDA, Decimal(4), "sell")
    assert [(m.acquisition, m.quantity, m.cost) for m in matches] == [("a", Decimal(2), Decimal(200)), ("b", Decimal(2), Decimal(400))]
    assert value.lots()[1].remaining_quantity == 1
    assert value.lots()[1].remaining_cost == 200


def test_unknown_or_insufficient_basis_does_not_mutate_any_lot():
    value = book()
    before = value.lots()
    with pytest.raises(AccountingUnavailable):
        value.consume(NVDA, Decimal(7), "oversell")
    assert value.lots() == before
    with pytest.raises(AccountingUnavailable):
        value.consume("EQ_US_MSFT", Decimal(1), "missing")
    match = value.consume(NVDA, Decimal(1), "sale")
    after = value.lots()
    assert value.consume(NVDA, Decimal(1), "sale") == match
    assert value.lots() == after
    with pytest.raises(SourceConflict):
        value.consume(NVDA, Decimal(2), "sale")


@pytest.mark.parametrize("rounding", [ROUND_CEILING, ROUND_DOWN])
def test_hostile_decimal_context_cannot_change_costs_or_ids(rounding):
    expected = book().consume(NVDA, Decimal(2), "s")
    with localcontext() as ctx:
        ctx.prec = 1
        ctx.rounding = rounding
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        actual = book().consume(NVDA, Decimal(2), "s")
    assert actual == expected


@pytest.mark.parametrize("quantity,cost", [("0", "1"), ("1.5", "1"), ("1", "-1"), ("NaN", "1")])
def test_invalid_acquisitions_refused(quantity, cost):
    with pytest.raises((TypeError, ValueError)):
        book(quantity, cost)


def test_integer_ties_are_half_even_and_cost_never_exceeds_total():
    assert allocate_cost(Decimal(".0001"), Decimal(2), Decimal(1), Decimal(0)) == 0
    assert allocate_cost(Decimal(".0003"), Decimal(2), Decimal(1), Decimal(0)) == Decimal(".0002")
    assert allocate_cost(Decimal(".00001"), Decimal(2), Decimal(1), Decimal(0)) == 0
    assert allocate_cost(Decimal(".00001"), Decimal(2), Decimal(2), Decimal(0)) == Decimal(".00001")
