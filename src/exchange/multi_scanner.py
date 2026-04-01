"""
MultiExchangeScanner — Scans prices across 20 exchanges for arbitrage opportunities.
"""

import ccxt
import logging
import statistics
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

logger = logging.getLogger("trade4me")

TOP_20_EXCHANGES = [
    "binance", "bybit", "okx", "coinbase", "kucoin",
    "gate", "bitget", "mexc", "htx", "kraken",
    "bitfinex", "poloniex", "bingx", "phemex", "lbank",
    "bitmart", "ascendex", "whitebit", "probit", "digifinex",
]


@dataclass
class ExchangePrice:
    exchange: str
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    available: bool = True
    suspended: bool = False
    suspend_reason: str = ""


@dataclass
class ArbitrageOpportunity:
    symbol: str
    buy_exchange: str
    buy_price: float
    sell_exchange: str
    sell_price: float
    spread: float
    spread_pct: float
    all_prices: list
    num_exchanges: int = 0
    buy_fee_pct: float = 0.0
    sell_fee_pct: float = 0.0
    total_fees_pct: float = 0.0
    net_spread_pct: float = 0.0
    rsi: float | None = None
    ema_trend: str = ""
    ema_9: float | None = None
    ema_21: float | None = None
    suspended_exchanges: list = field(default_factory=list)


class MultiExchangeScanner:
    DEFAULT_TAKER_FEES = {
        "binance": 0.10, "bybit": 0.10, "okx": 0.10, "coinbase": 0.40,
        "kucoin": 0.10, "gate": 0.15, "bitget": 0.10, "mexc": 0.00,
        "htx": 0.20, "kraken": 0.26, "bitfinex": 0.20, "poloniex": 0.20,
        "bingx": 0.10, "phemex": 0.10, "lbank": 0.10, "bitmart": 0.25,
        "ascendex": 0.10, "whitebit": 0.10, "probit": 0.20, "digifinex": 0.20,
    }
    FALLBACK_FEE = 0.20

    def __init__(self, exchanges: list[str] = None, tokens: list[str] = None):
        self.exchange_names = exchanges or TOP_20_EXCHANGES
        self.tokens = tokens
        self.exchanges: dict[str, ccxt.Exchange] = {}
        self.exchange_markets: dict[str, set] = {}
        self._discovered_tokens: list[str] = []
        self._fee_cache: dict[str, float] = {}
        self._suspended_pairs: dict[str, dict[str, str]] = {}
        self._init_exchanges()

    def _init_exchanges(self):
        for name in self.exchange_names:
            try:
                exchange_class = getattr(ccxt, name, None)
                if exchange_class:
                    ex = exchange_class({"enableRateLimit": True, "timeout": 10000})
                    self.exchanges[name] = ex
                    logger.info(f"Exchange initialized: {name}")
            except Exception as e:
                logger.warning(f"Cannot initialize {name}: {e}")

    def _load_markets(self, exchange_name: str) -> set:
        ex = self.exchanges.get(exchange_name)
        if not ex:
            return set()
        try:
            ex.load_markets()
            usdt_pairs = set()
            suspended = {}
            for symbol, market in ex.markets.items():
                if not symbol.endswith("/USDT") or not market.get("spot", True):
                    continue
                is_active = market.get("active", True)
                info = market.get("info", {}) or {}
                suspend_reason = self._detect_suspension(exchange_name, info, is_active)
                if suspend_reason:
                    suspended[symbol] = suspend_reason
                usdt_pairs.add(symbol)

            self.exchange_markets[exchange_name] = usdt_pairs
            self._suspended_pairs[exchange_name] = suspended

            try:
                fee = (ex.fees or {}).get("trading", {}).get("taker")
                self._fee_cache[exchange_name] = (fee * 100) if fee and fee > 0 else self.DEFAULT_TAKER_FEES.get(exchange_name, self.FALLBACK_FEE)
            except Exception:
                self._fee_cache[exchange_name] = self.DEFAULT_TAKER_FEES.get(exchange_name, self.FALLBACK_FEE)

            logger.info(f"{exchange_name}: {len(usdt_pairs)} USDT pairs (fee: {self._fee_cache.get(exchange_name)}%)")
            return usdt_pairs
        except Exception as e:
            logger.warning(f"Error loading markets {exchange_name}: {e}")
            return set()

    @staticmethod
    def _detect_suspension(exchange_name: str, info: dict, is_active: bool) -> str:
        if not is_active:
            return "trading inactive"
        checks = {
            "htx": lambda: info.get("state", "") in ("suspend", "suspended", "offline"),
            "gate": lambda: info.get("trade_disabled") or info.get("trade_status") == "untradable",
            "kucoin": lambda: info.get("enableTrading") is False,
            "okx": lambda: str(info.get("state", "")).lower() in ("suspend", "suspended"),
            "binance": lambda: str(info.get("status", "")).upper() in ("HALT", "BREAK"),
            "bybit": lambda: str(info.get("status", "")).lower() in ("settling", "closed"),
        }
        if exchange_name in checks and checks[exchange_name]():
            return "trading suspended"
        for key in ("tradingEnabled", "trade_status", "trading"):
            val = info.get(key)
            if val is False or (isinstance(val, str) and val.lower() in ("disabled", "suspended", "halt")):
                return "trading disabled"
        return ""

    def discover_tokens(self, min_exchanges: int = 3) -> list[str]:
        logger.info("Discovering tokens across exchanges...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self._load_markets, name): name for name in self.exchanges}
            for future in as_completed(futures, timeout=60):
                try:
                    future.result(timeout=15)
                except Exception:
                    pass

        token_count: dict[str, int] = {}
        for pairs in self.exchange_markets.values():
            for pair in pairs:
                token_count[pair] = token_count.get(pair, 0) + 1

        common_tokens = [t for t, c in token_count.items() if c >= min_exchanges]
        common_tokens.sort(key=lambda t: token_count[t], reverse=True)
        self._discovered_tokens = common_tokens
        logger.info(f"Discovered: {len(common_tokens)} tokens on >= {min_exchanges} exchanges")
        return common_tokens

    def get_token_list(self) -> list[str]:
        if self.tokens:
            return self.tokens
        if self._discovered_tokens:
            return self._discovered_tokens
        return self.discover_tokens(min_exchanges=3)

    def get_fee(self, exchange_name: str) -> float:
        return self._fee_cache.get(exchange_name, self.DEFAULT_TAKER_FEES.get(exchange_name, self.FALLBACK_FEE))

    def _fetch_ticker(self, exchange_name: str, symbol: str) -> ExchangePrice | None:
        if exchange_name in self.exchange_markets and symbol not in self.exchange_markets[exchange_name]:
            return None
        ex = self.exchanges.get(exchange_name)
        if not ex:
            return None
        is_susp = symbol in self._suspended_pairs.get(exchange_name, {})
        susp_reason = self._suspended_pairs.get(exchange_name, {}).get(symbol, "")
        try:
            ticker = ex.fetch_ticker(symbol)
            return ExchangePrice(
                exchange=exchange_name, symbol=symbol,
                bid=ticker.get("bid") or 0, ask=ticker.get("ask") or 0,
                last=ticker.get("last") or 0, volume_24h=ticker.get("quoteVolume") or 0,
                suspended=is_susp, suspend_reason=susp_reason,
            )
        except (ccxt.BadSymbol, ccxt.BadRequest):
            return None
        except Exception:
            return None

    @staticmethod
    def _filter_outlier_prices(prices: list[ExchangePrice]) -> list[ExchangePrice]:
        if len(prices) < 3:
            return prices
        last_prices = [p.last for p in prices if p.last > 0]
        if len(last_prices) < 2:
            return prices
        median_price = statistics.median(last_prices)
        if median_price <= 0:
            return prices
        return [p for p in prices if 0.33 <= (p.last / median_price) <= 3.0]

    @staticmethod
    def _filter_low_volume(prices: list[ExchangePrice], min_volume_usd: float = 1000) -> list[ExchangePrice]:
        return [p for p in prices if p.volume_24h >= min_volume_usd]

    def _fetch_indicators(self, exchange_name: str, symbol: str) -> dict:
        try:
            ex = self.exchanges.get(exchange_name)
            if not ex or not ex.has.get("fetchOHLCV", False):
                return {}
            ohlcv = ex.fetch_ohlcv(symbol, timeframe="1h", limit=50)
            if not ohlcv or len(ohlcv) < 21:
                return {}
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            import ta as ta_lib
            rsi_val = ta_lib.momentum.rsi(df["close"], window=14)
            rsi = round(float(rsi_val.iloc[-1]), 1) if pd.notna(rsi_val.iloc[-1]) else None
            ema_9 = float(ta_lib.trend.ema_indicator(df["close"], window=9).iloc[-1])
            ema_21 = float(ta_lib.trend.ema_indicator(df["close"], window=21).iloc[-1])
            trend = "BULLISH" if ema_9 > ema_21 else "BEARISH"
            return {"rsi": rsi, "ema_trend": trend, "ema_9": round(ema_9, 8), "ema_21": round(ema_21, 8)}
        except Exception:
            return {}

    def scan_token(self, symbol: str) -> ArbitrageOpportunity | None:
        target_exchanges = [
            name for name in self.exchanges
            if name not in self.exchange_markets or symbol in self.exchange_markets[name]
        ]
        if len(target_exchanges) < 2:
            return None

        prices: list[ExchangePrice] = []
        with ThreadPoolExecutor(max_workers=len(target_exchanges)) as executor:
            futures = {executor.submit(self._fetch_ticker, name, symbol): name for name in target_exchanges}
            for future in as_completed(futures, timeout=10):
                try:
                    result = future.result(timeout=3)
                    if result and result.available and result.ask > 0 and result.bid > 0:
                        prices.append(result)
                except Exception:
                    pass

        if len(prices) < 2:
            return None
        prices = self._filter_outlier_prices(prices)
        if len(prices) < 2:
            return None
        prices_vol = self._filter_low_volume(prices)
        if len(prices_vol) >= 2:
            prices = prices_vol
        if len(prices) < 2:
            return None

        active_prices = [p for p in prices if not p.suspended]
        if len(active_prices) < 2:
            return None

        best_buy = min(active_prices, key=lambda p: p.ask)
        best_sell = max(active_prices, key=lambda p: p.bid)
        spread = best_sell.bid - best_buy.ask
        spread_pct = (spread / best_buy.ask * 100) if best_buy.ask > 0 else 0

        if spread_pct > 50:
            return None

        buy_fee_pct = self.get_fee(best_buy.exchange)
        sell_fee_pct = self.get_fee(best_sell.exchange)
        net_spread_pct = spread_pct - buy_fee_pct - sell_fee_pct

        indicators = self._fetch_indicators(best_buy.exchange, symbol) if net_spread_pct > 0.1 else {}

        all_prices_data = [
            {"exchange": p.exchange, "bid": p.bid, "ask": p.ask, "last": p.last,
             "volume_24h": p.volume_24h, "suspended": p.suspended}
            for p in sorted(prices, key=lambda p: p.ask)
        ]

        suspended_exchanges = [
            {"exchange": p.exchange, "reason": p.suspend_reason}
            for p in prices if p.suspended
        ]

        return ArbitrageOpportunity(
            symbol=symbol, buy_exchange=best_buy.exchange, buy_price=best_buy.ask,
            sell_exchange=best_sell.exchange, sell_price=best_sell.bid,
            spread=spread, spread_pct=spread_pct, all_prices=all_prices_data,
            num_exchanges=len(active_prices),
            buy_fee_pct=buy_fee_pct, sell_fee_pct=sell_fee_pct,
            total_fees_pct=buy_fee_pct + sell_fee_pct, net_spread_pct=net_spread_pct,
            rsi=indicators.get("rsi"), ema_trend=indicators.get("ema_trend", ""),
            ema_9=indicators.get("ema_9"), ema_21=indicators.get("ema_21"),
            suspended_exchanges=suspended_exchanges,
        )

    def scan_all(self, max_tokens: int = 0) -> list[ArbitrageOpportunity]:
        tokens = self.get_token_list()
        if max_tokens > 0:
            tokens = tokens[:max_tokens]
        logger.info(f"Scanning {len(tokens)} tokens on {len(self.exchanges)} exchanges...")

        results = []
        batch_size = 10
        for i in range(0, len(tokens), batch_size):
            batch = tokens[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {executor.submit(self.scan_token, sym): sym for sym in batch}
                for future in as_completed(futures, timeout=60):
                    try:
                        result = future.result(timeout=15)
                        if result:
                            results.append(result)
                    except Exception:
                        pass

        results.sort(key=lambda r: r.net_spread_pct, reverse=True)
        return results
