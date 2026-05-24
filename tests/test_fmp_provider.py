"""Phase 1.1 verification — FMPProvider.get_daily_bars and get_universe.

Unit tests use ``httpx.MockTransport`` so the FMPProvider is exercised end
to end (request construction, response parsing, cache wiring) without
hitting the network. Integration tests (marked ``integration``) talk to
the real FMP /stable/ endpoints when ``FMP_API_KEY`` is present and are
skipped otherwise.
"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
import pytest

from ep.config import load_config
from ep.data.cache import DataFrameCache
from ep.data.fmp import FMPProvider


def _sample_daily_response(symbol: str = "AAPL") -> list[dict]:
    """Three bars in FMP /stable/ shape (most-recent-first)."""
    return [
        {
            "symbol": symbol,
            "date": "2024-01-05",
            "open": 185.0,
            "high": 187.0,
            "low": 183.0,
            "close": 185.5,
            "volume": 1_000_000,
        },
        {
            "symbol": symbol,
            "date": "2024-01-03",
            "open": 184.0,
            "high": 186.0,
            "low": 182.0,
            "close": 184.5,
            "volume": 900_000,
        },
        {
            "symbol": symbol,
            "date": "2024-01-02",
            "open": 183.0,
            "high": 185.0,
            "low": 181.0,
            "close": 183.5,
            "volume": 800_000,
        },
    ]


def _provider_with_mock(handler, tmp_path) -> FMPProvider:
    cache = DataFrameCache(tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FMPProvider(api_key="test-key", cache=cache, http_client=client)


def test_get_daily_bars_returns_ohlcv_dataframe(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_sample_daily_response("AAPL"))

    provider = _provider_with_mock(handler, tmp_path)
    df = provider.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "date"
    assert len(df) == 3
    # Chronological ordering (oldest first).
    assert df.index[0] < df.index[-1]


def test_get_daily_bars_caches_on_disk_and_second_call_skips_api(tmp_path):
    """First call hits API and writes cache; second call serves from cache."""
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_sample_daily_response("AAPL"))

    provider = _provider_with_mock(handler, tmp_path)

    df1 = provider.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert call_count == 1
    cache_file = tmp_path / "daily" / "AAPL.parquet"
    assert cache_file.exists(), "cache file should be created after first fetch"

    df2 = provider.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert call_count == 1, "second call should be served from cache, not API"
    pd.testing.assert_frame_equal(df1, df2)


def test_get_daily_bars_slices_to_requested_range(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_sample_daily_response("AAPL"))

    provider = _provider_with_mock(handler, tmp_path)
    df = provider.get_daily_bars("AAPL", date(2024, 1, 3), date(2024, 1, 4))

    # 2024-01-03 included, 2024-01-05 excluded.
    assert df.index.min() == pd.Timestamp("2024-01-03")
    assert df.index.max() == pd.Timestamp("2024-01-03")
    assert len(df) == 1


def test_get_universe_filters_etfs_and_non_us_exchanges(tmp_path):
    """Smoke test with mocked screener + delisted endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/stable/company-screener" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "AAPL",
                        "exchangeShortName": "NASDAQ",
                        "isEtf": False,
                        "isFund": False,
                    },
                    {
                        "symbol": "MSFT",
                        "exchangeShortName": "NASDAQ",
                        "isEtf": False,
                        "isFund": False,
                    },
                    # ETF — must be excluded.
                    {
                        "symbol": "SPY",
                        "exchangeShortName": "AMEX",
                        "isEtf": True,
                        "isFund": False,
                    },
                    # Canadian dual listing — excluded (NEO not in US set).
                    {
                        "symbol": "AAPL.NE",
                        "exchangeShortName": "NEO",
                        "isEtf": False,
                        "isFund": False,
                    },
                ],
            )
        if "/stable/delisted-companies" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "BBBY",
                        "exchange": "NASDAQ",
                        "delistedDate": "2023-04-23",
                    },
                    # Delisted before as_of_date — excluded.
                    {
                        "symbol": "OLDCO",
                        "exchange": "NYSE",
                        "delistedDate": "2010-01-15",
                    },
                ],
            )
        return httpx.Response(404, json={"error": "unknown endpoint"})

    provider = _provider_with_mock(handler, tmp_path)
    universe = provider.get_universe(date(2022, 6, 1))

    assert "AAPL" in universe
    assert "MSFT" in universe
    assert "BBBY" in universe, "delisted name still tradable on as_of_date kept"
    assert "SPY" not in universe, "ETF excluded"
    assert "AAPL.NE" not in universe, "non-US dual listing excluded"
    assert "OLDCO" not in universe, "already-delisted before as_of_date excluded"


def test_get_universe_excludes_warrants_and_units(tmp_path):
    """Strategy spec excludes warrants and units; symbols with `-UN`/`-WS` etc. dropped."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/stable/company-screener" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "AAPL",
                        "exchangeShortName": "NASDAQ",
                        "isEtf": False,
                        "isFund": False,
                    },
                    # Unit — must be excluded.
                    {
                        "symbol": "ACME-UN",
                        "exchangeShortName": "NASDAQ",
                        "isEtf": False,
                        "isFund": False,
                    },
                    # Warrant — must be excluded.
                    {
                        "symbol": "ACME-WS",
                        "exchangeShortName": "NASDAQ",
                        "isEtf": False,
                        "isFund": False,
                    },
                    # Right — must be excluded.
                    {
                        "symbol": "FOO-R",
                        "exchangeShortName": "NYSE",
                        "isEtf": False,
                        "isFund": False,
                    },
                ],
            )
        return httpx.Response(200, json=[])

    provider = _provider_with_mock(handler, tmp_path)
    universe = provider.get_universe(date(2024, 1, 1))
    assert "AAPL" in universe
    assert "ACME-UN" not in universe
    assert "ACME-WS" not in universe
    assert "FOO-R" not in universe


def test_empty_daily_response_returns_empty_frame(tmp_path):
    """An empty list from FMP yields an empty, well-formed DataFrame."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    provider = _provider_with_mock(handler, tmp_path)
    df = provider.get_daily_bars("NOPE", date(2024, 1, 1), date(2024, 1, 31))
    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


# --- Integration tests (real FMP API) -------------------------------------


def _live_provider_or_skip(tmp_path) -> FMPProvider:
    api_key = load_config().secrets.fmp_api_key
    if not api_key:
        pytest.skip("FMP_API_KEY not set in .env")
    return FMPProvider(api_key=api_key, cache=DataFrameCache(tmp_path))


@pytest.mark.integration
def test_live_get_daily_bars_aapl(tmp_path):
    provider = _live_provider_or_skip(tmp_path)
    df = provider.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert len(df) >= 15, "Jan 2024 has ~21 trading days; expected at least 15"
    assert (tmp_path / "daily" / "AAPL.parquet").exists()
    # Second call must not re-fetch — easiest check: cache file mtime unchanged.
    mtime_before = (tmp_path / "daily" / "AAPL.parquet").stat().st_mtime
    provider.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    mtime_after = (tmp_path / "daily" / "AAPL.parquet").stat().st_mtime
    assert mtime_before == mtime_after, "second call should not rewrite cache"


@pytest.mark.integration
def test_live_get_daily_bars_delisted_ticker(tmp_path):
    """BBBY (Bed Bath & Beyond) — delisted 2023-04-23. Should still return data."""
    provider = _live_provider_or_skip(tmp_path)
    df = provider.get_daily_bars("BBBY", date(2022, 1, 1), date(2022, 12, 31))
    assert len(df) >= 100, "BBBY traded all of 2022; expected ~252 daily bars"
    assert (tmp_path / "daily" / "BBBY.parquet").exists()
