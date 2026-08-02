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
