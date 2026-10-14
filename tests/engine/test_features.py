"""Versioned feature definitions and the float64 boundary (Part F; ADR-007; docs/tasks/M2-01.md)."""

from decimal import Decimal
from types import MappingProxyType

import pytest

from investment_engine.quant.adjusted import AdjustedBasis
from investment_engine.quant.features import (
    FeatureDefinition,
    FeatureRegistry,
    ParamSpec,
    float_inputs,
)

SPLIT = AdjustedBasis.SPLIT_ADJUSTED_AS_OF
SCHEMAS = {"sma": {"window": ParamSpec(int, minimum=1)}, "scale": {"factor": ParamSpec(float, minimum=0.0)}}


def sma(window=200, version="1.0.0", warmup=None):
    return FeatureDefinition("sma", version, {"window": window}, SPLIT, warmup if warmup is not None else window)


@pytest.mark.unit
def test_registering_the_same_definition_twice_is_idempotent():
    registry = FeatureRegistry(SCHEMAS)
    registry.register(sma())
    registry.register(sma())
    assert registry.get(sma().key) == sma()


@pytest.mark.unit
def test_a_changed_computation_under_the_same_key_raises():
    registry = FeatureRegistry(SCHEMAS)
    registry.register(sma())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(sma(warmup=150))  # same name/version/params/basis, different computation


@pytest.mark.unit
def test_keys_are_deterministic_and_unique():
    assert sma().key == sma().key
    assert sma(50).key != sma(200).key
    assert sma(version="1.0.1").key != sma().key
    a = FeatureDefinition("scale", "1.0.0", {"factor": 0.5}, SPLIT, 1)
    b = FeatureDefinition("scale", "1.0.0", {"factor": 0.25}, SPLIT, 1)
    assert a.key != b.key


@pytest.mark.unit
def test_keys_ignore_parameter_order_and_use_canonical_serialization():
    a = FeatureDefinition("x", "1.0.0", {"a": 1, "b": 2}, SPLIT, 1)
    b = FeatureDefinition("x", "1.0.0", {"b": 2, "a": 1}, SPLIT, 1)
    assert a.key == b.key
    assert "{" not in a.key or '"a":1' in a.key  # canonical JSON, not a Python repr


@pytest.mark.unit
def test_parameters_are_deeply_immutable():
    params = {"window": 200}
    d = FeatureDefinition("sma", "1.0.0", params, SPLIT, 200)
    params["window"] = 50
    assert d.params["window"] == 200
    assert isinstance(d.params, MappingProxyType)
    with pytest.raises(TypeError):
        d.params["window"] = 1


@pytest.mark.unit
@pytest.mark.parametrize("warmup", [0, -1, True, 1.5, None])
def test_warmup_sessions_is_required_and_a_positive_integer(warmup):
    with pytest.raises((TypeError, ValueError)):
        FeatureDefinition("sma", "1.0.0", {"window": 200}, SPLIT, warmup)


@pytest.mark.unit
@pytest.mark.parametrize("params", [
    {"window": True}, {"window": float("nan")}, {"window": float("inf")}, {"window": Decimal("200")},
    {"window": "200"}, {"window": [200]}, {"": 1}, {"bad key": 1},
])
def test_parameters_must_be_finite_numbers_with_identifier_keys(params):
    with pytest.raises((TypeError, ValueError)):
        FeatureDefinition("sma", "1.0.0", params, SPLIT, 1)


@pytest.mark.unit
@pytest.mark.parametrize("params", [{"window": 2.5}, {"window": 0}, {"windows": 200}, {}, {"window": 200, "x": 1}])
def test_the_registry_checks_parameters_against_the_features_schema(params):
    with pytest.raises((TypeError, ValueError)):
        FeatureRegistry(SCHEMAS).register(FeatureDefinition("sma", "1.0.0", params, SPLIT, 1))


@pytest.mark.unit
def test_an_undeclared_feature_name_is_refused():
    with pytest.raises(KeyError):
        FeatureRegistry(SCHEMAS).register(FeatureDefinition("ema", "1.0.0", {"window": 3}, SPLIT, 3))


@pytest.mark.unit
@pytest.mark.parametrize("version", ["1", "v1.0.0", "1.0", "1.0.0-beta extra", ""])
def test_versions_are_semantic(version):
    with pytest.raises(ValueError):
        FeatureDefinition("sma", version, {"window": 2}, SPLIT, 2)


@pytest.mark.unit
def test_names_cannot_carry_code_or_separators():
    for name in ("sma;rm", "SMA", "s m a", "eval(1)"):
        with pytest.raises(ValueError):
            FeatureDefinition(name, "1.0.0", {}, SPLIT, 1)


@pytest.mark.unit
def test_the_input_basis_is_part_of_the_definition():
    with pytest.raises(ValueError):
        FeatureDefinition("sma", "1.0.0", {"window": 2}, "RAW", 2)
    assert SPLIT.value in sma().key


@pytest.mark.unit
def test_getting_an_unknown_key_raises():
    with pytest.raises(KeyError):
        FeatureRegistry(SCHEMAS).get("nothing")


@pytest.mark.unit
def test_float_inputs_accept_floats_only():
    assert float_inputs([1.0, 2.5]) == (1.0, 2.5)
    for bad in ([Decimal("1")], [1], [True], [float("nan")], [float("inf")], ["1.0"]):
        with pytest.raises((TypeError, ValueError)):
            float_inputs(bad)
