# LOG — completed work, decisions, blockers

> Append newest at top. Recap here every ~10–20 messages and before any context reset.

## 2026-07-15 (late) — Intraday lane SHIPPED (P1 from the queue)
- **`NYSE_intraday.py`** (new root entrypoint): market-hours capture loop → own `US_intraday.db`
  (no writer contention with EOD). Every 60s ONE batched `yf.download(interval="1m")` for the FOCUS
  universe (open-position tickers from `trades` + 30 liquid leaders), full-day INSERT OR REPLACE so
  gaps self-heal; every 30 min a CBOE CDN delayed-chain snapshot (spot/ATM-IV/call-put-vol/PCR-vol/
  top-vol strikes) for open-position tickers only. UTC session gate = EDT∪EST window (no tzdata dep);
  45-day retention; `--once` test mode; ASCII console. Verified: 12,086 bars (full 09:30–15:59
  session, 31 tickers) + 2/2 chain snapshots (GOOGL IV 36.5%, PCR 0.22) on first run.
- **Bot consumers** (telegram_bot_optimized.py, section after ratings): `/live [TICKERS]` minute
  writeup (day% vs prev close, VWAP dislocation, volume pace vs 20d linear norm, 15m burst, ATM-IV
  drift from snapshots, breadth, staleness banner) · `/heat` scan — z = day move ÷ (ATR20·√elapsed):
  🔥 HEAT z≥1.5 + pace≥1.5 + still trending · 🌀 FADE z≥2 + (stalling 30m OR pace<1) →
  reversal watch · `heat_streamer_alert` run_repeating 900s, pushes STATE CHANGES only
  (`alert_dedup` atype `heat_stream`, age≤20min fresh-bar gate). Registered: handlers + BotCommands
  + job. Live check: GS earnings day flagged 🔥 (+10.2%, z+3.9, pace 1.6×); JPM +3.7% correctly
  unflagged (pace 0.8×). OI stays daily (OCC) — lane is volume/price/IV only, by design.
- **Lane supervisor (same night, user asked "why separate?"):** kept the separate process (bot
  restarts must not gap unrecoverable 1m bars; sync sweeps would stall the async loop; single-writer
  isolation) but removed the manual step — `intraday_lane_supervisor` bot job (300s) auto-spawns
  NYSE_intraday.py during market hours (dashboard-launch pattern: CREATE_NO_WINDOW, log
  `logs/intraday_lane.log`), gated on a `lane_meta` heartbeat the loop stamps every iteration, so a
  manual start is never duplicated. Verified: heartbeat written + readable via `_lane_heartbeat_age()`.
- **Open follow-ups** (PLAN): backtest heat/fade states vs forward 30–60m returns once ~1–2 wks of
  bars accrue; U-shape volume norm refinement.

## 2026-07-07 — Action Board digest + NYSE_YFin profiling + SEMIS rout confirmation
- **Action Board** (`/board` + `action_board_alert` 8:35 AM ET): bot-side consensus digest.
  `_action_board(conn)` freshens 5 DB-first scanners (revert/zrev/breakout/building/uoa — each
  already persists `scn_*` fires) then tallies today's fires per ticker; a name makes the board
  only if ≥2 scanners agree on direction (net≠0). Two mobile-safe _pipe_tables (longs/shorts) with
  #scanners + avg conf; sources listed beneath. Mirrors the dashboard `_ab_ideas()` Action Board
  (bot can't import dashboard → parallel impl on the same `scn_*` substrate). Consensus BACKTEST
  still gated on ~2wk of matured scn_* outcomes (PLAN). Verified live: 9 consensus names, SPY top
  (3 scanners), all longs (momentum-up regime).
- **NYSE_YFin.py profiling**: `stage_timer()` ctx-mgr + `finalize_timing()`. Times phases 1-7 and
  splits Phase 4 into 4a option-chain fetch loop / 4b OHLC enrichment / 4c options_daily write /
  4d weekly-monthly refresh. Prints longest-first summary + appends `yfin_stage_timings.csv`
  (DATA_DIR). Read that CSV after the next EOD run to attribute the ~4 hrs (suspects: 4a's per-ticker
  SECS_BETWEEN_TICKERS=1 loop over ~740 names, and 4b per-contract .info enrichment). Smoke-tested.
- **SEMIS rout (07-07, live −5.6% avg vs SPY −0.29%) — flagged in advance by our data:**
  Rotation Tracker had **Semis = 🟡 Weakening on 07-06** (strength +39%, momentum −18%) — the
  validated "money leaving" quadrant (−1.6%/10d); 8/12 semi names Weakening (MU −60/ARM −53/AMD −44
  momentum). **OpenBB skew_snapshot 07-06 (real IV) nailed the ETFs/equipment**: SMH pcvol 7.2×/pcoi
  3.4×/skew +0.070, SOXX pcvol 2.7×/pcoi 2.5×, LRCX pcvol 4.4×, KLAC skew +0.073 (highest) — heavy
  put hedging + downside skew priced the day before. US_data.db OI confirmed SMH/SOXX standing
  PCR_OI >5. **Takeaway:** rotation (price momentum) + OpenBB skew (options fear) are complementary —
  skew caught LRCX/KLAC that rotation still had as "Leading." Equipment (AMAT/LRCX/KLAC) fell hardest
  (−8 to −10%) on a fresh WFE/capex catalyst.

## 2026-07-08 (later) — Catalyst Radar + env-switchable DB, both apps tested on BB
- **Catalyst Radar** (`/catalysts` + `catalyst_alert` 8:20 AM ET, ≤3d gate): the one intraday-ish nudge
  from the EOD-vs-intraday discussion. Earnings via `_next_earnings` (per open-position ticker + SPY/QQQ);
  macro via FOMC (`_FOMC_DATES`) + hardcoded `_CPI_DATES`/`_PCE_DATES` 2026 (VERIFY yearly) + Jobs/NFP
  computed as first-Friday. Verified live: CPI Jul 15 (7d) + UNH earnings Jul 16 (8d) surfaced. ETF
  earnings lookups 404 harmlessly (return None).
- **Env-switchable DB (`NYSE_DB_PATH`)**: telegram_bot_optimized.py + dashboard.py DB_PATH now honor the
  env var (default = Yahoo). Set to US_data_OpenBB.db to run both apps on OpenBB, zero code edit, revert
  by unsetting. Dashboard caption shows active DB. Scheduler derive now `--stock` (BB stock_daily current).
- **Tested both apps on BB DB (via override):** building/rotation/GEX read correctly. GEX richer on BB
  (full chain vs Yahoo ±20 strikes → larger magnitude, more walls; NVDA got walls where Yahoo gave none).
  GEX=0 only when spot not passed — same on both DBs (harness, not migration). Dashboard delegates DB
  reads to the same engine + is env-aware → covered.
- **EOD-vs-intraday advice (user asked):** EOD is the CORRECT native frequency here — OI is EOD by nature
  (OCC settles overnight), and the validated edges (rotation/skew/positioning) are daily-frequency. EOD =
  screening/setup/direction+size layer; execute + manage risk with live data. Don't chase intraday. The
  semis call (flagged day before −5.6%) is the proof of what EOD does well. Catalyst Radar = the thin live nudge.

## 2026-07-08 (perf) — Serving layer (Tier 2/3) + option-OHLC fix
- **Dashboard slow after cutover** — root cause: BB has ~9x Yahoo's option rows/day (736 vs 88 tickers);
  `load_oi_for_date` did `SELECT *` pulling ~151k raw rows (~1937ms). Not fragmentation (freelist 0),
  not index (added date-leading idx), not pragmas (CPU-bound row materialization). Ladder measured:
  raw SELECT* 1937ms → aggregate-in-SQL 158ms (12x) → precomputed serving table 2-15ms (~130-780x) →
  RAM-resident ~µs. DuckDB (columnar) benched but not installed; not needed (no migration, ~0 extra space
  if used over sqlite_scan — it's an engine not a store).
- **Serving layer** `daily_ticker_summary` (NYSE_OpenBB_derive.build_serving_layer): per-ticker/date
  aggregates (call/put OI, PCR, OI-change, vol, notional, spot, atm_iv, skew25) — 734 rows/day, read in
  ~7-15ms vs ~1937ms. 0 accuracy loss (same sums over frozen EOD snapshot). Runs nightly via derive STEP 4.
- **Dashboard** `load_ticker_summary(td)` accessor (cached, with live-GROUP BY fallback for Yahoo DB / pre-build).
  Repointed the market-wrap OI aggregate to it. Other pages can adopt incrementally.
- **Option OHLC fix** (user: "columns not coming, not fixed"): Yahoo's per-contract OHLC was degenerate
  (open=high=low=close=lastPrice for thin options). OpenBB = EOD snapshot (no bars) → set close=lastPrice
  (exact), open/high/low=last. Now ~70% non-zero, MATCHING Yahoo's rate; R1/R12/S12 populated. money_coi_*/
  vol_rank_* stay NULL (dead in Yahoo too).

## 2026-07-08 (cutover) — OpenBB is now the PRIMARY DB
- User: "use BB as we have more tickers." Executed the cutover.
- **State sync** (one-time, scratchpad migrate_state_to_bb.py): copied bot-state tables US_data.db → BB
  (trades/positions, event_journal, bookmarks, signal_accuracy, signal_weights, momentum_ranks, alert_dedup,
  gamma_wall_trades, antibubble_watch, rotation_watch, hiprob_recs, fundamentals_cache) preserving schema/PKs.
  The 4 "missing" tables (antibubble_watch/rotation_watch/hiprob_recs/fundamentals_cache) were missing only
  because the bot never ran vs BB (auto-created via CREATE IF NOT EXISTS); migrating preserves tracking history.
- **DB_PATH flipped to BB** (default US_data_OpenBB.db, env NYSE_DB_PATH overrides) in telegram_bot_optimized.py,
  dashboard.py, and _lib/{options_tracker,news_and_earnings,market_news_aggregator,event_writeup_bot_hooks,
  event_writeup_engine}. Verified: bot reads BB, positions intact (GOOGL×2/UNH), 736-ticker universe, rotation/
  GEX/building work. Reversible: `set NYSE_DB_PATH=...US_data.db`.
- **Empty columns explained** (user asked): option OHLC (call_open/high/low/close, R12/S12) NULL because OpenBB
  captures a snapshot (last/bid/ask/vol/OI/IV/delta), no per-contract bars; bot uses NONE of them (grep=0);
  money_coi_*/vol_rank_* dead in Yahoo too. Gained IV/greeks. R1/S1 (from lastPrice) 100% populated.
- **Signal-pattern backtest (5y SPY/VIX, 1234 days):** MAGNITUDE predictable — VIX rank-IC +0.365 vs |next-day|,
  P(>1% move) 11%→50% across VIX quintiles. DIRECTION not — all features IC≈0 (p>0.3), "yday up→today up" 51%.
  Advice: turbulence/size engine (= Market Radar, now validated); don't chase index direction; direction edge
  is cross-sectional (Rotation). "Redo until perfect" on direction = overfitting; iteration 1 was conclusive.
- **Watch:** BB freshness depends on nightly OpenBB derive (non-fatal, no auto-fallback yet). NYSE_Telegram.py
  still on US_data.db. See docs/NEXT.md.

## 2026-07-08 — OpenBB migration: enrichment bridge + parallel EOD capture
- Direction shift: user wants to EVENTUALLY RETIRE yfinance and run on OpenBB. So the BB lane is now
  being made a self-contained drop-in (not just a research lane). See [[openbb-migration]].
- **Parity (BB vs Yahoo, raw options):** OI corr 1.000/0.999 & **100% EXACT on 07-06/07-07** (settled
  OCC OI is one daily number → proper EOD captures agree perfectly); lastPrice 0.995-0.998; vol 0.999
  (75-82% exact — vol is intraday, snapshot-timing). Coverage 734 vs 88. The **07-02 divergence (OI 48%
  exact) is NOT a systematic lag** — tested: BB 07-02 doesn't match YF 07-01 (27%) or 06-30 (22%) either;
  it was just the first/rough OpenBB capture. Frozen one-off (OCC serves no historical OI), irrelevant
  forward. So change_OI is exact from 07-06 onward (both baselines clean EOD).
- **Enrichment bridge `NYSE_OpenBB_derive.py`** — SELF-CONTAINED (own copy of compute_oi_vol_change/
  build_stock_daily, NO NYSE_YFin import, so yfinance can be deleted later). Maps options_openbb→
  options_daily→options_change (change_OI/R1/S1/now-prev) + stock_daily (--stock). Identical Yahoo
  schema → DB_PATH flip needs zero bot/dashboard change. VALIDATED: 07-07 change_OI corr **0.9998**,
  R1/S1 0.9998. 07-06 change_OI degraded (0.08) purely from the 07-02 baseline seam — NOT a logic bug.
- **NYSE_YFin.py:** parameterized `compute_oi_vol_change(day, db_path=)` + `build_stock_daily(...,db_path=)`
  (default preserves Yahoo path); fixed a latent bug — stock_daily dedup DELETE referenced undefined
  `trade_date_str_db` (swallowed by try/except → dedup never ran); now `trade_day_str_db`.
- **run_all_offhours.py:** launches `NYSE_OpenBB.py` in BACKGROUND parallel to the Yahoo fetch (JOB1),
  then runs `NYSE_OpenBB_derive.py` after. Fully NON-FATAL (success gate still `rc1==0 and rc2==0`
  on Yahoo jobs; BB writes only US_data_OpenBB.db). This is the path to "100% going forward" — every
  new day gets consecutive clean BB baselines so change_OI is internally exact (like 07-06→07-07).
- **On "100% match":** two independent vendors won't be byte-identical; the historical 07-02 + Yahoo→BB
  boundary seams can't be retro-fixed (data never captured by OpenBB pre-07-02). Cutover (flip DB_PATH)
  is the user's call after a few days of clean parallel captures. Not committed to remote unless asked.

## 2026-07-07 (later 2) — Skew backtest: CONDITIONAL fragility signal (regime-flip)
- `backtests/skew_backtest.py` (parallel lane): does OpenBB 25Δ skew / put-flow on day t predict
  forward downside? 2 snapshot dates (07-02, 07-06); yfinance backfills forward closes for all 720
  names so the crash window isn't starved. 1,440 name-window obs.
- **skew25 rank IC FLIPS by regime:** +0.10 (p=0.007) in the calm 07-02→07-06 up-window (high skew
  → bounce, buy-the-fear) vs **−0.14 (p=1.7e-4) in the 07-06→07-07 semi crash** (high-skew names —
  SMH/SOXX/LRCX/KLAC — underperformed exactly as the /skew flag said). Pooled ≈0 (they cancel).
- **Conclusion:** skew is a CONDITIONAL FRAGILITY signal — predicts cross-sectional downside only
  when a catalyst hits, not a standalone direction bet. Same shape as the earlier put-flow finding
  (predicts move SIZE, not unconditional direction). Cross-sectionally VALIDATES the semis call in
  the crash window. Still preliminary (2 windows); need ~15-20 dates for a time-series test. Do NOT
  ship as a directional bot signal yet — pair with a regime/trigger.

## 2026-07-07 (later) — /skew downside-risk command (live IV, respects OpenBB-parallel rule)
- User asked for a semis-style downside-fear scan with "how much downside, direction + size/range."
  Building it on the OpenBB DB would wire the parallel lane into the bot (locked constraint) → built
  `/skew [TICKERS]` on the **live yfinance chain** instead (allowed, universal). Same capability.
- `_skew_analyze(tk)`: front ~30-DTE expiry → ATM IV, **25Δ put−call skew via true `bs_greeks` delta**
  (DIRECTION), 1σ expected move (SIZE), 1σ/2σ down price targets (RANGE), P(≥5%↓) lognormal, earnings-
  in-window flag. `_skew_scan` sorts by skew; `_fmt_skew` = one _pipe_table (ST·Tkr·IV%·EM%·Skew) +
  per-ticker downside-target lines. `/skew`, `skew_view` callback, BotCommand registered.
- **Gotcha found:** two `_iv_rank` defs exist — `_iv_rank(sym)`@932 shadowed by `_iv_rank(conn,tk)`
  @19771; module-level name resolves to the 2-arg one. Dropped the unused `_iv_rank` call in `_skew`.
  (Left the collision itself alone — pre-existing, out of scope.)
- Verified live on semis: SMH/SOXX 🔴 skew +5, EM ±17/18%, 1σ↓ −17/−18%, 2σ↓ −33/−37%. Post-crash IV
  runs hot so ranges are wide; MU/AMD skew compressed to +2 (everything bid = put skew flattens).
- Committed bb69f9b (Action Board + profiling) earlier this session; /skew in the next commit.

## 2026-07-06 — Rotation Tracker built & VALIDATED (first signal that works)
- **Built** `/rotation` (bot) + 🔄 Rotation Tracker (dashboard) — RRG money-flow, hierarchical
  high→low: **Macro (CROSS-ASSET: eq/intl/bonds/credit/gold/commodities/crypto/$)** → Sectors →
  Themes → Stocks. Axes vs SPY: strength (63d excess) × momentum (21d excess − strength/3) →
  Leading/Weakening(out)/Improving(in)/Lagging. `rotation_watch` logs quadrants daily + flags
  transitions; macro adds a risk-on/off tilt. Universal (DB-first + yfinance). Plotly RRG scatter.
- **VALIDATED (backtests/rotation_backtest.py, 1,542 name-date obs):** momentum axis rank IC
  **+0.138, p=5.5e-08**. 🟡 **Weakening (fading leaders = money leaving) underperforms −1.56%/10d
  excess, only 33% beat SPY**; Improving−Weakening spread grows +1.7/+4.1/+6.6% at 5/10/20d.
  **First clearly-validated signal of the session** (vs the rejected risk-off composite, vulnerability
  score, pcp_dev). Caveat: ~6mo momentum regime — edge is momentum-driven, would fade in a sharp
  mean-reversion/crash. Live read: cross-asset RISK-OFF; Semis/Tech rotating OUT → Fins/Indust/Health.
- Note: this is the *proper* build of the "leader rolling over" idea that failed as a naive standalone —
  as an RS-momentum quadrant tested on EXCESS returns, it works. See [[market-radar-backtest]].

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

## 2026-07-15 — mega-session recap (pre-compact)
DONE+committed: accumulation BUY/SHORT+split-guard · ISO date fixes (substr+positional, 15 sites)
· /ratings + Benzinga news · OpenBB cutover confirmed + 6/6 compare PASS + skew_snapshot wired
nightly + root tidy · nested-expander close fix · Market Overview 1m-live overlay · Command
Center perf (cached parallel book, page-local refresh) · STOCK legs everywhere (CC/PP/Collar
detect, payoff, exit planner, cmd center; bot excludes via 27 guarded queries) · /tax engine
(Pub 550 put-reset verified vs GOOG Jul-26-2027, wash sale, 2026 MFJ) + entry-date backdating
· plain-English Greeks (portfolio caption + planner Real$/Time$/±$1/Θd cols) · Stk±1σ scenario
targets + honest Est Open captions (validated 4-7% err) · heatmap split-day guard (SOXS 1:10
2026-07-15 → +974% artifact, real +9%).
BS-model backtest artifacts: scratchpad bs_validate/bs_tune/bs_liquid.py (1.19M contract-days).
PENDING (PLAN.md): intraday 1-min lane + heat-seeking/reversal + live writeups · NSE India lane
(bhavcopy DELIV_PER verified) · bot stock-leg display · gated backtests (scanner fires, skew panel).

## 2026-07-16 (marathon session, part 2) — recap before /compact
- **Shipped & committed** (all on main): intraday lane supervisor · /live /heat + dashboard hub tabs
  (Live/Heat/Skew/Catalysts/Regime) · stock-leg crash fixes (VaR/MC/scenarios ×5 sites) · /tax Pub 550
  running-clock fix + NaN guards + app_settings income · /add one-line entry + typed-ticker wizard ·
  UX modernization (morphing wizards, readable /spreads, @bot inline search, collapsible /plan) ·
  Mini App /terminal (tunnel parked → local-only, NYSE_MINIAPP_TUNNEL=1 re-enables) · limit-guard
  hooks (Stop+PostToolUse → NEXT.md reset stamp + ClaudeResume task `claude --continue /standup`) ·
  token diet (CLAUDE.md 2.9k→1.1k tok, rules path-scoped) · date audit (DB 100% ISO; NYSE_YFin
  monthly-substr fix; _to_mdy→_exp_iso renames) · backtests P2/P3 (revert VALIDATED +2.7% t+5;
  uoa/building direction FAILED; heat/skew thin → rerun ~2wks; `backtest_summary` table) ·
  /premium rich-IV seller (VRP + tastytrade mechanics) bot+dashboard · EOD scheduler BB-primary
  (Yahoo fallback-only via bb_capture_ok) · stocks-separate manage tab (Exit Planner) ·
  universal _report() macro + format sweep (momentum/opex/squeeze/macro/gex/OI-flow).
- **Trades**: UNH closed (+$483 net); AMD −2×400P 7/31 + GOOGL collar + GOOG 100sh@167 open.
- **Verify method**: everything tested against live DB before commit; bot restarted on final code.
