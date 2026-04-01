"""
Fibonacci Martingale Strategy

On a red 15min candle:
  1. Calculate Fib levels from candle high/low
  2. Place buy orders at each level with doubling amounts
  3. Take profit when price returns to Fib 0 (candle top)
  4. Stop loss below Fib 1.678

Levels & amounts ($100 total capital):
  0.382  → buy $0.78
  0.500  → buy $1.56
  0.618  → buy $3.13
  0.650  → buy $6.25
  0.786  → buy $12.50
  1.000  → buy $25.00
  1.272  → buy $50.00
  1.678  → buy (remaining)

Take Profit: Fib 0.0 (top of red candle)
Stop Loss: below Fib 1.678 (2x candle range below bottom)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("trade4me")


# Fib levels and corresponding % of total capital
FIB_LEVELS = [
    (0.382, 0.0078125),   # 0.78%  = $0.78 on $100
    (0.500, 0.015625),    # 1.56%
    (0.618, 0.03125),     # 3.13%
    (0.650, 0.0625),      # 6.25%
    (0.786, 0.125),       # 12.5%
    (1.000, 0.25),        # 25%
    (1.272, 0.50),        # 50%
]
# Last level gets remaining capital (not in list, handled separately)
FIB_LAST_LEVEL = 1.678


@dataclass
class FibOrder:
    fib_level: float
    price: float
    amount_usdt: float
    qty: float = 0.0
    filled: bool = False
    fill_price: float = 0.0
    fill_time: str = ""


@dataclass
class FibSession:
    """One Fibonacci Martingale session triggered by a red candle."""
    candle_high: float
    candle_low: float
    candle_range: float
    orders: list = field(default_factory=list)
    take_profit: float = 0.0
    stop_loss: float = 0.0
    active: bool = True
    total_invested: float = 0.0
    total_qty: float = 0.0
    avg_entry: float = 0.0
    pnl: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def filled_count(self) -> int:
        return sum(1 for o in self.orders if o.filled)

    @property
    def is_complete(self) -> bool:
        return not self.active


class FibMartingaleStrategy:
    def __init__(self, config: dict = None):
        config = config or {}
        self.name = "fib_martingale"
        self.total_capital = config.get("total_capital", 100.0)
        self.tp_fib = config.get("tp_fib", 0.0)
        self.sl_margin_pct = config.get("sl_margin_pct", 0.5)
        self.min_candle_range_pct = config.get("min_candle_range_pct", 0.05)
        self.timeframes = config.get("timeframes", ["15m", "5m", "1m"])

        # Capital split across timeframes
        self.capital_per_tf = self.total_capital / len(self.timeframes)

        # Independent session per timeframe
        self.sessions: list[FibSession] = []
        self.active_sessions: dict[str, FibSession | None] = {tf: None for tf in self.timeframes}

    @property
    def active_session(self):
        """Backward compat — return first active session."""
        for s in self.active_sessions.values():
            if s and s.active:
                return s
        return None

    def calculate_fib_price(self, high: float, low: float, level: float) -> float:
        """
        Fib 0 = high (top), Fib 1 = low (bottom)
        Levels > 1 = extensions below the candle
        """
        return high - (high - low) * level

    def detect_red_candle(self, df) -> dict | None:
        """Detect the latest 15min red candle."""
        if len(df) < 2:
            return None
        last = df.iloc[-1]
        if last["close"] < last["open"]:  # Red candle
            range_pct = abs(last["high"] - last["low"]) / last["high"] * 100
            if range_pct >= self.min_candle_range_pct:
                return {
                    "high": last["high"],
                    "low": last["low"],
                    "open": last["open"],
                    "close": last["close"],
                    "range": last["high"] - last["low"],
                    "range_pct": range_pct,
                }
        return None

    def create_session(self, candle_high: float, candle_low: float, timeframe: str = "15m") -> FibSession:
        """Create a new Fib Martingale session with orders at each level."""
        candle_range = candle_high - candle_low
        orders = []

        # Use capital allocated to this timeframe
        tf_capital = self.capital_per_tf
        spent = 0.0

        for fib_level, capital_pct in FIB_LEVELS:
            price = self.calculate_fib_price(candle_high, candle_low, fib_level)
            amount = tf_capital * capital_pct
            spent += amount
            orders.append(FibOrder(
                fib_level=fib_level,
                price=round(price, 2),
                amount_usdt=round(amount, 4),
            ))

        # Last level: remaining capital
        remaining = tf_capital - spent
        last_price = self.calculate_fib_price(candle_high, candle_low, FIB_LAST_LEVEL)
        orders.append(FibOrder(
            fib_level=FIB_LAST_LEVEL,
            price=round(last_price, 2),
            amount_usdt=round(remaining, 4),
        ))

        # Take profit = top of candle (Fib 0)
        tp = candle_high

        # Stop loss = below Fib 1.678
        sl = last_price * (1 - self.sl_margin_pct / 100)

        session = FibSession(
            candle_high=candle_high,
            candle_low=candle_low,
            candle_range=candle_range,
            orders=orders,
            take_profit=round(tp, 2),
            stop_loss=round(sl, 2),
        )

        self.active_sessions[timeframe] = session
        self.sessions.append(session)

        logger.info(
            f"FIB SESSION [{timeframe}]: high=${candle_high:,.2f} low=${candle_low:,.2f} "
            f"range=${candle_range:,.2f} TP=${tp:,.2f} SL=${sl:,.2f} "
            f"orders={len(orders)} capital=${tf_capital:.2f}"
        )
        return session

    def check_fills(self, current_price: float, timeframe: str = None) -> list[FibOrder]:
        """Check if any unfilled orders should be filled at current price."""
        filled_all = []
        tfs = [timeframe] if timeframe else self.timeframes
        for tf in tfs:
            session = self.active_sessions.get(tf)
            if not session or not session.active:
                continue
            filled_all.extend(self._check_fills_session(session, current_price, tf))
        return filled_all

    def _check_fills_session(self, session: "FibSession", current_price: float, tf: str) -> list[FibOrder]:
        filled = []
        for order in session.orders:
            if not order.filled and current_price <= order.price:
                order.filled = True
                order.fill_price = order.price  # Fill at the Fib level price, not current
                order.qty = order.amount_usdt / order.price
                order.fill_time = datetime.now(timezone.utc).isoformat()
                filled.append(order)

                session.total_invested += order.amount_usdt
                session.total_qty += order.qty
                if session.total_qty > 0:
                    session.avg_entry = (
                        session.total_invested / session.total_qty
                    )

                logger.info(
                    f"FIB FILL [{tf}]: Fib {order.fib_level} @ ${order.price:,.2f} "
                    f"${order.amount_usdt:.2f} | Total: ${session.total_invested:.2f} "
                    f"avg=${session.avg_entry:,.2f}"
                )

        return filled

    def check_exit(self, current_price: float) -> list[dict]:
        """Check TP/SL on all active sessions. Returns list of exits."""
        exits = []
        for tf in self.timeframes:
            session = self.active_sessions.get(tf)
            if not session or not session.active or session.filled_count == 0:
                continue

            result = None
            if current_price >= session.take_profit:
                pnl = (current_price - session.avg_entry) * session.total_qty
                result = {"reason": "TAKE PROFIT", "tf": tf}
            elif current_price <= session.stop_loss:
                pnl = (current_price - session.avg_entry) * session.total_qty
                result = {"reason": "STOP LOSS", "tf": tf}

            if result:
                session.pnl = pnl
                session.active = False
                self.active_sessions[tf] = None
                result.update({
                    "exit_price": current_price,
                    "pnl": pnl,
                    "invested": session.total_invested,
                    "avg_entry": session.avg_entry,
                    "fills": session.filled_count,
                })
                exits.append(result)

        return exits

    def get_status(self, current_price: float) -> dict:
        """Get status of all active sessions."""
        active_tfs = {}
        for tf in self.timeframes:
            s = self.active_sessions.get(tf)
            if not s or not s.active:
                continue
            upnl = (current_price - s.avg_entry) * s.total_qty if s.total_qty > 0 else 0
            active_tfs[tf] = {
                "high": s.candle_high,
                "low": s.candle_low,
                "tp": s.take_profit,
                "sl": s.stop_loss,
                "fills": s.filled_count,
                "total_orders": len(s.orders),
                "invested": s.total_invested,
                "avg_entry": s.avg_entry,
                "unrealized_pnl": upnl,
            }
        return {"active": len(active_tfs) > 0, "sessions": active_tfs}

    @property
    def total_pnl(self) -> float:
        return sum(s.pnl for s in self.sessions)

    @property
    def stats(self) -> dict:
        completed = [s for s in self.sessions if not s.active]
        wins = [s for s in completed if s.pnl > 0]
        losses = [s for s in completed if s.pnl <= 0]
        return {
            "total_sessions": len(self.sessions),
            "completed": len(completed),
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl": self.total_pnl,
            "win_rate": len(wins) / len(completed) * 100 if completed else 0,
        }
