# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

This repo is **pre-Phase 0**: no code, no `pyproject.toml`, no tests, not a git repo. The only artifacts are:

- `EpisodicPivot.md` — the authoritative build plan. Phases 0–7, paste-one-prompt-at-a-time, each with a `Verify` step. **Do not skip ahead or batch phases.** Each phase's verification must pass before starting the next.
- `Episodic Pivot Initial requirement document.docx` — original requirements (superseded by `EpisodicPivot.md`).
- `.env` — already populated with Alpaca (paper), FMP Premium, and OpenRouter keys. Phase 0.1's `.gitignore` must exclude `.env` before any `git init`.

When asked to "start", "build", or "implement", begin at **Phase 0.1** in `EpisodicPivot.md` unless the user names a different phase.

## Hard constraints (never violate)

These come from `EpisodicPivot.md` §0 and Appendix A. They are non-negotiable.

- **Risk parameters and hard filters are human-only, forever.** Any future learning/scoring loop may touch only the soft scoring/ranking layer. Never auto-tune position size, stop distance, gap threshold, portfolio limits, or any hard filter.
- **One code path for entry/exit logic.** The backtest engine (Phase 3) and live engine (Phase 7) must share the same entry/exit code — not two parallel implementations.
- **All data access goes through `DataProvider`.** Strategy, scanner, backtest, and execution code must never import FMP (or any future provider) directly. The abstraction (Phase 0.3) is what lets Polygon/Alpaca SIP be swapped in later via config with zero strategy changes.
- **AI scoring (Phase 5) is optional, deterministic, and never a trigger.** Same input → same score. It only re-orders the review list. It is never a hard filter and never pulls a trade trigger. The system must run fully with scoring disabled.
- **No live trading until the go-live gate passes.** Gate (Phase 7.5): ≥ 2 months paper trading AND ≥ 30 paper trades AND paper performance broadly matches backtest. Attempting live mode before the gate must raise a clear error.
- **Every parameter lives in `config.yaml`.** No magic numbers in code. The full tunable list is in `EpisodicPivot.md` §0.
- **Conservative fill modeling.** A buy-stop fills only if a later bar's high *exceeds* the stop price — a mere touch does not fill. Always apply slippage. Gap-through stops fill at the open.
- **Human approves eligibility; bot pulls the trigger.** Human approves the 9:00 AM review list. Bot runs the 9:28 AM confirmation, places buy-stops on OR breakout, and manages stops/exits autonomously. Kill switch (per-position force-close + global halt) must always be available.

## Locked strategy numbers

Defaults that go into `config.yaml`. All tunable, but these are the starting values defined in §0:

| Parameter | Default |
|---|---|
| Gap threshold (premarket vs prior close) | 10% |
| ADR period | 20 days, excluding gap day |
| Opening-volume filter (first 15 min vs 20-day avg) | 10% |
| Opening-range length | 15 min (also supports 5/30/60) |
| Risk per trade | 1.0% of equity |
| Initial stop | 1× ADR below entry |
| Max concurrent positions | 5 |
| Max new entries per day | 3 |
| Max per sector | 2 |
| Partial exit | ½ at +2R **or** day 5, whichever first |
| After partial | Move remaining stop to breakeven |
| Trail | 10-day SMA on the runner |
| Backtest window | 5 years, **including delisted tickers** |

`R` = entry − stop = the dollar amount equal to 1% of equity. ADR is the *percentage* form: mean of `(H/L) − 1` over the 20 days before the gap day.

## Data provider notes

- **FMP Premium is the only v1 source.** Phase 0.4 audit (in `data_audit_report.md`, gitignored) confirmed: ~16 years of daily, ~7 years of 5-min/15-min intraday, premarket available with the `extended=true` flag. `backtest_lookback_years: 5` is supported.
- **Use `/stable/` endpoints, not `/api/v3/`.** FMP retired the legacy v3 family on **2025-08-31**; current API keys (anyone subscribing after that date) get 403 from v3. The audit script in `scripts/data_audit.py` is the reference for the path migration: daily → `/stable/historical-price-eod/full`, intraday → `/stable/historical-chart/{interval}`, news → `/stable/news/stock`, earnings → `/stable/earnings`, profile → `/stable/profile`. Symbol is always a query param (`?symbol=…`), never a path segment.
- **Pre/after-hours bars require `extended=true`.** Without that flag, `/stable/historical-chart/*` returns regular session only (09:30–16:00 ET). The EP scanner relies on premarket data, so the `FMPProvider` must pass `extended=true` for any call that needs pre-09:30 bars.
- **Delisted-ticker intraday gap (survivorship-bias risk).** Daily history works for delisted names, but intraday is partial — in the audit sample only 2/6 delisted symbols (BBBY, FRC) returned 5/15-min bars; SIVB, TWTR, SHOS, ZNGA returned daily only. Phase 3 backtest results must distinguish "delisted in sample with intraday" vs "delisted but missing intraday" and not silently drop the latter — flag explicitly in the trade log.
- **`/stable/delisted-companies` has coverage gaps.** Walking the full endpoint (9,000+ names back to 2002) found SIVB, TWTR, FRC, ZNGA, but *not* BBBY despite BBBY's daily bars being available via `/stable/historical-price-eod/full`. `get_universe` therefore under-counts delisted names. Phase 3 must not assume the universe is exhaustive — if a known delisted name is needed for a backtest fixture, fetch it explicitly rather than relying on universe membership.
- **Premarket quote fallback.** If no clean premarket print exists for a requested timestamp, return the regular 9:30 open and **set a flag** indicating the fallback was used.
- Cache aggressively on disk (parquet, keyed by symbol+range) — Phase 1 mandates this.

## Build/test commands

Will exist once Phase 0.1 runs. Expected toolchain (per the Phase 0.1 prompt): Python 3.11+, `pyproject.toml`, `pytest`, `ruff`. After Phase 0.1, the standard commands are:

```
pip install -e .
pytest                  # all tests
pytest tests/path/to/test_file.py::test_name   # single test
ruff check
```
