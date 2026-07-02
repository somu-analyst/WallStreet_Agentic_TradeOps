# LOG — completed work, decisions, blockers

> Append newest at top. Recap here every ~10–20 messages and before any context reset.

## 2026-07-02 (later) — OpenBB capture hardening + storage + rate limits
- **Storage fixed:** parquet-zstd daily export (`openbb_chains/chains_YYYY-MM-DD.parquet`), sqlite = staging
  only. Measured **7x compression** (26.5MB → 3.6MB/day → ~0.9GB/yr; contractSymbols dropped, float32).
- **Rate limits:** `KeyError 'data'` = CBOE throttle (NOT symbols). Mitigations shipped: chunking+rests,
  slow retry rounds, ADAPTIVE pacing (chunk >25% fails → slow down). Bad symbols removed from builder.
  Community options if still needed: curl_cffi browser-impersonation session (NYSE_YFin already does this
  for yahoo), provider interleave (alternate cboe/yfinance chunks), requests-cache. NOT done yet.
- Positions table: Event col (ER/ex-div pre-expiry) + event-aware Action (38bda1d).
- #10-16 user list done (engine consolidation e71d195, weekly rotate, scn_* persistence, /ic tearsheet,
  vectorbt sweep 22335ec). qlib deferred (own project), graphify blocked (no CLI).
- **NEXT: user's 743 capture SUMMARY → validate day → production migration** (ALTER options_daily,
  wire into run_all_offhours, retire 4-hr yfinance options leg).

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
