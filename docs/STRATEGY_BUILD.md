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
| 2 | Wheel CSP income optimizer (yield + assignment + IV-rank + earnings flag) | `/wheel` | ✅ Done | pending | pipe-table + score haircut |
| 3 | Covered-call income (yield on held/long names) | `/cc` | ⏳ Next | — | mirror wheel on call side |
| 4 | Pairs / statistical arbitrage (cointegration + z-score) | `/pairs` | ⏳ Planned | — | genuinely new; needs history depth |
| 5 | Calendar / diagonal spreads (theta + vega, term structure) | `/calendar` | ⏳ Planned | — | uses VIX/VIX3M + chain |
| 6 | Iron condor / strangle range-income optimizer | `/condor` | ⏳ Planned | — | extends /earnvol + /spreads |
| 7 | Seasonality engine (turn-of-month, DoW, pre-holiday) | `/season` | ⏳ Planned | — | needs multi-year yfinance pull |
| 8 | Sector rotation / relative-strength ranker | `/rotate` | ⏳ Planned | — | ETFs; from stock_daily |
| 9 | Cross-sectional mean-reversion (short-term reversal) | `/revert` | ⏳ Planned | — | from stock_daily |
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

## 4. Deferred / infeasible (with reason — so they aren't silently dropped)
| Strategy | Why not queued |
|----------|----------------|
| PEAD (post-earnings drift) | Needs Finnhub earnings-surprise history; API key pending ⛔ |
| Riskless arbitrage (box, put-call parity) | Gone for retail; DB has no bid/ask/borrow ❌ |
| Dispersion (index vs constituent vol) | Needs many live chains; heavy/fragile ⚠️ |
| Index rebalance (S&P add/delete) | Needs corporate-action announcement feed ❌ |
| Gamma scalping | Needs intraday tick data we don't store ❌ |
| ETF NAV arbitrage | Not accessible to retail ❌ |

**Recommendation order for build queue:** 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12.
