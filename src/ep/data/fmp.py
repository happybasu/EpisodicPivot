"""FMP Premium data provider.

Phase 0.3: stub only — every method raises ``NotImplementedError`` with a
pointer to the phase in which it is filled in. Real API integration lands
in Phase 1.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from ep.data.provider import (
    CompanyProfile,
    DataProvider,
    EarningsEvent,
    IntradayInterval,
    NewsItem,
    PremarketQuote,
)

if TYPE_CHECKING:
    import pandas as pd


class FMPProvider(DataProvider):
    """Concrete ``DataProvider`` backed by FMP Premium."""

    def get_universe(self, as_of_date: date) -> list[str]:
        raise NotImplementedError("Phase 1.1")

    def get_daily_bars(
        self, symbol: str, start: date, end: date
    ) -> pd.DataFrame:
        raise NotImplementedError("Phase 1.1")

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
