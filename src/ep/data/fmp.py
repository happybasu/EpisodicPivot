"""FMP Premium data provider.

Implements ``DataProvider`` against FMP's ``/stable/`` endpoint family.
The legacy ``/api/v3/`` family was retired by FMP on 2025-08-31 — see
CLAUDE.md for the migration map and gotchas (notably ``extended=true``
for premarket bars and the delisted-ticker intraday gap).

Phase 1.1 implements ``get_daily_bars`` (with on-disk parquet cache) and
``get_universe`` (active screener + delisted, filtered to US common stock).
Remaining methods stay stubbed for later phases.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

import httpx
import pandas as pd

from ep.data.cache import DataFrameCache
from ep.data.provider import (
    CompanyProfile,
    DataProvider,
    EarningsEvent,
    IntradayInterval,
    NewsItem,
    PremarketQuote,
)

FMP_BASE_URL = "https://financialmodelingprep.com"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
BACKOFF_BASE = 1.0

# Exchanges considered US for the universe filter.
US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX"}

# FMP symbol suffixes for warrants, units, and rights — excluded per strategy
# spec. Preferred shares (-PA, -PB, ...) are *not* excluded here; the Phase 2
# liquidity filter will drop the illiquid ones.
EXCLUDED_SYMBOL_SUFFIXES = ("-UN", "-WS", "-WT", "-WTA", "-WTB", "-W", "-R", "-RT")


def _is_excluded_symbol(symbol: str) -> bool:
    return any(symbol.endswith(s) for s in EXCLUDED_SYMBOL_SUFFIXES)

# Daily-history fetch window. We always fetch the full window so the cache
# captures everything; slicing happens client-side.
DAILY_FROM = "1995-01-01"
DAILY_TO = "2099-12-31"

DAILY_BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


class FMPProvider(DataProvider):
    """Concrete ``DataProvider`` backed by FMP Premium ``/stable/``."""

    def __init__(
        self,
        api_key: str | None = None,
        cache: DataFrameCache | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key or ""
        self._cache = cache if cache is not None else DataFrameCache()
        self._http = (
            http_client
            if http_client is not None
            else httpx.Client(timeout=DEFAULT_TIMEOUT)
        )

    def close(self) -> None:
        self._http.close()

    # ---- HTTP helper -------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        merged = dict(params or {})
        merged["apikey"] = self._api_key
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._http.get(f"{FMP_BASE_URL}{path}", params=merged)
                if resp.status_code == 429:
                    time.sleep(BACKOFF_BASE * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as e:
                last_err = e
                if attempt + 1 < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2**attempt))
        raise RuntimeError(
            f"FMP request to {path} failed after {MAX_RETRIES} retries: {last_err}"
        )

    # ---- get_daily_bars ---------------------------------------------

    def get_daily_bars(
        self, symbol: str, start: date, end: date
    ) -> pd.DataFrame:
        """Daily OHLCV bars in ``[start, end]`` inclusive, cached to parquet.

        On first call per symbol, fetches the full available history and
        caches it. Subsequent calls slice the cached DataFrame in memory.
        Cache staleness (today's bar appearing only on a fresh fetch) is
        not handled in Phase 1.1; the first call per process is the
        source of truth.
        """
        df = self._cache.get("daily", symbol)
        if df is None:
            df = self._fetch_daily(symbol)
            self._cache.put("daily", symbol, df)
        if df.empty:
            return df
        mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        return df.loc[mask].copy()

    def _fetch_daily(self, symbol: str) -> pd.DataFrame:
        data = self._get(
            "/stable/historical-price-eod/full",
            params={"symbol": symbol, "from": DAILY_FROM, "to": DAILY_TO},
        )
        if not isinstance(data, list) or not data:
            return pd.DataFrame(columns=DAILY_BAR_COLUMNS).rename_axis("date")
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df[DAILY_BAR_COLUMNS]

    # ---- get_universe -----------------------------------------------

    def get_universe(self, as_of_date: date) -> list[str]:
        """US common stock tradable on ``as_of_date``, including later-delisted.

        Combines the active company screener (US, non-ETF, non-fund,
        NASDAQ/NYSE/AMEX) with delisted-companies whose ``delistedDate`` is
        after ``as_of_date``. Symbols containing ``.`` are dropped — those
        are alternate-venue listings of names already covered by their
        primary symbol. Warrants and units are not cleanly distinguishable
        via FMP's screener; this is a known limitation documented in
        CLAUDE.md.
        """
        symbols: set[str] = set()

        for row in self._screen_active_us_stocks():
            sym = row.get("symbol")
            short = (row.get("exchangeShortName") or "").upper()
            if not sym or "." in sym or short not in US_EXCHANGES:
                continue
            if row.get("isEtf") or row.get("isFund"):
                continue
            if _is_excluded_symbol(sym):
                continue
            symbols.add(sym)

        cutoff = pd.Timestamp(as_of_date)
        for row in self._fetch_delisted():
            sym = row.get("symbol")
            exch = (row.get("exchange") or "").upper()
            delisted_at = row.get("delistedDate")
            if not sym or "." in sym or not delisted_at:
                continue
            if _is_excluded_symbol(sym):
                continue
            if not any(e in exch for e in US_EXCHANGES):
                continue
            try:
                if pd.Timestamp(delisted_at) > cutoff:
                    symbols.add(sym)
            except (ValueError, TypeError):
                continue

        return sorted(symbols)

    def _screen_active_us_stocks(self) -> list[dict[str, Any]]:
        """Walk pages of the company screener (active US, non-ETF, non-fund)."""
        out: list[dict[str, Any]] = []
        limit = 1000
        page = 0
        while page < 50:  # safety bound — universe shouldn't exceed 50k
            data = self._get(
                "/stable/company-screener",
                params={
                    "country": "US",
                    "isEtf": "false",
                    "isFund": "false",
                    "isActivelyTrading": "true",
                    "limit": limit,
                    "page": page,
                },
            )
            if not isinstance(data, list) or not data:
                break
            out.extend(data)
            if len(data) < limit:
                break
            page += 1
        return out

    def _fetch_delisted(self) -> list[dict[str, Any]]:
        """Walk pages of /stable/delisted-companies."""
        out: list[dict[str, Any]] = []
        limit = 100
        page = 0
        while page < 200:
            data = self._get(
                "/stable/delisted-companies",
                params={"page": page, "limit": limit},
            )
            if not isinstance(data, list) or not data:
                break
            out.extend(data)
            if len(data) < limit:
                break
            page += 1
        return out

    # ---- Remaining stubs (filled in later phases) -------------------

    def get_intraday_bars(
        self, symbol: str, day: date, interval: IntradayInterval
    ) -> pd.DataFrame:
        raise NotImplementedError("Phase 1.2")

    def get_premarket_quote(
        self, symbol: str, at: datetime
    ) -> PremarketQuote:
        raise NotImplementedError("Phase 1.2")

    def get_news(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[NewsItem]:
        raise NotImplementedError("Phase 1.3")

    def get_earnings_calendar(self, on: date) -> list[EarningsEvent]:
        raise NotImplementedError("Phase 1.3")

    def get_company_profile(self, symbol: str) -> CompanyProfile:
        raise NotImplementedError("Phase 1.3")
