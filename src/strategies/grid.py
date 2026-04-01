"""
GridStrategy — Grid trading with configurable price levels.
"""

import pandas as pd
from src.strategies.base import BaseStrategy, Signal, TradeSignal


class GridStrategy(BaseStrategy):
    def __init__(self, config: dict = None):
        super().__init__("grid", config)
        self.upper_price = self.config.get("upper_price", 70000)
        self.lower_price = self.config.get("lower_price", 60000)
        self.grid_levels_count = self.config.get("grid_levels", 10)
        self.grid_levels = self._calculate_grid_levels()
        self.filled_buys: set[float] = set()
        self.filled_sells: set[float] = set()

    def _calculate_grid_levels(self) -> list[float]:
        step = (self.upper_price - self.lower_price) / self.grid_levels_count
        return [round(self.lower_price + i * step, 2) for i in range(self.grid_levels_count + 1)]

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if df.empty:
            return TradeSignal(Signal.HOLD, symbol, "No data")

        current_price = df.iloc[-1]["close"]

        # Find nearest grid level below current price for BUY
        buy_levels = [
            lvl for lvl in self.grid_levels
            if lvl < current_price and lvl not in self.filled_buys
        ]
        if buy_levels:
            nearest_buy = max(buy_levels)  # Highest unfilled level below price
            distance_pct = (current_price - nearest_buy) / current_price * 100
            if distance_pct < 0.5:  # Within 0.5% of grid level
                return TradeSignal(
                    Signal.BUY, symbol,
                    f"Grid BUY at ${nearest_buy:,.2f} (price near grid level)",
                    strength=0.5, price=nearest_buy,
                )

        # Find nearest grid level above current price for SELL
        sell_levels = [
            lvl for lvl in self.grid_levels
            if lvl > current_price and lvl not in self.filled_sells
        ]
        if sell_levels:
            nearest_sell = min(sell_levels)
            distance_pct = (nearest_sell - current_price) / current_price * 100
            if distance_pct < 0.5:
                return TradeSignal(
                    Signal.SELL, symbol,
                    f"Grid SELL at ${nearest_sell:,.2f} (price near grid level)",
                    strength=0.5, price=nearest_sell,
                )

        return TradeSignal(Signal.HOLD, symbol, "Price between grid levels")

    def mark_filled(self, price: float, side: str):
        if side == "buy":
            self.filled_buys.add(price)
        else:
            self.filled_sells.add(price)

    def reset(self):
        self.filled_buys.clear()
        self.filled_sells.clear()
