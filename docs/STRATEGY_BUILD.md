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

### Best fits for THIS bot (priority order)
1. **Alphalens-reloaded** — plug OI/PCR/GEX signals → IC + quantile forward-return decay (rigorous `/validate-signal`). Highest-value.
2. **vectorbt** — sweep the 24-model ensemble across the whole universe fast (vs per-ticker loop).
3. **microsoft/qlib** — optional ML alpha layer with walk-forward CV (fixes low-N backtests).
4. **Riskfolio-Lib / PyPortfolioOpt** — signals → risk-sized positions (the genuinely Aladdin-like piece).

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
