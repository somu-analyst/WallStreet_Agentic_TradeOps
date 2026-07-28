# PLAN — remaining work (source of truth)

> Cross-model/session handoff. Keep this current; `LOG.md` records what's done, `NEXT.md` holds the one-glance switch-over note.
> Worked by `/task-loop` (loop-engineering): pick top unchecked → implement → verify → commit `loop: …` → tick here.

## Goal
Options-trading edge system: Telegram bot + dashboard + our own capture-forward options DB
(bid/ask/IV/delta), every signal validated against DB history — less API dependence, more provable edge.

## Open tasks
- [x] **Format-sweep COMPLETE 2026-07-17** — every genuine tabular reply now `_report()`/`_pipe_table`
  (/earnvol shape, ST emoji col 0). Final batches (commit 9237648): mirofish, group-save, confirm
  cards, quote view, RSI/MACD/BB/EMA/score, macro+positions minis, GTC orders, portfolio+ticker
  risk summaries, HP model+backtest tables, short-interest ranking, smart-money UOA/blocks, gamma
  advisor structure/ticket/expiry-walls, edge lab. Kept plain (judgment, narrative not tables):
  roll-detector descriptions, mood lines, keyless-macro fallback, note/detail mono() one-liners.
  Standard = `_report()`/`_pipe_table` (emoji col 0, ≤28 chars, legend) — user re-confirmed
  2026-07-17: EXACT /earnvol shape, ST emoji col FIRST, never text signal columns. DONE so far:
  all `_fmt_*`/`_send_*` formatters + positions_view + momentum/opex/squeeze/macro/gex/OI-flow +
  weekly-flow + prop setups + whale holdings + OI strike breakdown (tables A/B/C, OI timelines,
  summary, trade ideas — reworked to ST-emoji shape 07-17). REMAINING inventory (telegram_bot_optimized.py `mono(`/`"<pre>"` sites,
  line numbers pre-sweep, convert ONLY genuine multi-row tables — key:value metric readouts may
  stay mono): L2558, 2902-2929, 2990, 3126, 3259, 3294, 3630, 3935, 4024/4037, 4084, 5161-5167,
  5280/5282, 5359, 5898, 6899-6973 (indicator readouts — judgment call), 7356, 7543, 7808, 7844,
  7886/7892, 9465, 10972 (prop setups), 11019/11042, 11080 (whale holdings), 11153-11175,
  12016/12051/12167, 12826, 13203-13242, 13509/13600 (risk summaries), 15818-15883, plus any
  below L15900. Per /task-loop iteration: convert ~6-8 sites → verify render vs live DB
  (fake-query pattern in LOG) → commit → tick here. Restart bot after final batch.
- [~] Telegram Mini App (user ask 2026-07-16 "new age app"; Tier-1 UX shipped same day: morphing wizards, table+detail scanners, @bot inline search, collapsible /plan). **Phase 1 BUILT+VERIFIED 2026-07-16 then DISABLED by user ("no public exposure for now"):** `/terminal` is local-only (boots Streamlit 8502, replies localhost link). Full tunnel path (cloudflared quick tunnel + `web_app` button + `dash_token.txt` gate) stays in code behind env `NYSE_MINIAPP_TUNNEL=1`; re-enable also needs `tools\cloudflared.exe` re-downloaded (github.com/cloudflare/cloudflared releases — was verified working, then deleted). Phase 2 (later): purpose-built mobile SPA with TelegramUI React kit (github.com/telegram-mini-apps-dev/TelegramUI, tma.js SDK; crib hermes-telegram-miniapp) + initData HMAC auth; optional named tunnel for a STABLE domain.
- [x] Intraday lane — BUILT 2026-07-15 per design: `NYSE_intraday.py` (root) = market-hours loop (EDT/EST-union UTC gate, no tz dep) → `US_intraday.db`: 1m bars full-day-upsert (self-healing) for open positions + 30 leaders, 30-min CBOE CDN chain snapshots (spot/ATM-IV/PCR-vol/top-vol strikes) for positions only. Bot consumers: `/live` minute-writeup (VWAP dislocation, pace vs 20d, 15m burst, IV drift, breadth) · `/heat` heat-seeking/reversal scan (z = day move ÷ ATR20·√elapsed; 🔥 HEAT = z≥1.5 + pace≥1.5 + trending, 🌀 FADE = z≥2 + stalling/low-fuel) · `heat_streamer_alert` 15-min job pushing STATE CHANGES only (alert_dedup `heat_stream`, fresh-bars gate). Verified live: GS earnings day flagged 🔥 (+10.2%, z+3.9, 1.6x), JPM correctly unflagged (0.8x pace); staleness banner works. Volume time-of-day norm is LINEAR (approx) — U-shape refinement + heat-state backtest (house rule) once a few days of bars accrue. Launcher DONE same day: bot `intraday_lane_supervisor` (5-min job) auto-spawns/respawns the capture loop during market hours, gated on a `lane_meta` heartbeat so manual starts never duplicate. Follow-up: [ ] validate heat/fade states vs forward 30-60m returns after ~1-2 wks of bars.
- [x] **Portfolio track — DONE 2026-07-21 (Phases 1-3): MCP server (6 tools) + FTS5 RAG + Docker/compose/DOCKER.md.** Commits 66808f1 / 98db2c3 / e250c96. Remaining OPTIONAL: k8s manifest + CI + cloud deploy; and one `docker build` on a Docker-enabled host (never built here).
  Order: (1) MCP server exposing engine tools (get_positions/scan_premium/oi_breakdown/backtest_signal)
  via stdio MCP — headline skill, ~1 session; (2) RAG layer over event_journal + news + LOG.md with
  citations; (3) Dockerfile + docker-compose (bot + dashboard + DB volume) → free-tier deploy
  (Fly.io / Oracle ARM) + k8s manifests (k3d locally is enough); (4) README w/ architecture diagram +
  3-min demo video + short write-up for LinkedIn. Secrets stay out of images (env mounts).
- [ ] NSE holdings lane (user ask 2026-07-15: data + holdings tracking + OI/volume/price advice — NO trading APIs). VERIFIED endpoints: equity bhavcopy `nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` (200 OK, has **DELIV_PER** = real delivery % — better than the US volume proxy); F&O bhavcopy (same archive, UDiFF zip) = daily per-strike OI for ΔOI; live option-chain JSON (`nseindia.com/api/option-chain-equities`) responds but needs nsepython-style session handling — treat as optional garnish. BUILD: `NSE_EOD.py` daily (~09:00 ET = post-close IST, can piggyback run_all_offhours pre-market window) → own `NSE_data.db` (`nse_stock_daily` w/ delivery%, `nse_options_daily` → ΔOI, same schema pattern as US lane) → `/india` bot cmd + dashboard section scoped to .NS holdings: OI signal light, PCR, delivery%-backed accumulation (deliv%↑ + price↑ = institutions taking delivery), volume vs 20d, price action. `.NS` STOCK legs already track TODAY via yfinance (verified RELIANCE.NS etc.); FX-normalize ₹ P&L + optional Indian tax profile (LTCG 12.5% >1y above ₹1.25L, STCG 20%) as sub-items. `archive/NSE.py` = old lane, mine for parsing code. **Re-verified 2026-07-24** (user asked about OpenBB/Databento for India data): OpenBB has no dedicated India provider — its yfinance provider is a passthrough to the same yfinance library, confirmed working (`obb.equity.price.historical('RELIANCE.NS', provider='yfinance')` returns real data) but adds nothing over calling yfinance directly. Databento ruled out: no NSE/BSE coverage, paid-only, built for institutional low-latency use — wrong fit for this project's free-tier design. Sticking with plain yfinance for the NSE lane.
- [x] Bot stock-position awareness — DONE 2026-07-16: `/plan` now shows STOCK legs (📦 shares @entry, P&L, held-days LT/ST, 🛡 covered-call/protective-put hedge context via GOOG↔GOOGL class match + tax-clock warning); shares count in Net Δ, SPY-Δ and concentration but stay OUT of the option analytics (K>0 assumed). Stock-only tickers get their own block (`_pl_tickets` empty-guard).
- [x] Smart-Money "Volume-backed accumulation" tab pulled 0 stocks — FIXED 2026-07-14 (uncommitted): `_accumulation_screen` now split-aware (CRWD 4:1 on 07-02 detected & rescaled; ~integer-ratio >40% jumps = splits, closes/volumes adjusted), accurate 1d/5d/20d windows; tab rebuilt as TWO tables — 🟢 BUY (accumulation: rising 5d&20d) and 🔴 SHORT (distribution: falling 5d&20d, rides top ΔOI PUT via new `_sm_strike_map` `doi_p`) — with tiered fallback (vol>1.3× → >1.1× → quiet movers, tier labeled) so it never goes blank. Verified vs live DB: BUY→WFC (relaxed), SHORT→ORCL/UVXY (strong).
- [ ] BS next-day model insights → dashboard (validated 2026-07-14, scripts in session scratchpad `bs_validate/bs_tune/bs_liquid.py`; 1.2M contract-days, time-split): Est Open can't beat naive (kill/relabel); scenario "stock hits X → leg ≈ $Y" is the accurate output (liquid 22-45 DTE: close 5.3%/high 3.6%/low 5.2% med err); recipe = mid-quote IV anchor + liquidity gate (vol≥100, spread≤8%, grey-out others) + keep decay/sticky-IV as-is + no GBM (overfits on clean data); Day L–H already calibrated (72% ≈ 1σ). User to pick which parts to wire in.
- [x] (user) Parallel-test OpenBB vs yfinance for 3–5 days — GATE MET 2026-07-14: compare run over all 6 overlapping days (07-02→07-13): **6/6 PASS** (median OI diff ≤0.36%, lastPrice within 2% on 92–98%); BB also captured 07-09 which Yahoo missed. Cutover (DB_PATH flip) remains user's call. (Also fixed: verdict print was crashing cp1252 consoles on ✔ glyph — now ASCII.)
- [ ] (user, weekly) Offsite copy of `openbb_chains\*.parquet` (+ `US_data_OpenBB.db` if convenient) — capture-forward data is unrebuildable
- [~] Production migration to OpenBB (IN PROGRESS — user wants to eventually retire yfinance fully):
  - [x] Parity checked: BB vs Yahoo raw OI corr 1.000/0.999 (100% within 5%), lastPrice 0.995-0.998, vol 0.999 (75-82% within 5% = snapshot-timing); coverage 734 vs 88 tickers.
  - [x] Enrichment bridge `NYSE_OpenBB_derive.py` — SELF-CONTAINED (own copy of the derivation, no NYSE_YFin import, so yfinance code can be deleted later). Maps `options_openbb`→`options_daily`, then computes `options_change` (change_OI/R1/S1/now-prev) + `stock_daily` (--stock). Same schema as Yahoo → DB_PATH flip needs no bot/dashboard change. VALIDATED: 07-07 change_OI corr 0.9998, R1/S1 0.9998 vs Yahoo. (07-06 change_OI diverges — 07-02 baseline seam, not a logic issue.)
  - [x] Wire `NYSE_OpenBB.py` + `NYSE_OpenBB_derive.py` into `run_all_offhours.py` to run PARALLEL with the Yahoo fetch each EOD — VERIFIED 2026-07-14: 7/7 trading days captured (Jul 2→13, 734 tickers every run; BB even has Jul 9 which the Yahoo lane missed). skew_snapshot was manual-only (stale after Jul 7) — FIXED 2026-07-14: backfilled all 7 dates (~730 tickers/day) + wired into the nightly lane after derive (idempotent, self-heals).
  - [x] Cutover DONE (confirmed 2026-07-14): bot + dashboard default `DB_PATH` = `US_data_OpenBB.db` (734 tickers, full history seeded); revert via env `NYSE_DB_PATH`. Yahoo lane stays as nightly backup (`NYSE_YFin.py` → `US_data.db`; `NYSE_Telegram.py` report still reads it). Root tidy: `NYSE_OpenBB_EOD.py` + `_rewrite_portfolio.py` → `archive/`.
  - [x] OpenBB bid/ask/iv/delta into bot reads — DONE 2026-07-16: new `_bb_quote()` (latest `options_openbb` row → real bid/ask mid + IV + delta); `/plan` legs anchor to live yf mid → BB mid → DB last, and use BB REAL IV instead of solving implied from last-trade. Also fixed `_plan_prem` ISO bug (was `_to_mdy`-converting before querying the ISO `expiry_date` column → returned None for every leg). Verified: GOOGL 375P mid 19.50 / IV 38.4% flows into the plan.
- [x] Profile remaining `NYSE_YFin.py` stages — `stage_timer()` + `finalize_timing()` instrument phases 1-7 (4a fetch loop / 4b OHLC enrich / 4c DB write / 4d weekly-monthly refresh split out); prints longest-first summary + appends `yfin_stage_timings.csv`. Read the CSV after the next EOD run to see where the 4 hrs go.
- [x] Action Board daily Telegram digest — `/board` + `action_board_alert` (8:35 AM ET, weekday-gated) aggregate today's `scn_*` fires across 5 DB-first scanners (reversal/z-rev/52wk/OI-build/UOA); consensus = ≥2 scanners agree on direction; mobile-safe _pipe_tables. Bot-side mirror of the dashboard `_ab_ideas()` Action Board.
- [x] Scanner backtest — DONE 2026-07-16 (fires were NEVER persisted; signals RECOMPUTED per historical day over ~7mo stock_daily/options_change, t+5 signed fwd, persisted to `backtest_summary`): **revert VALIDATED** (N=362, 54% vs 49% base, +2.69% avg — the one real edge) · **uoa direction FAILED** (N=434, 46%, −0.35% — flow ≠ direction, consistent with riskoff finding) · **building direction FAILED/ANTI** (N=1108, 47%, −1.47% — naive OI-build direction anti-predicts; treat /building as descriptive, not directional). Rerun script: session scratchpad `backtests_p2_p3.py` pattern.
- [~] Heat/fade first read 2026-07-16 (N=6/5 from 2 days of bars — useless sample, FADE 1/5): harness built + persisted; RERUN after ~2 wks of intraday bars accrue.
- [~] Skew25 panel IC first read: 6 dates, mean daily rank-IC +2.2 (t=0.59 — noise; sign currently OPPOSITE the downside hypothesis). Rerun at 15–20 dates.
- [x] `/skew [TICKERS]` shipped on **live yfinance IV** (not OpenBB — kept parallel): direction (25Δ put−call skew via true BS delta) + size (1σ EM) + range (1σ/2σ down targets) + P(≥5%↓), earnings-in-window flag. Universal. `_skew_analyze/_skew_scan/_fmt_skew`.
- [ ] (gated: ~1 mo of OpenBB bid/ask captures) Dispersion (#14) + a skew *backtest* on the OpenBB `skew_snapshot` panel (does high 25Δ skew / put-flow predict fwd downside? need ~15-20 dates)
- [x] Catalyst Radar — `/catalysts [TICKERS]` + `catalyst_alert` (8:20 AM ET, ≤3d): earnings (per-ticker yfinance) + macro (FOMC in-code · CPI/PCE hardcoded 2026 · Jobs/NFP computed first-Friday) on the open book. The one intraday-ish nudge so EOD signals aren't blindsided by scheduled events. `_macro_events/_upcoming_catalysts/_fmt_catalysts`.

## DONE — 13F CIK audit (2026-07-24, 3 rounds, closed out)
- [x] **13F CIK re-audit.** Fixed 11 wrong/stale CIKs total in dashboard.py `_EDGAR_FUNDS`, each
  verified via conformed-name + a real recent filing date before swapping in: Vanguard ↔ Soros
  (SWAPPED with each other), Trian (dormant since 2011), Appaloosa, Viking Global, Oaktree, Gotham
  (dormant since 2009), Hotchkis & Wiley, Wasatch (renamed key — old CIK was the FUND not the
  advisor), Brandes (upgraded to the main LP filer), First Pacific Advisors, Moore Capital, Third
  Avenue. Markel-Gayner and Jana Partners re-checked and found FINE (heuristic false positives).
  Genuinely unresolved, left as-is: Omega Advisors (Cooperman — no newer registered entity found)
  and Greenlight (Einhorn — a DME Advisors LP lead was inconsistent under closer check). Running
  detail lives in a code comment right above `_EDGAR_FUNDS`.

## PENDING USER DECISIONS (carried 2026-07-21 → open)
- [x] ~~Vol analyst sign flip~~ (`_agent_vol`) — **ALREADY DONE**, found stale 2026-07-24 while building the `/debate` Bull/Bear round: code was flipped+dampened back on 2026-07-22 (docstring at `_agent_vol` confirms: "Sign flipped 2026-07-22... weight is dampened to 0.4"). This PLAN.md line was stale, not an open decision.
- [x] ~~`/debate` weight rebalance~~ — **DONE 2026-07-27** (see A17 below / commit fb97b29): built the actual agent-level backtest. Technical has a real edge (rank-IC +0.047, t=+7.05) — the earlier "-0.039 reversal" number also didn't replicate, it was equally unverified. Macro has zero edge vs SPY's own fwd return (t=-0.01), same verdict as Flow. Weights: Technical 1.0→1.3, Macro 0.7→0.3; Flow and Position (GEX, untested) left untouched.
- [x] ~~`_lib` orphan triage~~ — **DONE 2026-07-24** (commit d47908d): deleted `options_tracker.py`, `market_news_aggregator.py`, `news_and_earnings.py` (100% dead, verified zero call sites); underlying tables (`trades`/`market_snapshots`/`news_feed`) remain alive via separate direct code in the main files.

## Kronos foundation model (user ask 2026-07-22 — RESEARCHED, not built)
- [ ] Evaluate **Kronos** (`github.com/shiyu-coder/Kronos`, MIT, AAAI 2026) — first open-source foundation model for K-lines (OHLCV), 45 exchanges. Family: mini 4.1M/2048ctx · small 24.7M/512 · base 102.3M/512 · large 499.2M (weights NOT public). Probabilistic: `sample_count` paths via temperature/top_p.
  - **Fit:** `stock_history` (multi-year OHLCV, 734 tickers) is already exactly the input format. Path ensembles map onto POP / expected-move / 1σ ranges — currently computed from a single ATM-backed IV under a lognormal assumption (`_hiprob_scan`).
  - **Machine reality (verified 2026-07-22):** NO GPU, no torch/transformers installed, Python 3.13.14, 12 cores/16.6GB RAM, 24GB disk free. CPU-only ⇒ favour **mini/small**; base is feasible but slow; large unavailable anyway.
  - **BLOCKER for validation — pretraining leakage.** Kronos was pretrained on historical market data through an unpublished cutoff. Backtesting it on `stock_history` 2016–2026 is CONTAMINATED and will manufacture a fake edge. Any test must be strictly out-of-sample vs that cutoff (or forward-tested live). This is the single biggest trap.
  - Note repo's own caveat: its backtest demo is "not a production-ready quantitative trading system"; no accuracy benchmarks published. Qlib is needed only for their fine-tune demo — **inference does not require Qlib** (which stays out of scope).

## Adjacent-framework ideas (user 2026-07-24 — RESEARCHED, not built)
Deep-dived 3 repos the user asked about as a possible "AI hedge fund desk" architecture:
`koala73/worldmonitor` (74.1k★, real intel dashboard), `TauricResearch/TradingAgents` (94.5k★,
paid-LLM multi-agent debate framework), `NousResearch/hermes-agent` (real, self-improving
personal agent runtime). Wholesale adoption of any of the three rejected — TradingAgents needs
paid LLM calls per decision (conflicts with this project's free/deterministic design); worldmonitor
and hermes-agent are much bigger standalone products than a bolt-on. Four smaller, genuinely
scoped pieces worth doing instead, none requiring new paid dependencies:
- [x] ~~Bull-vs-Bear adversarial round in `/debate`~~ — **DONE** (commit 69e23a0): `_debate_bull_bear_case()` + `_debate_verdict_schema()`, structured Action/Entry/Stop/Target output, targets sized off real 5-day realized vol. Verified against live AAPL (BUY) and SPY (HOLD).
- [x] ~~Optional LLM prose-polish layer~~ — **DONE** (commit bd74c1f): `_debate_polish()`, `/debate TICKER polish` or a "✨ Polish" button. Verified the fallback path is bulletproof (forced a real APIConnectionError in this sandbox — Avast SSL interception, since fixed separately — confirmed identical deterministic output returned byte-for-byte).
- [ ] **Local-LLM narrative synthesis (Ollama, free)** — worldmonitor's core pattern: synthesize
  the day's headlines into an actual brief via a locally-run model, not just a headline list +
  `_headline_tone` score. Needs Ollama installed locally; zero API cost either way. Deferred
  2026-07-24 (Ollama not installed in this environment) — user to decide whether to install it.
- [x] ~~Country/supply-chain instability flag~~ — **DONE** (commit 2331abb): `_country_instability_flags()`, starter map (TSM/NVDA/AMD/AVGO/QCOM→Taiwan, AAPL/TSLA→China, NKE→Vietnam, ASML→Netherlands), scans existing keyless RSS aggregation for country name + geopolitical keyword. `/catalysts` gains a "GEOPOLITICAL / SUPPLY-CHAIN" section only when something fires. Verified: real call (correct empty result, no active conflict headline) + synthetic test (fake Taiwan-strait headline correctly flagged NVDA/TSM/AAPL).
- [x] ~~Persistent user-preference memory~~ — **DONE** (commit c456717): `ticker_interest` table,
  `/debate` logs a +1 view per ticker checked, dashboard Watchlist now orders by views DESC.
  Verified: standalone SQL test + live Playwright check against a running dashboard instance.

## Constraints / decisions locked in
- CLAUDE.md rules win: edit `telegram_bot_optimized.py`/`dashboard.py` directly (no patch scripts), single-engine (dashboard imports the bot), dates now ISO YYYY-MM-DD everywhere (substr sort trick retired 07-14-2026), secrets never committed/printed, `US_data.db` never written by NYSE_OpenBB.py.
- "Tested" = validated vs DB history (hit-rate vs baseline), not "it runs".
- Commit to `main`, one atomic commit per completed task; nothing pushed to remote unless asked.

## Out of scope (for now)
- qlib port (own data-format project) · macro-event positioner (needs econ-calendar feed) · index-rebalance (corp-action feed) · gamma-scalp (tick data) · box-arb (borrow rates) · ETF-NAV (institutional data) · AlphaVantage premium backfill ($50/mo, optional).

## ALERT CONSOLIDATION + polish (planned 2026-07-23, easy → hard)

Goal: stop ~5 recurring pushes filling the chat. Mechanism is Telegram
`editMessageText` — ONE status message edited in place, not re-sent.

### 1. [x] EASY — Market-structure table — DONE (commit 4f63e60)
Levered-ETF block in the Wrap writeup is now `_pipe_table` (`ST | ETF | Lev | Day%`),
sorted worst→best, replacing the old "worst fund named in a sentence" prose.

### 2. EASY — Read-through / narrative as links (~15 min)
Long narrative paragraphs (READ-THROUGH, OUTLOOK) → single clickable line via
`<a href>`, or wrap in `<blockquote expandable>` (already used by `/plan`).

### 3. MEDIUM — Timeline event-state bug (CORRECTNESS, not cosmetic)
Timeline prints scheduled times as if the event happened: "08:30 ET — Jobless
Claims release" shows even when no data has landed. That is a false statement.
Fix: tag each row `upcoming / awaiting / released`, only asserting release when
we hold the value. Widen window to **T−2 … T+2 days** (user ask) so you see what
is coming and what just passed.

### 4. HARD — Single edited STATUS message  ← the real win
- Store `status_msg_id` in `app_settings`.
- Recurring jobs (position_monitor, intraday_alert, heat/momentum, futures)
  write into ONE message via `bot.edit_message_text`; send only if no id or the
  edit 400s (message gone), then re-store the new id.
- Sections wrapped in `<blockquote expandable>` so the combined message
  collapses instead of running for pages.
- **Keep as separate pushes** anything that is genuine NEWS and should
  interrupt: assignment/pin risk firing, earnings landing, data-health break,
  trigger alerts. Recurring status is not news.
- Watch: combined length. Everything merged tonight had to be re-narrowed for
  mobile width (~40 chars); build sections narrow from the start.

### Notes
- Telegram edit has a rate limit — do not edit more often than ~1/5s per chat.
- Editing loses history; that is the trade-off and why event alerts stay separate.

## OI intent: separate BUYING from WRITING (user 2026-07-23)
"call OI building — bullish bets" is an unjustified leap: rising OI = contracts
OPENED, and every option has a buyer AND a writer. A call build 10% OTM is
usually covered-call WRITING, not a bullish bet. (Same error already fixed on the
money-flow chart labels; the text descriptions still carried it.)

**Build:** classify each strike by OI change x PRICE change — data is already in
`options_change` (`lastPrice_Call_now` + prior close):
  OI up + price up   -> BUY-TO-OPEN   (directional)
  OI up + price down -> WRITE/SELL-TO-OPEN (income/premium, NOT directional)
  OI dn + price up   -> SHORT COVERING
  OI dn + price down -> LONG LIQUIDATION
Combine with `_oi_intent_algo` zones (ATM = directional, >7% OTM call = covered
call, deep-OTM put = hedge).

**Also asked:** roll the read ACROSS EXPIRIES — same-week vs multi-week builds are
different animals (event play vs calendar roll vs sustained positioning).
`_oi_expiry_flow_table` already has per-expiry CdOI/PdOI to key off.

# ══ FULL AUDIT of 2026-07-23 session asks (user: "you missed many") ══
Compiled by re-reading the whole session. NOT DONE items are the real backlog.

## ❌ NOT DONE — asked, never built
| # | Ask | Where it stalled |
|---|-----|------------------|
| A1 | ~~Post-earnings IV crush in "Now" price~~ | **Already DONE (commit 24ec185, 2026-07-23), stale row.** During RTH, `cur_px` now overrides the BS/captured-IV model with a real live option mid (`_live_opt_mid`) whenever the market is open — the exact GOOG 300P case (was ~6.99 modelled vs ~6.10 real) is the case the fix comment cites. Outside RTH (market closed) the model still stands, correctly, since there's no live market to quote. |
| A2 | **HP engine spot is EOD, not live** — PARTIAL fix 2026-07-24 | Checked all 4 call sites of `high_prob_signals_engine`: /plan positions-card + morning-briefing callers already fetch a separate live spot via `_get_spot_with_ah()` for display, engine only used for its signal — those were fine. The ONE real leak: `_wan_ai_context()` fed the AI chat prompt an unlabeled `spot $X` (the engine's EOD stock_daily close) — fixed, now explicitly labeled "EOD close (engine input, not live)". Did NOT touch the engine itself — its EOD memoization is a documented, deliberate perf tradeoff (avoid recomputing 24 models every 60s refresh), not an oversight. If a genuinely live-priced variant is wanted for some future use, that's a separate ask. |
| A3 | ~~Sell-side LIMIT prices~~ | **DONE 2026-07-24** — added `_smart_close_limit()` + `_fetch_option_quote()` (dashboard.py). Both option-leg `Close @` sites (Next-Day Game Plan's flat view AND by-stock view — same `_legs`/`_by_tk` data, two render layouts) now start 1/3 into the spread from the best price (ask when selling to close, bid when buying to close), floored/ceilinged at mid; falls back to the old buffer heuristic (tagged "(est)") when no live quote. Checked: the Exit Planner's separate local `_fetch_option_mid` (inside `_ep_batch_table`) is NOT a duplicate `Close @` — it's only used for entry-side P&L math, no closing-limit suggestion there. Nothing left to fix. |
| A4 | ~~Hedge/spread exit advice for max price~~ | **DONE 2026-07-24** — `_spread_summary()` now gives a real 3-rung combo closing ladder (debit spreads SELL the combo, start above marketable; credit spreads BUY it back, start below marketable), same edge-preserving principle as A3. Caught + fixed a sign bug during testing (credit-spread close_value needed negating). Verified against hand-checked fake debit + credit spreads. |
| A5 | ~~OI buy-vs-write classifier~~ | **DONE 2026-07-27** (commit bc5373e) — `_oi_buy_write_split()` self-joins `options_daily`'s raw snapshot at whatever `trade_date` actually preceded `trade_date_now` (no assumed "yesterday") to get the missing prior lastPrice, classifies OI-up strikes as buy-open (price up) vs write-open (price flat/down), wired into `/oi`'s BULLISH/BEARISH rows. Verified live: several "BULLISH" call builds (NVDA, INTC, QQQ, AAPL) are actually >95% write-to-open — confirms the labeling bug was real. |
| A6 | ~~Same-week vs multi-week OI read~~ | **DONE 2026-07-24** — `_oi_expiry_flow_table` now classifies SUSTAINED (same direction across ≥2 expiries) / CALENDAR ROLL (near unwinding + far building same direction) / EVENT-ISOLATED (only the near expiry has a lean). Verified against synthetic fixtures — live AAPL/TSLA/GOOG/NVDA all show straddle bias (no directional lean) so the read correctly stays silent for them right now. |
| A7 | ~~Calendar events (FOMC/CPI) into EVENTS table~~ | **DONE 2026-07-24** — different bug than described (no `_ev_bits` blanking found), but a real one: dashboard's News & Calendar → Economic Calendar tab was a hardcoded static 2026-05/06 event list, stale as of 07-24 (showing already-passed events as "upcoming"). Replaced with a live call to the bot's `_macro_events(days=120)` (FOMC/CPI/PCE/Jobs, correctly future-filtered). Also fixed while in there: two divergent `_FOMC_DATES` lists existed (2953 and 32358) — Dec 2026 read 12-16 in one, 12-09 in the other; verified 12-09 is correct (Fed's own Dec 8-9 2-day meeting) via web search, consolidated to one list. |
| A8 | ~~Timeline event-state~~ | **Resolved as a side effect 2026-07-24** — the literal "08:30 Jobless Claims prints as released" bug couldn't be found in current code after multiple searches this session; the closely-related root cause (dashboard's News & Calendar tab had a stale HARDCODED event list with 2026-05/06 dates shown as "upcoming" months after they'd passed) was found and fixed independently — both calendar displays (Macro/Event Hub + News & Calendar) now compute live from `_macro_events()` and only ever show real upcoming items with day-counts, never a false "released" claim. If the original T-2..T+2 upcoming/awaiting/released tagging is still wanted as a distinct feature, re-open with a concrete example screenshot. |
| A9 | **Read-through / narrative as LINKS** | Not started. |
| A10 | **Single consolidated alert message** | Planned only (editMessageText design in PLAN). ~5 recurring pushes still separate. |
| A11 | ~~Dashboard: Summary + Per-leg detail at TOP~~ | **DONE 2026-07-24** (commit 3bc98b1) — used `st.empty()` to reserve the output slot right after the Analysis Mode radio, filled in later after `_legs`/`_by_tk`/`_checklist` finish computing; execution order is unchanged, only the DOM position of the section's output moved. A prior cut-paste attempt crashed (`NameError: _by_tk`) and was reverted — this is the real fix, verified live via Playwright (Layout/tables now render before Manage-positions/macro/Monte Carlo in the actual DOM). |
| A12 | **Dashboard: market overview collapsible dropdown at top** | Not started. |
| A13 | **Portfolio Greeks as dropdown** | Not started. |
| A14 | ~~Wire PEAD into a command~~ | **DONE** — `/pead` registered (`pead_command`, telegram_bot_optimized.py:27577), stale audit line. |
| A15 | **Dashboard Portfolio page render-check** | ~12 commits touched it; NEVER once opened. |
| A16 | ~~`_lib` orphan triage (B: position lifecycle, C: forex/crypto)~~ | **CLOSED 2026-07-27 — verified false alarm, no build needed.** (B) `options_tracker.py`'s `enter_trade/exit_trade/check_exit_conditions` was a parallel, never-called state machine over its own schema — the live bot already has a real, wired lifecycle on the actual `trades` table (`INSERT INTO trades` x2, `/add`, `/reopen`, tax-clock tracking, live mark repricing) that superseded it before the file was ever deleted. (C) `market_news_aggregator.py`'s `get_forex_news/get_crypto_news` were dedicated-category news scrapers with zero call sites; BTC-USD/ETH-USD/EURUSD=X PRICE data is already deeply wired (`/world`, `/flow`, macro wrap, cross-asset tables — 30+ call sites), and general world news (`_world_news_block` via `market_news_enhanced`) already surfaces major market-moving headlines including crypto/forex events. A dedicated forex/crypto news feed would be new scope, not a recovered gap — not building it without an explicit ask. |
| A17 | `/debate` weight rebalance | **DONE 2026-07-27** — ran the actual agent-level backtest (150 tickers, ~150d, fwd-5d, point-in-time formula replication). Technical: real edge, rank-IC +0.047 t=+7.05 (the −0.039 figure didn't replicate either — was also unverified). Macro: zero edge vs SPY fwd (t=−0.01), same verdict as Flow. Weights updated: Technical 1.0→1.3, Macro 0.7→0.3. Flow (1.2, zero edge, still highest) and Position (GEX, untested) left untouched — see code comment above `_AGENT_WEIGHTS`. |
| A18 | SI buildup/covering validation vs baseline | Blocked ~2-3 months on `short_interest` history accruing. |

## ✅ DONE (for the record)
AH prices (fast_info bug) · AH all-evening · AH alerts after close · manual button
throttle · /freq picker · vol-analyst flip · SELL_PREMIUM 0.0% scoring bug ·
BOOK RISK · EXPIRY/ASSIGNMENT · per-leg Buy→EOD→AH+TOTAL · Greeks per leg ·
CLOSED TODAY · spread/HP/OI/earnings tables · paired-warning once · news filtered ·
earnings est/actual stored · transcripts (AlphaVantage, on disk, go-forward) ·
2 orphan charts wired · volume panel · heatmap axis · sparklines · OPEX column ·
yield curve · mobile width sweep · OI PCR column · spy_ret param bug ·
Mag-7 study · PEAD validated · TSLA close recorded · dashboard AH fix ·
dashboard default page · Src column · SI columns

### A1 attempt 1 — FAILED, reverted (2026-07-23)
Wired the existing crush ratio into the leg reprice for events that have already
happened. **Overcorrected badly** — verified before shipping:

    GOOG 300P, spot 318.70, market ~6.50
      captured IV 38.6% -> 6.99   (7.5% HIGH  — the bug)
      crushed  IV 27.0% -> 3.35   (48% LOW    — my "fix")

**Why:** GOOG 300P expires Aug-28 (36 DTE). That expiry never carried the
earnings premium — event premium lives in the FRONT expiry. `_post_event_leg`'s
own docstring already says "ratio >= 1 means THIS expiry carries no event
premium (GOOG Aug-28 ...)". My helper applied a front-expiry crush to a
far-dated leg.

**Correct approach next time:** crush must scale with how much of the leg's
variance sat in the event — roughly, only the front expiry gets the full ratio;
a 36-DTE leg gets little to none. Back-solve the market IV where a live quote
exists (~35% here) rather than modelling the haircut. Better still: refresh IV
from a live chain for tickers that just reported, instead of adjusting a stale one.

Do NOT re-apply a flat ratio across all expiries.
