# LOG — completed work, decisions, blockers

> Append newest at top. Recap here every ~10–20 messages and before any context reset.

## 2026-07-02 (night) — OpenBB capture hardened to hands-off; ops guardrails in
- **Done (NYSE_OpenBB.py, commits c41e3f2→5c8ba59→this):** plain `python NYSE_OpenBB.py` now does
  everything — expanded 740-name universe by default (auto-builds sheet if missing), safe pacing
  (workers 4 / pace 0.75s), adaptive slowdown (pace+rest+worker-halving), **CBOE-CDN fallback with
  curl_cffi browser impersonation fired instantly on throttle** (verified live: AAPL/BRK-B/SPY
  recovered mid-throttle), progress-driven retry rounds (≤5, stop when stalled, skip optionless),
  PERMANENT_FAIL split (no-options vs throttled) in summary, **automatic daily parquet-zstd backup**
  to `openbb_chains\` (~3-4 MB/day; --parquet additionally clears sqlite), openbb version stamped in
  run log, auto `--compare` at end with **VERDICT: PASS/CHECK** line (go/no-go = openInt ≥95%;
  lastPrice informational). `requirements_openbb.txt` pins openbb 4.7.2 / cboe 1.6.1 / curl_cffi 0.15.0.
- **Decision:** throttle handling = pace+backoff+retries+browser-fingerprint fallback (community
  standard per OpenBB/yfinance issue threads); NO proxy rotation (ToS-grey, unneeded for 1 run/day).
  One capture per evening (post-close ET) — multiple same-day runs burn the throttle budget.
- **User routine:** evening `python NYSE_OpenBB.py` → read VERDICT; weekly offsite copy of
  `openbb_chains\` (capture-forward data is unrebuildable).

## 2026-07-02 (evening) — Event column in All-Positions batch tables
- **Done:** dashboard `_ep_batch_table` (feeds "🌐 All Open Positions" one-table + "🏢 by Ticker" legs)
  now has an **Event** column: 📊 ER Xd (⚠️pre-exp when it lands before that leg's expiry) + 💵 ex-div Xd;
  one cached lookup per ticker (`_next_earnings` + bot `_divcap_stats`). Event-aware Signal: plain ⚪ HOLD
  escalates to 🟡 ER PRE-EXP / 🟡 EX-DIV (short ITM call assignment); never masks TAKE PROFIT/CUT LOSS/
  NEAR EXPIRY. Action-Required alert filter + both "how to read" legends updated. (Deep-dive per-leg
  table got Event earlier today.)
- **Status:** scanner backtests still auto-accumulating — no `scn_*` rows in `signal_accuracy` yet
  (they populate as /uoa /building /breakout /zrev /revert + building_alert fire; t+5 outcomes follow).
- **OpenBB lane parked by user** — parallel test ready (daily capture → `--compare`); all other pending
  items are OpenBB- or data-gated (see STRATEGY_BUILD.md).

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
