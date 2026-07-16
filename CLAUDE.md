# NYSE_DATA — Claude Code Reference

## ⚡ Efficiency rules (read first — saves tokens / avoids limits)
- **Canonical files:** `telegram_bot_optimized.py` (~23k lines, THE running bot) · `dashboard.py` (Streamlit). Edit these directly — no patch/helper scripts.
- **NEVER read whole big files.** `telegram_bot_optimized.py`/`dashboard.py` are huge → use `Grep` to locate, then `Read` with `offset`/`limit`. Don't re-read a file you just edited.
- `telegram_bot_optimized.py` = THE single source (bot runtime + engine). `dashboard.py` imports IT at runtime (hub + 24-model engine + macro pages) — no more root `telegram_bot.py` (archived 2026-07-02; `build_optimized.py` retired too, both under `archive/`).
- Dates: ALL DB tables are ISO `YYYY-MM-DD` now (censused 07-14-2026: options_change/options_daily/stock_daily/stock_history 100% ISO) → plain string sort/`MAX()` works. The old `MM-DD-YYYY` substr sort trick is RETIRED — don't reintroduce it.
- `datetime.utcnow()` → `datetime.now(timezone.utc).replace(tzinfo=None)` (3.12+).
- Dead/NULL cols: `vol_rank_call/put`, `money_coi_*`. SPY PCR can spike 11+ on expiry (not signal).
- Secrets: `token.txt`, `us_bot_*.txt`, `api_keys.env/.enc` are gitignored — never commit/print. `*.db`, `logs/`, `*.log` ignored too.
- Git: commit to `main` directly (no feature branches) only when asked.

## 🧭 Working method (think → act, save tokens)
<!-- Condensed; full long-form detail in .claude/rules/workflow.md (loads contextually). -->
- **Graph first:** if `graphify-out/GRAPH_REPORT.md` exists, read it before `Glob`/`Grep` to locate god-files, subsystems, and reusable code. If absent, generate it via `/graphify` (or `graphifyy` CLI) — don't assume a graph exists.
- **Think before coding:** restate the task in one line, weigh ≤2 approaches and pick the simplest, state assumptions, make surgical/local edits, define how you'll verify, and stop to ask when genuinely confused.
- **Token-aware:** usage is tracked (ccusage / claude-monitor). Prefer short, file-scoped spec-style prompts; avoid re-running expensive scans/builds; reuse cached context; disable unused tools/MCP servers; for big jobs outline the plan + token impact before staging.
- **Scope small:** one focused task per prompt, ~2–3 sessions/day; lean on slash commands and existing skills instead of ad-hoc multi-step asks.
- **Agentic workflow (`.claude/commands/`):** `/standup` orient → `/plan-task` decompose into PLAN.md → `/task-loop` implement·verify·commit·tick → `/self-review` audit the commit → `/recap` handoff. Side lanes: `/route` (Claude vs cheaper lane) · `/research` (read-only Explore subagent) · `/map` · `/validate-signal` · `/usage`. PLAN.md = queue, LOG.md = history, git = one commit per loop iteration.
- **Conventions win:** match existing patterns; if a request conflicts with the rules above, follow the project rules and flag the conflict.
- **Multi-provider lanes:** Claude = hard/multi-file/security work; offload bulk research, summarizing, and routine mechanical edits to cheaper lanes (Gemini / local agents) when it conserves limits.
- **Continuity files (`docs/`):** `docs/PLAN.md` = remaining work (source of truth) · `docs/LOG.md` = done/decisions/blockers · `docs/NEXT.md` = short switch-over notes. Update before a context reset or handoff to another model/session.
- **Session hygiene:** keep this file < ~200 lines (move deep specialized rules to `.claude/rules/*.md` with `paths:` frontmatter); manual `/compact` near ~50% context; recap to `LOG.md` every ~10–20 messages; keep subtasks under half the context window.
- **Limit lockouts:** when usage is throttled, write a fresh-start summary to `LOG.md`/`NEXT.md` and resume cold from those rather than replaying the whole thread.

## ▶️ Run · build · test
- **Bot (runtime):** `python telegram_bot_optimized.py` → `main()` (≈L23203) → `app.run_polling`; token from `token.txt`. This is the live process — edit it directly for runtime fixes.
- **Rebuild (retired):** `telegram_bot_optimized.py` was originally generated from `telegram_bot.py` by `build_optimized.py` — BOTH now live in `archive/` (root copy removed 2026-07-02; dashboard repointed to optimized). Edit `telegram_bot_optimized.py` directly.
- **Dashboard:** `streamlit run dashboard.py`.
- **EOD pipeline:** `run_all_offhours.py` = NY-time-gated scheduler (pre-mkt 00:00–09:00 → prev trading day; post-close 17:00+ → today; keeps Windows awake). Launches JOB1 `NYSE_YFin.py` (yfinance/curl_cffi fetch → writes `US_data.db`) then JOB2 `NYSE_Telegram.py` (OI/price/vol PNGs + Excel + send).
- **Tests / parallel `core/` / migrations:** moved to `archive/` (see below). Run from there, e.g. `cd archive && python -m core.validate --ticker SPY` or `pytest archive/tests/`.

## 🗺️ Repo map
- **Entrypoints (root):** `telegram_bot_optimized.py` (bot) · `dashboard.py` (Streamlit, launched by bot) · `run_all_offhours.py` (EOD scheduler → `NYSE_YFin.py` + `NYSE_Telegram.py`) · `NYSE_intraday.py` (market-hours 1m-bar + 30-min CBOE-chain capture → own `US_intraday.db`; AUTO-spawned/respawned by the bot's `intraday_lane_supervisor` job via `lane_meta` heartbeat — separate process on purpose: bot restarts must not gap unrecoverable 1m bars, and sync sweeps would stall the async loop; feeds `/live` `/heat` + heat streamer).
- **Data layer:** `NYSE_YFin.py` (fetch/enrich → DB) · `NYSE_Telegram.py` (daily report + charts).
- **Shared engine:** `telegram_bot_optimized.py` — `dashboard.py` imports it everywhere (hub, 24-model engine, macro pages). One file, no sync needed. (`archive/telegram_bot.py` = old source, unused.)
- **`archive/`** (not wired into the running bot): `build_optimized.py`; duplicates/standalone `bot_optimized.py`, `streamlit_dashboard.py`, `send_organized_report.py`, `run_event_writeups.py`, `run_eod_pipeline.py`+`eod_pipeline/`, `NSE.py`; manual utilities `NYSE_OpenBB_EOD.py` (multi-year stock_history backfill) + `_rewrite_portfolio.py` (one-off, moved 2026-07-14); tools `core/`, `tests/`, `migrations/`; and `_lib/{abnormal_activity_detector,market_events_db,options_flow_detector,telegram_rich_formatter}`.

### `_lib/` modules (root — the 7 the bot actually loads)
- `event_writeup_engine` — automated pre/post-market event narratives (macro releases, earnings, intraday regime breaks). `event_writeup_bot_hooks` — Telegram scheduling hooks (ET times) for those writeups.
- `news_and_earnings` — Finnhub news/earnings/dividends/events. `market_news_aggregator` — news+data across stocks/indices/commodities/FX/crypto. `market_news_enhanced` — premium-source news with links.
- `options_tracker` — open-positions/Greeks helper; dynamically imported by the bot for `get_open_positions`.
- (Archived `_lib`: `market_events_db`, `options_flow_detector`, `abnormal_activity_detector`, `telegram_rich_formatter` — used only by archived apps.)

### Bot commands (registered in `telegram_bot_optimized.py`)
- `/start` `/menu` entry + command list · `/gex` signed GEX profile (walls, zero-gamma flip) · `/vanna` vanna exposure · `/opex` OPEX / max pain · `/regime` market regime (VIX term structure) · `/squeeze` squeeze scan.
- Scanners: `/spreads` · `/wheel` (CSP) · `/cc` covered-call income (OTM calls ranked by annualized yield vs call-away POP; IV-rank + earnings-before-expiry flag) · `/hiprob` high-prob ensemble · `/momentum` momentum ranks · `/earnvol` pre-earnings IV-crush (IV-rank + expected move; short-premium vs long-vol) · `/pead` post-earnings drift (Finnhub EPS surprises; beat→long/miss→short; needs FINNHUB_API_KEY). Daily 8:45am ET **Earnings Radar** job (`earnings_alert`) pushes /earnvol + /pead together · `/pairs` within-sector stat mean-reversion (spread z-score + half-life; risky screen, NOT riskless arb) · `/season` calendar seasonality (on-the-fly ~10y yfinance: current-month avg/win-rate, day-of-week, turn-of-month; weak/decaying edge) · `/rotate` sector-ETF relative-strength ranking (blended 1/3/6-mo return, excess vs SPY; overweight leaders) · `/revert` cross-sectional short-term reversal (5-day return z-score; oversold bounce vs overbought fade) · `/condor` iron-condor range income (short strikes ~1 expected-move OTM, defined-risk wings; ranked by POP + return-on-risk) · `/calendar` ATM call calendar spreads (sell near/buy far; ranked by front/back IV richness) · `/divcap` dividend calendar (forward yield + next ex-date; assignment-risk aware; not free money) · `/pwindex` approximate put-write index backtest (BS-priced monthly ATM puts, IV=RV+VRP; vs buy-and-hold — educational, not real option marks).
- Narratives/data: `/wrap` market wrap · `/briefing` daily briefing · `/macro` macro (BLS+yields) · `/earnings` earnings/news · `/event` event writeup · `/logevent` add event.
- RelStr/MeanRev: `/rs` single-stock relative strength vs SPY (3M/6M excess) · `/breakout` 52-week highs/lows · `/zrev` single-name price z-score vs 20d mean. All DB-first `stock_history`, in dashboard hub.
- Vol: `/vrp` variance risk premium — ATM IV (`_iv_rank`) vs jump-robust realized vol (MAD estimator, so earnings gaps don't inflate RV); high VRP→sell premium (🔴), negative→buy vol (🟢). Also in dashboard hub.
- Ratings: `/ratings [TICKERS]` — analyst upgrades/downgrades + price-target raises/cuts, last 45d (keyless `yf.Ticker().upgrades_downgrades`, Benzinga-sourced via Yahoo — no paid Benzinga API). Net = ups−downs + ½·(PT raises−cuts); median PT; defaults to open positions else skew universe. Also in dashboard Strategy Scanners hub. Benzinga markets RSS also feeds the briefing headlines + dashboard News page.
- Intraday: `/live [TICKERS]` minute-level writeup (VWAP dislocation, volume pace vs 20d, 15m burst, ATM-IV drift, breadth) · `/heat` heat-seeking/reversal scan (z = day move ÷ ATR20·√elapsed; 🔥 HEAT z≥1.5+pace≥1.5+trending · 🌀 FADE z≥2+stalling) · `heat_streamer_alert` 15-min job pushes state CHANGES only. All read `US_intraday.db` (needs `NYSE_intraday.py` running); OI is daily → volume/price/IV edge only.
- Flow: `/uoa` unusual options activity — contracts with today's volume ≫ standing OI (vol/OI ≥2), DTE≥7 to skip 0DTE index churn; calls=bullish/puts=bearish; ranked by $ notional; `options_change` only. Also in dashboard hub.
- Positioning: `/building` positioning-builder — new/increasing call OI (LONG) or put OI (SHORT) vs standing OI, staged S(tarting)/I(ncreasing)/C(onfirmed, price already moving) from `options_change` + `stock_daily`. Finds bets forming before/as the move starts. Also in dashboard hub.
- Tax: `/tax [INCOME]` — stock tax lots: holding period, ST→LT flip date + $ saved by waiting, est. tax if sold now (2026 MFJ brackets approx, defaults $200K), protective-put clock-reset + qualified-covered-call + wash-sale warnings, realized YTD ST/LT. Engine `_tax_scan/_fmt_tax`; same panel in dashboard Portfolio → P&L Breakdown tab. NOT tax advice.
- Portfolio: `/allocate [sharpe|minvar|rp] [TICKERS]` — Aladdin-style risk optimizer: long-only weights from the `stock_history` covariance (max-Sharpe tangency / min-variance / risk-parity), weight-capped; reports ann μ/σ/Sharpe. Native (numpy, no dep). Defaults to open-position tickers. Also in dashboard hub.
- Validation: `/ic` Alphalens-style factor IC — cross-sectional rank IC (Spearman) + quantile spread vs forward returns over stock_daily history (factors: reversal/momentum/lowvol; reports N + t-stat; ~6mo = low power). Also in dashboard hub.
- Tools: `/plan` trade planner · `/add` one-line position add (order-free grammar: `TICKER 375P YYYY-MM-DD ±QTY @PX [entry-date]` or `TICKER stock QTY @PX [entry-date]`; Add-Position wizard step 1 also accepts a TYPED ticker, 10-min freshness gate in `ai_chat_handler`) · `/journal` trade/event journal · `/bookmarks` saved items · `/tv` TradingView chart bridge.
- `/wan` WAN-streamer: live snapshot of actionable 24-model ensemble signals (BULL/BEAR, conf≥MED, prob≥70). Also runs as a 15-min `run_repeating` job (market-hours, daily dedup) that pushes new fires; its cached snapshot feeds `ai_chat_handler`, so plain-text questions like "why is NVDA bullish?" are answered with the live signal context.

## Tables (Telegram) — ALWAYS use the shared helper
- `_pipe_table(headers, rows, right_cols=None, title=None, legend=None)` → Excel-style `<pre>`, **emoji/width-aware** (`_disp_w`: emoji/CJK=2) so columns align at the same index. `title` (bold+stars) and `legend` (italic key) render OUTSIDE `<pre>`.
- Put status emoji in **column 0** only (uniform 🟢/🔴/🟡 family) so it doesn't shift columns. Numbers → `right_cols`. K/M notation (452K not 452,000). Don't hand-roll `mono()` grids — route through `_pipe_table`.
- "test" = validate signal correctness vs DB history, not just that it runs.

## DB Schema (key tables)
- `options_change`: ticker, strike, expiry_date, trade_date_now, change_OI_Call/Put, openInt_Call/Put_now/prev, pct_change_OI_Call/Put, vol_Call/Put_now, lastPrice_Call/Put_now, R1, S1
- `stock_daily`: ticker, trade_date, close, pcr_oi (also high/low/volume)
- `options_daily`: same as options_change (raw daily snapshot)
- `trades`: trade_id, ticker, strategy, entry_date, expiry, status (OPEN/CLOSED), strike, option_type, quantity, entry_price, pnl. **STOCK legs** (2026-07-15): option_type='STOCK' = shares — strike 0, expiry '' (never auto-close), qty=share count, multiplier 1 (not ×100), entry_date = purchase date (drives tax clock). Dashboard fully supports (covered-call/protective-put/collar detection, payoff, exit planner); bot option analytics EXCLUDE STOCK rows (27 queries guarded), ticker universes include them.
- `us_analytics_daily`: call_notional_oi, put_notional_oi, bull_score, bear_score, avg_spot
- self-managed: `signal_accuracy`, `signal_weights`, `momentum_ranks`, `gamma_wall_trades`, `event_journal`, `bookmarks`, `alert_dedup`
- `stock_history`: ticker, trade_date, open, high, low, close, volume (multi-year daily; DB-first history layer). Read via `_daily_history(tk, years)` (single) / `_history_matrix(tickers, years)` (universe) — DB-first; backfill = `_fetch_yf_history`; write-through; maintained FREE by `_sync_history_from_daily()` folding in `stock_daily`. Powers `/ic`, `/season`, `/rotate`, `/pwindex` with years of history instead of the ~6mo `stock_daily` window.
- **PRIMARY DB = `US_data_OpenBB.db`** (cutover 2026-07-14 after 6/6 compare PASS): bot+dashboard default `DB_PATH` to it (734 tickers, real IV/bid-ask/delta in `options_openbb`, `skew_snapshot` IV panel; full history seeded back to 2025-12). Revert switch: env `NYSE_DB_PATH` → `US_data.db`. Yahoo lane (`NYSE_YFin.py` → `US_data.db` + `NYSE_Telegram.py` report) keeps running nightly as the BACKUP feed. BB lane in scheduler: `NYSE_OpenBB.py` capture ∥ Yahoo fetch → `NYSE_OpenBB_derive.py` → `skew_snapshot.py`.

## Key functions
- `_oi_signal_light(call_chg, put_chg, pcr)` — hedge-aware aggregate OI signal
- `_oi_intent_algo(df, spot)` — per-strike intent (ATM/NEAR/DEEP zones)
- `_compute_gex(ticker, conn, spot)` — signed GEX, zero-gamma flip, call/put walls
- `high_prob_signals_engine(ticker, conn, spy_ret)` — 24-model ensemble (adaptive weights in `signal_weights`)
- `analyze_oi_rolls / analyze_mean_reversion / analyze_inst_signals / analyze_technical_signals`
- Scanners: `_spreads_scan_bot`, `_wheel_scan_bot`, `_hiprob_scan`, `_live_momentum_scanner`, `compute_universe_momentum`

## Signal logic
- Mean Rev composite: `PCR_z×1.5 - Price_z - NetOI_z`; ≥+3 → LONG; lookback 20d
- Gamma Walls: call+put OI ≥ 2× mean OI · Max Pain: min Σ ITM loss per expiry
- Put Skew: skip expiries where call < $0.50 · VIX/VIX3M >1.05 BACKWARDATION, <0.95 CONTANGO
- Spreads score = 0.40·POP + 0.25·R/R + 0.20·cushion + 0.15·liquidity; drop legs `maxp/maxl≤0.05`, credit `net/width<0.05`, `rr<0.10`. NaN IV is truthy → guard `not (iv>0)`.

## 🔬 Signal validation ("test" = prove it would've been right)
Running ≠ tested. To validate a signal, backtest it against DB history and report hit-rate + avg forward return, not just "no crash."
1. **Pull historical fires** of the signal from `options_change`/`stock_daily` (or recompute it per past `trade_date`). Dates are ISO `YYYY-MM-DD` — plain string sort works.
2. **Join forward return:** for each fire on day *t*, get `stock_daily.close` at *t+N* (N≈3/5/10) for the same ticker → `fwd_ret = close_{t+N}/close_t - 1`.
3. **Score by bucket:** hit-rate = % of fires where `sign(fwd_ret)` matches the call (LONG→up); also avg `fwd_ret`. Compare vs the unconditional baseline over the same window.
4. **Persist** results to `signal_accuracy` and let adaptive weights flow to `signal_weights` (the ensemble reads these).
5. **Report** as a `_pipe_table` (signal · N · hit% · avg fwd · vs base). Flag thin samples — current ~6-mo hit-rates are weak/low-N, so don't over-claim.

## Streamlit caching
- `@st.cache_data(ttl=60)` yfinance: `_cached_history/_cached_price/load_oi_for_date/load_stock_daily`; `ttl=30` `_cached_trades`. Auto-close OPEN trades where expiry < today on portfolio load.
