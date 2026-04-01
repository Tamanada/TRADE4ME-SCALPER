"""
TerminalUI — Rich terminal interface for TRADE4ME-CEX.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text


console = Console()

BANNER = r"""
 _____ ____    _    ____  _____ _  _   __  __ _____        ____ _______  __
|_   _|  _ \  / \  |  _ \| ____| || | |  \/  | ____|      / ___| ____\ \/ /
  | | | |_) |/ _ \ | | | |  _| | || |_| |\/| |  _| _____ | |   |  _|  \  /
  | | |  _ </ ___ \| |_| | |___|__   _| |  | | |__|_____|| |___| |___ /  \
  |_| |_| \_/_/   \_|____/|_____|  |_| |_|  |_|_____|      \____|_____/_/\_\
"""


class TerminalUI:
    def __init__(self):
        self.console = console

    def print_banner(self, mode: str, exchange: str, symbols: list, strategies: int, capital: float):
        self.console.print(f"[bold cyan]{BANNER}[/bold cyan]")
        mode_str = "[bold yellow]PAPER TRADING[/bold yellow]" if mode == "paper" else "[bold red]LIVE TRADING[/bold red]"
        self.console.print(Panel.fit(
            f"  Mode: {mode_str}\n"
            f"  Exchange: [bold]{exchange}[/bold]\n"
            f"  Pairs: [bold]{', '.join(symbols)}[/bold]\n"
            f"  Strategies: [bold]{strategies}[/bold] active\n"
            f"  Capital: [bold]${capital:,.2f}[/bold]",
            title="[bold cyan]TRADE4ME-CEX[/bold cyan]",
            border_style="cyan",
        ))

    def print_status(self, capital: float, stats: dict, mode: str):
        table = Table(title="Bot Status", show_header=False, border_style="cyan", padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value", justify="right")

        mode_str = "PAPER" if mode == "paper" else "LIVE"
        pnl = stats.get("total_pnl", 0)
        pnl_style = "green" if pnl >= 0 else "red"

        table.add_row("Mode", mode_str)
        table.add_row("Capital", f"${capital:,.2f}")
        table.add_row("Total Trades", str(stats.get("total_trades", 0)))
        table.add_row("Win Rate", f"{stats.get('win_rate', 0):.1f}%")
        table.add_row("P&L", f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]")
        table.add_row("Open Positions", str(stats.get("open_positions", 0)))
        self.console.print(table)

    def print_signal(self, signal_value: str, symbol: str, reason: str):
        style_map = {"BUY": "bold green", "SELL": "bold red", "HOLD": "bold yellow"}
        style = style_map.get(signal_value, "bold white")
        self.console.print(f"  [{style}]{signal_value}[/{style}] {symbol} | {reason}")

    def print_trade(self, side: str, symbol: str, price: float, amount: float, pnl: float = None):
        style = "bold green" if side.upper() == "BUY" else "bold red"
        self.console.print(
            f"  [{style}]{side.upper()}[/{style}] {symbol} | "
            f"${price:,.2f} x {amount:.6f}"
        )
        if pnl is not None:
            pnl_style = "green" if pnl >= 0 else "red"
            self.console.print(f"    P&L: [{pnl_style}]{pnl:+.2f} USDT[/{pnl_style}]")

    def print_arb_table(self, opportunities: list):
        if not opportunities:
            self.console.print("[yellow]  No arbitrage opportunities found[/yellow]")
            return

        table = Table(title="Arbitrage Opportunities", border_style="cyan")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Symbol", style="bold")
        table.add_column("Buy", style="green")
        table.add_column("Buy $", justify="right")
        table.add_column("Sell", style="red")
        table.add_column("Sell $", justify="right")
        table.add_column("Spread %", justify="right")
        table.add_column("Net %", justify="right", style="bold")
        table.add_column("RSI", justify="right")
        table.add_column("Trend")
        table.add_column("Exch", justify="right", style="dim")

        for i, opp in enumerate(opportunities[:30], 1):
            net_style = "green" if opp.net_spread_pct > 0 else "red"
            rsi_str = f"{opp.rsi:.0f}" if opp.rsi else "-"
            trend_style = "green" if opp.ema_trend == "BULLISH" else "red" if opp.ema_trend == "BEARISH" else "white"

            table.add_row(
                str(i),
                opp.symbol,
                opp.buy_exchange,
                f"${opp.buy_price:,.4f}",
                opp.sell_exchange,
                f"${opp.sell_price:,.4f}",
                f"{opp.spread_pct:.3f}%",
                f"[{net_style}]{opp.net_spread_pct:.3f}%[/{net_style}]",
                rsi_str,
                f"[{trend_style}]{opp.ema_trend or '-'}[/{trend_style}]",
                str(opp.num_exchanges),
            )

        self.console.print(table)

    def print_grid_status(self, grid_levels: list, filled_buys: set, filled_sells: set, current_price: float):
        table = Table(title="Grid Status", border_style="cyan")
        table.add_column("Level", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Status")

        for level in sorted(grid_levels, reverse=True):
            price_str = f"${level:,.2f}"
            if level in filled_buys:
                status = "[green]BUY FILLED[/green]"
            elif level in filled_sells:
                status = "[red]SELL FILLED[/red]"
            elif abs(level - current_price) / current_price < 0.001:
                status = "[yellow]<-- CURRENT[/yellow]"
            else:
                status = "pending"
            table.add_row(str(grid_levels.index(level) + 1), price_str, status)

        self.console.print(table)

    def print_backtest_report(self, result):
        self.console.print()
        self.console.print(Panel.fit(
            f"[bold cyan]Backtest: {result.strategy_name}[/bold cyan]\n"
            f"Symbol: {result.symbol} | Timeframe: {result.timeframe}",
            border_style="cyan",
        ))

        table = Table(title="Performance", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        pnl_style = "green" if result.total_pnl >= 0 else "red"
        table.add_row("Total Trades", str(result.total_trades))
        table.add_row("Wins / Losses", f"{result.wins} / {result.losses}")
        table.add_row("Win Rate", f"{result.win_rate:.1f}%")
        table.add_row("P&L Total", f"[{pnl_style}]${result.total_pnl:+,.2f}[/{pnl_style}]")
        table.add_row("Avg Win", f"[green]${result.avg_win:+,.2f}[/green]")
        table.add_row("Avg Loss", f"[red]${result.avg_loss:+,.2f}[/red]")
        table.add_row("Profit Factor", f"{result.profit_factor:.2f}")
        table.add_row("Sharpe Ratio", f"{result.sharpe_ratio:.2f}")
        table.add_row("Max Drawdown", f"[red]{result.max_drawdown:.2f}%[/red]")
        self.console.print(table)

        if result.trades:
            trade_table = Table(title="Last 20 Trades", show_header=True, header_style="bold")
            trade_table.add_column("#", justify="right")
            trade_table.add_column("Entry $", justify="right")
            trade_table.add_column("Exit $", justify="right")
            trade_table.add_column("P&L", justify="right")
            trade_table.add_column("%", justify="right")
            trade_table.add_column("Reason")

            for i, trade in enumerate(result.trades[-20:], 1):
                style = "green" if trade.pnl > 0 else "red"
                trade_table.add_row(
                    str(i), f"${trade.entry_price:,.2f}", f"${trade.exit_price:,.2f}",
                    f"[{style}]${trade.pnl:+,.2f}[/{style}]",
                    f"[{style}]{trade.pnl_pct:+.2f}%[/{style}]",
                    trade.reason,
                )
            self.console.print(trade_table)

    def confirm_live_mode(self) -> bool:
        self.console.print("\n[bold red]" + "!" * 60)
        self.console.print("  WARNING: LIVE TRADING MODE")
        self.console.print("  You are about to trade with REAL money!")
        self.console.print("!" * 60 + "[/bold red]\n")
        confirm = input("Type 'YES I CONFIRM' to continue: ")
        return confirm == "YES I CONFIRM"
