"""
RiskManager — Position sizing, SL/TP/trailing, drawdown protection.
"""

import logging

logger = logging.getLogger("trade4me")


class RiskManager:
    def __init__(self, config: dict):
        self.max_position_pct = config.get("max_position_pct", 2.0)
        self.stop_loss_pct = config.get("stop_loss_pct", 1.0)
        self.take_profit_pct = config.get("take_profit_pct", 1.5)
        self.trailing_stop_pct = config.get("trailing_stop_pct", 0.0)
        self.max_drawdown_pct = config.get("max_drawdown_pct", 10.0)
        self.max_open_positions = config.get("max_open_positions", 3)
        self.max_daily_loss_pct = config.get("max_daily_loss_pct", 5.0)

        self.initial_capital: float = 0.0
        self.peak_capital: float = 0.0
        self.daily_pnl: float = 0.0

    def set_capital(self, capital: float):
        self.initial_capital = capital
        self.peak_capital = capital

    def reset_daily(self):
        self.daily_pnl = 0.0

    def record_pnl(self, pnl: float):
        self.daily_pnl += pnl

    def calculate_position_size(self, capital: float, price: float) -> float:
        max_amount_usdt = capital * (self.max_position_pct / 100)
        return max_amount_usdt / price if price > 0 else 0.0

    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        if side == "long":
            return entry_price * (1 - self.stop_loss_pct / 100)
        return entry_price * (1 + self.stop_loss_pct / 100)

    def calculate_take_profit(self, entry_price: float, side: str) -> float:
        if side == "long":
            return entry_price * (1 + self.take_profit_pct / 100)
        return entry_price * (1 - self.take_profit_pct / 100)

    def calculate_trailing_stop(self, entry_price: float, current_price: float, current_sl: float, side: str) -> float:
        if self.trailing_stop_pct <= 0:
            return current_sl
        if side == "long":
            new_sl = current_price * (1 - self.trailing_stop_pct / 100)
            return max(current_sl, new_sl)
        else:
            new_sl = current_price * (1 + self.trailing_stop_pct / 100)
            return min(current_sl, new_sl) if current_sl > 0 else new_sl

    def can_open_position(self, current_open: int) -> bool:
        if current_open >= self.max_open_positions:
            logger.warning(f"Max positions reached ({self.max_open_positions})")
            return False
        return True

    def check_daily_loss(self) -> bool:
        if self.initial_capital == 0:
            return False
        daily_loss_pct = abs(self.daily_pnl) / self.initial_capital * 100
        if self.daily_pnl < 0 and daily_loss_pct >= self.max_daily_loss_pct:
            logger.error(f"DAILY LOSS LIMIT: {daily_loss_pct:.2f}% >= {self.max_daily_loss_pct}%")
            return True
        return False

    def check_drawdown(self, current_capital: float) -> bool:
        if current_capital > self.peak_capital:
            self.peak_capital = current_capital
        if self.peak_capital == 0:
            return False
        drawdown = ((self.peak_capital - current_capital) / self.peak_capital) * 100
        if drawdown >= self.max_drawdown_pct:
            logger.error(
                f"MAX DRAWDOWN: {drawdown:.2f}% >= {self.max_drawdown_pct}% | "
                f"Capital: ${current_capital:,.2f} (peak: ${self.peak_capital:,.2f})"
            )
            return True
        if drawdown > self.max_drawdown_pct * 0.7:
            logger.warning(f"High drawdown: {drawdown:.2f}%")
        return False

    def validate_trade(self, capital: float, price: float, current_open: int, side: str = "long") -> dict | None:
        if not self.can_open_position(current_open):
            return None
        if self.check_drawdown(capital):
            return None
        if self.check_daily_loss():
            return None
        amount = self.calculate_position_size(capital, price)
        if amount <= 0:
            return None
        return {
            "amount": amount,
            "stop_loss": self.calculate_stop_loss(price, side),
            "take_profit": self.calculate_take_profit(price, side),
            "position_value_usdt": amount * price,
            "position_pct": (amount * price / capital * 100) if capital > 0 else 0,
        }
