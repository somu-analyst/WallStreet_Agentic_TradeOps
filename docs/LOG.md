# LOG — completed work, decisions, blockers

> Append newest at top. Recap here every ~10–20 messages and before any context reset.

## 2026-07-06 — "Vulnerability score" investigated & REJECTED (validation win)
- **Trigger:** UNH −1.7% (07-02→07-06) rotational pullback. Ran UNH through the full battery
  (OI, GEX, 24-model ensemble, mean-rev, PCR): positioning read **complacent/bullish** into it
  (low PCR, call-heavy flow, ensemble 7-BULL/2-BEAR, positive/pinning GEX). NOT foreshadowed;
  only soft tells = extension + `pcp_dev` BEAR. Backtested `pcp_dev`: n too small, BEAR t+3 hit 50%
  = **luck** (signal_accuracy only ~2mo/23 dates old).
- **Built + cross-sectional backtested a Vulnerability Score** (extended + complacent → fade) over
  2,339 obs. **REJECTED — do NOT build:** extension/momentum IC is significantly **POSITIVE**
  (t=+3.3 at t+20) → this regime **rewards** stretched names (same lesson as the Market Radar froth
  pillar). Six formulations × 3 horizons tested (scratchpad `vuln_backtest.py`/`vuln_battery.py`).
- **Only significant fade = cross-sectional low-PCR complacency** (IC −0.06..−0.07, t≈−2.9; feared
  Q5 beats complacent Q1 by ~3%/10d) — BUT the **time-series control (PCR vs own history) is null
  (t=−0.19)** → the effect is **structural (name fixed-effects), not a timing signal.** Not shippable.
- **Conclusion:** no shippable "find-the-next-UNH" signal in current data. The research-backed edge
  (put/IV **skew**) needs clean bid/ask/IV → **gated on the OpenBB capture** (`options_daily` only
  stores lastPrice). Skew = first thing to test once OpenBB is live. See [[market-radar-backtest]].

## 2026-07-06 — Market Radar: built, backtested, redesigned (turbulence gauge)
- **Investigated the Jul-2 tech/semis selloff** (SMH −5.4%, QQQ −2.1%, SPY −0.36%, VIX flat 16.7 =
  narrow flush, not broad). Found the bot's own scanners had logged BEAR fires on the index/semis
  complex from 07-01 EOD (`scn_uoa` SPY/QQQ/IWM/SMH, `scn_building` QQQ) — so the signal was there.
- **Done (feature, bot + dashboard):** `/riskoff` **Market Radar** — plain-English readout + a
  next-session SPY game plan (gamma walls: hold 740→755 / lose 740→729). Auto-push on startup
  (once/day `alert_dedup` grp `market_radar`) + daily post-close gated on turbulence≥ELEVATED.
  Menu entries added. `/rovalidate` = on-demand backtest (no scipy; rank corr via numpy).
- **Done (validation — the important part):** backtested all 5 pillars vs ~6mo DB history (104 days,
  fwd SPY/QQQ t+3/t+5). **Old composite 0-100 score = decoration** (Spearman +0.017, p=0.86).
  Per-pillar: **index put-flow predicts move SIZE** (|QQQ| t+5 corr **+0.37, p<0.001**) — the one
  real signal; **dealer-gamma+breadth** give a weak, correctly-signed (−0.15) but insignificant
  DIRECTION lean; **froth/overbought is MOMENTUM here (+0.15), not reversal**; vol-underpriced is
  contrarian. Scripts in scratchpad (`backtest_pillars.py`, `backtest_v2.py`).
- **Decision:** rebuilt `_riskoff_scan` into a **two-gauge** model — Turbulence (proven, primary) +
  soft low-confidence Direction lean; froth/VRP demoted to "context (not proven)". Honest framing:
  "big move brewing, direction unreliable" beats a fake "71/100 RISK-OFF".
- **Decision:** **OpenBB stays a PARALLEL test lane only** — removed `_fetch_openbb_history` from the
  live `_daily_history` backfill (yfinance-only in bot); OpenBB isolated in `NYSE_OpenBB*.py`. Added
  `NYSE_OpenBB_EOD.py` (EOD price puller → `stock_history`, run manually). CLAUDE.md note updated.
- **Git note:** my commits (7e90743→a0f1ad8) are ancestors of current HEAD e3fa26d; parallel work
  layered on top — all Market Radar content verified present in HEAD, tree clean, both files parse.
- **Pending (user actions):** restart bot + rerun Streamlit to deploy; `git push` if using a remote.

## 2026-07-03 — First stringent DB compare (Jul 2): OpenBB VALIDATED, yahoo OI exposed
- **Contract-level audit** (17,615 shared contracts, 87 tickers): coverage 100% (0 yfinance
  contracts missing from openbb; openbb adds 646 extra tickers); lastPrice 98% within 2%;
  volumes ~70% exact; call-OI only 58% within 2% BUT median diff 0.36%.
- **Arbiter test settled it:** 5 worst OI mismatches re-fetched fresh from CBOE — all 5 matched
  the OpenBB value EXACTLY (e.g. FXI 33.5C: ob=1255, yahoo=2, CBOE-now=1255). Yahoo serves
  stale/near-zero OI on many strikes → the old ≥95% strike-agreement gate measured yahoo's
  data quality, not ours. Verdict redefined: median OI diff ≤2% + price agreement ≥90% (PASS ✔ day 1).
- **Hygiene:** deleted 35,055 rows mislabeled 2026-07-03 (holiday; pre-fix run), regenerated
  chains_2026-07-02.parquet from the full day (178,344 rows / 734 tickers / 3.8 MB), compare now
  joins ^VIX↔VIX. Self-healing skip file live (openbb_skip.txt, 9 names; universe loads 734).
- **Implication:** OpenBB/CBOE is the more trustworthy OI source — strengthens the migration case.

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
