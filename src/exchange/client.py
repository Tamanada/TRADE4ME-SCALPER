"""
ExchangeClient — Unified CCXT wrapper for any exchange.
"""

import ccxt
from typing import Optional


class ExchangeClient:
    def __init__(
        self,
        exchange_name: str = "binance",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        password: Optional[str] = None,
        sandbox: bool = True,
    ):
        self.exchange_name = exchange_name
        self.sandbox = sandbox

        exchange_class = getattr(ccxt, exchange_name, None)
        if exchange_class is None:
            raise ValueError(f"Exchange '{exchange_name}' not supported by CCXT")

        config = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
        if api_key and api_secret:
            config["apiKey"] = api_key
            config["secret"] = api_secret
        if password:
            config["password"] = password

        self.exchange: ccxt.Exchange = exchange_class(config)
        if sandbox:
            self.exchange.set_sandbox_mode(True)

    def get_balance(self, currency: str = "USDT") -> dict:
        balance = self.exchange.fetch_balance()
        return {
            "free": balance.get("free", {}).get(currency, 0),
            "used": balance.get("used", {}).get(currency, 0),
            "total": balance.get("total", {}).get(currency, 0),
        }

    def get_ticker(self, symbol: str) -> dict:
        return self.exchange.fetch_ticker(symbol)

    def get_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> list:
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def get_order_book(self, symbol: str, limit: int = 20) -> dict:
        return self.exchange.fetch_order_book(symbol, limit=limit)

    def create_market_buy(self, symbol: str, amount: float) -> dict:
        return self.exchange.create_market_buy_order(symbol, amount)

    def create_market_sell(self, symbol: str, amount: float) -> dict:
        return self.exchange.create_market_sell_order(symbol, amount)

    def create_limit_buy(self, symbol: str, amount: float, price: float) -> dict:
        return self.exchange.create_limit_buy_order(symbol, amount, price)

    def create_limit_sell(self, symbol: str, amount: float, price: float) -> dict:
        return self.exchange.create_limit_sell_order(symbol, amount, price)

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        return self.exchange.cancel_order(order_id, symbol)

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        return self.exchange.fetch_open_orders(symbol)

    def get_markets(self) -> list:
        self.exchange.load_markets()
        return list(self.exchange.markets.keys())
