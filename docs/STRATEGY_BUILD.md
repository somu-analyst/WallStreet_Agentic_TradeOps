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
| 5 | Calendar / diagonal spreads (theta + vega, term structure) | `/calendar` | ⏳ Planned | — | uses VIX/VIX3M + chain |
| 6 | Iron condor / strangle range-income optimizer | `/condor` | ⏳ Planned | — | extends /earnvol + /spreads |
| 7 | Seasonality engine (current-month avg/win, DoW, turn-of-month) | `/season` | ✅ Done | pending | on-the-fly ~10y yfinance, cached 24h |
| 8 | Sector rotation / relative-strength ranker | `/rotate` | ✅ Done | pending | 12 sector ETFs, blended 1/3/6-mo RS vs SPY, 1h cache |
| 9 | Cross-sectional mean-reversion (short-term reversal) | `/revert` | ✅ Done | pending | 5d return z-score vs universe; pure stock_daily |
| 10 | Macro event positioner (FOMC/CPI/NFP drift+vol) | `/macro` (enhance) | ⏳ Planned | — | modest, decaying edge |
| 11 | Dividend-capture / ex-div assignment risk | `/divcap` | ⏳ Planned | — | needs dividend calendar |
| 12 | Put-write / covered-call systematic index (PUT/BXM style) | `/pwindex` | ⏳ Planned | — | backtest-style, educational |

## 2. Already in the bot (don't rebuild — enhance only)
- Credit/debit spreads → `/spreads` · High-prob ensemble → `/hiprob` · Momentum 12-1 → `/momentum`
- Signed GEX / walls → `/gex` · Vanna → `/vanna` · Max pain/OPEX → `/opex` · Squeeze → `/squeeze`
- Regime / VIX term structure → `/regime` · Macro (BLS+yields) → `/macro` · Earnings news → `/earnings`

## 3. Infrastructure (validation & sizing — NOT strategies, hence not in build queue)
- **Alphalens-reloaded** — IC / quantile forward-return validation (upgrade `/validate-signal`)
- **vectorbt** — fast universe-wide signal sweeps · **microsoft/qlib** — ML alpha with walk-forward CV
- **PyPortfolioOpt / Riskfolio-Lib** — turn signals into risk-sized positions (the "Aladdin" piece)

## 4. Later backlog (blocked on a prerequisite — do once unblocked, NOT dropped)
| # | Strategy | Command | Prerequisite to unblock |
|---|----------|---------|-------------------------|
| 13 | PEAD (post-earnings drift) | `/earnvol` (lane 2) | Finnhub earnings-surprise history (API key) |
| 14 | Dispersion (index vs constituent vol) | `/dispersion` | Bulk live option chains + perf budget |
| 15 | Index rebalance (S&P add/delete) | `/rebal` | Corporate-action announcement feed |
| 16 | Gamma scalping | `/gscalp` | Intraday tick storage |
| 17 | Riskless arbitrage (box / put-call parity) | `/boxarb` | Live bid/ask + borrow rates in DB |
| 18 | ETF NAV arbitrage | — | Institutional-only; likely stays parked |

**Recommendation order:** 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12, then unblock 13–18 as data allows.
