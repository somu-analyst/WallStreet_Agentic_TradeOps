# Strategy Build Tracker

Full menu of income / opportunity / event / relative-value strategies for `telegram_bot_optimized.py`,
built one-by-one. Marked ✅ after implemented **and** verified.

**Curation rule (why something is / isn't queued):** a row is *queued to build* only if it is (a) a
distinct tradeable strategy, (b) feasible with data we actually have, and (c) not already in the bot.
Everything else is still listed below under **Already in bot**, **Infrastructure**, or **Deferred/Infeasible**
so nothing is hidden.

**Reality note:** none of these are "sure-thing" edges. They are screeners; validate vs DB history
(`/validate-signal`) before trusting. Backtests so far are low-N / weak.

## 1. Build queue (feasible, distinct, ordered by recommendation)
| # | Strategy | Command | Status | Commit | Notes |
|---|----------|---------|--------|--------|-------|
| 0 | WAN-streamer — 24-model ensemble stream + AI chat | `/wan` | ✅ Done | `8f7fbb5` | 15-min job, daily dedup |
| 1 | Earnings IV-crush income scanner | `/earnvol` | ✅ Done | `075a8d1` | IV-rank + expected move |
| 2 | Wheel CSP income optimizer | `/wheel` | ✅ Done (pre-existing) | — | already had annualized yield + POP; left as-is |
| 3 | Covered-call income (yield on held/long names) | `/cc` | ✅ Done | `c1dcd63` | OTM calls ranked yield vs call-away POP; IVR + earnings flag |
| 4 | Pairs / statistical mean-reversion (within-sector z-score) | `/pairs` | ✅ Done | `3d73271` | spread z-score + OU half-life; risky screen, not arb |
| 5 | Calendar / diagonal spreads (theta + vega, term structure) | `/calendar` | ✅ Done | pending | ATM call calendar, front/back IV ratio |
| 6 | Iron condor / strangle range-income optimizer | `/condor` | ✅ Done | pending | ~1-EM shorts, defined-risk wings; POP + RoR |
| 7 | Seasonality engine (current-month avg/win, DoW, turn-of-month) | `/season` | ✅ Done | pending | on-the-fly ~10y yfinance, cached 24h |
| 8 | Sector rotation / relative-strength ranker | `/rotate` | ✅ Done | pending | 12 sector ETFs, blended 1/3/6-mo RS vs SPY, 1h cache |
| 9 | Cross-sectional mean-reversion (short-term reversal) | `/revert` | ✅ Done | pending | 5d return z-score vs universe; pure stock_daily |
| 10 | Macro event positioner (FOMC/CPI/NFP drift+vol) | `/macro` (enhance) | ⛔ Deferred | — | needs econ-event calendar feed (Finnhub key); /macro data already exists |
| 11 | Dividend-capture / ex-div assignment risk | `/divcap` | ✅ Done | pending | fwd yield + ex-date via yfinance .info, 12h cache |
| 12 | Put-write / covered-call systematic index (PUT/BXM style) | `/pwindex` | ✅ Done | pending | APPROX BS-priced backtest vs B&H; labeled educational |

| 19 | Positioning builder (new/increasing OI + price starting) | `/building` | ✅ Done | `e1cf636`/`404e9c9` | LONG=calls / SHORT=puts vs standing OI; stage S/I/C; options_change+stock_daily; dashboard hub + **30-min scheduled stream** (daily dedup) |

| 20 | Portfolio risk optimizer (Aladdin risk side) | `/allocate` | ✅ Done | pending | max-Sharpe/min-var/risk-parity on 6y covariance; weight-capped; native; dashboard hub |
| 21 | Factor IC validation (Alphalens-style) | `/ic` | ✅ Done | `b35d7e8` | rank IC + IC-IR + t-stat + Q5−Q1 quantile spread vs fwd returns; reversal/momentum/lowvol; dashboard hub |

## 1e. Scheduled jobs & UX (this session)
| Item | What | Commit |
|------|------|--------|
| WAN streamer | 15-min market-hours push of new ensemble signals (daily dedup) | `8f7fbb5` |
| Positioning streamer | 30-min push of new long/short OI builds (daily dedup) | `404e9c9` |
| **Earnings Radar** job | daily 8:45am ET push: `/earnvol` + `/pead` combined | `80e7d6f` |
| **Slash-command autocomplete** | `set_my_commands` — 35 commands in Telegram "/" menu | `8ceeb28` |
| **OpenBB history fallback** | `_fetch_openbb_history` dormant fallback in `_daily_history` | `9753eec` |
| **NYSE_OpenBB.py** | isolated OpenBB options-fetch benchmark (separate DB) | `ddd8625` |

## 1d. OpenBB benchmark (NYSE_OpenBB.py) — status 2026-07-02
- `NYSE_OpenBB.py` written: OpenBB CBOE full-chain-in-one-call + threaded, isolated output DB
  (`US_data_openbb_test.db`, never touches `US_data.db`). User installed OpenBB.
- **Schema VALIDATED live:** CBOE AAPL = 3,538 rows in **one 5.6s call** (all expiries); columns
  (expiration/strike/option_type/open_interest/volume/last_trade_price/contract_symbol/underlying_price)
  match `_normalize_chain()` → no tweak needed. `import openbb` ~31s one-time.
- Pending: user runs the actual A/B benchmark (`python NYSE_OpenBB.py --limit 50 --workers 8`).
  Real win = parallelism + no 1s inter-ticker sleep (same levers apply to the yfinance pipeline).

## 1c. Data layer — DB-first history (reduce API dependence)
- ✅ **`stock_history` table** added to `US_data.db` — multi-year daily OHLC. `_daily_history()` / `_history_matrix()`
  read DB-first, lazily backfill from yfinance once (write-through), and `_sync_history_from_daily()` folds in
  `stock_daily` for FREE ongoing maintenance (no repeat API). Backfilled full universe (~135 tickers, ~105k rows, 6y).
- Repointed `/ic`, `/season`, `/rotate`, `/pwindex` to it → `/ic` momentum N went **21 → ~1,400** (t≈+5, real edge).
- Can't be backfilled (yfinance serves no history): option-chain bid/ask/IV → `/cc /condor /calendar` stay live.

## 1b. Streamlit dashboard mirror
- ✅ **"⚙️ Strategy Scanners" page** (dashboard.py) — one hub, selectbox + Run scan, reuses the
  `telegram_bot_optimized` scanner functions (single engine, two front-ends). Covers WAN, Earnvol,
  Pairs, Season, Rotation, Reversal, Condor, Calendar, Dividends, Put-Write. Wheel/CC already have
  their own dashboard pages. Commit pending.

## 2. Already in the bot (don't rebuild — enhance only)
- Credit/debit spreads → `/spreads` · High-prob ensemble → `/hiprob` · Momentum 12-1 → `/momentum`
- Signed GEX / walls → `/gex` · Vanna → `/vanna` · Max pain/OPEX → `/opex` · Squeeze → `/squeeze`
- Regime / VIX term structure → `/regime` · Macro (BLS+yields) → `/macro` · Earnings news → `/earnings`

## 3. External quant-repo catalog (reference — infra/tools, NOT strategies)

### 3A. The real gems — serious, widely-used infrastructure
| Repo | What it is | Significance | Effort | Realistic edge |
|------|-----------|--------------|--------|----------------|
| `microsoft/qlib` | AI quant platform (data/factor/model zoo/backtest) | Closest "open Aladdin" for research | Med–High | Framework, not a signal |
| `OpenBB-finance/OpenBB` | Open Bloomberg-Terminal alternative | Best free data+analytics aggregation | Low–Med | Data/analysis, no alpha itself |
| `QuantConnect/Lean` | Institutional backtest+live engine, multi-asset incl options | Production-grade, broker-connected | Med | Infra; supports options (fits us) |
| `mementum/backtrader` | Python event-driven backtester | De-facto teaching/retail standard | Low | Infra |
| `stefan-jansen/zipline-reloaded` | Backtest engine behind old Quantopian | Historically dominant; pairs w/ Alphalens | Med | Infra |
| `polakowo/vectorbt` | Vectorized ultra-fast backtest/research | Best for large-scale signal sweeps | Med | Infra; great for our OI signal grid |
| `stefan-jansen/alphalens-reloaded` | Factor/alpha eval (IC, quantile returns) | Standard way to prove a signal | Low | **What /validate-signal should mimic** |
| `robertmartin8/PyPortfolioOpt` | Mean-variance / Black-Litterman opt | Cleanest portfolio construction lib | Low | Allocation, not prediction |
| `dcajasn/Riskfolio-Lib` | Advanced risk & portfolio opt | "Aladdin-ish" on the risk side | Med | Risk/allocation |

### 3B. ML / prediction-oriented (higher hype, handle with care)
| Repo | What it is | Honest note |
|------|-----------|-------------|
| `AI4Finance-Foundation/FinRL` | Deep RL for trading | Impressive demos; live edge unproven, overfits easily |
| `AI4Finance-Foundation/FinGPT` | LLMs for finance | Good for *features* (sentiment), not a price oracle |
| `ProsusAI/finBERT` | BERT financial sentiment | Solid input feature, not a signal alone |
| `microsoft/qlib` (benchmarks) | LightGBM/Transformer alpha baselines | Realistic ~small IC; honest about decay |

### 3C. Naive / popular-but-overrated (do NOT trust blindly)
| Pattern | Why popular | Why it fails |
|---------|-------------|--------------|
| "LSTM stock price prediction" (thousands of clones) | Looks impressive | Predicts lagged price ≈ yesterday; future leaks; no edge |
| MA crossover / RSI bots | Simple, intuitive | ~Zero edge net of costs on liquid names |
| Prophet / ARIMA "forecast" | One-liner | Markets aren't smoothly trending; garbage on returns |
| Single-indicator "signal" repos | Easy to copy | No OOS validation; survivorship bias |

### 3D. Adoption status (are we USING these, or just aware of them?)
| Tool | "Bloomberg/Aladdin" role | Status in our stack | Decision |
|------|--------------------------|---------------------|----------|
| **OpenBB** (Bloomberg-like terminal) | data+analytics terminal | ❌ not integrated (researched 2026-07-02) | Real edge = ~100 providers with **standardization → automatic multi-provider fallback** (matches "reduce API dep" goal) + REST/CLI/**MCP-for-AI**/Excel from one def. BUT: heavy dep, redundant with our direct feeds + dashboard, and its *free* option data still has **no historical chains/bid-ask/borrow** → does NOT unblock dispersion/box-arb/gamma. **Verdict: keep parked**; only selectively adopt as a fallback data layer (e.g. `pip install openbb` + CBOE/macro extensions) if a relied-on provider flakes |
| **PyPortfolioOpt / Riskfolio-Lib** (Aladdin *risk* side) | signals → risk-sized positions | ✅ **built natively as `/allocate`** | max-Sharpe/min-var/risk-parity on 6y covariance, weight-capped, no dep; bot + dashboard hub |
| **Alphalens** (factor eval) | prove a signal | ✅ built natively as `/ic` | done |
| **vectorbt** (fast backtest) | universe signal sweeps | ❌ not adopted | optional; our scanners already vectorize enough. Revisit if backtests get heavy |
| **microsoft/qlib** (ML alpha) | walk-forward ML | ❌ not adopted | big lift; only if we want an ML alpha layer. Parked |

### Best fits for THIS bot (priority order)
1. ✅ **DONE — Alphalens-style IC built natively** as `/ic` (`_ic_analyze`): cross-sectional rank IC (Spearman) + IC-IR + t-stat + Q5−Q1 quantile spread vs forward returns, no dependency. In bot + dashboard hub. (Adopting the actual `alphalens-reloaded` lib later would add plotting/tearsheets.)
2. **vectorbt** — sweep the 24-model ensemble across the whole universe fast (vs per-ticker loop).
3. **microsoft/qlib** — optional ML alpha layer with walk-forward CV (fixes low-N backtests).
4. **Riskfolio-Lib / PyPortfolioOpt** — signals → risk-sized positions (the genuinely Aladdin-like piece).

## 3E. Candidate additions (FEASIBLE with current data — not yet built, audit 2026-07-02)
| Candidate | Command | Data | Note |
|-----------|---------|------|------|
| VRP screener (IV vs realized vol) | `/vrp` | options IV + stock_history RV | exists as internal ensemble model (`vrp`/`rv_iv`); surface standalone |
| Unusual options activity (vol÷OI) | `/uoa` | options_change | ✅ **BUILT** — vol≫OI, DTE≥7 (skips 0DTE index churn), ranked by $ notional; bot + dashboard hub |
| IV-skew extremes (put/call skew) | `/skew` | options IV | internal model (`iv_skew`); surface standalone |
| 52-week high/low breakout / proximity | `/breakout` | stock_history (6y) | classic momentum-breakout, not built |
| Single-name time-series mean-reversion | `/zrev` | stock_history | /revert is cross-sectional; this is per-ticker Bollinger/z |
| Stock-level relative strength vs SPY | `/rs` | stock_history | /rotate is sector-level only |
- Git repos: all catalog items reconciled — Alphalens→/ic, PyPortfolioOpt/Riskfolio→/allocate built;
  qlib/vectorbt/OpenBB/Lean/backtrader/zipline/FinRL/FinGPT/finBERT parked (finBERT redundant — Finnhub
  sentiment already wired). Nothing missed.

## 4. Later backlog (blocked on a prerequisite — do once unblocked, NOT dropped)
| # | Strategy | Command | Prerequisite to unblock |
|---|----------|---------|-------------------------|
| 13 | PEAD (post-earnings drift) — ✅ DONE `/pead` | `/pead` | UNBLOCKED: FINNHUB_API_KEY is set (verified 2026-07-01). Finnhub calendar/earnings; in dashboard hub too |
| 14 | Dispersion (index vs constituent vol) | `/dispersion` | Bulk live option chains for ~full constituent set. TRIED 2026-07-01 with top-8 only → implied-correlation math meaningless (8-name tech basket ~37% IV vs SPY 14% → corr ≈ 0, misleading). Reverted; needs ≥30-50 weighted constituents to be valid. |
| 15 | Index rebalance (S&P add/delete) | `/rebal` | Corporate-action announcement feed |
| 16 | Gamma scalping | `/gscalp` | Intraday tick storage |
| 17 | Riskless arbitrage (box / put-call parity) | `/boxarb` | Live bid/ask + borrow rates in DB |
| 18 | ETF NAV arbitrage | — | Institutional-only; likely stays parked |

**Recommendation order:** 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12, then unblock 13–18 as data allows.
