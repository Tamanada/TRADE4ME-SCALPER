"""
DataFetcher — OHLCV retrieval and formatting.
"""

import pandas as pd
from src.exchange.client import ExchangeClient


class DataFetcher:
    def __init__(self, client: ExchangeClient):
        self.client = client

    def get_candles(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> pd.DataFrame:
        raw = self.client.get_ohlcv(symbol, timeframe, limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def get_current_price(self, symbol: str) -> float:
        ticker = self.client.get_ticker(symbol)
        return ticker["last"]

    def get_spread(self, symbol: str) -> dict:
        book = self.client.get_order_book(symbol, limit=1)
        best_bid = book["bids"][0][0] if book["bids"] else 0
        best_ask = book["asks"][0][0] if book["asks"] else 0
        spread = best_ask - best_bid
        spread_pct = (spread / best_ask * 100) if best_ask > 0 else 0
        return {"bid": best_bid, "ask": best_ask, "spread": spread, "spread_pct": round(spread_pct, 4)}
