"""
ArbitrageStrategy — Inter-exchange spread detection wrapper.
"""

from src.strategies.base import BaseStrategy, Signal, TradeSignal
import pandas as pd


class ArbitrageStrategy(BaseStrategy):
    """
    Wrapper strategy for arbitrage. Unlike scalp strategies, this doesn't use
    a standard analyze() flow — it delegates to MultiExchangeScanner.
    The analyze() method is a no-op; the bot calls scan() directly.
    """

    def __init__(self, config: dict = None):
        super().__init__("arbitrage", config)
        self.min_net_spread_pct = self.config.get("min_net_spread_pct", 0.3)

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        return TradeSignal(Signal.HOLD, symbol, "Use scan() for arbitrage")
