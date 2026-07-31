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

---

# Part 2 — "Private AI quant management system" survey (2026-07-30)

User ask: find repos in the self-hosted / private AI-quant-platform category worth
borrowing from. Vitals pulled from the **GitHub API**, not page scrapes — because the
headline star counts in this category are actively misleading (see QuantMuse below).

## Vitals

| Repo | Stars | Last push | Commits | Verdict |
|---|---:|---|---:|---|
| `virattt/ai-hedge-fund` | 62,495 | 2026-07-30 | active | **Already borrowed** |
| `TauricResearch/TradingAgents` | 95,085 | 2026-07-18 | active | Already reviewed → rejected |
| `microsoft/qlib` | 46,857 | 2026-07-23 | active | Different architecture |
| `AI4Finance-Foundation/FinRL` | 15,854 | 2026-07-13 | active | Different architecture |
| `OpenBB-finance/OpenBB` | 71,203 | 2026-07-30 | active | **Already the primary data lane** |
| `polakowo/vectorbt` | 8,488 | 2026-07-14 | active | **Adopted** (Part 1) |
| `dgunning/edgartools` | 2,524 | 2026-07-29 | active | Parked (Part 1) |
| `jasonstrimpel/volatility-trading` (= `volest`) | 1,936 | 2024-10-21 | stale | **Adopted** (Part 1) |
| `0xemmkty/QuantMuse` | 2,824 | 2025-07-29 | **9** | ⚠️ **Avoid — see below** |

## ⚠️ QuantMuse — why the star count is a trap

It surfaces first in every search for this category and reads impressively. The API says
otherwise:

- **2,824 stars / 588 forks — but 9 commits, from 1 contributor.** That is ~314 stars per
  commit, wildly outside any normal ratio.
- Commit messages are `readme`, `readme`, `7.28`, `7.27`, `3.18` — no meaningful history.
- **Last push 2025-07-29 — a full year stale** (as of 2026-07-30).
- There *is* real code (79 `.py` files, 629 KB), but 629 KB landing in 9 commits with no
  iteration means it was bulk-dumped, never battle-tested, and then abandoned.

**Verdict: do not depend on it.** Fine to read for ideas; treat every claim in its README
as unverified. This is the clearest example in the survey of why star count is not evidence.

## The actual finding: this project already absorbed this category

Cross-checking each platform's headline features against what already exists here:

| Their headline feature | Status in NYSE_DATA |
|---|---|
| Multi-agent LLM investor committee | **Built** — AI Hedge Fund page, 12 investor personas + Risk Manager + Portfolio Manager, explicitly *"inspired by virattt/ai-hedge-fund"* — and **deterministic**: no LLM keys, no paid data |
| Multi-agent debate / bull-vs-bear | **Built** — `/debate`, 5 weighted agents, Bull-vs-Bear adversarial round, weights rebalanced from a real backtest (A17) |
| Portfolio optimization | **Built** — `/allocate` (max-Sharpe, min-variance, risk-parity) |
| Risk management (VaR / CVaR / drawdown) | **Built** — Portfolio & Risk pages, VaR/CVaR + Monte Carlo P&L |
| Factor screening / factor IC | **Built** — `/ic` factor rank-IC validation |
| Backtesting engine | **Built** — 60+ backtest call sites; `backtest_summary`, `signal_accuracy` |
| Adaptive / self-improving weights | **Built** — `signal_accuracy` → `signal_weights` feedback loop |
| Multi-source market data | **Built** — OpenBB/CBOE primary, yfinance fallback, own capture-forward DB |
| Streamlit dashboard | **Built** — 36 pages |
| LLM market narrative | **Built** — `_debate_polish()`, optional, graceful fallback |

**Conclusion:** there is very little left to take from this category. The differentiator
those platforms *don't* have is the one this project already owns: a **capture-forward
options database with real bid/ask/IV/delta**, which is what makes signals here
backtestable against history that genuinely existed at the time.

## Genuinely missing (candidates, user to decide)

Not "features other repos have" — these are real gaps found while comparing:

1. **Walk-forward / out-of-sample discipline as a standard.** `signal_accuracy` grades
   live fires, and individual backtests were run properly this session, but there's no
   enforced train/test split convention. The Kronos evaluation already flagged
   pretraining-leakage as a trap; the same discipline belongs in ordinary signal work.
2. **Realistic fill modelling.** Backtests assume mid-price fills; real spreads on the
   options this book trades are wide. `flashalpha-fill-simulator` (Part 1, parked)
   addresses exactly this and would make `/spreads` and `/hiprob` results more honest.
3. **Portfolio-level strategy allocation.** `/allocate` sizes *tickers*; nothing sizes
   capital across *strategies* by their measured edge (the `signal_accuracy` data needed
   to do it already exists).

Item 3 is the most interesting: the data to do it is already being collected.
