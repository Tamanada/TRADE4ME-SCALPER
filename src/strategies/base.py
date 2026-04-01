"""
BaseStrategy — Abstract base class for all trading strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    signal: Signal
    symbol: str
    reason: str
    strength: float = 0.0  # 0.0 to 1.0
    price: float = 0.0


class BaseStrategy(ABC):
    def __init__(self, name: str, config: dict = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        pass

    def _validate_data(self, df: pd.DataFrame, min_rows: int = 50) -> bool:
        return len(df) >= min_rows and not df.empty
