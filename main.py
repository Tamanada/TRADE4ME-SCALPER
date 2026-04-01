"""
TRADE4ME-CEX — Entry point.

Usage:
    python main.py trade              # Paper trading (default)
    python main.py trade --live       # Live trading (REAL money!)
    python main.py scan               # Arbitrage scanner
    python main.py backtest           # Backtest strategies
"""

import argparse
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_trade(args):
    from src.bot import TradingBot
    from src.ui.terminal import TerminalUI

    bot = TradingBot(config_path=args.config)

    if args.live:
        ui = TerminalUI()
        if not ui.confirm_live_mode():
            print("Cancelled. Bot not started.")
            sys.exit(0)
        bot.paper_mode = False
        bot.order_manager.paper_mode = False

    bot.run()


def cmd_scan(args):
    from src.bot import TradingBot

    bot = TradingBot(config_path=args.config)
    bot.run_scan()


def cmd_backtest(args):
    from backtest.runner import run_backtest

    run_backtest(
        symbol=args.symbol,
        timeframe=args.timeframe,
        limit=args.limit,
        capital=args.capital,
        strategy=args.strategy,
        config_path=args.config,
    )


def main():
    parser = argparse.ArgumentParser(description="TRADE4ME-CEX — Super Trading Bot")
    parser.add_argument("--config", default="config/settings.yaml", help="Config file path")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # trade
    trade_parser = subparsers.add_parser("trade", help="Start trading bot")
    trade_parser.add_argument("--live", action="store_true", help="Live trading mode")

    # scan
    subparsers.add_parser("scan", help="Run arbitrage scanner")

    # backtest
    bt_parser = subparsers.add_parser("backtest", help="Backtest strategies")
    bt_parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    bt_parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    bt_parser.add_argument("--limit", type=int, default=500, help="Number of candles")
    bt_parser.add_argument("--capital", type=float, default=10000.0, help="Starting capital")
    bt_parser.add_argument("--strategy", default="all", help="Strategy name or 'all'")

    args = parser.parse_args()

    if args.command == "trade":
        cmd_trade(args)
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    else:
        # Default: paper trading
        args.live = False
        cmd_trade(args)


if __name__ == "__main__":
    main()
