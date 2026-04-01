"""
Scalp EMA Strategy — EMA 9/21 crossover + RSI filter + volume confirmation.
"""

import pandas as pd
from src.strategies.base import BaseStrategy, Signal, TradeSignal


class ScalpEMAStrategy(BaseStrategy):
    def __init__(self, config: dict = None):
        super().__init__("scalp_ema", config)
        self.ema_fast = self.config.get("ema_fast", 9)
        self.ema_slow = self.config.get("ema_slow", 21)
        self.rsi_oversold = self.config.get("rsi_oversold", 30)
        self.rsi_overbought = self.config.get("rsi_overbought", 70)
        self.min_volume_ratio = self.config.get("min_volume_ratio", 1.5)

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if not self._validate_data(df):
            return TradeSignal(Signal.HOLD, symbol, "Insufficient data")

        current = df.iloc[-1]
        previous = df.iloc[-2]

        ema_fast_col = f"ema_{self.ema_fast}"
        ema_slow_col = f"ema_{self.ema_slow}"

        required = [ema_fast_col, ema_slow_col, "rsi", "volume_ratio"]
        if not all(col in df.columns for col in required):
            return TradeSignal(Signal.HOLD, symbol, "Missing indicators")

        cross_up = (
            previous[ema_fast_col] <= previous[ema_slow_col]
            and current[ema_fast_col] > current[ema_slow_col]
        )
        cross_down = (
            previous[ema_fast_col] >= previous[ema_slow_col]
            and current[ema_fast_col] < current[ema_slow_col]
        )

        rsi = current["rsi"]
        volume_ok = current["volume_ratio"] >= self.min_volume_ratio

        if cross_up and rsi < self.rsi_overbought and volume_ok:
            strength = min(1.0, current["volume_ratio"] / 3.0)
            return TradeSignal(
                Signal.BUY, symbol,
                f"EMA{self.ema_fast} cross EMA{self.ema_slow} UP | RSI={rsi:.1f} | Vol={current['volume_ratio']:.1f}x",
                strength=strength, price=current["close"],
            )

        if cross_down and rsi > self.rsi_oversold and volume_ok:
            strength = min(1.0, current["volume_ratio"] / 3.0)
            return TradeSignal(
                Signal.SELL, symbol,
                f"EMA{self.ema_fast} cross EMA{self.ema_slow} DOWN | RSI={rsi:.1f} | Vol={current['volume_ratio']:.1f}x",
                strength=strength, price=current["close"],
            )

        return TradeSignal(Signal.HOLD, symbol, "No EMA crossover")
