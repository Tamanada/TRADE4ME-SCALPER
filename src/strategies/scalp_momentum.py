"""
Scalp Momentum Strategy — MACD crossover + Bollinger Band bounce + volume.
"""

import pandas as pd
from src.strategies.base import BaseStrategy, Signal, TradeSignal


class ScalpMomentumStrategy(BaseStrategy):
    def __init__(self, config: dict = None):
        super().__init__("scalp_momentum", config)
        self.min_volume_ratio = self.config.get("min_volume_ratio", 1.0)
        self.bb_proximity_pct = self.config.get("bb_proximity_pct", 2.0)
        self.require_bb = self.config.get("require_bb", False)

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if not self._validate_data(df):
            return TradeSignal(Signal.HOLD, symbol, "Insufficient data")

        current = df.iloc[-1]
        previous = df.iloc[-2]

        required = ["macd", "macd_signal", "bb_lower", "bb_upper", "bb_middle", "volume_ratio"]
        if not all(col in df.columns for col in required):
            return TradeSignal(Signal.HOLD, symbol, "Missing indicators")

        # MACD crossover detection
        macd_cross_up = (
            previous["macd"] <= previous["macd_signal"]
            and current["macd"] > current["macd_signal"]
        )
        macd_cross_down = (
            previous["macd"] >= previous["macd_signal"]
            and current["macd"] < current["macd_signal"]
        )

        price = current["close"]
        bb_pct = self.bb_proximity_pct / 100

        # BB position: near lower half or upper half
        near_bb_lower = price <= current["bb_lower"] * (1 + bb_pct)
        near_bb_upper = price >= current["bb_upper"] * (1 - bb_pct)

        # Relaxed: price below BB middle = favorable for BUY
        below_middle = price < current["bb_middle"]
        above_middle = price > current["bb_middle"]

        volume_ok = current["volume_ratio"] >= self.min_volume_ratio

        # BUY: MACD cross up + (near BB lower OR below BB middle) + volume
        bb_buy_ok = near_bb_lower if self.require_bb else (near_bb_lower or below_middle)
        if macd_cross_up and bb_buy_ok and volume_ok:
            strength = min(1.0, current["volume_ratio"] / 3.0)
            bb_info = "BB lower" if near_bb_lower else "below BB mid"
            return TradeSignal(
                Signal.BUY, symbol,
                f"MACD cross UP + {bb_info} | Vol={current['volume_ratio']:.1f}x",
                strength=strength, price=price,
            )

        # SELL: MACD cross down + (near BB upper OR above BB middle) + volume
        bb_sell_ok = near_bb_upper if self.require_bb else (near_bb_upper or above_middle)
        if macd_cross_down and bb_sell_ok and volume_ok:
            strength = min(1.0, current["volume_ratio"] / 3.0)
            bb_info = "BB upper" if near_bb_upper else "above BB mid"
            return TradeSignal(
                Signal.SELL, symbol,
                f"MACD cross DOWN + {bb_info} | Vol={current['volume_ratio']:.1f}x",
                strength=strength, price=price,
            )

        return TradeSignal(Signal.HOLD, symbol, "No momentum confluence")
