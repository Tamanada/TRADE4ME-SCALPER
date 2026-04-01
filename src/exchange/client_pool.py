"""
MultiExchangeClientPool — Manages authenticated CCXT clients for arbitrage.
"""

import os
import logging
from src.exchange.client import ExchangeClient

logger = logging.getLogger("trade4me")


class MultiExchangeClientPool:
    PASSPHRASE_EXCHANGES = {"kucoin", "okx"}

    def __init__(self, exchanges_config: list[dict]):
        self.clients: dict[str, ExchangeClient] = {}
        self._init_clients(exchanges_config)

    def _init_clients(self, exchanges_config: list[dict]):
        for ex_config in exchanges_config:
            name = ex_config.get("name", "").lower()
            if not name:
                continue
            env_prefix = name.upper()
            api_key = os.getenv(f"{env_prefix}_API_KEY", "").strip()
            api_secret = os.getenv(f"{env_prefix}_API_SECRET", "").strip()
            if not api_key or not api_secret:
                logger.info(f"No API keys for {name} — skip")
                continue
            password = None
            if name in self.PASSPHRASE_EXCHANGES:
                password = os.getenv(f"{env_prefix}_PASSPHRASE", "").strip() or None
            sandbox = ex_config.get("sandbox", True)
            try:
                client = ExchangeClient(
                    exchange_name=name, api_key=api_key,
                    api_secret=api_secret, password=password, sandbox=sandbox,
                )
                self.clients[name] = client
                logger.info(f"Authenticated client: {name} (sandbox={sandbox})")
            except Exception as e:
                logger.warning(f"Failed to create client for {name}: {e}")

    def get_client(self, exchange_name: str) -> ExchangeClient | None:
        return self.clients.get(exchange_name.lower())

    def has_client(self, exchange_name: str) -> bool:
        return exchange_name.lower() in self.clients

    def get_configured_exchanges(self) -> list[str]:
        return list(self.clients.keys())
