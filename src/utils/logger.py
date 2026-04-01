"""
Logger — Rich console + file logging.
"""

import logging
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

TRADE_THEME = Theme({
    "buy": "bold green",
    "sell": "bold red",
    "hold": "bold yellow",
    "profit": "bold green",
    "loss": "bold red",
    "info": "bold cyan",
})

console = Console(theme=TRADE_THEME)


def setup_logger(name: str = "trade4me", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    rich_handler = RichHandler(
        console=console, show_path=False, show_time=True, rich_tracebacks=True,
    )
    rich_handler.setLevel(logging.DEBUG)
    logger.addHandler(rich_handler)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "trade4me.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    ))
    logger.addHandler(file_handler)

    return logger


def log_trade(action: str, symbol: str, price: float, amount: float, **kwargs):
    style = "buy" if action.upper() == "BUY" else "sell"
    console.print(
        f"  [{style}]{action.upper()}[/{style}] {symbol} | "
        f"Prix: ${price:,.2f} | Qty: {amount:.6f}",
        highlight=False,
    )
    if "pnl" in kwargs:
        pnl = kwargs["pnl"]
        pnl_style = "profit" if pnl >= 0 else "loss"
        console.print(f"    P&L: [{pnl_style}]{pnl:+.2f} USDT[/{pnl_style}]", highlight=False)


def log_signal(signal: str, symbol: str, reason: str):
    style_map = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}
    style = style_map.get(signal.upper(), "info")
    console.print(f"  [{style}]{signal.upper()}[/{style}] {symbol} | {reason}", highlight=False)
