"""
TradingBot — Main orchestrator: fetch -> analyze -> risk -> execute -> log.
"""

import time
import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv
import os

from src.exchange.client import ExchangeClient
from src.data.fetcher import DataFetcher
from src.data.csv_logger import CSVLogger
from src.indicators.technical import add_all_indicators
from src.strategies.base import Signal
from src.strategies.scalp_ema import ScalpEMAStrategy
from src.strategies.scalp_rsi import ScalpRSIStrategy
from src.strategies.scalp_momentum import ScalpMomentumStrategy
from src.execution.order_manager import OrderManager
from src.execution.position_tracker import PositionTracker
from src.risk.manager import RiskManager
from src.ui.terminal import TerminalUI
from src.utils.logger import setup_logger, log_signal

logger = logging.getLogger("trade4me")


class TradingBot:
    def __init__(self, config_path: str = "config/settings.yaml"):
        load_dotenv()

        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        with open(Path("config/strategies.yaml")) as f:
            self.strat_config = yaml.safe_load(f)

        log_level = self.config.get("bot", {}).get("log_level", "INFO")
        setup_logger("trade4me", log_level)

        self.paper_mode = self.config.get("trading", {}).get("mode", "paper") == "paper"

        self.client = ExchangeClient(
            exchange_name=os.getenv("EXCHANGE_NAME", self.config["exchange"]["name"]),
            api_key=os.getenv("EXCHANGE_API_KEY"),
            api_secret=os.getenv("EXCHANGE_API_SECRET"),
            sandbox=self.config["exchange"].get("sandbox", True),
        )

        self.fetcher = DataFetcher(self.client)
        self.order_manager = OrderManager(self.client, paper_mode=self.paper_mode)
        self.position_tracker = PositionTracker()
        self.risk_manager = RiskManager(self.config.get("risk", {}))
        self.csv_logger = CSVLogger() if self.config.get("bot", {}).get("csv_logging", True) else None
        self.ui = TerminalUI()

        self.strategies = self._load_strategies()

        self.symbols = self.config.get("trading", {}).get("symbols", ["BTC/USDT"])
        self.timeframe = self.config.get("trading", {}).get("timeframe", "5m")
        self.candle_limit = self.config.get("trading", {}).get("candle_limit", 100)
        self.loop_interval = self.config.get("bot", {}).get("loop_interval_sec", 10)

        self.running = False
        self.paper_capital = self.config.get("bot", {}).get("paper_capital", 10000.0)

        # Arbitrage components (lazy loaded)
        self._arb_scanner = None
        self._arb_executor = None
        self._client_pool = None

        # Grid strategy (lazy loaded)
        self._grid_strategy = None

        # ML strategy (lazy loaded)
        self._ml_strategy = None

    def _load_strategies(self) -> list:
        strategies = []
        if self.strat_config.get("scalp_ema", {}).get("enabled", False):
            strategies.append(ScalpEMAStrategy(self.strat_config["scalp_ema"]))
            logger.info("Strategy loaded: Scalp EMA")
        if self.strat_config.get("scalp_rsi", {}).get("enabled", False):
            strategies.append(ScalpRSIStrategy(self.strat_config["scalp_rsi"]))
            logger.info("Strategy loaded: Scalp RSI")
        if self.strat_config.get("scalp_momentum", {}).get("enabled", False):
            strategies.append(ScalpMomentumStrategy(self.strat_config["scalp_momentum"]))
            logger.info("Strategy loaded: Scalp Momentum")
        if self.strat_config.get("ml_predictor", {}).get("enabled", False):
            try:
                from src.strategies.ml_predictor import MLPredictorStrategy
                self._ml_strategy = MLPredictorStrategy(
                    self.strat_config["ml_predictor"],
                    self.config.get("ml", {}),
                )
                strategies.append(self._ml_strategy)
                logger.info("Strategy loaded: ML Predictor")
            except Exception as e:
                logger.warning(f"ML strategy unavailable: {e}")
        if not strategies:
            logger.warning("No strategies enabled!")
        return strategies

    def _init_arbitrage(self):
        if self._arb_scanner is not None:
            return
        if not self.strat_config.get("arbitrage", {}).get("enabled", False):
            return
        try:
            from src.exchange.multi_scanner import MultiExchangeScanner
            from src.exchange.client_pool import MultiExchangeClientPool
            from src.execution.arb_executor import ArbitrageExecutor

            self._arb_scanner = MultiExchangeScanner()
            self._client_pool = MultiExchangeClientPool(
                self.config.get("exchanges", [])
            )
            self._arb_executor = ArbitrageExecutor(
                self._client_pool, self.config.get("arbitrage", {})
            )
            logger.info("Arbitrage system initialized")
        except Exception as e:
            logger.warning(f"Arbitrage init failed: {e}")

    def _init_grid(self):
        if self._grid_strategy is not None:
            return
        if not self.strat_config.get("grid", {}).get("enabled", False):
            return
        try:
            from src.strategies.grid import GridStrategy
            grid_config = self.config.get("grid", {})
            self._grid_strategy = GridStrategy(grid_config)
            logger.info("Grid strategy initialized")
        except Exception as e:
            logger.warning(f"Grid init failed: {e}")

    def _get_capital(self) -> float:
        if self.paper_mode:
            return self.paper_capital
        balance = self.client.get_balance("USDT")
        return balance["free"]

    def _process_symbol(self, symbol: str):
        try:
            df = self.fetcher.get_candles(symbol, self.timeframe, self.candle_limit)
        except Exception as e:
            logger.error(f"Fetch error {symbol}: {e}")
            return

        df = add_all_indicators(df)

        # Check SL/TP/trailing for existing positions
        if self.position_tracker.has_position(symbol):
            current_price = df.iloc[-1]["close"]
            position = self.position_tracker.get_position(symbol)

            # Update trailing stop
            trail_pct = self.risk_manager.trailing_stop_pct
            if trail_pct > 0:
                position.update_trailing_stop(current_price, trail_pct)

            exit_reason = self.position_tracker.check_exits(symbol, current_price)
            if exit_reason:
                pnl = self.position_tracker.close_position(position, current_price)
                self.order_manager.place_market_order(symbol, "sell", position.amount, current_price)
                if self.paper_mode:
                    self.paper_capital += pnl
                self.risk_manager.record_pnl(pnl)
                if self.csv_logger:
                    self.csv_logger.log_trade({
                        "symbol": symbol, "side": "sell", "price": current_price,
                        "amount": position.amount, "pnl": pnl,
                        "pnl_pct": position.unrealized_pnl_pct(current_price),
                        "strategy": exit_reason, "mode": "paper" if self.paper_mode else "live",
                    })
                return

        # Analyze with each strategy
        for strategy in self.strategies:
            signal = strategy.analyze(df, symbol)
            if signal.signal == Signal.HOLD:
                continue

            log_signal(signal.signal.value, symbol, signal.reason)

            if signal.signal == Signal.BUY and not self.position_tracker.has_position(symbol):
                capital = self._get_capital()
                trade_params = self.risk_manager.validate_trade(
                    capital, signal.price, len(self.position_tracker.open_positions)
                )
                if trade_params is None:
                    continue

                order = self.order_manager.place_market_order(
                    symbol, "buy", trade_params["amount"], signal.price
                )
                if order.status == "filled":
                    self.position_tracker.open_position(
                        symbol=symbol, side="long",
                        entry_price=order.filled_price,
                        amount=trade_params["amount"],
                        stop_loss=trade_params["stop_loss"],
                        take_profit=trade_params["take_profit"],
                    )
                    if self.paper_mode:
                        self.paper_capital -= trade_params["position_value_usdt"]
                    if self.csv_logger:
                        self.csv_logger.log_trade({
                            "symbol": symbol, "side": "buy", "price": order.filled_price,
                            "amount": trade_params["amount"], "pnl": 0,
                            "pnl_pct": 0, "strategy": strategy.name,
                            "mode": "paper" if self.paper_mode else "live",
                        })
                break

            elif signal.signal == Signal.SELL and self.position_tracker.has_position(symbol):
                position = self.position_tracker.get_position(symbol)
                pnl = self.position_tracker.close_position(position, signal.price)
                self.order_manager.place_market_order(symbol, "sell", position.amount, signal.price)
                if self.paper_mode:
                    self.paper_capital += pnl
                self.risk_manager.record_pnl(pnl)
                if self.csv_logger:
                    self.csv_logger.log_trade({
                        "symbol": symbol, "side": "sell", "price": signal.price,
                        "amount": position.amount, "pnl": pnl,
                        "pnl_pct": position.unrealized_pnl_pct(signal.price),
                        "strategy": strategy.name,
                        "mode": "paper" if self.paper_mode else "live",
                    })
                break

    def _process_arbitrage(self):
        if self._arb_scanner is None:
            return
        try:
            scan_top_n = self.strat_config.get("arbitrage", {}).get("scan_top_n", 50)
            opportunities = self._arb_scanner.scan_all(max_tokens=scan_top_n)
            if opportunities:
                self.ui.print_arb_table(opportunities)
                if self.csv_logger:
                    for opp in opportunities[:10]:
                        self.csv_logger.log_arb_scan({
                            "symbol": opp.symbol,
                            "buy_exchange": opp.buy_exchange,
                            "buy_price": opp.buy_price,
                            "sell_exchange": opp.sell_exchange,
                            "sell_price": opp.sell_price,
                            "spread_pct": opp.spread_pct,
                            "net_spread_pct": opp.net_spread_pct,
                            "num_exchanges": opp.num_exchanges,
                        })

                # Auto-execute if configured
                auto_cfg = self.config.get("arbitrage", {}).get("auto_exec", {})
                if auto_cfg.get("enabled", False):
                    min_net = auto_cfg.get("min_net_spread_pct", 1.0)
                    max_exec = auto_cfg.get("max_per_cycle", 3)
                    executed = 0
                    for opp in opportunities:
                        if executed >= max_exec:
                            break
                        if opp.net_spread_pct >= min_net:
                            self._arb_executor.execute(
                                symbol=opp.symbol,
                                buy_exchange=opp.buy_exchange,
                                buy_price=opp.buy_price,
                                sell_exchange=opp.sell_exchange,
                                sell_price=opp.sell_price,
                                spread_pct=opp.spread_pct,
                                buy_fee_pct=opp.buy_fee_pct,
                                sell_fee_pct=opp.sell_fee_pct,
                            )
                            executed += 1
        except Exception as e:
            logger.error(f"Arbitrage scan error: {e}")

    def _process_grid(self):
        if self._grid_strategy is None:
            return
        try:
            grid_symbol = self.config.get("grid", {}).get("symbol", "BTC/USDT")
            df = self.fetcher.get_candles(grid_symbol, self.timeframe, 10)
            current_price = df.iloc[-1]["close"]
            signal = self._grid_strategy.analyze(df, grid_symbol)

            if signal.signal == Signal.BUY:
                amount = self.config.get("grid", {}).get("amount_per_grid", 20) / current_price
                self.order_manager.place_limit_order(grid_symbol, "buy", amount, signal.price)
                self._grid_strategy.mark_filled(signal.price, "buy")
            elif signal.signal == Signal.SELL:
                amount = self.config.get("grid", {}).get("amount_per_grid", 20) / current_price
                self.order_manager.place_limit_order(grid_symbol, "sell", amount, signal.price)
                self._grid_strategy.mark_filled(signal.price, "sell")
        except Exception as e:
            logger.error(f"Grid error: {e}")

    def _print_status(self):
        stats = self.position_tracker.stats
        capital = self._get_capital()
        mode = "paper" if self.paper_mode else "live"
        self.ui.print_status(capital, stats, mode)
        if self.csv_logger:
            self.csv_logger.log_performance({
                "capital": capital,
                "total_pnl": stats["total_pnl"],
                "open_positions": stats["open_positions"],
                "total_trades": stats["total_trades"],
                "win_rate": stats["win_rate"],
                "drawdown_pct": 0,
            })

    def run(self):
        self.running = True
        self.risk_manager.set_capital(self._get_capital())

        mode = "paper" if self.paper_mode else "live"
        self.ui.print_banner(
            mode=mode,
            exchange=self.client.exchange_name,
            symbols=self.symbols,
            strategies=len(self.strategies),
            capital=self._get_capital(),
        )

        # Init optional systems
        self._init_arbitrage()
        self._init_grid()

        logger.info("Bot started!")

        try:
            cycle = 0
            while self.running:
                cycle += 1
                logger.debug(f"--- Cycle {cycle} ---")

                # Scalp + ML strategies
                for symbol in self.symbols:
                    self._process_symbol(symbol)

                # Grid trading
                self._process_grid()

                # Arbitrage (every 6 cycles to save API calls)
                if cycle % 6 == 0:
                    self._process_arbitrage()

                # Status every 6 cycles
                if cycle % 6 == 0:
                    self._print_status()

                # Drawdown check
                if self.risk_manager.check_drawdown(self._get_capital()):
                    self.ui.console.print("[bold red]BOT STOPPED — MAX DRAWDOWN REACHED[/bold red]")
                    self.stop()
                    break

                # Daily loss check
                if self.risk_manager.check_daily_loss():
                    self.ui.console.print("[bold red]BOT STOPPED — DAILY LOSS LIMIT[/bold red]")
                    self.stop()
                    break

                time.sleep(self.loop_interval)

        except KeyboardInterrupt:
            self.ui.console.print("\n[bold yellow]Bot stopping (Ctrl+C)...[/bold yellow]")
            self.stop()

    def run_scan(self):
        """Run arbitrage scanner once and display results."""
        self._init_arbitrage()
        if self._arb_scanner is None:
            logger.error("Arbitrage not configured. Enable it in strategies.yaml")
            return
        scan_top_n = self.strat_config.get("arbitrage", {}).get("scan_top_n", 50)
        opportunities = self._arb_scanner.scan_all(max_tokens=scan_top_n)
        self.ui.print_arb_table(opportunities)

    def stop(self):
        self.running = False
        self._print_status()
        logger.info("Bot stopped.")
