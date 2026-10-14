"""Versioned feature definitions and the float64 boundary (Part F; ADR-007; docs/tasks/M2-01.md).

A feature has a name, a semantic version, frozen numeric parameters, the
adjusted series it reads and a declared warm-up. Its key is derived from all
of these through canonical JSON, so the same computation always has the same
key and any change needs a new version. A registry checks each definition
against its feature's declared parameter schema and refuses a different
definition under an existing key.

Quant code works in float64. Values cross in from Decimal only through the
M1-02 converters; float_inputs() is the explicit check at a computation's
door, refusing Decimal, int, bool and non-finite values.
"""

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from investment_engine.quant.adjusted import AdjustedBasis

_NAME = re.compile(r"[a-z][a-z0-9_]*")
_PARAM = re.compile(r"[a-z][a-z0-9_]*")
_VERSION = re.compile(r"\d+\.\d+\.\d+")


def _number(value: object, what: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{what} must be an int or float, not {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{what} must be finite, not {value}")
    return value


@dataclass(frozen=True)
class FeatureDefinition:
    name: str  # e.g. "sma"
    version: str  # semantic version; bumped on any change to the computation
    params: Mapping[str, int | float]  # frozen
    input_basis: AdjustedBasis  # which M2-00 series it reads
    warmup_sessions: int  # input sessions needed before a value exists
    key: str = field(init=False)  # canonical name/version/params/input_basis

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise ValueError(f"a feature name is a lowercase identifier, not {self.name!r}")
        if not isinstance(self.version, str) or not _VERSION.fullmatch(self.version):
            raise ValueError(f"a feature version is semantic (MAJOR.MINOR.PATCH), not {self.version!r}")
        if not isinstance(self.params, Mapping):
            raise TypeError("params must be a mapping")
        params = {}
        for k, v in self.params.items():
            if not isinstance(k, str) or not _PARAM.fullmatch(k):
                raise ValueError(f"a parameter name is a lowercase identifier, not {k!r}")
            params[k] = _number(v, f"parameter {k}")
        object.__setattr__(self, "params", MappingProxyType(dict(sorted(params.items()))))
        object.__setattr__(self, "input_basis", AdjustedBasis(self.input_basis))
        w = self.warmup_sessions
        if isinstance(w, bool) or not isinstance(w, int):
            raise TypeError(f"warmup_sessions must be an int, not {type(w).__name__}")
        if w < 1:
            raise ValueError(f"warmup_sessions must be positive, not {w}")
        canonical = json.dumps({"input_basis": str(self.input_basis), "name": self.name, "params": params,
                                "version": self.version}, sort_keys=True, separators=(",", ":"))
        object.__setattr__(self, "key", canonical)


@dataclass(frozen=True)
class ParamSpec:
    kind: type  # int or float
    minimum: int | float | None = None

    def check(self, name: str, value: int | float) -> None:
        if self.kind is int and not isinstance(value, int):
            raise TypeError(f"parameter {name} must be an int, not {value!r}")
        if self.kind is float and not isinstance(value, float):
            raise TypeError(f"parameter {name} must be a float, not {value!r}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"parameter {name} must be at least {self.minimum}, not {value}")


class FeatureRegistry:
    """Registered definitions by key; each feature name has a declared parameter schema."""

    def __init__(self, schemas: Mapping[str, Mapping[str, ParamSpec]]) -> None:
        self._schemas = MappingProxyType({n: MappingProxyType(dict(s)) for n, s in schemas.items()})
        self._definitions: dict[str, FeatureDefinition] = {}

    def register(self, definition: FeatureDefinition) -> None:
        if not isinstance(definition, FeatureDefinition):
            raise TypeError(f"expected a FeatureDefinition, not {type(definition).__name__}")
        schema = self._schemas[definition.name]  # an undeclared feature raises KeyError
        if set(definition.params) != set(schema):
            raise ValueError(f"{definition.name} takes parameters {sorted(schema)}, not {sorted(definition.params)}")
        for name, spec in schema.items():
            spec.check(name, definition.params[name])
        existing = self._definitions.get(definition.key)
        if existing is not None and existing != definition:
            raise ValueError(f"{definition.key} is already registered with a different definition")
        self._definitions[definition.key] = definition

    def get(self, key: str) -> FeatureDefinition:
        return self._definitions[key]

    def __contains__(self, key: object) -> bool:
        return key in self._definitions


def float_inputs(values: Sequence[float]) -> tuple[float, ...]:
    """The explicit float64 boundary: only finite floats enter a feature computation."""
    out = []
    for v in values:
        if not isinstance(v, float):
            raise TypeError(f"feature inputs must be float64, not {type(v).__name__}; convert with money.to_float64")
        if not math.isfinite(v):
            raise ValueError(f"feature inputs must be finite, not {v}")
        out.append(v)
    return tuple(out)
