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

---

# Part 3 — Cross-strategy allocator: investigated, NOT built (2026-07-30)

Attempted gap #3 above. **Correct call was to stop.** Recording why, so it isn't
re-attempted prematurely.

## Two false alarms I raised first (corrected)

1. *"All models share one `actual_ret` — data is corrupt."* **Wrong.** Every model predicts
   the same underlying, so they are graded against the same forward return. Correct design.
2. *"NEUTRAL is graded as a bearish call — grading bug."* **Wrong.** `_score_signal()` is
   sound and well-documented: BULL needs `ret > +0.3%`, BEAR `ret < -0.3%`,
   NEUTRAL/SELL_PREMIUM `|ret| < 1.2%` — the last is a *volatility* call (move contained),
   not direction. Every aggregate reconciles against it. There's even a documented fix from
   2026-07-22 for a genuine earlier scoring bug.

Lesson (same one as the TradingKey scrape): check the implementation before alleging a bug
from aggregates.

## The real blocker: the measurement is too imprecise to allocate on

`signal_accuracy` holds 16,311 rows / 30 models / 730 tickers, but only 2026-05-13 →
2026-07-31 (~2.5 months). Per model that's ~262 graded fires.

**Median 95% CI width on per-model hit-rate: 12.0 percentage points.**

| Model | n | hit% | 95% CI |
|---|---:|---:|---|
| scn_building | 1333 | 47.9 | 45.2 – 50.5 |
| scn_breakout | 302 | 44.7 | 39.1 – 50.3 |
| scn_revert | 289 | 34.3 | 28.8 – 39.7 |
| gex | 262 | 38.9 | 33.0 – 44.8 |
| gamma_pin | 262 | 49.2 | 43.2 – 55.3 |
| left_skew | 262 | 40.8 | 34.9 – 46.8 |

At n=262 a 44% model is statistically indistinguishable from a 50% model. Sizing capital
across strategies on that would be **fitting noise** — precisely the failure this project
has repeatedly avoided (`/building`, `/uoa`, capflow, A18 all ended in honest null results).

**Revisit at n≈1000+ per model** (CI ≈ ±3 pts). At the current ~100 graded fires/model/month
that is roughly 7 more months of accrual. No code needed meanwhile — the writer already runs.

## Worth a look NOW, though: possible inverted edges

Most CIs straddle 50% (no demonstrated edge). Three sit **entirely below** it:

- `scn_revert` 28.8 – 39.7
- `gex` 33.0 – 44.8
- `left_skew` 34.9 – 46.8

A directional signal that is reliably *wrong* is as useful as one that is right — this is
exactly the `/debate` Vol-agent case, which was sign-flipped on 2026-07-22 after the same
observation. Caveats before acting: the sample has negative drift (only ~45% of forward
returns positive), so a long-biased signal will look bad for reasons that are not its own
fault, and 2.5 months is one regime. Treat as a **hypothesis to test properly**, not a
finding — same bar every other signal here had to clear.

---

# Part 4 — The validation harness was broken (2026-07-31)

Triggered by asking whether the strategy additions in Part 2/3 would "create value or
better results". Testing that honestly surfaced a bigger problem than any missing feature.

## The test

Generated random alpha expressions from the standard operator vocabulary (rank, delay,
rolling mean/std, ratios) over the real 149-ticker x 756-day price matrix, and scored each
by rank-IC vs forward returns — exactly as a real alpha search would.

Any "alpha" found this way is meaningless by construction. A sound harness should reject
~95% of them.

| Method | Random alphas passing p<0.05 | Passing \|t\|>4 | Best random \|t\| |
|---|---:|---:|---:|
| **Pooled rank-IC** (what the recipe used) | **68–79%** | **35–46%** | **10.80** |
| **Daily cross-sectional IC** (correct) | **0%** | **0%** | 1.57 |

## Why

`t = IC·√(N−2)/√(1−IC²)` assumes independent observations. Neither holds:
1. **Overlap** — fwd-5d returns sampled daily share 4 of 5 days with the next row.
2. **Cross-correlation** — 149 tickers all load on the market; one day is not 149 draws.

Nominal N (~100k) is ~100x overstated, inflating t by roughly √100 ≈ 10x. A random
expression reached **|t| = 10.80** — higher than the "+7.05" used the night before to
justify a live weight change.

## Consequence: one shipped result was wrong, and is reverted

`/debate` Technical weight was raised 1.0 → 1.3 on 2026-07-30 citing rank-IC +0.047,
t=+7.05. Re-run correctly, the **full `_agent_technical` composite** scores:

| Horizon | Pooled (invalid) | Daily-IC (correct) |
|---|---|---|
| fwd-5d | t = −1.21 | **t = +1.04** |
| fwd-10d | t = −0.69 | **t = +1.10** |

No edge. **Weight reverted to 1.0.** Note the pooled stat doesn't even reproduce its own
earlier sign — it is unstable, not merely inflated.

**Macro's 0.3 stands.** It was lowered on a *null* result, and inflation can only create
false positives — a null under an inflation-prone test is still a null.

## What is and isn't affected

- ✅ **Hit-rate vs baseline is fine** — makes no independence claim. `/revert`, `/pead`,
  `/building`, `/uoa` verdicts stand.
- ✅ **All null results stand** — A18 short interest, capflow, Macro agent. Inflation
  cannot manufacture a null.
- ⚠️ **Positive results from a pooled IC must be re-tested.** Caveated in-place pending
  re-test: Market Radar "QQQ t+5 corr +0.37", Rotation Tracker "momentum axis IC +0.14",
  and the ~20d positioning tilt "IC +0.03, t≈3".

## Answer to "will the new strategies create value?"

**Mostly no — and this is why.** With a harness that passes 68% of random noise, adding
strategies would have produced confident nonsense faster. Ranked honestly:

| Item | Real expected value |
|---|---|
| **Fix the harness** (done) | **Highest.** Determines whether any result can be trusted. |
| **Realistic fill modelling** | High — makes existing results *honest* (worse-looking, truer). Doesn't chase new edge. |
| **Inverted-edge test** | Medium — must now be run with the daily-IC method. |
| **Formulaic alpha discovery** | **Downgraded from #1 to "do not build yet."** It is an overfitting machine; on this sample size it would have found the same garbage the random test just did. Revisit only with walk-forward + the corrected harness. |
| Extra indicators (SAR, Heikin-Ashi…) | ~Zero. More indicators is not more edge. |

The base rate supports this: of ~8 signals rigorously tested here, 3 validated and 5 came
back null. That ~37% is a realistic hit rate for *economically reasoned* signals. Mined
signals would be worse, not better.

---

# Part 5 — Backtest of every settled recommendation (2026-07-31)

311 settled recs (236 LIVE, 75 BACKFILL). Tested per the corrected rule: the unit of
independence is the **expiry cohort**, not the individual rec.

## The finding that governs everything else

| src | cohorts | rec_dates | expiries |
|---|---|---|---|
| LIVE | **1** | 2026-07-08 only | 2026-07-31 only |
| BACKFILL | 2 | 5 | 07-24, 07-31 |

**All 236 LIVE recs were written on one day into one expiry.** They share a single market
path. That is **one observation**, not 236 — no significance test on them is meaningful.
Everything below is description, not evidence of edge.

## POP calibration

| src | predicted | actual | miss |
|---|---|---|---|
| LIVE | 81.6% | 95.3% | +13.7pp |
| BACKFILL | 80.5% | 92.0% | +11.5pp |

One calm cohort cannot separate "model is conservative" from "we got a quiet month".

## The EV rule validated — and it inverts the win rate

| src | group | n | win % | return on capital |
|---|---|---|---|---|
| LIVE | trap (paid<need) | 185 | **96.8%** | **+1.89%** |
| LIVE | edge (paid>need) | 51 | 90.2% | **+16.95%** |
| BACKFILL | trap | 16 | **100.0%** | +21.3% |
| BACKFILL | edge | 59 | 89.8% | **+136.8%** |

The "trap" group wins *more often* and returns *~9x less per dollar risked*. This is the
clearest possible confirmation that **win rate is the wrong objective** and that the
`paid% > need%` column is the one to sort on.

## Payoff asymmetry (LIVE)

avg win **$207** · avg loss **−$476** · ratio **2.30x** · breakeven win rate **69.7%**

Stress on the realized fill quality:

| win rate | P&L | on capital |
|---|---|---|
| 95.3% (actual) | +$41,429 | +2.07% |
| 90% | +$32,812 | +1.64% |
| 80% (the POP target) | +$16,672 | +0.83% |
| 70% | +$533 | **+0.03%** |

At its own stated 80% target the book returns <1%. At 70% it is flat. The +2.07% came
from the tape being kind, not from the edge being large.

## Where the capital actually goes

| strategy | n | win % | P&L | ret/cap | paid | need |
|---|---|---|---|---|---|---|
| Cash-secured put | 84 | 97.6% | $29,193 | **+1.52%** | **0.018** | 0.180 |
| Call credit spread | 77 | 93.5% | $6,051 | **+14.81%** | 0.178 | 0.188 |
| Put credit spread | 74 | 94.6% | $5,968 | **+14.44%** | 0.168 | 0.186 |

**CSPs are the capital sink.** They collect 1.8% of width against a 18% requirement,
tie up the overwhelming majority of the $2.0M capital base, and return 1.52%. The
spreads return ~10x better per dollar. The book's headline +2.07% is CSP drag.

**Actionable:** filter CSPs out of the basket (or size them far smaller) and the same
selection returns materially more on the same capital.
