"""Abstract data-provider interface.

Every strategy / scanner / backtest / execution module depends on this
interface, never on a concrete provider. The point: swapping FMP → Polygon
→ Alpaca SIP later is a single line change in ``config.yaml``, not a
code change. See CLAUDE.md for the hard constraint.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    import pandas as pd


IntradayInterval = Literal[5, 15, 30, 60]
"""Allowed intraday bar lengths in minutes."""


class PremarketQuote(BaseModel):
    """A single premarket quote.

    ``is_fallback`` is set when no clean premarket print existed near the
    requested time and the regular 9:30 open was returned instead. The
    scanner/backtester is expected to honour this flag (Phase 1.2).
    """

    symbol: str
    timestamp: datetime
    price: float
    is_fallback: bool = False


class NewsItem(BaseModel):
    """A single news article keyed to a symbol."""

    symbol: str
    timestamp: datetime
    headline: str
    body: str | None = None
    source: str | None = None
    url: str | None = None


class EarningsEvent(BaseModel):
    """A scheduled earnings release."""

    symbol: str
    when: datetime
    fiscal_period: str | None = None
    eps_estimate: float | None = None


class CompanyProfile(BaseModel):
    """Static company metadata returned by ``get_company_profile``."""

    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    shares_outstanding: float | None = None
    float_shares: float | None = None


class DataProvider(ABC):
    """Abstract market-data source.

    Concrete implementations live alongside this module
    (``FMPProvider`` first; ``PolygonProvider`` and ``AlpacaSipProvider``
    later). Strategy code receives a ``DataProvider`` — never a concrete
    class — so the v1 → v2 provider swap is purely configuration.
    """

    @abstractmethod
    def get_universe(self, as_of_date: date) -> list[str]:
        """Return US common-stock symbols tradable on ``as_of_date``.

        Must include symbols later delisted (historical-constituent and
        delisted-companies sources) so backtests are not survivorship-biased.
        Excludes ETFs, funds, warrants, and units.
        """

    @abstractmethod
    def get_daily_bars(
        self, symbol: str, start: date, end: date
    ) -> pd.DataFrame:
        """Daily OHLCV bars for ``symbol`` in ``[start, end]`` inclusive.

        Returns a DataFrame indexed by trading day with columns
        ``open, high, low, close, volume``.
        """

    @abstractmethod
    def get_intraday_bars(
        self, symbol: str, day: date, interval: IntradayInterval
    ) -> pd.DataFrame:
        """Intraday OHLCV bars for ``symbol`` on ``day`` at ``interval`` minutes.

        Returns a DataFrame indexed by tz-aware (US/Eastern) timestamp with
        columns ``open, high, low, close, volume``.
        """

    @abstractmethod
    def get_premarket_quote(
        self, symbol: str, at: datetime
    ) -> PremarketQuote:
        """Premarket price for ``symbol`` as close to ``at`` as available.

        If no clean premarket print exists, returns the regular 9:30 open
        with ``is_fallback=True`` so the caller can log/flag the fallback.
        """

    @abstractmethod
    def get_news(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[NewsItem]:
        """News items for ``symbol`` between ``start`` and ``end`` (inclusive)."""

    @abstractmethod
    def get_earnings_calendar(self, on: date) -> list[EarningsEvent]:
        """Earnings releases scheduled on ``on`` (any symbol)."""

    @abstractmethod
    def get_company_profile(self, symbol: str) -> CompanyProfile:
        """Static metadata: sector, industry, market cap, float, shares."""
