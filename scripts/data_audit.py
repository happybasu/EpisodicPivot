"""FMP data audit — Phase 0.4.

Probes FMP Premium across a ~30-ticker sample (large-cap, small-cap,
known-delisted) and reports the empirical history depth so the realistic
backtest window can be set honestly in `config.yaml`.

Per symbol we probe:
  1. earliest available daily bar (full history call)
  2. earliest available 5-min and 15-min intraday bar (by year-probe)
  3. premarket print existence (look for pre-09:30 ET stamps in 1-min data)
  4. delisted-ticker data availability (same probes applied to delisted)
  5. news / earnings history depth

Run:
    python scripts/data_audit.py
    python scripts/data_audit.py --output custom_report.md --delay 0.2
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ep.config import load_config

BASE_URL = "https://financialmodelingprep.com"
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3
BACKOFF_BASE = 1.0

# Tickers — edit freely; the audit just needs a representative spread.
LARGE_CAPS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "JNJ"]
SMALL_CAPS = ["RIOT", "MARA", "PLUG", "FCEL", "AMC", "GME", "BB", "NIO", "RVLV", "OMER"]
DELISTED = ["BBBY", "SIVB", "FRC", "TWTR", "SHOS", "ZNGA"]

# Year-windows used to probe earliest available intraday data.
# Each window is a short range (5 trading days) — we just need yes/no per year.
INTRADAY_PROBES: list[tuple[str, str, str]] = [
    ("2017", "2017-06-12", "2017-06-16"),
    ("2018", "2018-06-11", "2018-06-15"),
    ("2019", "2019-06-10", "2019-06-14"),
    ("2020", "2020-06-15", "2020-06-19"),
    ("2021", "2021-06-14", "2021-06-18"),
    ("2022", "2022-06-13", "2022-06-17"),
    ("2023", "2023-06-12", "2023-06-16"),
    ("2024", "2024-06-10", "2024-06-14"),
]

# Date window used for the premarket probe (recent + known-volatile in 2024).
PREMARKET_PROBE_DATE = "2024-06-13"  # FOMC day, lots of pre-09:30 activity


@dataclass
class AuditResult:
    symbol: str
    category: str
    earliest_daily: str | None = None
    daily_bars_count: int = 0
    earliest_5min_year: str | None = None
    earliest_5min_date: str | None = None
    earliest_15min_year: str | None = None
    earliest_15min_date: str | None = None
    has_premarket: bool = False
    earliest_premarket_stamp: str | None = None
    news_count: int = 0
    earliest_news: str | None = None
    earnings_count: int = 0
    earliest_earnings: str | None = None
    profile_available: bool = False
    errors: list[str] = field(default_factory=list)


def call_fmp(
    client: httpx.Client,
    path: str,
    params: dict[str, Any] | None = None,
    api_key: str = "",
) -> Any:
    """GET with retry + exponential backoff. Returns parsed JSON or {'_error': msg}."""
    full_params = dict(params or {})
    full_params["apikey"] = api_key
    last_err = "unknown"
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(
                f"{BASE_URL}{path}", params=full_params, timeout=TIMEOUT_SECONDS
            )
            if resp.status_code == 429:
                wait = BACKOFF_BASE * (2**attempt)
                print(f"    rate-limited, sleeping {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt + 1 < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * (2**attempt))
    return {"_error": last_err}


def probe_daily(
    client: httpx.Client, symbol: str, api_key: str
) -> tuple[str | None, int, str | None]:
    data = call_fmp(
        client,
        "/stable/historical-price-eod/full",
        params={"symbol": symbol, "from": "2010-01-01", "to": "2030-01-01"},
        api_key=api_key,
    )
    if isinstance(data, dict) and "_error" in data:
        return None, 0, data["_error"]
    if not isinstance(data, list) or not data:
        return None, 0, "empty"
    # /stable/ returns most-recent-first; the last entry is the oldest.
    return data[-1].get("date"), len(data), None


def probe_intraday_year(
    client: httpx.Client,
    symbol: str,
    interval: str,
    from_date: str,
    to_date: str,
    api_key: str,
) -> tuple[bool, str | None, str | None]:
    """Returns (has_data, earliest_stamp_in_window, error)."""
    data = call_fmp(
        client,
        f"/stable/historical-chart/{interval}",
        params={"symbol": symbol, "from": from_date, "to": to_date},
        api_key=api_key,
    )
    if isinstance(data, dict) and "_error" in data:
        return False, None, data["_error"]
    if not isinstance(data, list) or not data:
        return False, None, None
    stamps = [row.get("date") for row in data if row.get("date")]
    return bool(stamps), (min(stamps) if stamps else None), None


def probe_intraday_earliest(
    client: httpx.Client, symbol: str, interval: str, delay: float, api_key: str
) -> tuple[str | None, str | None, str | None]:
    """Walk INTRADAY_PROBES oldest→newest; return (earliest_year, earliest_stamp, error)."""
    for year, frm, to in INTRADAY_PROBES:
        has, stamp, err = probe_intraday_year(client, symbol, interval, frm, to, api_key)
        time.sleep(delay)
        if err:
            return None, None, err
        if has:
            return year, stamp, None
    return None, None, None


def probe_premarket(
    client: httpx.Client, symbol: str, api_key: str
) -> tuple[bool, str | None, str | None]:
    # `extended=true` is required on FMP /stable/ to include pre/after-hours bars.
    data = call_fmp(
        client,
        "/stable/historical-chart/1min",
        params={
            "symbol": symbol,
            "from": PREMARKET_PROBE_DATE,
            "to": PREMARKET_PROBE_DATE,
            "extended": "true",
        },
        api_key=api_key,
    )
    if isinstance(data, dict) and "_error" in data:
        return False, None, data["_error"]
    if not isinstance(data, list) or not data:
        return False, None, None
    # FMP timestamps are "YYYY-MM-DD HH:MM:SS" in US/Eastern.
    pm = [
        row["date"]
        for row in data
        if isinstance(row.get("date"), str) and "04:00:00" <= row["date"][11:19] < "09:30:00"
    ]
    if pm:
        return True, min(pm), None
    return False, None, None


def probe_news(
    client: httpx.Client, symbol: str, api_key: str
) -> tuple[int, str | None, str | None]:
    data = call_fmp(
        client,
        "/stable/news/stock",
        params={"symbols": symbol, "limit": 100},
        api_key=api_key,
    )
    if isinstance(data, dict) and "_error" in data:
        return 0, None, data["_error"]
    if not isinstance(data, list):
        return 0, None, None
    stamps = [n.get("publishedDate") for n in data if n.get("publishedDate")]
    return len(data), (min(stamps) if stamps else None), None


def probe_earnings(
    client: httpx.Client, symbol: str, api_key: str
) -> tuple[int, str | None, str | None]:
    data = call_fmp(
        client,
        "/stable/earnings",
        params={"symbol": symbol, "limit": 100},
        api_key=api_key,
    )
    if isinstance(data, dict) and "_error" in data:
        return 0, None, data["_error"]
    if not isinstance(data, list):
        return 0, None, None
    dates = [e.get("date") for e in data if e.get("date")]
    return len(data), (min(dates) if dates else None), None


def probe_profile(client: httpx.Client, symbol: str, api_key: str) -> bool:
    data = call_fmp(
        client, "/stable/profile", params={"symbol": symbol}, api_key=api_key
    )
    return isinstance(data, list) and bool(data)


def audit_symbol(
    client: httpx.Client, symbol: str, category: str, delay: float, api_key: str
) -> AuditResult:
    r = AuditResult(symbol=symbol, category=category)
    print(f"[{category:>10}] {symbol:<6} ", end="", flush=True)

    earliest, count, err = probe_daily(client, symbol, api_key)
    r.earliest_daily = earliest
    r.daily_bars_count = count
    if err:
        r.errors.append(f"daily: {err}")
    time.sleep(delay)

    yr5, stamp5, err = probe_intraday_earliest(client, symbol, "5min", delay, api_key)
    r.earliest_5min_year = yr5
    r.earliest_5min_date = stamp5
    if err:
        r.errors.append(f"5min: {err}")

    yr15, stamp15, err = probe_intraday_earliest(client, symbol, "15min", delay, api_key)
    r.earliest_15min_year = yr15
    r.earliest_15min_date = stamp15
    if err:
        r.errors.append(f"15min: {err}")

    pm, pm_stamp, err = probe_premarket(client, symbol, api_key)
    r.has_premarket = pm
    r.earliest_premarket_stamp = pm_stamp
    if err:
        r.errors.append(f"premarket: {err}")
    time.sleep(delay)

    n_count, e_news, err = probe_news(client, symbol, api_key)
    r.news_count = n_count
    r.earliest_news = e_news
    if err:
        r.errors.append(f"news: {err}")
    time.sleep(delay)

    eg_count, e_earn, err = probe_earnings(client, symbol, api_key)
    r.earnings_count = eg_count
    r.earliest_earnings = e_earn
    if err:
        r.errors.append(f"earnings: {err}")
    time.sleep(delay)

    r.profile_available = probe_profile(client, symbol, api_key)

    flag = "OK" if not r.errors else f"{len(r.errors)} err"
    print(
        f"daily={r.daily_bars_count:>5} "
        f"5m≥{r.earliest_5min_year or '—':<4} "
        f"15m≥{r.earliest_15min_year or '—':<4} "
        f"pm={'Y' if r.has_premarket else 'N'} "
        f"[{flag}]"
    )
    return r


def write_report(results: list[AuditResult], output: Path) -> None:
    L: list[str] = []
    L.append("# FMP Data Audit Report")
    L.append("")
    L.append(f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}")
    L.append(f"Symbols probed: **{len(results)}**")
    L.append("")

    for cat in ("large-cap", "small-cap", "delisted"):
        subset = [r for r in results if r.category == cat]
        if not subset:
            continue
        L.append(f"## {cat.title()} ({len(subset)})")
        L.append("")
        L.append(
            "| Symbol | Profile | Daily start | Daily bars | 5-min ≥ | 5-min stamp |"
            " 15-min ≥ | 15-min stamp | Premarket | News (start, #) |"
            " Earnings (start, #) |"
        )
        L.append("|---|---|---|---:|---|---|---|---|---|---|---|")
        for r in subset:
            L.append(
                "| {sym} | {prof} | {dstart} | {dcount} | {y5} | {s5} | {y15} | {s15} |"
                " {pm} | {news} | {earn} |".format(
                    sym=r.symbol,
                    prof="OK" if r.profile_available else "—",
                    dstart=r.earliest_daily or "—",
                    dcount=r.daily_bars_count,
                    y5=r.earliest_5min_year or "—",
                    s5=(r.earliest_5min_date or "—")[:16],
                    y15=r.earliest_15min_year or "—",
                    s15=(r.earliest_15min_date or "—")[:16],
                    pm=("Y " + (r.earliest_premarket_stamp or "")[11:16])
                    if r.has_premarket
                    else "N",
                    news=f"{(r.earliest_news or '—')[:10]} ({r.news_count})",
                    earn=f"{(r.earliest_earnings or '—')[:10]} ({r.earnings_count})",
                )
            )
        L.append("")

    err_results = [r for r in results if r.errors]
    if err_results:
        L.append("## Errors / Caveats")
        L.append("")
        for r in err_results:
            L.append(f"- **{r.symbol}** ({r.category}): {'; '.join(r.errors)}")
        L.append("")

    # --- Verdict ---
    L.append("## Verdict")
    L.append("")
    live = [r for r in results if r.category != "delisted"]
    delisted_results = [r for r in results if r.category == "delisted"]

    daily_starts = [r.earliest_daily for r in live if r.earliest_daily]
    if daily_starts:
        L.append(
            f"- **Daily history**: every probed live symbol has daily bars going back at"
            f" least to **{max(daily_starts)[:10]}**."
        )

    y5 = [r.earliest_5min_year for r in live if r.earliest_5min_year]
    y15 = [r.earliest_15min_year for r in live if r.earliest_15min_year]
    if y15:
        L.append(
            f"- **Intraday 15-min**: earliest year reached for *every* live symbol is"
            f" **{max(y15)}** (latest of the per-symbol earliest years —"
            f" the worst case in the sample)."
        )
    if y5:
        L.append(
            f"- **Intraday 5-min**: earliest year reached for *every* live symbol is"
            f" **{max(y5)}**."
        )

    pm_live = sum(1 for r in live if r.has_premarket)
    L.append(
        f"- **Premarket prints** on the probed recent date ({PREMARKET_PROBE_DATE}): "
        f"{pm_live}/{len(live)} live symbols showed pre-09:30 ET data."
    )

    delisted_daily = sum(1 for r in delisted_results if r.daily_bars_count > 0)
    delisted_intra = sum(1 for r in delisted_results if r.earliest_15min_year)
    L.append(
        f"- **Delisted tickers**: {delisted_daily}/{len(delisted_results)} returned daily"
        f" data; {delisted_intra}/{len(delisted_results)} returned 15-min intraday."
    )

    news_starts = [r.earliest_news for r in live if r.earliest_news]
    if news_starts:
        L.append(f"- **News history**: oldest article seen in sample is {min(news_starts)[:10]}.")

    earn_starts = [r.earliest_earnings for r in live if r.earliest_earnings]
    if earn_starts:
        L.append(
            f"- **Earnings history**: oldest scheduled event in sample is"
            f" {min(earn_starts)[:10]}."
        )

    L.append("")
    L.append("### Recommended backtest window")
    L.append("")
    if y15:
        worst_year = max(y15)
        try:
            current_year = datetime.now(UTC).year
            usable_years = current_year - int(worst_year)
            L.append(
                f"Worst-case 15-min coverage in the sample reaches {worst_year} →"
                f" ~**{usable_years} years** of intraday history."
            )
            if usable_years < 5:
                L.append("")
                L.append(
                    f"> ⚠️ **Less than 5 years usable**. Reduce"
                    f" `strategy.backtest_lookback_years` in `config.yaml`"
                    f" to **{usable_years}** before continuing to Phase 1."
                )
            else:
                L.append("")
                L.append("> ✓ ≥ 5 years usable — current `backtest_lookback_years: 5` is fine.")
        except ValueError:
            L.append("(could not infer years from probe data)")
    else:
        L.append(
            "No live symbol returned intraday data — investigate FMP plan limits"
            " before continuing."
        )

    L.append("")
    L.append("### Caveats")
    L.append("")
    L.append(
        "- Earliest-year columns are the oldest *probed* window that returned data, not"
        " a per-day exact bound. The true earliest may be earlier than the first probe."
    )
    L.append(
        "- Premarket probe used a single recent date; a `Y` here does not guarantee"
        " premarket coverage for older history."
    )
    L.append(
        "- Sample size is small (~26 symbols). Outliers can skew the worst-case columns —"
        " spot-check the per-symbol table before locking the window."
    )

    output.write_text("\n".join(L) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="FMP data audit (Phase 0.4)")
    parser.add_argument(
        "--output",
        default="data_audit_report.md",
        help="Output Markdown path (default: %(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.15,
        help="Seconds between requests (default: %(default)s)",
    )
    args = parser.parse_args()

    cfg = load_config()
    api_key = cfg.secrets.fmp_api_key
    if not api_key:
        print("FMP_API_KEY not set in .env — aborting.", file=sys.stderr)
        return 1

    print(f"Probing {len(LARGE_CAPS) + len(SMALL_CAPS) + len(DELISTED)} symbols...\n")
    results: list[AuditResult] = []
    with httpx.Client() as client:
        for sym in LARGE_CAPS:
            results.append(audit_symbol(client, sym, "large-cap", args.delay, api_key))
        for sym in SMALL_CAPS:
            results.append(audit_symbol(client, sym, "small-cap", args.delay, api_key))
        for sym in DELISTED:
            results.append(audit_symbol(client, sym, "delisted", args.delay, api_key))

    output = Path(args.output)
    write_report(results, output)
    print(f"\nReport written to: {output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
