"""
ArbitrageExecutor — Simultaneous dual-leg arbitrage execution.
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from src.exchange.client_pool import MultiExchangeClientPool

logger = logging.getLogger("trade4me")


@dataclass
class ArbLegResult:
    exchange: str
    side: str
    symbol: str
    intended_price: float
    filled_price: float
    amount: float
    status: str
    order_id: str
    error: str | None
    timestamp: str


@dataclass
class ArbExecutionResult:
    id: str
    symbol: str
    buy_leg: ArbLegResult
    sell_leg: ArbLegResult
    intended_spread_pct: float
    actual_spread_pct: float
    gross_profit_usdt: float
    net_profit_usdt: float
    buy_fee_pct: float
    sell_fee_pct: float
    total_fees_usdt: float
    trade_amount_usdt: float
    status: str
    paper_mode: bool
    executed_at: str


class ArbitrageExecutor:
    def __init__(self, client_pool: MultiExchangeClientPool, config: dict):
        self.client_pool = client_pool
        self.paper_mode = config.get("mode", "paper") == "paper"
        self.max_trade_usdt = config.get("max_trade_usdt", 100)
        self.min_spread_pct = config.get("min_spread_pct", 0.3)
        self.execution_history: list[ArbExecutionResult] = []

    def _execute_leg(self, exchange_name: str, symbol: str, side: str,
                     amount: float, expected_price: float) -> ArbLegResult:
        now = datetime.now(timezone.utc).isoformat()
        if self.paper_mode:
            return ArbLegResult(
                exchange=exchange_name, side=side, symbol=symbol,
                intended_price=expected_price, filled_price=expected_price,
                amount=amount, status="paper_filled",
                order_id=f"paper_{uuid.uuid4().hex[:8]}", error=None, timestamp=now,
            )

        client = self.client_pool.get_client(exchange_name)
        if not client:
            return ArbLegResult(
                exchange=exchange_name, side=side, symbol=symbol,
                intended_price=expected_price, filled_price=0, amount=amount,
                status="failed", order_id="",
                error=f"No client for {exchange_name}", timestamp=now,
            )
        try:
            if side == "buy":
                order = client.create_market_buy(symbol, amount)
            else:
                order = client.create_market_sell(symbol, amount)
            filled_price = order.get("average") or order.get("price") or expected_price
            return ArbLegResult(
                exchange=exchange_name, side=side, symbol=symbol,
                intended_price=expected_price, filled_price=float(filled_price),
                amount=amount, status="filled",
                order_id=str(order.get("id", "")), error=None, timestamp=now,
            )
        except Exception as e:
            logger.error(f"Arb leg error {side} {symbol} on {exchange_name}: {e}")
            return ArbLegResult(
                exchange=exchange_name, side=side, symbol=symbol,
                intended_price=expected_price, filled_price=0, amount=amount,
                status="failed", order_id="", error=str(e), timestamp=now,
            )

    def execute(self, symbol: str, buy_exchange: str, buy_price: float,
                sell_exchange: str, sell_price: float, spread_pct: float,
                buy_fee_pct: float = 0.0, sell_fee_pct: float = 0.0) -> ArbExecutionResult:
        exec_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        if spread_pct < self.min_spread_pct:
            logger.debug(f"Spread too low: {spread_pct:.3f}% < {self.min_spread_pct}%")
            failed_leg = ArbLegResult("", "", symbol, 0, 0, 0, "failed", "", "Spread too low", now)
            return ArbExecutionResult(
                id=exec_id, symbol=symbol, buy_leg=failed_leg, sell_leg=failed_leg,
                intended_spread_pct=spread_pct, actual_spread_pct=0,
                gross_profit_usdt=0, net_profit_usdt=0,
                buy_fee_pct=buy_fee_pct, sell_fee_pct=sell_fee_pct,
                total_fees_usdt=0, trade_amount_usdt=0,
                status="failed", paper_mode=self.paper_mode, executed_at=now,
            )

        amount = self.max_trade_usdt / buy_price if buy_price > 0 else 0

        logger.info(
            f"Executing arb {symbol}: BUY {buy_exchange} @ {buy_price} -> "
            f"SELL {sell_exchange} @ {sell_price} (spread: {spread_pct:.3f}%, "
            f"{'PAPER' if self.paper_mode else 'LIVE'})"
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_buy = executor.submit(self._execute_leg, buy_exchange, symbol, "buy", amount, buy_price)
            future_sell = executor.submit(self._execute_leg, sell_exchange, symbol, "sell", amount, sell_price)
            buy_leg = future_buy.result(timeout=30)
            sell_leg = future_sell.result(timeout=30)

        if buy_leg.filled_price > 0 and sell_leg.filled_price > 0:
            actual_spread = sell_leg.filled_price - buy_leg.filled_price
            actual_spread_pct = (actual_spread / buy_leg.filled_price * 100)
            gross_profit = actual_spread * amount
            buy_fee_usdt = (buy_fee_pct / 100) * buy_leg.filled_price * amount
            sell_fee_usdt = (sell_fee_pct / 100) * sell_leg.filled_price * amount
            total_fees_usdt = buy_fee_usdt + sell_fee_usdt
            net_profit = gross_profit - total_fees_usdt
        else:
            actual_spread_pct = gross_profit = total_fees_usdt = net_profit = 0

        both_filled = buy_leg.status in ("filled", "paper_filled") and sell_leg.status in ("filled", "paper_filled")
        status = "success" if both_filled else "partial" if buy_leg.status != "failed" or sell_leg.status != "failed" else "failed"

        result = ArbExecutionResult(
            id=exec_id, symbol=symbol, buy_leg=buy_leg, sell_leg=sell_leg,
            intended_spread_pct=spread_pct, actual_spread_pct=actual_spread_pct,
            gross_profit_usdt=gross_profit, net_profit_usdt=net_profit,
            buy_fee_pct=buy_fee_pct, sell_fee_pct=sell_fee_pct,
            total_fees_usdt=total_fees_usdt, trade_amount_usdt=self.max_trade_usdt,
            status=status, paper_mode=self.paper_mode, executed_at=now,
        )
        self.execution_history.append(result)
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]

        logger.info(
            f"Arb {exec_id[:8]}: {status} | Spread: {spread_pct:.3f}% -> {actual_spread_pct:.3f}% | "
            f"Net: ${net_profit:.4f}"
        )
        return result
