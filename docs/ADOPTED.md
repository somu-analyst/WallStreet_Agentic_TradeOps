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
| BACKFILL | trap | 16 | **100.0%** | ~~+21.3%~~ |
| BACKFILL | edge | 59 | 89.8% | ~~+136.8%~~ |

> **CORRECTION (same day).** The BACKFILL percentages above were an artifact and are
> withdrawn. `_hiprob_scan_asof` set `risk: None` for cash-secured puts, so they persisted
> with `capital = 0` — 25 CSPs contributed $15,532 of P&L against a **zero denominator**.
> Fixed at source in both scanners (`risk = (K − credit) × 100`) and 89 historical rows
> repaired. Restated on real capital, **spreads only**, the two sources agree:
> BACKFILL **+18.79%** vs LIVE **+14.84%** — no "same inversion", just the same bug.
> Whole-book restated: LIVE +2.07%, BACKFILL +1.56%.
> The LIVE trap-vs-edge inversion (+1.89% vs +16.95%) is unaffected — it was never
> distorted by this, since LIVE CSPs always carried correct collateral.

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

---

# Part 6 — Crash behaviour & index-vs-stock (2026-07-31)

Correcting an earlier claim of mine: I said we could not backtest before 2026-07-02. **Wrong.**
A credit spread's OUTCOME depends only on where the underlying lands, and `stock_history`
has that from 1990 (9,227 days, 749 tickers). Only the ENTRY CREDIT needs modelling. So a
decade including 2018, COVID-2020 and the 2022 bear IS testable.

Method: 1σ-OTM put credit spread, 23 DTE, held to expiry, credit priced by Black-Scholes on
trailing 20d realised vol × 1.15 VRP.

**Calibration caveat (important):** the model collects a median **11.0%** of width where the
live book collects **19.0%**. Short-dated OTM puts carry a skew premium the model misses, so
**every absolute number below is too pessimistic.** The STRUCTURE is what's robust, not the levels.

## Crash behaviour — the structural finding

| Date | SPY move | Result |
|---|---|---|
| 2020-02-05 (COVID) | −13.4% | **−100% of risk** |
| 2022-08-25 | −11.3% | **−100%** |
| 2022-04-13 | −7.9% | **−100%** |
| 2025-02-18 | −7.5% | **−100%** |
| 2018-09-20 | −6.4% | **−100%** |

**A ~6–7% index drop is a total loss on the spread.** Max loss isn't a tail event; it's a
routine monthly move.

## One bad year erases many good ones — SPY by year

| Year | Win % | Return on risk |
|---|---|---|
| 2017 | 100% | +22.2% |
| 2018 | 73% | **−66.7%** |
| 2019 | 100% | +70.5% |
| 2020 | 82% | **−46.6%** |
| 2021 | 100% | +82.6% |
| **2022** | **64%** | **−179.4%** |
| 2023 | 91% | +61.4% |
| 2024 | 91% | +29.8% |
| 2025 | 91% | −14.0% |

10-year total: **−45%**. 2022 alone lost more than 2019+2021 gained. Answers the question
directly: **yes, emphatically.**

## Index vs single stocks — NOT significant

Common window 2020-08 → 2026-07 (every ticker sees the same tape, incl. 2022):

| Group | n | Win % | Per cycle | Worst | Sharpe |
|---|---|---|---|---|---|
| INDEX | 4 | 85.5% | −1.37% | **−100%** | −0.039 |
| STOCK | 20 | 86.7% | +0.97% | **−100%** | +0.050 |

**t = 1.49, p = 0.186 — not significant.** Stocks look better on the mean but the sample
cannot support the claim.

**A prior version of this ranking was contaminated** and is withdrawn: XOM/NVDA/MU/COST/
UNH/BA only have history from 2020-07 and therefore skipped the COVID crash entirely, while
SPY/QQQ/IWM/AMD/AAPL absorbed 2018 + COVID + 2022. Comparing them was survivorship, not skill.

**What actually dominates:** dispersion WITHIN single stocks (UNH −6.82%/cycle to NVDA
+8.54%) is far larger than any index-vs-stock gap. Ticker selection matters more than the
index/stock question — and worst case is −100% for every name in the table, both groups.

---

# Part 7 — Hedging a premium-selling book (2026-07-31)

Question: what hedges this? Tested on the same 2017-2026 cycles (SPY/QQQ/IWM, 23 DTE).

## The methodology trap, caught mid-analysis

First run priced every option at a single ATM vol. Results said tail puts and collars were
excellent. **Then I measured the actual skew in our own captured chains:**

| Underlying | ATM IV | 5% OTM | 10% OTM | 15% OTM |
|---|---|---|---|---|
| SPY | 14.1% | 20.0% (1.42x) | 25.4% (**1.80x**) | 33.0% (**2.34x**) |
| QQQ | 24.8% | 28.4% (1.15x) | 32.7% (1.32x) | 38.8% (1.56x) |
| IWM | 19.0% | 23.9% (1.26x) | 28.7% (1.51x) | 36.4% (1.92x) |

Flat vol underprices OTM puts badly. Re-run with skew fitted to that surface
(`iv_mult = 1 + 5.4 x OTM_fraction`) — **every conclusion reversed:**

| Variant | Flat vol (WRONG) | With real skew |
|---|---|---|
| BASE | +83% | **+121%** |
| TAIL PUT | +223% | **−506%** |
| COLLARED | **+1451%** | **−4016%** |
| WIDE OTM | −462% | **+271%** (best Sharpe 0.043) |

## Conclusions

**Buying tail protection is systematically −EV here.** Not because puts fail in crashes —
they pay — but you buy them EVERY cycle at a 1.5–2x vol markup and they expire worthless
~95% of the time. Premium bleed dwarfs the crash payoffs. Collars were worse: selling
closer to fund the hedge added risk *and* paid up for insurance.

**Selling FURTHER OTM won under skew** (+271%), reversing the flat-vol result — that is
where the skew premium is richest. Better to sell expensive tail risk than buy it.

**Structural facts surviving every variant:** worst case −100% on all of them; a 6–7% index
drop is still a total loss. No configuration removed the tail.

**Position sizing is the hedge.** If a full loss on any single cycle is survivable, there is
no need to buy protection at a 2x markup.

**Caveat:** calibration still off (model 9.8% of width vs 19.0% live), so RANKINGS are the
finding, not magnitudes.

---

# Part 8 — QuantConnect / LEAN for backtesting? (suggestion, 2026-07-31)

Asked whether to use QuantConnect for backtests. Evaluated against the limitations this
session actually exposed, not against its feature list.

## The honest framing: our bottleneck is DATA, not tooling

Tonight's three biggest problems were all data problems:

| Problem found | Root cause |
|---|---|
| LIVE recs = **1 cohort** (one rec_date, one expiry) | `options_openbb` starts 2026-07-02 — 20 days of quotes |
| Model collects **9.8% of width** vs **19.0%** live | No historical IV surface, so credits are modelled not observed |
| Every backtest assumes **mid-price fills** | No historical bid/ask before 07-02 |

We already have a perfectly good backtest *engine* — we wrote several tonight. What we do
not have is **years of real option quotes**. That is exactly what LEAN sells.

## What it would genuinely solve

- **Historical options quotes with bid/ask.** LEAN exposes `QuoteBar` objects carrying
  bid/ask OHLC consolidated from NBBO (AlgoSeek US Equity Options dataset). This is the
  single thing blocking a multi-cohort credit-spread study.
- **Realistic fills** — fill models price off bid/ask rather than mid. That is open item #9.
- **Real historical skew** — instead of our fitted `1 + 5.4 x OTM` approximation, the actual
  surface. Tonight proved this is not a detail: pricing at flat vol reversed every hedge
  conclusion (TAIL PUT +223% became −506%).

## What it would NOT solve

- **Statistical discipline.** Cohort independence, overlap, cross-correlation — LEAN will
  happily compute a beautiful, meaningless Sharpe. We produced the pooled-IC error with our
  own code and would reproduce it there. Tooling does not confer rigour.
- **The live system.** LEAN is a separate C#/Python research ecosystem. It does not replace
  the Telegram bot, the dashboard, the capture lane, or the MCP server.
- **The capture-forward DB.** Still needed for live ops and for data LEAN does not carry.

## Suggested use — research lane only, and scoped

Use it for the specific questions our own data **cannot** answer, then bring the *findings*
back. Do not migrate the platform.

1. Multi-year, multi-cohort put-credit-spread study on **real quotes** — the study that is
   currently impossible (we have 2 expiry cohorts; this needs ~50+).
2. Re-run the hedge comparison (Part 7) against the **real** historical skew surface, to
   confirm or overturn the tail-put finding.
3. Calibrate `paid%` vs `need%` against years of actual credits, replacing the single
   19.0% observation.

## Before committing

- **Verify options data cost.** Options quote data is the expensive tier everywhere; confirm
  the actual subscription/download price for the coverage years wanted.
- **Verify coverage start date** for the underlyings that matter here.
- Budget real learning time — LEAN's architecture is nothing like this codebase.

## Verdict

**Worth trialling for research, not for migration.** It plugs the one hole we cannot plug
ourselves (historical option quotes) and leaves everything we do well untouched. But note
the discipline problem is ours to keep solving either way — a better engine fed the same
flawed assumptions returns better-looking wrong answers.

Sources: QuantConnect docs — Equity Options historical data, US Equity Options (AlgoSeek).

---

## Head-to-head: QuantConnect vs Quantiacs (both reviewed 2026-07-31)

Vitals from the **GitHub API**, not marketing pages:

| | **QuantConnect / LEAN** | **Quantiacs** |
|---|---|---|
| Main repo stars | **21,011** | 82 (`toolbox`) |
| Last push | **2026-07-31 (today)** | 2025-12-19 (**~7 mo stale**) |
| Public repos | 93 | 33 (mostly small strategy samples) |
| **OPTIONS data** | ✅ **Yes** — bid/ask `QuoteBar`, AlgoSeek + a `Lean.DataSource.ThetaData` integration | ❌ **None found** |
| Asset classes | Equities, **options**, futures, FX, crypto, CFD | Futures (49), S&P500/NASDAQ equities, crypto |
| History depth | Multi-year (dataset dependent) | Up to **25 years, free**, back to 1990 |
| Survivorship-free | Yes | Yes (explicitly marketed) |
| Frictions modelled | Yes (fill/slippage/fee models) | Yes (fees, slippage) |
| Cost | Free engine; **options data is a paid tier** | **Free** data + toolbox |
| Language | C# (engine), Python | Python, Matlab |
| Business model | Platform + data subscriptions | Futures/crypto **contests**, allocates capital to winners |

### Verdict for THIS project

**QuantConnect — trial it (research lane only).** It is the only one of the two that carries
the thing we actually lack: years of real option quotes with bid/ask. That single asset
would fix the 1-cohort problem, the 9.8%-vs-19.0% calibration gap, and the mid-price fill
assumption in one move.

**Quantiacs — not applicable. No options data.** This is not a quality judgement; it is a
category mismatch. Quantiacs is a strong, genuinely free futures/crypto research platform
whose business is contest-based capital allocation. For an equity-**options** book it cannot
answer any of our open questions, and its main toolbox has been stale ~7 months.

**If cost blocks QuantConnect's options tier**, the fallback is not Quantiacs — it is to
keep accruing our own capture-forward DB (already ~20 days and growing daily, which is
exactly how it reaches multi-cohort on its own), or price a direct options-data vendor
(ThetaData appears as a first-party LEAN integration and is worth a quote).

## 8.1 - Databento (asked 2026-07-26, written up 2026-08-08)

Asked alongside the OpenBB-vs-yfinance question and answered in conversation at the time,
but never written down - so it kept resurfacing. Recording it here closes that loop.

**What it is:** an institutional market-data vendor selling normalised historical and live
data straight from venue feeds - full order book (MBO/MBP), trades, and OHLCV, with
nanosecond timestamps and point-in-time correctness. It is a paid, usage-priced service; the
free tier is a trial credit, not a lane you can run a daily job on.

**Where it would genuinely help us.** Exactly one place, and it is the same gap Part 8
identified: OPTIONS QUOTE HISTORY. Our `options_openbb` table only reaches back as far as we
have been capturing, which is why `_hiprob_scan_asof` backfill is bounded and why
`/recperf` must keep LIVE and BACKFILL rows apart. Databento sells OPRA history, which would
retire that limitation outright.

**Why it is still not adopted:**

| Consideration | Finding |
|---|---|
| Cost | Usage-priced. OPRA is the largest feed in US markets - a wide chain history over years is not a hobby-budget purchase |
| Our actual blocker | Not tooling and not equity prices. `stock_history` already goes back to 1990 and cost nothing |
| Free alternatives | yfinance + OpenBB-cboe already cover spot, chains and fundamentals for 741 names |
| Self-capture | The DB accrues forward every day at zero marginal cost, and now stores macro vintages and Reddit snapshots the same way |

**Verdict: not adopted, and the reason is unchanged.** Buying options history only makes
sense once a specific question is BLOCKED by its absence and that question is worth the
invoice. Every validation this project has run so far - the pooled-t-stat retraction, the
Investment Clock rejection, the earnings-drift asymmetry, the 89%-firing big-move alert -
was answerable from data we already hold. When a test finally fails for want of deeper
options history rather than for want of edge, get a Databento quote and price it against
ThetaData. Until then it is a solution shopping for a problem.


---

# Part 9 — Validation pass: re-testing what we already claimed (2026-08-02)

Three backlog items (tracker IDs 7, 32, 33) asked the same question from three angles:
**does this system have edge, or does the measurement flatter it?** Everything downstream —
sizing, CSP filtering, allocation — rests on numbers this pass re-checks. Ran together
because fixing sizing against a fake signal would be optimising noise.

Method throughout: daily cross-sectional IC, de-overlapped, per
`.claude/rules/bot-conventions.md`. **Harness sanity gate: 300 random signals → 3.0% false
positives (expected 5%).** The harness is sound; results below are about the signals.

## 9.1 — Claim A: Rotation RRG momentum axis · **WITHDRAWN**

Claimed `IC +0.14 (p<1e-7), 1,542 obs`.

First problem: `rotation_watch` holds **6 distinct dates**. The 1,542-obs figure cannot
have come from it. Rebuilt the RRG axes from price history (33 ETFs × 1,500 days, RS vs
SPY, 63d ratio / 21d momentum), scored against **excess** fwd return vs SPY:

| horizon | pooled (banned) | daily-IC (correct) | verdict |
|---|---|---|---|
| fwd 5d  | IC +0.010, t=+2.25, N=46,596 | IC −0.005, **t=−0.28, p=0.78**, N=282 days | no edge |
| fwd 10d | IC +0.028, t=+5.98, N=46,431 | IC +0.012, **t=+0.41, p=0.68**, N=140 days | no edge |

The pooled stat turned t=+0.41 into t=+5.98. Same inflation as the `/debate` weight.

**The separate quadrant result stands** — "Weakening underperforms −1.6%/10d vs SPY" is a
hit-rate-vs-baseline measurement, which makes no independence claim and was never affected.

## 9.2 — Claim B: Market Radar put-flow · **DOWNGRADED to suggestive**

Claimed `QQQ t+5 corr +0.37, p<0.001` on ~104 days.

This one is a *time series*, not a cross-section, so the fix is de-overlapping rather than
daily IC. t+5 windows sampled daily overlap 4-of-5 days: **104 days is ~21 independent
draws, and +0.37 at n=21 is p≈0.10 — not p<0.001.** The reported p-value was never
attainable from that sample size.

Reconstructing the nearest available proxy (index put/call volume ratio vs |QQQ fwd-5d|,
146 days) and sweeping the five equivalent sampling offsets:

| offset | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| corr | +0.007 | **+0.360** | +0.002 | −0.172 | −0.057 |

Five equally-valid samples of the same data swing +0.36 to −0.17. Note offset 1 reproduces
roughly the originally-claimed magnitude — which is the point: that number was reachable by
sampling luck.

**Caveat:** this proxy is not certainly the original pillar's exact definition (the source
script's signal lived in scratchpad). The n=21 arithmetic is definitive regardless of
definition; the offset sweep is corroborating, not conclusive.

Kept in the UI as **SUGGESTIVE**, not established. Turbulence remains the primary gauge.

## 9.3 — ID 32: Inverted-edge test · **NO inverted edge — do not build it**

`scn_revert` / `gex` / `left_skew` had hit-rate 95% CIs entirely below 50%. A reliably wrong
signal is tradeable inverted, so this was worth checking. It does not survive.

The fires are **clustered**: `scn_revert`'s 1,516 observations span **17 dates** across 354
tickers. On a given day almost every ticker resolves with the market, so 1,516 is nearer 17
independent draws. Collapsing each date to one observation:

| model | n | naive hit% | naive p | → de-overlapped hit% | independent dates |
|---|---|---|---|---|---|
| scn_revert | 1,162 | 45.3% | 0.0014 "INVERTED" | **53.9%** | 3 |
| scn_zrev | 379 | 43.3% | 0.0101 "INVERTED" | **53.2%** | 3 |
| gex | 107 | 40.2% | 0.053 | 29.7% (p=0.21) | 7 |
| scn_building | 3,620 | 54.1% | 0.0000 "EDGE" | 58.1% | 4 |

Both "inverted" signals **flip to above 50%** once dates stop double-counting. The wrongness
was an artefact, not a signal. `gamma_pin` shows p=0.019 de-overlapped, but at n=6 dates
across 13 models tested (~0.65 false positives expected at α=0.05) that is not evidence.

**`scn_building`'s edge is also not established** — 3,620 fires over 4 independent dates.
It is not disproven either; it simply has not been tested yet at an honest sample size.

**Outcome: no inverse scanner built.** This item is closed as a save, not a feature.

## 9.4 — ID 33: Realistic fill modelling · **the real cost, measured**

Every backtest except the 50%-exit test books entry at the **mid**. Re-priced all settled
put recommendations off their own real `options_openbb` bid/ask on their own `rec_date`.
`f` = fraction of the half-spread given up on each leg. Outcome re-derived from strikes +
`settle_px`, so only the entry credit changes.

**Median quoted spread on the short leg: 17.6% of mid. 75th pct 35.8%. 90th pct 54.4%.**

| fill assumption | n | win% | mean ret | total ret | credit kept |
|---|---|---|---|---|---|
| mid (what we assume today) | 203 | 94.6% | **+7.25%** | +1471% | 100% |
| good execution (f=0.25) | 201 | 94.5% | +5.31% | +1067% | 93% |
| midway to touch (f=0.50) | 190 | 94.2% | **+3.81%** | +724% | 87% |
| cross the spread (f=1.00) | 169 | 93.5% | +2.54% | +428% | 74% |

**Mid-pricing overstates per-trade return by roughly 2× at a realistic fill.** Win rate
barely moves (94.6% → 94.2%) — this is not about being wrong more often, it is that the
credit collected is the entire edge, and the spread eats half of it.

Note the shrinking `n`: at f=0.5, **13 recs no longer have a positive credit at all** and at
f=1.0, 34 do not. Those are structures that only exist at mid.

| source | mid | f=0.25 | f=0.50 | cross |
|---|---|---|---|---|
| LIVE (n=154) | +8.02% | +5.86% | +4.27% | +3.31% |
| BACKFILL (n=50) | +4.88% | +3.65% | +2.53% | +0.65% |

Widest-spread names (BIIB, GILD, SPXS, EFA, FXI) quote **spread = 200% of mid — i.e. no bid
at all**. Those legs are untradeable at any modelled price and need a liquidity gate, not a
slippage haircut.

### What to change
1. **Adopt f=0.50 as the default backtest assumption.** It is the honest midpoint and the
   one a limit order at the mid actually achieves only sometimes.
2. **Add a liquidity gate to the scanner** — reject legs with no bid, or spread > ~35% of
   mid (the 75th percentile). This is the single highest-value fix here.
3. Restate the $10k projection at f=0.50 — the existing figure is a mid-fill number.

## 9.5 — Standing

| ID | item | outcome |
|---|---|---|
| 7 | Re-test 3 caveated claims | Rotation **withdrawn**; Radar **downgraded**; skew panel **untestable** (21 dates → 4 independent) |
| 32 | Inverted-edge test | **No inverted edge.** Closed, nothing built |
| 33 | Realistic fill modelling | **Measured: ~2× overstatement.** Two follow-ups queued |

Net: two claims removed from the UI, one strategy idea correctly killed before it was built,
and one quantified correction that makes every existing backtest number honest. No new edge
was found in this pass — that is the expected outcome of a validation pass, and preferable
to the alternative.

---

# Part 10 — GEX: we had been testing the wrong claim (2026-08-02)

Every prior test scored GEX on **direction** — the `gex` model's 40.2% hit rate over 107
fires, p=0.21 once same-day fires stop double-counting. On that basis it was written off.

But the dealer-hedging story makes **no directional claim at all**. It says positive net
GEX means dealers buy dips and sell rallies, so realised vol is *suppressed*; negative
means they sell weakness and buy strength, so vol is *amplified*. The testable claim is
about the SIZE of subsequent moves. That is what this measures.

**Proxy note:** real GEX needs per-strike Black-Scholes gamma, which needs IV — available
only in `options_openbb` (21 days). To reach 7 months this uses the OI-weighted proxy
(net OI × strike², the same shape `dashboard.py` already uses). It preserves sign and
ordering, which is all these tests need, but it is not the gamma-weighted quantity.

## 10.1 — The first harness failed its own sanity gate

Raw net-GEX scored cross-sectionally against forward realised vol gave **IC +0.146,
t=+3.85, p=0.0008**. Then the gate: **15% of RANDOM signals also passed** (expect ~5%).
The number was discarded, not reported. Two causes, both the same mistake:

1. **Level effect.** Comparing raw GEX *across tickers* mostly ranks tickers, not states —
   big-OI index names sit at systematically different GEX *and* vol levels, so any
   persistent per-ticker quantity scores. Fixed by z-scoring each ticker against its own
   history.
2. **Persistence.** Forward realised vol is strongly autocorrelated, so consecutive daily
   ICs aren't independent even sampled every 5 days. Fixed by sampling at 2× the horizon.

| H | step | signal | IC | t | p | days | gate | verdict |
|---|---|---|---|---|---|---|---|---|
| 5 | 5 | raw | +0.146 | +3.85 | 0.0008 | 25 | **14.5%** | harness unreliable |
| 5 | 10 | raw | +0.143 | +2.25 | 0.048 | 11 | 6.5% | significant, **sign wrong** |
| 5 | 10 | z-scored | +0.131 | +1.86 | 0.096 | 10 | 6.5% | not significant |
| 10 | 10 | z-scored | +0.186 | +2.53 | 0.035 | 9 | 9.0% | significant, **sign wrong** |

Cross-sectionally, higher GEX goes with *higher* forward vol — the opposite of theory.
That is the level effect surviving even the z-score: the names carrying the most gamma are
simply the most volatile names.

## 10.2 — Framed as the theory actually states it, the sign flips to correct

The claim is a **time-series** one: *when this underlying's own GEX is high, its own next
week is quieter*. Split each index against its own median:

| horizon | ticker | high-GEX fwd vol | low-GEX fwd vol | diff | t | p | n |
|---|---|---|---|---|---|---|---|
| 5d | SPY | **10.2%** | **14.0%** | −3.8pp | −1.77 | 0.091 | 12/12 |
| 5d | QQQ | **16.6%** | **23.6%** | −7.0pp | −1.97 | 0.061 | 12/13 |

Both **correctly signed**, both economically large (SPY's forward vol is ~27% lower in the
high-GEX half; QQQ's ~30% lower), and **neither significant** at n=12 per bucket.

## 10.3 — What this changes

**This is the first GEX result in this project that points the right way.** It is not proof
— p≈0.06–0.09 on 12 observations is exactly the sample size that produces false positives,
and this project has already been burned twice by acting on underpowered results.

What it does justify:
- **Keep GEX as a volatility-REGIME read, drop it as a direction signal.** That is already
  how `/gexplan` frames it ("expect chop" vs "expect velocity") — this is the first
  evidence that framing is the right one.
- **The natural use is strategy selection and sizing**, not entries: premium-selling suits
  a +GEX regime, and −GEX argues for smaller size or long premium. That is directly
  testable against the existing `hiprob_recs` book.
- **Do not build a directional GEX scanner.** Cross-sectionally the sign is wrong, and
  directionally it is a coin flip.

**Re-test gate:** revisit when there are ≥40 independent observations per bucket (roughly
8 more months at 5-day sampling), or sooner using `options_openbb`'s real gamma once that
table has more history.


---

# Part 11 - Scenario tools & decision flowcharts (2026-08-07)

Asked to find well-proven, time-tested scenario tools and flow charts worth adopting.
Verified every repo through the GitHub API rather than trusting stars - that check has
twice caught something that looked credible and wasn't (QuantMuse 2,824 stars / 9 commits;
the 24.95%-CAGR repo with 0 commits).

## 11.1 - What's actually out there

| Repo | Stars | Contributors | Last push | Verdict |
|---|---|---|---|---|
| **fortitudo.tech** | 303 | **4** | 2026-07-09 | **The real find** - Entropy Pooling |
| Riskfolio-Lib | 4,431 | 6 | 2026-06-22 | Real, but overlaps `/allocate` |
| quantstats | 7,528 | 30 | 2026-07-20 | Reporting, not scenarios |
| pyfolio | 6,390 | 39 | **2023-12-23** | **Dead 2.5 years** - Quantopian is defunct |
| risk-lab | 0 | 1 | 2026-03-07 | Solo hobby project |
| qrisklab | 10 | 1 | 2026-03-11 | Solo |
| financial-risk-analyzer | 8 | 1 | 2025-10-14 | Solo, stale |

**Four of seven fail on inspection.** pyfolio is the trap: 6,390 stars is 20x what
fortitudo.tech has, and it has been unmaintained since 2023.

## 11.2 - Entropy Pooling: the one worth having

Meucci's framework (2008), productionised by fortitudo.tech. It answers exactly the
question this system cannot currently answer:

> *"If gold rallies 5%, what happens to MY book?"*

The naive approach shocks gold and leaves everything else alone, which is wrong - gold does
not move in isolation. Entropy Pooling takes the **joint** distribution of all assets,
applies your view as a constraint, and finds the minimum-relative-entropy re-weighting
consistent with it. Every other asset then moves as the historical joint distribution says
it should.

**Why it fits here:** it needs a panel of joint scenarios, and we have one - `stock_history`
back to 1990, already including 2000, 2008, 2020 and 2022. The scenarios are *real
historical days*, so correlations are whatever they actually were rather than whatever a
copula assumes.

**What it would replace:** the current crash analysis picks historical windows by hand.
Entropy Pooling generalises that to any view, with the correlation structure handled
properly.

## 11.3 - Decision flowcharts: what is genuinely time-tested

| Framework | Vintage | Testable here? | Value |
|---|---|---|---|
| **Merrill Lynch Investment Clock** | 2004 | Yes - needs growth + inflation, both in the macro lane | **Highest** |
| CBOE BXM / PUT indices | 1986/2007 | Already the evidence base for premium selling | Already used |
| Sector rotation cycle | 1990s | Already built (RRG) | Have it |
| Fed real-rates -> gold | - | Now encoded in `/whymoved` | Just shipped |
| Dalio All Weather quadrants | 1996 | Partly - needs an inflation proxy | Overlaps the Clock |
| Elliott Wave / Gann | 1930s | **No - not falsifiable** | Reject |

**The Investment Clock is the one to build.** Two axes (growth rising/falling, inflation
rising/falling) give four quadrants, each with an expected asset leadership order -
Reflation -> bonds, Recovery -> stocks, Overheat -> commodities, Stagflation -> cash. It is
simple, 20+ years old, and **makes a falsifiable claim testable against 1990-2026 history**
with the walk-forward harness.

That last point is what separates it from the rest. Most "flowcharts" in finance are
unfalsifiable; the Clock is not.

## 11.4 - Recommendation

1. **Build the Investment Clock and TEST it** before wiring it to anything. If quadrant
   leadership does not hold out-of-sample on our own history, say so and stop - exactly the
   trap Parts 4 and 9 documented.
2. **Trial Entropy Pooling** for book scenarios. Feed it `stock_history`, ask "gold +5%",
   and check the implied book move against what actually happened on real gold-rally days.
   If the two disagree badly, the panel is wrong.
3. **Adopt nothing else.** Riskfolio-Lib duplicates `/allocate`; quantstats duplicates
   `/recperf`; the three solo repos are the QuantMuse pattern again.

**Not started - logged as tracker items 131/132, not shipped.**

---

# Part 12 - The Investment Clock, tested and rejected (2026-08-08)

Part 11 recommended building the Merrill Lynch Investment Clock **only if it survived a test
first**. It did not. This part records the result so nobody rebuilds it in six months.

Harness: `tools/test_investment_clock.py`. 832 months, 1957-02 to 2026-06, from FRED
(`INDPRO`, `CPIAUCSL`, `SPASTT01USM661N`, `GS10`, `TB3MS`, `PPIACO`). All macro inputs lagged
**2 months** so nothing uses a number before it was published. Four pass/fail gates were
written down **before** the run.

## 12.1 - The result

| Gate | Result |
|---|---|
| aggregate t > 2.0 | **PASS** t=+2.68 |
| beats block-shuffled regimes | **PASS** p=0.014 |
| beats a static always-stocks book | **FAIL** t=-0.17 |
| >=3 of 4 quadrant maps correct | **FAIL** 1 of 4 |

Only **Recovery -> stocks** is right. The other three are wrong:

| Quadrant | Clock says | Actually wins | Designated asset's excess |
|---|---|---|---|
| Reflation | bonds | **stocks** (+6.00%) | -0.26% |
| Recovery | stocks | **stocks** (+6.63%) | +6.63% (match) |
| Overheat | commodities | **bonds** (+1.40%) | +0.23% |
| Stagflation | cash | **bonds** (+1.70%) | +1.13% |

## 12.2 - Why the headline number lied

The aggregate looked good - +1.89%/yr over an equal-weight basket, t=+2.68, and it beat a
block-shuffled null at p=0.014. Every one of those numbers is real. They are also **beside
the point**, because the entire edge is the equity risk premium arriving through the one
quadrant that happens to designate stocks. Against the benchmark a person would actually
hold - all stocks - the Clock adds **-0.25%/yr, t=-0.17**.

This is the Part 9 lesson in a new costume: *the null you choose decides the answer.* An
equal-weight basket containing two assets that lose to stocks over 70 years is not a
benchmark, it is a handicap. The gate that caught it was "beat the best static allocation",
and it is now the gate to apply to any regime or rotation idea.

## 12.3 - The one real finding

The growth axis is close to noise; the **inflation axis is not**. Absolute annualised returns:

| Quadrant | stocks | bonds | commodities | cash |
|---|---|---|---|---|
| Reflation (infl falling) | **+12.05%** | +5.79% | +2.10% | +4.26% |
| Recovery (infl falling) | **+12.87%** | +5.37% | +2.58% | +4.14% |
| Overheat (infl rising) | +3.14% | **+5.82%** | +4.66% | +4.07% |
| Stagflation (infl rising) | +0.38% | **+5.26%** | +3.91% | +4.69% |

The two falling-inflation rows are near-identical and so are the two rising-inflation rows -
that is the growth axis contributing nothing. But **stocks earn ~12.5%/yr when inflation is
falling and ~1.5%/yr when it is rising**, and bonds are flat near 5.5% in all four states.

A one-axis rule (inflation falling -> stocks, rising -> bonds) gives CAGR 9.00% vs 6.65%,
Sharpe 0.50 vs 0.24, max drawdown **-22.0% vs -53.3%**.

**This is not adopted either**, for two stated reasons:

1. **It is in-sample.** It was found by reading the result matrix, not pre-registered. Its
   return edge over always-stocks is **not significant**: +1.86%/yr, t=+1.46 (halves +2.10
   t=+1.19 and +1.62 t=+0.89 - same sign, neither conclusive).
2. **The equity series is price-only.** No dividends, so always-stocks is understated by
   roughly 2-3%/yr and most of the CAGR gap would close on total-return data.

The Sharpe and drawdown gap is the part least likely to be an artifact, because halving a
53% drawdown is not something a missing dividend explains. Logged as tracker **ID 168**:
re-run on total-return series, then track it **forward** rather than re-testing the same 832
months.

## 12.4b - The one-axis rule, retested on TOTAL returns (2026-08-08)

Part 12.3 kept one finding alive and attached two objections to it. The bigger objection -
**price-only equity** - is now tested, using Shiller's `ie_data` (monthly S&P price AND
dividends, one consistent source that also supplies CPI and the 10y rate). 1,169 months,
1926-2023, CPI lagged 2 months. Harness: `tools/test_inflation_rule.py`.

**The FINDING survives.** Inflation direction really does split equity returns, and adding
dividends slightly WIDENS the gap rather than closing it:

| State | stocks (total return) | stocks (price only) | bonds |
|---|---|---|---|
| inflation FALLING | **12.95%** | 9.17% | 4.65% |
| inflation RISING | **8.58%** | 4.97% | 4.93% |

Gap, falling minus rising: **+4.37%/yr** on total return, versus +4.20% price-only.

**The RULE dies.** Switching to bonds when inflation rises costs **-1.71%/yr against
always-stocks (t=-1.35)**, and both halves agree (-3.34% and -0.09%).

| Strategy | CAGR | vol | Sharpe | maxDD |
|---|---|---|---|---|
| one-axis rule | 8.91% | 11.04% | 0.40 | -71.6% |
| **always stocks** | **10.16%** | 15.43% | 0.40 | -81.8% |
| static 60/40 | 8.28% | 9.74% | 0.38 | -61.0% |

**Why it looked good before, in one sentence:** without dividends, rising-inflation equities
appeared to earn ~1.5%/yr, so almost anything beat them - but their real total return is
**8.58%**, which comfortably beats bonds' 4.93%, so the switch was never justified. The
entire apparent edge was the missing dividend, exactly as flagged.

Sharpe is a dead heat (0.40 vs 0.40) and the drawdown improvement (-71.6% vs -81.8%) is not
worth 1.7%/yr of CAGR when both numbers are catastrophic.

**Not adopted.** What to keep is the descriptive fact - equities pay you far less while
inflation is rising - as CONTEXT in the macro read, never as a switching signal.

**The transferable lesson:** a caveat you write down is only worth something if you later go
and test it. This one was recorded the same day and overturned the conclusion within hours.

# Part 13 - Entropy Pooling: ADOPTED (2026-08-08)

The first thing in this whole review sequence that PASSED its pre-registered test. Parts 4,
9, 11 and 12 all ended in rejection; recording a pass matters as much as recording a failure,
because otherwise the file reads as reflexive scepticism rather than measurement.

**The method.** Meucci's Entropy Pooling takes a panel of historical JOINT scenarios and
re-weights them so a stated view holds on average, moving the probabilities as little as
possible (minimum relative entropy). Package: `fortitudo.tech` 1.2.4 (pulls `cvxopt`).

**The test, exactly as pre-registered in tracker row 132.** Feed `stock_history` as the joint
panel, impose "GLD +5% over 21 days", and compare the IMPLIED move of every other asset
against what ACTUALLY happened on real gold-rally windows. Harness:
`tools/test_entropy_pooling.py`, 1,500 overlapping 21-day windows, 6 assets.

| Asset | baseline | EP implied | actual (386 real windows) | error |
|---|---|---|---|---|
| SPY | 1.36% | 1.53% | 1.89% | -0.36 |
| QQQ | 1.58% | 1.71% | 1.73% | -0.02 |
| TLT | -0.64% | 0.10% | 0.67% | -0.57 |
| IWM | 1.21% | 1.58% | 2.11% | -0.53 |
| USO | 2.48% | 2.45% | 2.16% | +0.29 |

**Mean absolute error 0.35pp on the non-viewed assets; direction correct 5 of 5.** It
reproduced the historical record without being shown which windows were the gold rallies.

**Why it earns its place.** Our crash analysis uses HAND-PICKED windows, so it can only
answer questions we thought of in advance. This answers an arbitrary what-if from the same
history, and critically it keeps real cross-asset correlations intact rather than assuming a
beta. Shipped as `/whatif TICKER +N` and a Streamlit tab; the book's own tickers are pulled
into the panel automatically, so it reports the implied move on positions actually held.

**The honest framing kept in the output:** "Impl%" is the average outcome ACROSS HISTORY WHEN
THIS HAPPENED. That is a different and more defensible question than "what will happen", and
the caption says so rather than letting the number imply a forecast.

**Coherence check also run:** opposite views must not give the same answer. GLD +5% implies
SPY +1.53%; GLD -5% implies SPY -0.32%.

---

## 12.4 - What carries forward

- **Benchmark against the best static allocation**, never only against a basket average.
- **Read the per-cell matrix, not the aggregate.** The aggregate hid a 1-of-4 hit rate.
- Pre-committed gates work. The verdict line said HOLDS on the first two gates alone; the
  two written down afterwards are what produced the correct answer.

---

# Part 14 - The academic factor zoo, tested (2026-08-08)

Row 193 asked whether the HKU Alpha Zoo's 450+ published factor definitions are worth
mining. Ten were pre-registered and tested. Harness: `tools/test_alpha_zoo.py`.

## 14.1 - The protocol, fixed before the first run

Testing many ideas at p<0.05 manufactures winners by arithmetic: 10 dead factors give about
one "significant" hit, 450 would give ~22. So the method was written down first:

1. The 10 factors were **named before any was run** - none added, dropped or re-specified
   after seeing a score.
2. None has a free parameter, so there is nothing to fit and `daily_ic` is the right tool.
3. Daily cross-sectional IC, de-overlapped by the 21-day horizon. Never a pooled t-stat.
4. **Benjamini-Hochberg FDR across all 10** - ten tests at 5% is not a 5% error rate.
5. Sanity gate first: 7% of random signals passed (expect ~5%, >10% means broken harness).
6. **Losers reported.** A table of only the winners is how the zoo earned its reputation.

Panel: 492 tickers x 2,931 days (2015-2026), from `stock_history` alone.

## 14.2 - The result: nothing survives

| Factor | expected | IC | t | p | sign |
|---|---|---|---|---|---|
| prox_52w_high | + | +0.0474 | +1.25 | 0.221 | ok |
| momentum_12_1 | + | +0.0435 | +1.68 | **0.098** | ok |
| mom_vol_scaled | + | +0.0417 | +1.40 | 0.169 | ok |
| idio_vol | - | +0.0364 | +1.50 | 0.140 | **WRONG** |
| reversal_36m | - | +0.0303 | +1.13 | 0.268 | **WRONG** |
| low_volatility | + | +0.0228 | +0.67 | 0.506 | ok |
| skewness | - | +0.0196 | +1.14 | 0.260 | **WRONG** |
| illiquidity | + | -0.0079 | -0.38 | 0.703 | **WRONG** |
| max_daily | - | +0.0033 | +0.12 | 0.904 | **WRONG** |
| reversal_1m | - | -0.0004 | -0.02 | 0.987 | ok |

**Raw p<0.05 survivors: 0 of 10** (chance alone would give ~0.5). **After FDR: 0.**
And **5 of 10 carry the wrong sign** against their own published direction.

## 14.3 - The caveat that keeps this honest

This test is **underpowered**, and saying so matters more than the headline. De-overlapping
a 21-day horizon leaves only **37-72 independent dates** per factor. Detecting a true IC of
0.04 on ~50 observations is hard, so "nothing survives" is NOT proof these factors are dead
- it is proof they are not strong enough to find in this panel at this horizon.

What the wrong signs add is different and more damning: if these were weak-but-real effects,
they should at least lean the right way. Half of them do not, which looks like noise rather
than faint signal.

## 14.4 - Verdict

**Do not ship any of them, and do not mine the remaining 440.** If ten of the most-cited
factors in finance cannot clear a correctly-specified test on our own universe, screening
440 more would mostly produce false positives - which is the exact failure this project
already paid for once with the pooled rank-IC t-stat.

The one thing worth carrying forward is `momentum_12_1`: right sign, p=0.098, the closest
to real. **Track it forward** rather than re-testing the same panel.
