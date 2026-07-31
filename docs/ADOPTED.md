# ADOPTED — ideas taken from `awesome-systematic-trading`

Source: `github.com/wangzhe3224/awesome-systematic-trading` (reviewed 2026-07-30, full
295-entry catalog tabulated). This file records what was **adopted**, what was
**deliberately rejected and why**, and what is **parked for a later decision** — so the
same list doesn't get re-litigated from scratch in a future session.

House rule that governs everything here: adopt the *idea*, verified against real data
in this DB, rather than bolting on a dependency. "Tested" = measured on real history,
not "it imports".

---

## ✅ ADOPTED (built 2026-07-30)

### 1. Range-based volatility estimators (`volest`)

**Idea taken:** close-to-close realized vol discards the intraday high/low that
`stock_history` already stores. Range-based estimators use the *same* data with much
lower variance (Parkinson ≈5x more efficient than close-to-close, Garman-Klass ≈7x).

**Built:** `_daily_ohlc()` + `_realized_vol()` in `telegram_bot_optimized.py`.
Five estimators: `close_close`, `parkinson`, `garman_klass`, `rogers_satchell`,
`yang_zhang` (default). No new dependency — pure numpy/pandas over existing data.

**Wired into:** `_vrp_scan()` (`/vrp`), replacing a close-to-close MAD estimator.
Falls back to the old MAD path when OHLC is unavailable, so nothing regresses.

**Why Yang-Zhang as the default:** it is the only one of the five that handles *both*
overnight gaps and drift — which matters enormously for an options book full of
earnings names.

**Measured on real data (2026-07-30, 30d window):**

| Ticker | Close-Close | Parkinson | Garman-Klass | Rogers-Satchell | **Yang-Zhang** |
|---|---|---|---|---|---|
| AAPL | 34.6% | 28.4% | 27.4% | 27.0% | 30.0% |
| NVDA | 37.3% | 31.4% | 31.6% | 33.7% | 39.7% |
| SPY  | 14.0% | 12.5% | 14.0% | 14.6% | 17.3% |
| GOOG | 34.7% | 29.5% | 30.4% | 30.3% | 36.2% |
| MU   | 112.1% | 73.2% | 82.4% | 92.1% | **136.3%** |
| TSLA | 55.7% | 45.3% | 45.8% | 46.3% | 50.4% |

Behaviour matches theory: Parkinson lowest (blind to gaps), Yang-Zhang highest (counts
them). **MU is the case that proves the point** — 73% vs 136% depending on whether
earnings gaps are counted, a ~2x difference in RV that flips the VRP verdict outright.
Post-change `/vrp` now scores MU as BUY (VRP −7.2) where the gap-blind estimator would
have called it rich.

> Unrelated pre-existing issue noticed while testing, NOT introduced by this change and
> NOT silently patched: `_iv_rank` returns an implausible ~133% IV for AAPL. Worth a
> separate look.

### 2. Vectorized backtesting pattern (`vectorbt`)

**Idea taken:** signal backtests should be matrix operations over a wide
(dates × tickers) frame, not a per-ticker Python loop. Several validations run this
session (the `/debate` agent-weight rebalance, the A18 short-interest study) used the
loop pattern.

**Benchmarked before adopting** — same data, same signal, same forward window:

| Approach | Time | N | rank-IC |
|---|---|---|---|
| Hand-rolled per-ticker loop | 3.012s | 87,600 | −0.01808 |
| Vectorized (matrix ops) | **0.050s** | 87,600 | −0.01808 |

**60x faster, identical rank-IC to 5 decimals** on a real 120-ticker × 756-day universe.

**Status:** `vectorbt` v1.0.0 is already installed and imports cleanly. The *pattern* is
what matters and is what future backtests should use (`_history_matrix()` already returns
exactly the wide frame this needs). Adopting the library's full `Portfolio` abstraction
is **not** required to get this win and was not done.

---

## ❌ REJECTED — already built here, verified

| Item | Why not |
|---|---|
| `vollib`, `FinancePy`, `QuantLib`/PyQL | A working Black-Scholes + Greeks engine already runs throughout the bot. QuantLib/FinancePy's exotic-derivative and fixed-income depth is overkill for vanilla equity options. |
| `pyfolio`, `quantstats` | Overlaps the existing Portfolio & Risk pages — Greeks, VaR/CVaR, Monte Carlo P&L. |
| `pandas-ta`, TA-Lib, `finta` | `pandas_ta` is already a dashboard dependency and in use. |
| `13F Insight`, `AlphaSMO`, `CongressionalStockBrain` | Paid/AI-scored versions of trackers already built free here (EDGAR 13F, insider, congress) and hand-verified across several CIK audit rounds. |
| `Helium MCP`, `The Stall` | Paid MCP options-pricing/market-data servers; this project computes its own Greeks and already has an MCP server exposing them. |
| The whole "AI Powered Systematic Trading Systems" section (FinRL, FinGPT, QLib, Qbot, agent frameworks) | Different architecture entirely — Python ML/RL research stacks, not a Telegram + Streamlit + SQLite terminal. Same conclusion this project already reached researching TradingAgents and worldmonitor. |

---

## 🅿️ PARKED — user to decide later

| Item | The case for it | The catch |
|---|---|---|
| `edgartools` | Maintained SEC EDGAR library (13F, Form 4, 8-K). Would likely have avoided the manual 11-CIK bug hunt. | Current tracker works and is verified — no reason to rip it out. Reach for this on *new* EDGAR work instead of hand-rolling again. |
| `Wickra` | 514 streaming O(1)-per-tick indicators. | Only pays off if the intraday lane (`/live`, `/heat`) grows in scope. Not urgent. |
| `hftbacktest` | Models limit-order queue position and latency. | Only relevant if execution modelling ever matters here; currently no live broker execution. |
| `ArcticDB` / `DuckDB` | Purpose-built timeseries/columnar stores; would outperform SQLite on wide scans. | SQLite is working, and the busy_timeout fix (2026-07-30) resolved the one real contention failure. Migration is real scope for a speed problem that isn't currently biting. |
| `flashalpha-fill-simulator` | Realistic fill simulation for options credit/debit spreads. | Would sharpen `/spreads` and `/hiprob` backtests, which currently assume mid-price fills. Genuinely interesting — parked only because it's new scope, not because it lacks merit. |
| `Ib_insync` | Mature IBKR API wrapper. | Only if live execution is ever wanted; the project is explicitly analytics-only today. |

---

## Full catalog

All 295 entries across 13 sections, searchable, with the options/volatility/Greeks-relevant
ones flagged:
https://claude.ai/code/artifact/217b79aa-285e-4c16-ab07-240542479445
