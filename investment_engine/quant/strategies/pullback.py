"""A2, pullback within the trend: RSI extremes only in the 200-day trend's direction (docs/tasks/M2-05.md).

| Condition                          | Direction |
| close > SMA200 and RSI <= 30       | BULLISH   |
| close < SMA200 and RSI >= 70       | BEARISH   |
| otherwise                          | NEUTRAL   |

"close vs SMA200" is the sign of dist_sma200. Both RSI thresholds are
inclusive. Parameters are fixed; changing any of them is a new version.
"""

from dataclasses import dataclass

from investment_engine.market.candles import Timeframe
from investment_engine.market.corporate_actions import ActionType
from investment_engine.market.data_health import SourceKey
from investment_engine.quant.features import FeatureDefinition
from investment_engine.quant.indicators import DIST_SMA200, RSI14
from investment_engine.quant.snapshot import FeatureSnapshot
from investment_engine.quant.strategies.base import Direction, StrategySignal, declared_snapshot

OVERSOLD, OVERBOUGHT = 30.0, 70.0


@dataclass(frozen=True)
class PullbackStrategy:
    name: str = "daily-pullback"
    version: str = "0.1.0"
    required_sources: tuple[SourceKey, ...] = (SourceKey("yfinance", Timeframe.D1),)
    required_actions: tuple[ActionType, ...] = (ActionType.SPLIT,)
    features: tuple[FeatureDefinition, ...] = (RSI14, DIST_SMA200)
    strength_scale = "min(1, |RSI - 50| / 50): distance of RSI from neutral; not a probability"

    def evaluate(self, snapshot: FeatureSnapshot) -> StrategySignal | None:
        values = declared_snapshot(snapshot, self.features).values
        rsi, dist = values[RSI14.key], values[DIST_SMA200.key]
        if rsi is None or dist is None:
            return None
        side = "above" if dist > 0 else "below" if dist < 0 else "at"
        if dist > 0 and rsi <= OVERSOLD:
            direction, rule = Direction.BULLISH, f"RSI {rsi:.1f} at or below {OVERSOLD:.0f}"
        elif dist < 0 and rsi >= OVERBOUGHT:
            direction, rule = Direction.BEARISH, f"RSI {rsi:.1f} at or above {OVERBOUGHT:.0f}"
        else:
            direction, rule = Direction.NEUTRAL, f"RSI {rsi:.1f}: no pullback in the trend's direction"
        reason = f"close {abs(dist) * 100:.1f}% {side} SMA200; {rule}"
        return StrategySignal(self.name, self.version, direction, min(1.0, abs(rsi - 50.0) / 50.0), (reason,),
                              tuple(d.key for d in self.features))
