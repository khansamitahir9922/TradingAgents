"""A1, trend: the regime from the 200-day average and the 50/200 state (docs/tasks/M2-05.md).

| Condition                                  | Direction |
| close > SMA200 and SMA50 > SMA200          | BULLISH   |
| close < SMA200 and SMA50 < SMA200          | BEARISH   |
| otherwise (equalities included)            | NEUTRAL   |

"close vs SMA200" is the sign of dist_sma200 = (close - SMA200) / SMA200.
Parameters are fixed; changing any of them is a new version.
"""

from dataclasses import dataclass

from investment_engine.market.candles import Timeframe
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import SourceKey
from investment_engine.quant.features import FeatureDefinition
from investment_engine.quant.indicators import DIST_SMA200, SMA50, SMA200
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import Direction, StrategySignal, declared_snapshot

FULL_STRENGTH_DISTANCE = 0.10


@dataclass(frozen=True)
class TrendStrategy:
    name: str = "daily-trend"
    version: str = "0.1.0"
    required_sources: tuple[SourceKey, ...] = (SourceKey("yfinance", Timeframe.D1),)
    required_actions: tuple[ActionType, ...] = (ActionType.SPLIT,)
    features: tuple[FeatureDefinition, ...] = (SMA50, SMA200, DIST_SMA200)
    strength_scale = ("min(1, |close - SMA200| / SMA200 / 0.10): a distance scale where 10% from the average is "
                      "full strength; not a probability")

    def evaluate(self, snapshot: FeatureSnapshot) -> StrategySignal | None:
        values = declared_snapshot(snapshot, self.features).values
        fast, slow, dist = values[SMA50.key], values[SMA200.key], values[DIST_SMA200.key]
        if fast is None or slow is None or dist is None:
            return None
        if dist > 0 and fast > slow:
            direction = Direction.BULLISH
        elif dist < 0 and fast < slow:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL
        side = "above" if dist > 0 else "below" if dist < 0 else "at"
        state = "above" if fast > slow else "below" if fast < slow else "equal to"
        reason = f"close {abs(dist) * 100:.1f}% {side} SMA200; SMA50 {state} SMA200"
        return StrategySignal(self.name, self.version, direction, min(1.0, abs(dist) / FULL_STRENGTH_DISTANCE),
                              (reason,), tuple(d.key for d in self.features))
