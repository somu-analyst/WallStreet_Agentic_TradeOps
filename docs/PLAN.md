# PLAN — remaining work (source of truth)

> Cross-model/session handoff. Keep this current; `LOG.md` records what's done, `NEXT.md` holds the one-glance switch-over note.
> Worked by `/task-loop` (loop-engineering): pick top unchecked → implement → verify → commit `loop: …` → tick here.

## Goal
Options-trading edge system: Telegram bot + dashboard + our own capture-forward options DB
(bid/ask/IV/delta), every signal validated against DB history — less API dependence, more provable edge.

## Open tasks
- [ ] (user) Parallel-test OpenBB vs yfinance for 3–5 days — ONE evening run of `python NYSE_OpenBB.py` (auto: 740-name universe, CDN throttle fallback, retries, daily parquet backup, auto-compare); pass = compare prints `VERDICT: PASS` (OI ≥95%) on 3–5 days
- [ ] (user, weekly) Offsite copy of `openbb_chains\*.parquet` (+ `US_data_OpenBB.db` if convenient) — capture-forward data is unrebuildable
- [~] Production migration to OpenBB (IN PROGRESS — user wants to eventually retire yfinance fully):
  - [x] Parity checked: BB vs Yahoo raw OI corr 1.000/0.999 (100% within 5%), lastPrice 0.995-0.998, vol 0.999 (75-82% within 5% = snapshot-timing); coverage 734 vs 88 tickers.
  - [x] Enrichment bridge `NYSE_OpenBB_derive.py` — SELF-CONTAINED (own copy of the derivation, no NYSE_YFin import, so yfinance code can be deleted later). Maps `options_openbb`→`options_daily`, then computes `options_change` (change_OI/R1/S1/now-prev) + `stock_daily` (--stock). Same schema as Yahoo → DB_PATH flip needs no bot/dashboard change. VALIDATED: 07-07 change_OI corr 0.9998, R1/S1 0.9998 vs Yahoo. (07-06 change_OI diverges — 07-02 baseline seam, not a logic issue.)
  - [ ] Wire `NYSE_OpenBB.py` + `NYSE_OpenBB_derive.py` into `run_all_offhours.py` to run PARALLEL with the Yahoo fetch each EOD (keeps BB DB current).
  - [ ] (user's call) Cutover: flip `DB_PATH` → US_data_OpenBB.db after a few days of parallel captures (both-day OI parity ≥95%). Optional: carry OpenBB bid/ask/iv/delta into the bot reads (that part WOULD need bot changes).
- [x] Profile remaining `NYSE_YFin.py` stages — `stage_timer()` + `finalize_timing()` instrument phases 1-7 (4a fetch loop / 4b OHLC enrich / 4c DB write / 4d weekly-monthly refresh split out); prints longest-first summary + appends `yfin_stage_timings.csv`. Read the CSV after the next EOD run to see where the 4 hrs go.
- [x] Action Board daily Telegram digest — `/board` + `action_board_alert` (8:35 AM ET, weekday-gated) aggregate today's `scn_*` fires across 5 DB-first scanners (reversal/z-rev/52wk/OI-build/UOA); consensus = ≥2 scanners agree on direction; mobile-safe _pipe_tables. Bot-side mirror of the dashboard `_ab_ideas()` Action Board.
- [ ] (gated: ~2 wks of scn_* fires with t+5 outcomes) First scanner backtest read — hit-rate + avg fwd vs baseline for uoa/building/breakout/zrev/revert, persist to `signal_accuracy`, flag thin N
- [x] `/skew [TICKERS]` shipped on **live yfinance IV** (not OpenBB — kept parallel): direction (25Δ put−call skew via true BS delta) + size (1σ EM) + range (1σ/2σ down targets) + P(≥5%↓), earnings-in-window flag. Universal. `_skew_analyze/_skew_scan/_fmt_skew`.
- [ ] (gated: ~1 mo of OpenBB bid/ask captures) Dispersion (#14) + a skew *backtest* on the OpenBB `skew_snapshot` panel (does high 25Δ skew / put-flow predict fwd downside? need ~15-20 dates)
- [ ] Action Board daily Telegram digest — reuse `_ab_ideas()` sources bot-side; push top ⭐ consensus ideas each morning like the Earnings Radar job

## Constraints / decisions locked in
- CLAUDE.md rules win: edit `telegram_bot_optimized.py`/`dashboard.py` directly (no patch scripts), single-engine (dashboard imports the bot), dates MM-DD-YYYY sort trick, secrets never committed/printed, `US_data.db` never written by NYSE_OpenBB.py.
- "Tested" = validated vs DB history (hit-rate vs baseline), not "it runs".
- Commit to `main`, one atomic commit per completed task; nothing pushed to remote unless asked.

## Out of scope (for now)
- qlib port (own data-format project) · macro-event positioner (needs econ-calendar feed) · index-rebalance (corp-action feed) · gamma-scalp (tick data) · box-arb (borrow rates) · ETF-NAV (institutional data) · AlphaVantage premium backfill ($50/mo, optional).
