"""
TRADE4ME-CEX — BTC/USDT Scalping Machine

Multi-timeframe: 15m (direction) → 5m (confirm) → 1m (entry)
Indicators: Stoch RSI, Williams %R, MFI, CRSI, RSI+SMA, BB %B, MACD
Double direction: LONG and SHORT
1 crypto: BTC/USDT

Usage:
    python scalper.py                 # Paper trading
    python scalper.py --live          # Live trading (REAL money!)
    python scalper.py --backtest      # Backtest on historical data
"""

import sys
import os
import time
import logging
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.exchange.client import ExchangeClient
from src.data.fetcher import DataFetcher
from src.indicators.technical import add_all_indicators
from src.strategies.scalp_multi_tf import MultiTFScalpStrategy, Direction
from src.strategies.fib_martingale import FibMartingaleStrategy
from src.utils.logger import setup_logger, console

logger = logging.getLogger("trade4me")

# ══════════════════════════════════════════════════════════════
#   CONFIG
# ══════════════════════════════════════════════════════════════

SYMBOL          = "BTC/USDT"
TIMEFRAMES      = ["15m", "5m", "1m"]
CANDLE_LIMIT    = 200
SCAN_INTERVAL   = 30        # seconds between scans
POSITION_PCT    = 5.0        # % of capital per trade
PAPER_CAPITAL   = 10000.0

# Strategy config
STRATEGY_CONFIG = {
    "stoch_oversold": 20,
    "stoch_overbought": 80,
    "wr_buy_threshold": -50,
    "wr_oversold": -80,
    "wr_overbought": -20,
    "mfi_oversold": 20,
    "mfi_overbought": 80,
    "crsi_buy": 40,
    "crsi_sell": 60,
    "sl_pct": 0.3,           # 0.3% stop loss
    "tp_pct": 0.6,           # 0.6% take profit (2:1 R/R)
    "min_agree": 4,           # 4/7 indicators must agree
}

# Fib Martingale config
FIB_CONFIG = {
    "total_capital": 100.0,
    "tp_fib": 0.0,
    "sl_margin_pct": 0.5,
    "min_candle_range_pct": 0.05,
}


# ══════════════════════════════════════════════════════════════
#   DISPLAY
# ══════════════════════════════════════════════════════════════

def print_banner(mode: str, capital: float):
    console.print("""[bold cyan]
 ╔════════════════════════════════════════════════════╗
 ║   TRADE4ME — BTC/USDT SCALPING MACHINE            ║
 ║   15m → 5m → 1m | LONG & SHORT | 7 Indicators     ║
 ╚════════════════════════════════════════════════════╝[/bold cyan]""")
    mode_str = "[yellow]PAPER[/yellow]" if mode == "paper" else "[red]LIVE[/red]"
    console.print(f"  Mode: {mode_str} | Capital: [bold]${capital:,.2f}[/bold]")
    console.print(f"  Symbol: [bold]{SYMBOL}[/bold] | Scan: {SCAN_INTERVAL}s")
    console.print(f"  SL: {STRATEGY_CONFIG['sl_pct']}% | TP: {STRATEGY_CONFIG['tp_pct']}% | Min agree: {STRATEGY_CONFIG['min_agree']}/7")
    console.print()


def print_signal(signal, scan_count: int):
    now = datetime.now().strftime("%H:%M:%S")

    # Timeframe alignment display
    tf_colors = {
        Direction.LONG: "[green]LONG[/green]",
        Direction.SHORT: "[red]SHORT[/red]",
        Direction.NEUTRAL: "[yellow]----[/yellow]",
    }

    tf_15m = tf_colors[signal.tf_15m]
    tf_5m = tf_colors[signal.tf_5m]
    tf_1m = tf_colors[signal.tf_1m]

    # Indicator values for 1m (entry timeframe)
    ind = signal.indicators.get("1m", {})
    stoch = f"StRSI:{ind.get('stoch_k', 0):.0f}/{ind.get('stoch_d', 0):.0f}"
    wr = f"%R:{ind.get('williams_r', 0):.0f}"
    mfi_v = f"MFI:{ind.get('mfi', 0):.0f}"
    crsi_v = f"CRSI:{ind.get('crsi', 0):.0f}"
    rsi_v = f"RSI:{ind.get('rsi', 0):.0f}"
    bb_v = f"BB:{ind.get('bb_pct_b', 0):.2f}"
    bull = ind.get("bull_score", 0)
    bear = ind.get("bear_score", 0)

    # RSI vs SMA for each TF
    rsi_tf = ""
    for tf_key in ["15m", "5m", "1m"]:
        tf_ind = signal.indicators.get(tf_key, {})
        r = tf_ind.get("rsi", 50)
        s = tf_ind.get("rsi_sma", 50)
        if r > s:
            rsi_tf += "[green]↑[/green]"
        elif r < s:
            rsi_tf += "[red]↓[/red]"
        else:
            rsi_tf += "[yellow]-[/yellow]"

    # Main line
    console.print(
        f"  [{now}] #{scan_count} | 15m:{tf_15m} 5m:{tf_5m} 1m:{tf_1m} | RSI:{rsi_tf} | "
        f"{stoch} {wr} {mfi_v} {crsi_v} {rsi_v} {bb_v} | "
        f"[green]B:{bull}[/green]/[red]S:{bear}[/red]",
        highlight=False,
    )

    # Trade signal
    if signal.direction != Direction.NEUTRAL:
        dir_style = "green" if signal.direction == Direction.LONG else "red"
        console.print(
            f"  [bold {dir_style}]{'═' * 50}[/bold {dir_style}]",
            highlight=False,
        )
        console.print(
            f"  [bold {dir_style}]  {signal.direction.value} @ ${signal.entry_price:,.2f} "
            f"| SL: ${signal.stop_loss:,.2f} | TP: ${signal.take_profit:,.2f} "
            f"| Strength: {signal.strength:.0%}[/bold {dir_style}]",
            highlight=False,
        )
        console.print(
            f"  [bold {dir_style}]  {signal.reason}[/bold {dir_style}]",
            highlight=False,
        )
        console.print(
            f"  [bold {dir_style}]{'═' * 50}[/bold {dir_style}]",
            highlight=False,
        )


def print_status(capital: float, position: dict, stats: dict, mode: str):
    console.print(f"\n  [cyan]{'─' * 55}[/cyan]")
    pnl = stats["total_pnl"]
    pnl_style = "green" if pnl >= 0 else "red"
    pos_str = f"{position['side']} @ ${position['entry']:,.2f}" if position else "None"
    console.print(
        f"  Capital: [bold]${capital:,.2f}[/bold] | "
        f"P&L: [{pnl_style}]${pnl:+,.2f}[/{pnl_style}] | "
        f"Trades: {stats['total']} (W:{stats['wins']} L:{stats['losses']}) | "
        f"Pos: {pos_str}"
    )
    console.print(f"  [cyan]{'─' * 55}[/cyan]\n")


# ══════════════════════════════════════════════════════════════
#   PAPER TRADING ENGINE
# ══════════════════════════════════════════════════════════════

class PaperTrader:
    def __init__(self, capital: float):
        self.capital = capital
        self.position = None  # {"side": "LONG"/"SHORT", "entry": price, "amount": qty, "sl": sl, "tp": tp}
        self.trades = []

    def open_position(self, direction: Direction, price: float, sl: float, tp: float):
        if self.position:
            return  # already in a trade
        amount_usdt = self.capital * (POSITION_PCT / 100)
        qty = amount_usdt / price
        self.position = {
            "side": direction.value,
            "entry": price,
            "amount": qty,
            "usdt": amount_usdt,
            "sl": sl,
            "tp": tp,
        }
        console.print(f"  [bold]OPEN {direction.value}[/bold] {qty:.6f} BTC @ ${price:,.2f} (${amount_usdt:,.2f})")

    def check_exit(self, current_price: float):
        if not self.position:
            return
        pos = self.position
        pnl = 0

        if pos["side"] == "LONG":
            if current_price <= pos["sl"]:
                pnl = (pos["sl"] - pos["entry"]) * pos["amount"]
                self._close("SL HIT", pos["sl"], pnl)
            elif current_price >= pos["tp"]:
                pnl = (pos["tp"] - pos["entry"]) * pos["amount"]
                self._close("TP HIT", pos["tp"], pnl)
        elif pos["side"] == "SHORT":
            if current_price >= pos["sl"]:
                pnl = (pos["entry"] - pos["sl"]) * pos["amount"]
                self._close("SL HIT", pos["sl"], pnl)
            elif current_price <= pos["tp"]:
                pnl = (pos["entry"] - pos["tp"]) * pos["amount"]
                self._close("TP HIT", pos["tp"], pnl)

    def close_on_signal(self, new_direction: Direction, price: float):
        """Close position if signal reverses."""
        if not self.position:
            return
        if self.position["side"] == "LONG" and new_direction == Direction.SHORT:
            pnl = (price - self.position["entry"]) * self.position["amount"]
            self._close("REVERSE → SHORT", price, pnl)
        elif self.position["side"] == "SHORT" and new_direction == Direction.LONG:
            pnl = (self.position["entry"] - price) * self.position["amount"]
            self._close("REVERSE → LONG", price, pnl)

    def _close(self, reason: str, exit_price: float, pnl: float):
        self.capital += pnl
        pnl_style = "green" if pnl >= 0 else "red"
        console.print(
            f"  [bold]CLOSE[/bold] {self.position['side']} @ ${exit_price:,.2f} | "
            f"[{pnl_style}]P&L: ${pnl:+,.2f}[/{pnl_style}] | {reason}"
        )
        self.trades.append({
            "side": self.position["side"],
            "entry": self.position["entry"],
            "exit": exit_price,
            "pnl": pnl,
            "reason": reason,
            "time": datetime.now(timezone.utc).isoformat(),
        })
        self.position = None

    @property
    def stats(self) -> dict:
        wins = [t for t in self.trades if t["pnl"] > 0]
        losses = [t for t in self.trades if t["pnl"] <= 0]
        return {
            "total": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl": sum(t["pnl"] for t in self.trades),
            "win_rate": len(wins) / len(self.trades) * 100 if self.trades else 0,
        }


# ══════════════════════════════════════════════════════════════
#   MAIN
# ══════════════════════════════════════════════════════════════

def run_scalper(live: bool = False):
    setup_logger("trade4me", "INFO")

    exchange_name = os.getenv("EXCHANGE_NAME", "binance")
    client = ExchangeClient(
        exchange_name=exchange_name,
        api_key=os.getenv("EXCHANGE_API_KEY"),
        api_secret=os.getenv("EXCHANGE_API_SECRET"),
        password=os.getenv("EXCHANGE_PASSWORD"),  # KuCoin passphrase
        sandbox=not live,
    )
    fetcher = DataFetcher(client)
    strategy = MultiTFScalpStrategy(STRATEGY_CONFIG)
    fib = FibMartingaleStrategy(FIB_CONFIG)
    trader = PaperTrader(PAPER_CAPITAL)

    mode = "live" if live else "paper"
    print_banner(mode, trader.capital)

    scan_count = 0
    start_time = time.time()

    try:
        while True:
            scan_count += 1

            try:
                # Fetch all 3 timeframes
                dfs = {}
                for tf in TIMEFRAMES:
                    dfs[tf] = add_all_indicators(
                        fetcher.get_candles(SYMBOL, tf, CANDLE_LIMIT)
                    )

                current_price = dfs["1m"].iloc[-1]["close"]

                # Check SL/TP on existing position
                trader.check_exit(current_price)

                # Analyze
                signal = strategy.analyze(dfs["15m"], dfs["5m"], dfs["1m"])

                # Display
                print_signal(signal, scan_count)

                # Trade logic
                if signal.direction != Direction.NEUTRAL:
                    # Close opposite position if exists
                    trader.close_on_signal(signal.direction, current_price)

                    # Open new position
                    if not trader.position:
                        trader.open_position(
                            signal.direction,
                            signal.entry_price,
                            signal.stop_loss,
                            signal.take_profit,
                        )

                # ── FIB MARTINGALE — scan all 3 TF ────────────
                for tf in TIMEFRAMES:
                    if fib.active_sessions.get(tf) is not None:
                        continue  # already has active session on this TF
                    red_candle = fib.detect_red_candle(dfs[tf])
                    if red_candle:
                        session = fib.create_session(red_candle["high"], red_candle["low"], tf)
                        console.print(
                            f"\n  [bold magenta]FIB [{tf}][/bold magenta] "
                            f"Red candle: ${red_candle['high']:,.2f} -> ${red_candle['low']:,.2f} "
                            f"(range: {red_candle['range_pct']:.2f}%) "
                            f"capital: ${fib.capital_per_tf:.2f}"
                        )
                        for o in session.orders:
                            console.print(
                                f"    Fib {o.fib_level:.3f} -> ${o.price:,.2f} -> buy ${o.amount_usdt:.2f}",
                                highlight=False,
                            )
                        console.print(
                            f"    TP: [green]${session.take_profit:,.2f}[/green] | "
                            f"SL: [red]${session.stop_loss:,.2f}[/red]\n"
                        )

                # Check fills on all active sessions
                fills = fib.check_fills(current_price)
                for f_order in fills:
                    console.print(
                        f"  [bold magenta]FIB FILL[/bold magenta] "
                        f"Fib {f_order.fib_level:.3f} @ ${f_order.fill_price:,.2f} "
                        f"-> ${f_order.amount_usdt:.2f}"
                    )

                # Check TP/SL on all sessions
                exits = fib.check_exit(current_price)
                for exit_info in exits:
                    pnl_style = "green" if exit_info["pnl"] >= 0 else "red"
                    console.print(
                        f"\n  [bold magenta]FIB {exit_info['reason']} [{exit_info['tf']}][/bold magenta] "
                        f"@ ${exit_info['exit_price']:,.2f} | "
                        f"[{pnl_style}]P&L: ${exit_info['pnl']:+,.2f}[/{pnl_style}] | "
                        f"Invested: ${exit_info['invested']:.2f} | "
                        f"Fills: {exit_info['fills']}\n"
                    )

                # Show Fib status every 10 scans
                if scan_count % 10 == 0:
                    status = fib.get_status(current_price)
                    if status["active"]:
                        for tf, s in status["sessions"].items():
                            upnl = s["unrealized_pnl"]
                            upnl_style = "green" if upnl >= 0 else "red"
                            console.print(
                                f"  [magenta]FIB [{tf}]: {s['fills']}/{s['total_orders']} fills | "
                                f"${s['invested']:.2f} | avg ${s['avg_entry']:,.2f} | "
                                f"uP&L: [{upnl_style}]${upnl:+,.2f}[/{upnl_style}][/magenta]"
                            )

                # Status every 10 scans
                if scan_count % 10 == 0:
                    print_status(
                        trader.capital,
                        trader.position,
                        trader.stats,
                        mode,
                    )
                    # Fib stats
                    fib_stats = fib.stats
                    if fib_stats["total_sessions"] > 0:
                        console.print(
                            f"  [magenta]FIB: Sessions:{fib_stats['total_sessions']} "
                            f"W:{fib_stats['wins']} L:{fib_stats['losses']} "
                            f"P&L: ${fib_stats['total_pnl']:+,.2f}[/magenta]\n"
                        )

            except Exception as e:
                logger.error(f"Scan error: {e}")

            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        console.print("\n[yellow]Bot stopped.[/yellow]")
        print_status(trader.capital, trader.position, trader.stats, mode)


def run_backtest():
    """Quick backtest on historical 1m data."""
    setup_logger("trade4me", "WARNING")

    client = ExchangeClient(exchange_name="binance", sandbox=False)
    fetcher = DataFetcher(client)
    strategy = MultiTFScalpStrategy(STRATEGY_CONFIG)

    console.print("[cyan]Fetching historical data for backtest...[/cyan]")
    df_15m = add_all_indicators(fetcher.get_candles(SYMBOL, "15m", 500))
    df_5m = add_all_indicators(fetcher.get_candles(SYMBOL, "5m", 500))
    df_1m = add_all_indicators(fetcher.get_candles(SYMBOL, "1m", 500))

    console.print(f"Data: 15m={len(df_15m)} 5m={len(df_5m)} 1m={len(df_1m)} candles\n")

    trader = PaperTrader(PAPER_CAPITAL)
    signals = 0

    # Walk through 1m candles
    for i in range(100, len(df_1m)):
        window_1m = df_1m.iloc[:i + 1]
        # Map 1m index to approximate 5m and 15m windows
        idx_5m = min(i // 5, len(df_5m) - 1)
        idx_15m = min(i // 15, len(df_15m) - 1)
        window_5m = df_5m.iloc[:idx_5m + 1]
        window_15m = df_15m.iloc[:idx_15m + 1]

        if len(window_5m) < 50 or len(window_15m) < 50:
            continue

        price = df_1m.iloc[i]["close"]
        trader.check_exit(price)

        signal = strategy.analyze(window_15m, window_5m, window_1m)

        if signal.direction != Direction.NEUTRAL:
            signals += 1
            trader.close_on_signal(signal.direction, price)
            if not trader.position:
                trader.open_position(signal.direction, price, signal.stop_loss, signal.take_profit)

    # Close final position
    if trader.position:
        final_price = df_1m.iloc[-1]["close"]
        side = trader.position["side"]
        pnl = (final_price - trader.position["entry"]) * trader.position["amount"] if side == "LONG" else (trader.position["entry"] - final_price) * trader.position["amount"]
        trader._close("END", final_price, pnl)

    stats = trader.stats
    console.print(f"\n[bold cyan]BACKTEST RESULTS[/bold cyan]")
    console.print(f"  Signals detected: {signals}")
    console.print(f"  Trades: {stats['total']} (W:{stats['wins']} L:{stats['losses']})")
    console.print(f"  Win Rate: {stats['win_rate']:.1f}%")
    pnl_style = "green" if stats['total_pnl'] >= 0 else "red"
    console.print(f"  P&L: [{pnl_style}]${stats['total_pnl']:+,.2f}[/{pnl_style}]")
    console.print(f"  Capital: ${trader.capital:,.2f} (started: ${PAPER_CAPITAL:,.2f})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TRADE4ME BTC/USDT Scalper")
    parser.add_argument("--live", action="store_true", help="Live trading")
    parser.add_argument("--backtest", action="store_true", help="Run backtest")
    args = parser.parse_args()

    if args.backtest:
        run_backtest()
    else:
        run_scalper(live=args.live)
