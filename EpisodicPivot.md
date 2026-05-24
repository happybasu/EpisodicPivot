# EpisodicPivot.md — Build Plan & Claude Code Prompts

> An automated **Episodic Pivot (EP)** swing-trading system.
> EP = a stock gaps up hard on a genuine catalyst, then breaks out of its opening
> range with heavy volume and trends for days to weeks.
>
> **How to use this file:** Each phase is a group of numbered sub-prompts. Paste
> them into Claude Code **one at a time, in order**. After each sub-prompt,
> run the stated *Verify* step before moving on. Do not start a phase until the
> previous phase's final verification passes.

---

## 0. Locked Strategy Decisions (Single Source of Truth)

These were finalized during planning. Every phase below depends on them. They are
restated in `CLAUDE.md` (Phase 0) as hard constraints.

| Area | Decision |
|---|---|
| **Market data** | FMP Premium is the **only** v1 source. All data access goes through an abstracted `DataProvider` interface so Polygon.io / Alpaca SIP can be swapped in later via config — **no strategy code changes**. |
| **Data fidelity caveat** | FMP Premium's deep historical intraday/premarket is the known weak spot. Phase 0 includes an audit to discover the *real* usable backtest window before building on it. |
| **Backtest universe** | All US common stock, **5-year** lookback. Must include **delisted tickers** (historical constituents) to avoid survivorship bias. |
| **Gap definition** | Premarket price **≥ 10%** above **prior official close**. |
| **Scan timing** | Two-stage. **9:00 AM ET**: build review list (all gappers ≥10% + catalysts) for human approval. **9:28 AM ET**: auto-confirm — drop any approved name whose gap has faded below threshold. |
| **ADR** | 20-day **percentage** ADR = mean of `(High / Low) - 1` over the 20 days **prior to** the gap day (gap day excluded so it doesn't inflate the stop). |
| **Opening-volume filter** | First-15-min volume **≥ 10%** of 20-day average daily volume. Threshold is a tunable parameter. |
| **"Institutional pressure"** | **Not** a hard filter. Computed as observable signals — VWAP-hold, opening-range strength — shown on dashboard and fed to AI score. Promotable to a filter later only if the backtest earns it. |
| **Entry trigger** | Opening-range breakout. OR length is a **parameter** (5/15/30/60 min); **default = 15 min**. Entry is a **buy-stop** just above the OR high. No fill if the high is only touched, not exceeded. |
| **Position sizing** | **Risk-based. 1.0% risk per trade.** Position size derived from the 1×ADR stop distance. Risk % is a tunable parameter. |
| **Initial stop** | **1 × ADR** below entry. |
| **Portfolio limits** | Max **5** concurrent positions · max **3** new entries/day · max **2** per sector. All tunable. |
| **Exit** | Sell **½** at **+2R OR day 5**, whichever first. On partial, move stop on remaining half to **breakeven**. Trail the runner on the **10-day SMA**. All values tunable. |
| **AI scoring** | Hybrid. A **one-time calibration run** studies historical EP winners vs losers and produces (a) a human-readable rubric and (b) a **deterministic** scoring function. Re-run periodically as live trades accumulate. **Optional layer** — the system trades fully without it. |
| **Feedback loop** | **Manual-review only.** System logs every trade with full context and produces periodic edge reports. Every parameter/rubric change is a deliberate human decision. |
| **Hard boundary** | Risk parameters and hard filters are **human-only, forever**. Any future learning loop may touch **only** the soft scoring/ranking layer. |
| **Execution model** | Human approves *eligibility* premarket (the 9:00 list). Bot pulls the trigger only on *confirmation* (OR breakout). Bot manages stops/exits **autonomously**. |
| **Auto-cancel** | If an approved name's gap collapses below threshold after 9:28 but before its breakout, the bot **cancels the pending entry** (protective, removal-only, deterministic). Below-VWAP breakouts are still traded but **flagged** in logs. |
| **Kill switch** | Dashboard always offers manual force-close of any position and a global halt-all-trading control. |
| **Go-live gate** | Real capital is blocked until: **≥ 2 months** paper trading **AND ≥ 30** paper trades **AND** paper results broadly in line with the backtest. |

**Glossary:** *R* = initial risk per trade = entry − stop = the dollar amount equal
to 1.0% of equity. *+2R* = unrealized gain of twice that amount. *ADR* = Average
Daily Range (percentage, as defined above). *OR* = opening range.

---

## Phase 0 — Project Scaffold & Data Audit

*Goal: a clean repo, a config system, the data abstraction, and — critically —
an honest measurement of how far back FMP intraday data actually reaches.*

**0.1 — Repo scaffold.**
> Create a Python project for an automated Episodic Pivot trading system. Set up:
> a `pyproject.toml` (Python 3.11+), a `src/ep/` package, and `tests/`. Create
> these submodules as empty packages with docstrings describing their future role:
> `data/`, `scanner/`, `backtest/`, `metrics/`, `scoring/`, `risk/`, `execution/`,
> `dashboard/`, `reports/`, `journal/`. Add `requirements.txt`, `.gitignore`
> (ignore `.env`, `__pycache__`, data caches, logs), and a `README.md` stub.
> Use `ruff` for linting and `pytest` for tests. Do not implement logic yet.

*Verify:* `pip install -e .` succeeds; `pytest` runs (0 tests OK); `ruff check` is clean.

**0.2 — Config system.**
> Build a config system in `src/ep/config.py`. Load a `config.yaml` plus a `.env`
> for secrets (FMP API key). Provide a typed config object (use `pydantic`).
> Include every tunable parameter from the strategy table: gap threshold (0.10),
> ADR period (20), opening-volume threshold (0.10), OR length minutes (15),
> risk-per-trade (0.01), max positions (5), max new/day (3), max per sector (2),
> partial fraction (0.5), profit-take R-multiple (2.0), day-backstop (5),
> trail SMA length (10), gap-collapse auto-cancel threshold. Ship a fully
> commented `config.yaml` with these defaults. Add a `.env.example`.

*Verify:* a unit test loads the config and asserts every default matches the table above.

**0.3 — DataProvider abstraction.**
> Define an abstract base class `DataProvider` in `src/ep/data/provider.py` with
> methods the rest of the system will depend on (signatures only, fully
> type-hinted, docstringed): `get_universe(as_of_date)`,
> `get_daily_bars(symbol, start, end)`, `get_intraday_bars(symbol, date, interval)`,
> `get_premarket_quote(symbol, datetime)`, `get_news(symbol, start, end)`,
> `get_earnings_calendar(date)`, `get_company_profile(symbol)`.
> Then create `FMPProvider(DataProvider)` as a stub that raises
> `NotImplementedError` for each method. The point: all later code imports the
> abstract type, never FMP directly. Add a `get_provider()` factory that reads
> the provider name from config.

*Verify:* a test confirms `get_provider()` returns an `FMPProvider` and that it is a `DataProvider` subclass.

**0.4 — FMP data audit (do not skip).**
> Implement a standalone script `scripts/data_audit.py`. Using the FMP Premium
> API, for a sample of ~30 tickers (mix of large-cap, small-cap, and at least 5
> known-delisted symbols), probe and report: (1) earliest available daily bar;
> (2) earliest available 5-min and 15-min intraday bar; (3) whether premarket
> prints exist historically and how far back; (4) whether delisted tickers
> return data at all; (5) news/earnings history depth. Output a clear Markdown
> report `data_audit_report.md` with a final verdict: the realistic backtest
> start date and any quality caveats. Handle rate limits gracefully.

*Verify:* run the script; read `data_audit_report.md`. **Decision point:** if the
usable intraday window is materially less than 5 years, note it and adjust the
backtest window in `config.yaml` accordingly before continuing.

---

## Phase 1 — Data Layer

*Goal: a fully working `FMPProvider` with caching, plus the derived calculations
(ADR, average volume) every later phase calls.*

**1.1 — FMP daily + universe.**
> Implement `FMPProvider.get_daily_bars()` and `get_universe()` against the FMP
> Premium API. `get_universe(as_of_date)` must return the set of US common stock
> tradable on that date, **including symbols later delisted** (use FMP's
> symbol/historical-constituent and delisted-companies endpoints). Exclude ETFs,
> funds, warrants, units. Add a local on-disk cache (parquet) keyed by
> symbol+range so repeated calls don't re-hit the API.

*Verify:* fetch daily bars for AAPL and one delisted ticker; confirm the cache file
appears and a second call is served from cache.

**1.2 — Intraday + premarket.**
> Implement `get_intraday_bars(symbol, date, interval)` for 5/15/30/60-min
> intervals and `get_premarket_quote(symbol, datetime)`. Premarket quote must
> return the consolidated price as close to the requested time as available;
> if no clean premarket print exists, return a documented fallback (the regular
> 9:30 open) **with a flag** indicating the fallback was used. Cache intraday
> data on disk.

*Verify:* fetch the 15-min bars for a known historical gap day; fetch a 9:00 AM
premarket quote; confirm the fallback flag behaves correctly on a thin ticker.

**1.3 — News & catalyst ingestion.**
> Implement `get_news()`, `get_earnings_calendar()`, and `get_company_profile()`.
> `get_news` returns headline, body/snippet, timestamp, source. `get_company_profile`
> returns sector, industry, market cap, shares outstanding, float if available.

*Verify:* pull news for a stock around a known earnings date; confirm sector/float fields populate.

**1.4 — Derived calculations.**
> In `src/ep/data/calculations.py` implement pure, well-tested functions:
> `adr_pct(daily_bars, period=20, exclude_last=True)` — mean of `(H/L)-1` over the
> N bars **before** the last bar; `avg_daily_volume(daily_bars, period=20)`;
> `gap_pct(premarket_price, prior_close)`; `sma(series, length)`;
> `vwap(intraday_bars)`. These are the math core — unit-test each with hand-checked
> fixtures.

*Verify:* `pytest` — every calculation has a test with a manually computed expected value.

---

## Phase 2 — Scanner / Screener

*Goal: the two-stage premarket scan that produces the human review list and the
9:28 confirmation.*

**2.1 — Catalyst classifier.**
> Build `src/ep/scanner/catalyst.py`. Given a stock's recent news, classify the
> catalyst into a taxonomy with priority weights (highest → lowest): FDA
> approval / major contract / M&A; earnings beat with raised guidance; analyst
> upgrade / major partnership; product launch; vague PR / no clear catalyst.
> Return the catalyst type, the matched headline, and a priority weight. Keep
> classification rule-based and transparent for now (keyword + source heuristics);
> the AI layer comes in Phase 5.

*Verify:* feed in sample headlines of each type; confirm correct classification and weight.

**2.2 — Hard filters.**
> Build `src/ep/scanner/filters.py` implementing each hard filter as an
> independent, individually testable predicate: gap ≥ threshold vs prior close;
> ADR ≥ minimum (tunable, default e.g. 3%); price ≥ minimum (avoid sub-$1
> illiquid names); average dollar-volume ≥ minimum (liquidity floor);
> first-15-min volume ≥ 10% of 20-day avg daily volume. Each predicate returns a
> pass/fail plus the computed value (for logging and the dashboard).

*Verify:* unit-test each predicate at, just above, and just below its threshold.

**2.3 — Soft signals.**
> Build `src/ep/scanner/signals.py` computing the non-gating signals: VWAP-hold
> (fraction of opening period the price traded above VWAP), opening-range
> strength (where in the OR the price closed — upper/mid/lower third), and the
> same-window relative volume (first-15-min vs average first-15-min). These are
> numeric outputs only — no pass/fail.

*Verify:* compute all three for a known gap day; sanity-check against the chart.

**2.4 — Stage-one scan (9:00 AM).**
> Build `src/ep/scanner/scan.py` with `run_premarket_scan(date)`. It iterates the
> universe, finds all names gapping ≥10% vs prior close as of 9:00 AM, runs the
> hard filters that are computable premarket, attaches catalyst classification,
> ADR, float, gap %, and any premarket volume signal. Output a structured
> `ReviewList` object (sortable, serializable to JSON/CSV) — this is what the
> human approves.

*Verify:* run for a historical date with known big gappers; confirm they appear with correct catalysts.

**2.5 — Stage-two confirmation (9:28 AM).**
> Add `confirm_approved(review_list, approved_symbols, datetime)`. For each
> human-approved symbol, re-check the gap at 9:28 AM; drop any whose gap has
> faded below the (tunable) confirmation threshold. Return the confirmed set with
> a reason logged for every drop.

*Verify:* simulate a faded approved name; confirm it is dropped with a logged reason.

---

## Phase 3 — Backtest Engine

*Goal: an event-driven simulator that replays the full strategy on historical
data with realistic, conservative fills.*

**3.1 — Engine skeleton.**
> Build an event-driven backtester in `src/ep/backtest/engine.py`. It steps
> through trading days; on each day it calls the scanner, simulates the
> (auto-)approval, then steps through intraday bars to manage entries and exits.
> Define core dataclasses: `Trade`, `Position`, `Order`, `Fill`, `PortfolioState`.
> No fill logic yet — just the loop and state objects.

*Verify:* engine runs over a 1-month window without entering trades and produces an empty but well-formed result.

**3.2 — Entry simulation.**
> Implement the opening-range breakout entry. After the OR (default 15 min)
> completes, place a **buy-stop** just above the OR high. Fill **only if a later
> bar's high exceeds the stop price** — a mere touch does not fill. Fill price =
> stop price + slippage (tunable, model as a fraction of ADR). Respect all
> portfolio limits (5 positions / 3 new per day / 2 per sector) and skip entries
> that would breach them.

*Verify:* on a known clean breakout, confirm entry; on a name that never exceeds
its OR high, confirm no entry; confirm limits block the 4th sector-mate.

**3.3 — Position sizing.**
> Implement risk-based sizing in `src/ep/risk/sizing.py`: shares =
> `(equity * risk_pct) / (entry_price - stop_price)`, where stop = entry − 1×ADR.
> Round down to whole shares. Reject trades whose required size is zero or whose
> notional would exceed sane bounds.

*Verify:* unit-test — a tight-ADR name gets a larger position than a wide-ADR name for the same dollar risk.

**3.4 — Exit simulation.**
> Implement the full exit logic: hard stop at 1×ADR below entry; sell **½** at
> **+2R or day 5** (whichever first); on the partial, move the remaining stop to
> **breakeven**; trail the runner on the **10-day SMA** (exit remaining shares on
> a daily close below the SMA). Model intraday stop fills with slippage; if a gap
> opens through the stop, fill at the open. Handle the day-5 backstop as an
> end-of-day action.

*Verify:* construct fixtures for each exit path (stopped out; +2R partial then
trail; day-5 partial; gap-through stop) and assert correct P&L.

**3.5 — Auto-cancel & flags.**
> Add the post-approval auto-cancel: if a pending (not-yet-filled) entry's gap
> collapses below the threshold before the breakout triggers, cancel it. Also
> tag any filled trade whose breakout occurred below VWAP with a `below_vwap`
> flag (traded, not blocked — for later analysis).

*Verify:* simulate a collapsing approved name → entry cancelled; simulate a below-VWAP breakout → trade taken and flagged.

**3.6 — Results & trade log.**
> Produce a complete backtest result: per-trade log (entry/exit dates, prices,
> R-multiple, catalyst, ADR, gap %, all signals, flags) and an equity curve.
> Serialize to disk (parquet + JSON summary).

*Verify:* run a full 5-year (or audited-window) backtest; confirm the trade log and equity curve are well-formed.

---

## Phase 4 — Metrics & Validation

*Goal: turn raw backtest output into a trustworthy go/no-go picture, and stress
the strategy for robustness.*

**4.1 — Core KPIs.**
> Build `src/ep/metrics/kpis.py`: win rate, average win/loss (in R), expectancy,
> profit factor, max drawdown, CAGR, Sharpe and Sortino, average holding period,
> exposure, longest losing streak. Output a clean metrics report.

*Verify:* feed a hand-built trade set with known stats; assert each KPI matches.

**4.2 — Regime split.**
> Add a regime analyzer: classify each trading day as bull / bear / chop using
> SPY vs its 200-day SMA (and slope). Re-compute the KPIs separately per regime
> so EP performance is visible in each environment.

*Verify:* confirm trades are bucketed correctly around a known SPY 200-SMA cross.

**4.3 — Walk-forward optimization.**
> Build a walk-forward optimizer over the tunable parameters (OR length,
> opening-volume threshold, profit-take R, partial fraction, trail SMA length,
> gap threshold). Optimize on in-sample windows, validate on rolling
> out-of-sample windows. Report in-sample vs out-of-sample degradation — large
> degradation = overfit warning.

*Verify:* optimizer runs end-to-end; produces an in-sample/out-of-sample comparison table.

**4.4 — Monte Carlo & robustness.**
> Add (a) a Monte Carlo bootstrap that resamples the trade sequence to produce a
> distribution of drawdowns and final equity, and (b) a parameter-perturbation
> test that nudges each parameter ±10–20% and checks results don't collapse.

*Verify:* both run; produce a drawdown distribution and a perturbation-sensitivity table.

**4.5 — Master validation report.**
> Build a master orchestration script that runs the backtest + all of the above
> and emits a single `validation_report.md` with explicit **pass/fail deployment
> criteria** (e.g. positive out-of-sample expectancy, profit factor above a
> threshold, drawdown within tolerance, acceptable parameter sensitivity).

*Verify:* generate the report; confirm a clear PASS/FAIL verdict appears.

---

## Phase 5 — AI Scoring Module (Optional Layer)

*Goal: a transparent, deterministic ranking aid. The system already trades
without this — scoring only re-orders the review list.*

> **Framing note for Claude Code:** the score is a heuristic triage aid, not a
> validated probability of profit. It must be deterministic and human-readable.
> It must never act as a hard filter or trade trigger.

**5.1 — Calibration dataset.**
> Build `scripts/build_scoring_dataset.py`: from the backtest trade log, assemble
> a labelled dataset of historical EP setups — each row is the pre-entry context
> (catalyst type, headline, sector, float, gap %, ADR, premarket volume signal,
> regime) joined to the outcome (R-multiple, win/loss). Sample a balanced set
> (~100+) of clear winners and clear losers.

*Verify:* dataset builds; inspect a few rows for correctness.

**5.2 — Calibration run → rubric.**
> Build a one-time calibration process that analyzes the dataset and produces a
> **human-readable rubric** (`scoring_rubric.md`) — explicit, inspectable weights
> and rules describing which catalyst types, float ranges, gap sizes, and signal
> combinations historically preceded strong vs weak outcomes.

*Verify:* read `scoring_rubric.md`; confirm it is sensible and matches trading intuition.

**5.3 — Deterministic scoring function.**
> Implement `score_candidate(context) -> int (0–100)` in `src/ep/scoring/score.py`
> that applies the rubric **deterministically** — same input always yields the
> same score. Wire it into the scanner so the review list can be sorted by score.
> Keep it fully optional via a config flag.

*Verify:* score the same candidate twice → identical; disable via config → system still runs.

**5.4 — Recalibration support.**
> Add a documented procedure + script to re-run calibration later using
> accumulated live trade outcomes, producing a new rubric **diff** for human
> review. The new rubric never goes live without explicit human replacement of
> the file.

*Verify:* dry-run recalibration on the backtest data; confirm it emits a reviewable diff.

---

## Phase 6 — Dashboard & Approval Workflow

*Goal: the human control surface — review, approve, monitor, override.*

**6.1 — Review-list view.**
> Build a local dashboard (Streamlit or FastAPI + simple frontend). The morning
> view shows the 9:00 AM review list: each candidate with catalyst, headline,
> gap %, ADR, float, volume signals, VWAP/range strength, and AI score (if
> enabled). Sortable and filterable.

*Verify:* load a historical scan into the dashboard; confirm all fields render.

**6.2 — Approve / reject workflow.**
> Add approve/reject controls per candidate. The approved set is persisted and
> handed to the 9:28 confirmation step. Show the confirmation result (which names
> survived, which were dropped and why).

*Verify:* approve a few names; confirm persistence and that the 9:28 result displays.

**6.3 — Live position monitor.**
> Add a positions view: open trades with entry, current price, stop, unrealized
> R, distance to next exit action, and flags. Plus an account summary (equity,
> open risk, positions used vs limits).

*Verify:* with simulated open positions, confirm the monitor displays correct live values.

**6.4 — Kill switch & overrides.**
> Add a per-position **force-close** control and a global **halt-all-trading**
> switch. Both take effect immediately and are clearly logged.

*Verify:* trigger a force-close and a global halt in a paper context; confirm both act and log.

**6.5 — Edge reports.**
> Add an edge-report view: score-vs-outcome, performance by catalyst type, by
> regime, below-VWAP vs above-VWAP, parameter drift over time. This is the
> manual-review feedback surface.

*Verify:* generate edge reports from backtest data; confirm breakdowns are correct.

---

## Phase 7 — Live Execution & Paper-Trading Gate

*Goal: connect to the broker, run the autonomous execution loop, and enforce the
hard gate before any real capital.*

**7.1 — Alpaca integration.**
> Build `src/ep/execution/broker.py` wrapping Alpaca for **paper trading first**.
> Implement: submit/cancel buy-stop orders, submit stop and market orders,
> query positions and account equity. Mirror the abstraction style of
> `DataProvider` so the broker is swappable. Read paper/live mode from config.

*Verify:* against the Alpaca **paper** endpoint, place and cancel a test order.

**7.2 — Autonomous execution loop.**
> Build the live loop: run the 9:00 scan → present the review list → wait for
> human approval → run the 9:28 confirmation → at the open, for confirmed names,
> place buy-stops above the OR high → on fill, immediately place the 1×ADR stop →
> manage the +2R/day-5 partial, the breakeven move, and the 10-day-SMA trail
> autonomously. Reuse the exact entry/exit logic from the backtest engine — one
> code path, not two.

*Verify:* run a full simulated session on the paper account; confirm entries,
stops, and exits fire per the rules.

**7.3 — Auto-cancel & safety in live.**
> Wire the post-approval auto-cancel into the live loop (cancel a pending entry
> if its gap collapses pre-breakout). Ensure the kill switch halts the loop
> cleanly and that a crash/restart recovers open-position state from the broker.

*Verify:* simulate a gap collapse → pending order cancelled; restart mid-session → state recovered.

**7.4 — Trade journaling.**
> On every fill and exit, append a full record to the trade journal (all context,
> signals, flags, R-multiple, regime). This is the dataset for edge reports and
> future recalibration.

*Verify:* run paper trades; confirm each produces a complete journal entry.

**7.5 — Go-live gate (enforced).**
> Implement a `go_live_gate` check that **blocks** switching the broker to live
> mode until ALL are true: ≥ 2 months of paper trading elapsed; ≥ 30 paper
> trades recorded; paper performance broadly in line with backtest expectations
> (compare win rate, expectancy, slippage within a documented tolerance).
> Until the gate passes, attempting live mode raises a clear error explaining
> which criteria remain unmet.

*Verify:* with insufficient paper history, confirm live mode is refused with a clear message; simulate a passing record and confirm it unlocks.

---

## Appendix A — CLAUDE.md Contents (create in Phase 0.1)

Place a `CLAUDE.md` at the repo root so every Claude Code session inherits the
rules. It must contain, as **hard constraints**:

- The entire Section 0 decision table, verbatim.
- **Risk parameters and hard filters are human-only. Never auto-tune them.**
- The backtest engine and live engine must share **one** entry/exit code path.
- All data access goes through `DataProvider`; never call FMP directly from
  strategy code.
- The AI score is optional, deterministic, and never a trade trigger or hard filter.
- No live trading until the go-live gate passes.
- Every parameter lives in `config.yaml` — no magic numbers in code.
- Conservative fill modeling: no fill unless price genuinely exceeds the stop;
  always apply slippage.

## Appendix B — Suggested Build Order Summary

`Phase 0` scaffold/audit → `Phase 1` data → `Phase 2` scanner → `Phase 3`
backtest → `Phase 4` validation → **decision point: does validation PASS?** →
`Phase 5` AI scoring (optional) → `Phase 6` dashboard → `Phase 7` live + paper
gate → **2-month paper period** → go-live gate → live.

> Do not let a failing Phase 4 validation report be overridden by enthusiasm.
> If the strategy does not show a positive out-of-sample edge, the right move is
> to revise the strategy — not to skip to Phase 7.
