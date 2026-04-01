"""
Scalp RSI Strategy — RSI bounce at oversold/overbought + EMA 50 trend.
"""

import pandas as pd
from src.strategies.base import BaseStrategy, Signal, TradeSignal


class ScalpRSIStrategy(BaseStrategy):
    def __init__(self, config: dict = None):
        super().__init__("scalp_rsi", config)
        self.rsi_entry = self.config.get("rsi_entry", 35)
        self.rsi_exit = self.config.get("rsi_exit", 65)
        self.ema_trend = self.config.get("ema_trend", 50)
        self.min_volume_ratio = self.config.get("min_volume_ratio", 0.8)
        self.use_ema_filter = self.config.get("use_ema_filter", True)

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if not self._validate_data(df):
            return TradeSignal(Signal.HOLD, symbol, "Insufficient data")

        current = df.iloc[-1]
        previous = df.iloc[-2]
        ema_trend_col = f"ema_{self.ema_trend}"

        required = ["rsi", "volume_ratio"]
        if not all(col in df.columns for col in required):
            return TradeSignal(Signal.HOLD, symbol, "Missing indicators")

        rsi = current["rsi"]
        prev_rsi = previous["rsi"]
        price = current["close"]
        volume_ok = current["volume_ratio"] >= self.min_volume_ratio

        # EMA filter is optional — when disabled, more signals fire
        ema_bullish = True
        ema_bearish = True
        if self.use_ema_filter and ema_trend_col in df.columns:
            ema_val = current[ema_trend_col]
            ema_bullish = price > ema_val
            ema_bearish = price < ema_val

        # BUY: RSI crosses above oversold zone (reversal bounce)
        if rsi <= self.rsi_entry and prev_rsi <= self.rsi_entry and volume_ok and ema_bullish:
            strength = min(1.0, (self.rsi_entry - rsi) / self.rsi_entry + 0.3)
            ema_info = f" | EMA{self.ema_trend} OK" if self.use_ema_filter else ""
            return TradeSignal(
                Signal.BUY, symbol,
                f"RSI oversold ({rsi:.1f} < {self.rsi_entry}){ema_info} | Vol={current['volume_ratio']:.1f}x",
                strength=strength, price=price,
            )

        # SELL: RSI in overbought zone
        if rsi >= self.rsi_exit and prev_rsi >= self.rsi_exit and volume_ok and ema_bearish:
            strength = min(1.0, (rsi - self.rsi_exit) / (100 - self.rsi_exit) + 0.3)
            ema_info = f" | EMA{self.ema_trend} OK" if self.use_ema_filter else ""
            return TradeSignal(
                Signal.SELL, symbol,
                f"RSI overbought ({rsi:.1f} > {self.rsi_exit}){ema_info} | Vol={current['volume_ratio']:.1f}x",
                strength=strength, price=price,
            )

        return TradeSignal(Signal.HOLD, symbol, f"RSI neutral ({rsi:.1f})")
