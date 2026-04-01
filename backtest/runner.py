"""
Backtest Runner — CLI entry point for backtesting strategies.
"""

import sys
import os
import yaml
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchange.client import ExchangeClient
from src.data.fetcher import DataFetcher
from src.strategies.scalp_ema import ScalpEMAStrategy
from src.strategies.scalp_rsi import ScalpRSIStrategy
from src.strategies.scalp_momentum import ScalpMomentumStrategy
from src.ui.terminal import TerminalUI
from src.utils.logger import setup_logger
from backtest.engine import BacktestEngine

logger = logging.getLogger("trade4me")


def run_backtest(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    limit: int = 500,
    capital: float = 10000.0,
    strategy: str = "all",
    config_path: str = "config/settings.yaml",
):
    setup_logger("trade4me", "INFO")
    ui = TerminalUI()

    with open(config_path) as f:
        config = yaml.safe_load(f)
    with open("config/strategies.yaml") as f:
        strat_config = yaml.safe_load(f)

    ui.console.print(f"\n[bold cyan]Fetching {limit} candles for {symbol} ({timeframe})...[/bold cyan]")

    client = ExchangeClient(
        exchange_name=config["exchange"]["name"],
        sandbox=False,  # Use real data for backtest
    )
    fetcher = DataFetcher(client)

    try:
        df = fetcher.get_candles(symbol, timeframe, limit)
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        return

    ui.console.print(f"[green]Got {len(df)} candles[/green]\n")

    # Build strategy list
    strategies = []
    if strategy in ("all", "scalp_ema"):
        strategies.append(ScalpEMAStrategy(strat_config.get("scalp_ema", {})))
    if strategy in ("all", "scalp_rsi"):
        strategies.append(ScalpRSIStrategy(strat_config.get("scalp_rsi", {})))
    if strategy in ("all", "scalp_momentum"):
        strategies.append(ScalpMomentumStrategy(strat_config.get("scalp_momentum", {})))

    if not strategies:
        logger.error(f"Unknown strategy: {strategy}")
        return

    engine = BacktestEngine(
        initial_capital=capital,
        risk_config=config.get("risk", {}),
    )

    for strat in strategies:
        ui.console.print(f"[bold]Running backtest: {strat.name}[/bold]")
        result = engine.run(strat, df, symbol, timeframe)
        ui.print_backtest_report(result)
        ui.console.print()
