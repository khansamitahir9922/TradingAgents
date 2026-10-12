"""The Decimal boundary (ADR-007; docs/tasks/M1-02.md).

Money and quantities are Decimal with an explicit currency or unit. Floats
cross into Decimal only through from_float64, with a stated quantum and the
one rounding rule (half-even).
"""

import math
from decimal import Decimal

import pytest

from investment_engine.money import (
    PRICE_QUANTUM,
    ROUNDING,
    SHARE_QUANTUM,
    Money,
    Quantity,
    from_float64,
    quantize,
    to_float64,
)


def usd(text: str) -> Money:
    return Money(Decimal(text), "USD")


def shares(text: str) -> Quantity:
    return Quantity(Decimal(text), "shares")


# ---------------------------------------------------------------- Money


@pytest.mark.unit
def test_money_adds_exactly():
    assert usd("0.1") + usd("0.2") == usd("0.3")


@pytest.mark.unit
def test_money_subtracts_and_multiplies_by_a_decimal():
    assert usd("10.00") - usd("0.01") == usd("9.99")
    assert usd("2.50") * Decimal("4") == usd("10.00")
    assert Decimal("4") * usd("2.50") == usd("10.00")


@pytest.mark.unit
@pytest.mark.parametrize("amount", [0.1, 1, True])
def test_money_refuses_a_non_decimal_amount(amount):
    with pytest.raises(TypeError):
        Money(amount, "USD")


@pytest.mark.unit
@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_money_refuses_a_non_finite_amount(amount):
    with pytest.raises(ValueError):
        Money(Decimal(amount), "USD")


@pytest.mark.unit
@pytest.mark.parametrize("currency", ["usd", "US", "USDT", "", "U$D", 840])
def test_money_refuses_a_bad_currency_code(currency):
    with pytest.raises((ValueError, TypeError)):
        Money(Decimal("1"), currency)


@pytest.mark.unit
@pytest.mark.parametrize("op", ["add", "sub", "lt", "le", "gt", "ge"])
def test_money_refuses_to_mix_currencies(op):
    a, b = usd("1"), Money(Decimal("1"), "EUR")
    with pytest.raises(ValueError):
        {"add": a.__add__, "sub": a.__sub__, "lt": a.__lt__, "le": a.__le__,
         "gt": a.__gt__, "ge": a.__ge__}[op](b)


@pytest.mark.unit
def test_money_in_different_currencies_is_never_equal():
    assert usd("1") != Money(Decimal("1"), "EUR")


@pytest.mark.unit
def test_money_compares_within_a_currency():
    assert usd("1.00") < usd("1.01") <= usd("1.01")
    assert usd("2") > usd("1") >= usd("1")
    assert usd("1.0") == usd("1.00")


@pytest.mark.unit
@pytest.mark.parametrize("other", [1, 0.5, "2"])
def test_money_multiplies_only_by_a_decimal(other):
    with pytest.raises(TypeError):
        usd("1") * other


@pytest.mark.unit
def test_money_does_not_add_to_a_bare_number():
    with pytest.raises(TypeError):
        usd("1") + Decimal("1")


@pytest.mark.unit
def test_money_is_immutable():
    with pytest.raises(AttributeError):
        usd("1").amount = Decimal("2")


# ---------------------------------------------------------------- Quantity


@pytest.mark.unit
def test_quantity_adds_and_compares_within_a_unit():
    assert shares("10") + shares("5") == shares("15")
    assert shares("10") - shares("4") == shares("6")
    assert shares("1") < shares("2")


@pytest.mark.unit
@pytest.mark.parametrize("op", ["add", "sub", "lt", "ge"])
def test_quantity_refuses_to_mix_units(op):
    a, b = shares("1"), Quantity(Decimal("1"), "contracts")
    with pytest.raises(ValueError):
        {"add": a.__add__, "sub": a.__sub__, "lt": a.__lt__, "ge": a.__ge__}[op](b)


@pytest.mark.unit
@pytest.mark.parametrize("amount", [1.0, 1, False])
def test_quantity_refuses_a_non_decimal_amount(amount):
    with pytest.raises(TypeError):
        Quantity(amount, "shares")


@pytest.mark.unit
@pytest.mark.parametrize("unit", ["", " shares", "shares ", None])
def test_quantity_refuses_a_bad_unit(unit):
    with pytest.raises((ValueError, TypeError)):
        Quantity(Decimal("1"), unit)


@pytest.mark.unit
def test_money_and_quantity_never_mix():
    with pytest.raises(TypeError):
        usd("1") + shares("1")


# ---------------------------------------------------------------- converters


@pytest.mark.unit
def test_from_float64_removes_binary_noise_at_the_stated_quantum():
    assert 0.1 + 0.2 != 0.3
    assert from_float64(0.1 + 0.2, PRICE_QUANTUM) == Decimal("0.3000")


@pytest.mark.unit
def test_from_float64_keeps_the_quantum_exponent():
    assert from_float64(185.2, PRICE_QUANTUM).as_tuple().exponent == -4
    assert from_float64(1234567.0, SHARE_QUANTUM) == Decimal("1234567")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.00005", "0.0000"),   # half-even: ties go to the even digit
        ("0.00015", "0.0002"),
        ("0.00025", "0.0002"),
        ("-0.00015", "-0.0002"),
        ("0.000051", "0.0001"),  # not a tie
    ],
)
def test_quantize_rounds_half_even(value, expected):
    assert ROUNDING == "ROUND_HALF_EVEN"
    assert quantize(Decimal(value), PRICE_QUANTUM) == Decimal(expected)


@pytest.mark.unit
def test_from_float64_accepts_numpy_float64():
    # Batch-1 self-review: pandas hands over numpy.float64, a float subclass
    # whose repr in numpy 2 is "np.float64(0.1)", not "0.1". The conversion
    # must use the plain float representation.
    np = pytest.importorskip("numpy")
    assert from_float64(np.float64(0.1) + np.float64(0.2), PRICE_QUANTUM) == Decimal("0.3000")
    assert from_float64(np.float64(1208.88), PRICE_QUANTUM) == Decimal("1208.8800")
    with pytest.raises(ValueError):
        from_float64(np.float64("nan"), PRICE_QUANTUM)


@pytest.mark.unit
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_from_float64_refuses_non_finite_values(value):
    with pytest.raises(ValueError):
        from_float64(value, PRICE_QUANTUM)


@pytest.mark.unit
@pytest.mark.parametrize("value", [Decimal("1.5"), "1.5", True])
def test_from_float64_takes_only_floats(value):
    with pytest.raises(TypeError):
        from_float64(value, PRICE_QUANTUM)


@pytest.mark.unit
def test_to_float64_converts_a_decimal():
    assert to_float64(Decimal("123.4567")) == 123.4567


@pytest.mark.unit
def test_to_float64_refuses_non_decimals_and_non_finite_values():
    with pytest.raises(TypeError):
        to_float64(123.4567)
    with pytest.raises(ValueError):
        to_float64(Decimal("NaN"))


@pytest.mark.unit
def test_float_round_trip_at_the_price_quantum():
    for text in ["0.0001", "185.2000", "1208.8800", "99999.9999"]:
        value = Decimal(text)
        assert from_float64(to_float64(value), PRICE_QUANTUM) == value
