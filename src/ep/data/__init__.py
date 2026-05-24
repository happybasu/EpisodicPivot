"""Data layer.

Houses the abstract ``DataProvider`` interface and concrete provider
implementations (FMP first; Polygon / Alpaca SIP later via config swap).
Also contains pure derived calculations (ADR, average volume, VWAP, SMA,
gap %) used by every later layer. Strategy code must depend on this package,
never on a specific provider SDK.
"""

from __future__ import annotations

from ep.config import Config, load_config
from ep.data.fmp import FMPProvider
from ep.data.provider import DataProvider

__all__ = ["DataProvider", "FMPProvider", "get_provider"]


def get_provider(config: Config | None = None) -> DataProvider:
    """Return the configured ``DataProvider`` instance.

    Reads the provider name from ``config.data.provider``. This indirection
    is the contract: strategy code never imports a concrete provider — it
    receives a ``DataProvider`` and the swap happens here.
    """
    cfg = config or load_config()
    name = cfg.data.provider
    if name == "fmp":
        return FMPProvider()
    raise ValueError(f"Unknown data provider: {name!r}")
