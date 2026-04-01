"""
CSVLogger — Thread-safe CSV logging for trades, performance, and arb scans.
"""

import csv
import threading
from pathlib import Path
from datetime import datetime, timezone


class CSVLogger:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self._lock = threading.Lock()

    def _append(self, filename: str, headers: list[str], row: dict):
        filepath = self.data_dir / filename
        file_exists = filepath.exists()
        with self._lock:
            with open(filepath, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)

    def log_trade(self, data: dict):
        headers = [
            "timestamp", "symbol", "side", "price", "amount",
            "pnl", "pnl_pct", "strategy", "mode",
        ]
        data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._append("trades.csv", headers, data)

    def log_performance(self, data: dict):
        headers = [
            "timestamp", "capital", "total_pnl", "open_positions",
            "total_trades", "win_rate", "drawdown_pct",
        ]
        data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._append("performance.csv", headers, data)

    def log_arb_scan(self, data: dict):
        headers = [
            "timestamp", "symbol", "buy_exchange", "buy_price",
            "sell_exchange", "sell_price", "spread_pct", "net_spread_pct",
            "num_exchanges",
        ]
        data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._append("arb_scans.csv", headers, data)
