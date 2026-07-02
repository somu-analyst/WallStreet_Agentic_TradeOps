# LOG — completed work, decisions, blockers

> Append newest at top. Recap here every ~10–20 messages and before any context reset.

## 2026-07-02 — Strategy build series + DB history layer + portfolio/validation
- **Done (strategy scanners, bot + dashboard "⚙️ Strategy Scanners" hub):** `/wan` `/earnvol` `/cc`
  `/pairs` `/season` `/rotate` `/revert` `/condor` `/calendar` `/divcap` `/pwindex` `/pead`
  `/building`. Each verified vs live data before commit. `/wan` (15m) + `/building` (30m) are
  market-hours scheduled streamers with daily `alert_dedup`.
- **Done (infra):** `stock_history` table in US_data.db — multi-year OHLC; `_daily_history()`/
  `_history_matrix()` DB-first + lazy yfinance backfill (write-through) + `_sync_history_from_daily()`
  free maintenance from `stock_daily`. Backfilled ~135 tickers / ~105k rows / 6y. Repointed
  `/ic` `/season` `/rotate` `/pwindex` to it → **`/ic` momentum N 21→~1400 (t≈+5)**.
- **Done (Aladdin/validation gems, native — no heavy deps):** `/ic` = Alphalens-style rank IC +
  quantile spread; `/allocate` = max-Sharpe/min-var/risk-parity optimizer on the 6y covariance.
- **Decision:** build IC + optimizer natively rather than add alphalens/PyPortfolioOpt deps
  (keeps lean single-file style). OpenBB researched → keep PARKED (heavy, redundant with dashboard +
  direct feeds, doesn't unblock option-history strategies); selective fallback-layer adoption only.
- **Decision:** dispersion (#14) tried with top-8 constituents → meaningless (subset), reverted.
- **Blocker (data-gated, in tracker backlog):** #10 macro-event calendar (needs econ-calendar feed),
  #14 dispersion (needs ~full constituent chains), #15 index-rebalance (corp-action feed),
  #16 gamma-scalp (tick data), #17 box-arb (live bid/ask+borrow), #18 ETF-NAV (institutional).
  None doable without data we don't store. Finnhub key IS set (unblocked #13 `/pead`).
- **Source of truth:** `docs/STRATEGY_BUILD.md` (done vs pending vs parked, + repo catalog §3).

## YYYY-MM-DD
- **Done:** <what shipped / verified>
- **Decision:** <choice + why>
- **Blocker:** <what's stuck + what would unblock it>
