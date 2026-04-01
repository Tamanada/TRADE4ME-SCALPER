"""
PositionTracker — Track open/closed positions with SL/TP/trailing and P&L.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("trade4me")


@dataclass
class Position:
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    amount: float
    stop_loss: float = 0.0
    take_profit: float = 0.0
    highest_price: float = 0.0  # For trailing stop
    opened_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def cost(self) -> float:
        return self.entry_price * self.amount

    def unrealized_pnl(self, current_price: float) -> float:
        if self.side == "long":
            return (current_price - self.entry_price) * self.amount
        return (self.entry_price - current_price) * self.amount

    def unrealized_pnl_pct(self, current_price: float) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == "long":
            return ((current_price - self.entry_price) / self.entry_price) * 100
        return ((self.entry_price - current_price) / self.entry_price) * 100

    def should_stop_loss(self, current_price: float) -> bool:
        if self.stop_loss <= 0:
            return False
        if self.side == "long":
            return current_price <= self.stop_loss
        return current_price >= self.stop_loss

    def should_take_profit(self, current_price: float) -> bool:
        if self.take_profit <= 0:
            return False
        if self.side == "long":
            return current_price >= self.take_profit
        return current_price <= self.take_profit

    def update_trailing_stop(self, current_price: float, trail_pct: float):
        if trail_pct <= 0:
            return
        if self.side == "long":
            if current_price > self.highest_price:
                self.highest_price = current_price
            new_sl = self.highest_price * (1 - trail_pct / 100)
            if new_sl > self.stop_loss:
                self.stop_loss = new_sl


class PositionTracker:
    def __init__(self):
        self.open_positions: list[Position] = []
        self.closed_positions: list[dict] = []
        self.total_realized_pnl: float = 0.0

    def open_position(
        self, symbol: str, side: str, entry_price: float, amount: float,
        stop_loss: float = 0.0, take_profit: float = 0.0,
    ) -> Position:
        pos = Position(
            symbol=symbol, side=side, entry_price=entry_price, amount=amount,
            stop_loss=stop_loss, take_profit=take_profit, highest_price=entry_price,
        )
        self.open_positions.append(pos)
        logger.info(
            f"Position opened: {side.upper()} {amount:.6f} {symbol} @ ${entry_price:,.2f} "
            f"| SL=${stop_loss:,.2f} TP=${take_profit:,.2f}"
        )
        return pos

    def close_position(self, position: Position, exit_price: float) -> float:
        pnl = position.unrealized_pnl(exit_price)
        self.total_realized_pnl += pnl
        self.closed_positions.append({
            "symbol": position.symbol, "side": position.side,
            "entry_price": position.entry_price, "exit_price": exit_price,
            "amount": position.amount, "pnl": pnl,
            "pnl_pct": position.unrealized_pnl_pct(exit_price),
            "opened_at": position.opened_at,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        })
        self.open_positions.remove(position)
        logger.info(f"Position closed: {position.symbol} | P&L: {pnl:+.2f} USDT ({position.unrealized_pnl_pct(exit_price):+.2f}%)")
        return pnl

    def get_position(self, symbol: str) -> Position | None:
        for pos in self.open_positions:
            if pos.symbol == symbol:
                return pos
        return None

    def has_position(self, symbol: str) -> bool:
        return any(p.symbol == symbol for p in self.open_positions)

    def check_exits(self, symbol: str, current_price: float) -> str | None:
        pos = self.get_position(symbol)
        if pos is None:
            return None
        if pos.should_stop_loss(current_price):
            return "stop_loss"
        if pos.should_take_profit(current_price):
            return "take_profit"
        return None

    @property
    def stats(self) -> dict:
        if not self.closed_positions:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": 0.0, "open_positions": len(self.open_positions),
            }
        wins = [t for t in self.closed_positions if t["pnl"] > 0]
        losses = [t for t in self.closed_positions if t["pnl"] <= 0]
        return {
            "total_trades": len(self.closed_positions),
            "wins": len(wins), "losses": len(losses),
            "win_rate": len(wins) / len(self.closed_positions) * 100,
            "total_pnl": self.total_realized_pnl,
            "open_positions": len(self.open_positions),
        }
