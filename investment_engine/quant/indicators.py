"""Indicators for the first strategies (docs/tasks/M2-02.md).

SMA(50), SMA(200), RSI(14) and the distance of the close from SMA(200), each a
registered, versioned feature on the split-adjusted daily view as of T.
Inputs are the closes of consecutive sessions ending at T, oldest first (M2-03
supplies calendar-validated windows); before a feature's warm-up is complete
its value is None, never a partial-window value.

RSI uses Wilder's smoothing. With n = window and changes c_i between
consecutive closes, it is seeded by the simple averages of the first n gains
max(c, 0) and losses max(-c, 0); each later average is
(previous * (n - 1) + current) / n. RSI = 100 - 100 / (1 + gain / loss), with
100 when only gains, 0 when only losses and 50 when both averages are zero.
The value depends on where the history starts (the seed), so callers pass the
declared seed-to-T history.
"""

import math
from collections.abc import Sequence

from investment_engine.quant.adjusted import AdjustedBasis
from investment_engine.quant.features import (
    FeatureDefinition,
    FeatureRegistry,
    ParamSpec,
    float_inputs,
)

_SPLIT = AdjustedBasis.SPLIT_ADJUSTED_AS_OF


def _window(window: object) -> int:
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError(f"window must be an int, not {type(window).__name__}")
    if window < 1:
        raise ValueError(f"window must be positive, not {window}")
    return window


def _prices(values: Sequence[float]) -> tuple[float, ...]:
    prices = float_inputs(values)
    if any(p <= 0 for p in prices):
        raise ValueError("prices must be positive")
    return prices


def _finite(value: float, what: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{what} is not finite")
    return value


def sma(closes: Sequence[float], window: int) -> float | None:
    """The mean of the last `window` closes; None before `window` values."""
    window = _window(window)
    closes = _prices(closes)
    if len(closes) < window:
        return None
    return _finite(sum(closes[-window:]) / window, "SMA")


def rsi(closes: Sequence[float], window: int = 14) -> float | None:
    """Wilder's RSI over the whole history given; None before window + 1 values."""
    window = _window(window)
    closes = _prices(closes)
    if len(closes) < window + 1:
        return None
    changes = [b - a for a, b in zip(closes, closes[1:], strict=False)]
    gain = sum(max(c, 0.0) for c in changes[:window]) / window
    loss = sum(max(-c, 0.0) for c in changes[:window]) / window
    for c in changes[window:]:
        gain = (gain * (window - 1) + max(c, 0.0)) / window
        loss = (loss * (window - 1) + max(-c, 0.0)) / window
    if loss == 0.0:
        return 50.0 if gain == 0.0 else 100.0
    if gain == 0.0:
        return 0.0
    return _finite(100.0 - 100.0 / (1.0 + gain / loss), "RSI")


def distance_from(close: float, average: float) -> float:
    """(close - average) / average."""
    close, average = float_inputs([close, average])
    if average <= 0:
        raise ValueError(f"the average must be positive, not {average}")
    return _finite((close - average) / average, "distance")


SMA50 = FeatureDefinition("sma", "1.0.0", {"window": 50}, _SPLIT, 50)
SMA200 = FeatureDefinition("sma", "1.0.0", {"window": 200}, _SPLIT, 200)
RSI14 = FeatureDefinition("rsi", "1.0.0", {"window": 14}, _SPLIT, 15)
DIST_SMA200 = FeatureDefinition("dist_sma", "1.0.0", {"window": 200}, _SPLIT, 200)
DEFINITIONS: tuple[FeatureDefinition, ...] = (SMA50, SMA200, RSI14, DIST_SMA200)

SCHEMAS = {
    "sma": {"window": ParamSpec(int, minimum=1)},
    "rsi": {"window": ParamSpec(int, minimum=1)},
    "dist_sma": {"window": ParamSpec(int, minimum=1)},
}


def registry() -> FeatureRegistry:
    """A registry holding the four definitions."""
    reg = FeatureRegistry(SCHEMAS)
    for d in DEFINITIONS:
        reg.register(d)
    return reg


def evaluate(definition: FeatureDefinition, closes: Sequence[float]) -> float | None:
    """The feature's value at the last close given, or None during its warm-up."""
    closes = _prices(closes)
    if len(closes) < definition.warmup_sessions:
        return None
    window = definition.params["window"]
    if definition.name == "sma":
        return sma(closes, window)
    if definition.name == "rsi":
        return rsi(closes, window)
    if definition.name == "dist_sma":
        return distance_from(closes[-1], sma(closes, window))
    raise KeyError(f"no computation for feature {definition.name}")
