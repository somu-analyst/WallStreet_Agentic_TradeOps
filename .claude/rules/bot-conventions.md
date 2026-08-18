---
paths:
  - "telegram_bot_optimized.py"
  - "dashboard.py"
---

# Bot & engine conventions (loads only when touching the bot/dashboard)

## Bot commands (registered in telegram_bot_optimized.py)
- `/start` `/menu` entry · `/gex` signed GEX (walls, zero-gamma flip) · `/vanna` · `/opex` max pain · `/regime` risk-on/off read · `/squeeze`.
- Scanners: `/spreads` · `/wheel` (CSP) · `/cc` covered-call income · `/hiprob` ensemble · `/momentum` · `/earnvol` pre-earnings IV-crush · `/pead` post-earnings drift (needs FINNHUB_API_KEY; `earnings_alert` pushes both at 13:45 UTC = 9:45am EDT / 8:45am EST — the EDT firing is AFTER the open despite the "pre-market" label, see tracker ID 249) · `/pairs` sector stat mean-reversion · `/season` seasonality · `/rotate` sector RS · `/revert` 5d reversal z · `/condor` iron condor · `/calendar` ATM calendars · `/divcap` dividend calendar · `/pwindex` put-write backtest (BS approx, educational).
- Narratives: `/wrap` · `/briefing` · `/macro` (BLS+yields, keyless) · `/earnings` · `/event` · `/logevent`.
- DB-first singles: `/rs` (vs SPY) · `/breakout` 52wk · `/zrev` price z · `/vrp` (ATM IV vs MAD realized vol; high→sell premium).
- `/ratings [TICKERS]` — analyst up/downgrades + PT moves 45d (keyless yf `upgrades_downgrades`, Benzinga-via-Yahoo). Net = ups−dns + ½·(PT±). Benzinga RSS also feeds briefing + News page.
- Intraday: `/live` minute writeup · `/heat` heat/reversal scan (z = day move ÷ ATR20·√elapsed; 🔥 z≥1.5+pace≥1.5 trending · 🌀 z≥2 stalling) · `heat_streamer_alert` pushes state CHANGES only. Read `US_intraday.db`; OI is daily → volume/price/IV edge only.
- Flow/positioning: `/uoa` vol/OI ≥2, DTE≥7 · `/building` new OI staged S/I/C.
- `/tax [INCOME]` — lots, ST→LT flip, Pub 550 protective-put clock (chronological vs RUNNING restarted clock; GOOG↔GOOGL class match = first 4 chars & len ±1), QCC, wash sale. Engine `_tax_scan/_fmt_tax`; same panel dashboard Portfolio → P&L. NOT advice.
- `/allocate [sharpe|minvar|rp]` covariance optimizer · `/ic` factor rank-IC validation.
- Tools: `/plan` game plan · `/add` one-line add (order-free: `TICKER 375P YYYY-MM-DD ±QTY @PX [entry-date]` | `TICKER stock QTY @PX [date]`; wizard step 1 accepts typed ticker, 10-min gate in `ai_chat_handler`) · `/journal` · `/bookmarks` · `/tv` · `/terminal` (dashboard; tunnel parked — env `NYSE_MINIAPP_TUNNEL=1` re-enables).
- `/wan` 24-model ensemble stream (15-min job, daily dedup); cached snapshot feeds `ai_chat_handler` plain-text answers.
- **Added 2026-08-08** (all also in the Macro/Event Hub as tabs):
  - `/dealer` CFTC Traders-in-Financial-Futures — the sell-side FUTURES book, where written options get hedged. 10 PINNED contract codes (name-matching returns MICRO E-mini by mistake). **Read the PERCENTILE, not the level** — dealers are structurally net short index futures, so -33.9% of OI at the 47th pctile is normal.
  - `/whatif TICKER ±PCT` Entropy Pooling scenario — re-weights real history so a view holds, keeping cross-asset correlations. ADOPTED after passing its test (MAE 0.35pp vs 386 real gold-rally windows, 5/5 directions).
  - `/insight` LLM synthesis across book + OI/volume + flow + dealer + vol + news. Every lane block is separately guarded AND must always emit something: a silently-missing lane made the model INVENT positions.
  - `/desk [TICKER]` 11-section research-desk report, every claim tagged + source-cited.
  - `/why` narrative vs OUR data — LLM turns a headline into a falsifiable claim, the DB returns the verdict. Stored in `narrative_checks`; the product is the per-source hit-rate once it accrues.
  - `/feed` public Telegram channel (`_TG_CHANNELS`, t.me/s/ needs no key/session) + LLM read.
  - `/llm` free-provider status + live round-trip. `/xirr` annualised return per holding (suppressed under 30d — annualising noise gives +800%/yr). `/india` NSE EOD + **delivery %** (own DB).
- **Added 2026-08-14**:
  - `/indianews [daily|weekly|monthly]` — material company news on Indian holdings + an advisor
    view per name. Keyless Google News RSS **pinned to India** (`hl=en-IN&gl=IN`); the US-pinned
    feed used elsewhere buries domestic coverage. Searches the **company name**, not the bare
    symbol (TITAN/BSE/MMTC are English words or other companies) — names cached in `india_names`.
    8 materiality buckets; non-material price blurbs are dropped. Job `india_news_job` at 02:30
    UTC (~08:00 IST, pre-open) serves all three horizons: weekly on Fri, monthly on the last weekday.
    **Keyword matching is letter-bounded, never a bare substring** — `"ban" in "bank"` filed every
    HDFC/ICICI/Axis headline under Regulator.
    ⚠️ **The advisor layer is PAID-Anthropic-only by design**: its prompt names the user's
    holdings, and the free tier trains on prompts. No key ⇒ news without advice, never a
    silent downgrade to the free lane.
- **Added 2026-08-10**:
  - `/positions` — the REAL book. It never existed before: the open book was menu-button-only,
    so typing `/positions` did nothing. The command delegates to `positions_view`, which only
    uses `.message.reply_text` — an Update carries that too, so there is no second renderer.
  - **Country flags on holdings** — `_ticker_flag(tk)` resolves suffix (`.NS`→🇮🇳, 45 of them)
    → `_CROSS_MARKET` adr/etf/lev/internet → `_FLAG_EXTRA` curated ADRs → `ticker_country`
    cache → 🇺🇸 default. **Offline by design** (a `.info` call is 1-2s; a 20-name book would
    blow the Telegram timeout) — `tools/seed_ticker_country.py` fills the cache out of band.
    NSE membership is NOT a lane: BSE/TITAN/MMTC collide with US tickers. Dashboard shares the
    same resolver through `_flag_of`/`_with_flag` — never reimplement it there.
  - `_disp_w` counts a **regional-indicator PAIR as 2 cells, not 4**. Charging 2 per codepoint
    made every header row sit 2 cells wider than its flagged data rows.
  - Ticker grammar in `_parse_add_args` is 15 chars and may start with a digit (`RELIANCE.NS`,
    `7203.T`). The old 8-char letter-first cap silently rejected long foreign symbols.
- **Previously undocumented (swept 2026-08-08)** — these were live but appeared in no doc:
  - `/antibubble` anti-bubble watchlist
  - `/board` command board
  - `/breaking` market-wide + your-positions breaking news, two sections
  - `/catalysts` catalyst radar — events with consensus vs actual
  - `/catchup` what you missed — fires on laptop open, then hourly
  - `/data` data-health / capture audit
  - `/digest` EOD digest (morning/midday/evening editions)
  - `/feargreed` Fear & Greed history 1d/1w/1m/3m/1y, reconstructed
  - `/freq` alert frequency control
  - `/gexcheck` GEX pre-trade check
  - `/gexplan` GEX blueprint for a ticker
  - `/heatmap` sector treemap PNG, tile=market cap, colour=move
  - `/paper` paper-trading book
  - `/premium` premium-selling scan
  - `/reopen` reopen a closed trade
  - `/riskoff` risk-on/off master read
  - `/rotation` sector rotation tracker
  - `/rovalidate` risk-on/off validation
  - `/screen` 8 master-investor fundamental screens (Buffett/Munger/Graham/Lynch…)
  - `/skew` put-skew panel
  - `/status` bot + lane health
  - `/watchlist` watchlist add/edit/list
  - `/whymoved` why a name moved — cause + knock-on
- Most scanners are ALSO in dashboard: ⚙️ Strategy Scanners (24) + 📡 Macro/Event Hub (incl. Live/Heat/Skew/Catalysts/Regime tabs) via `_render_tg` bridge — one engine, no duplication.

## Telegram UX conventions (2026-07-16)
- Wizards morph in place: `_wiz_show(query, text, kb)` edits the SAME message per step; falls back to reply.
- Inline mode: `inline_query_handler` = `@bot TICKER` autocomplete (needs BotFather `/setinline` once).
- Long reports: `<blockquote expandable>` per section (see `/plan`; strip-and-resend fallback).
- Scanner output = `_pipe_table` rank table (≤28 chars wide) + per-row HTML detail lines (see `_send_spreads`, `/ratings`) — never crammed single-line bullets.

## Tables — ALWAYS `_report()` / `_pipe_table()`
- `_report(title, headers, rows, right_cols, legend, notes, details)` = THE universal
  result-message macro (header bar + table + legend + detail lines + italic note) — use it
  for every new tabular command output. Tables embedded mid-narrative use `_pipe_table` directly.
- Swept 2026-07-16: momentum/opex/squeeze/macro/gex/OI-expiry-flow all converted off hand-rolled
  `<pre>` grids. Charts = `make_mini_chart` PNG.
Emoji/width-aware (`_disp_w`: emoji/CJK=2). Status emoji in column 0 only (🟢/🔴/🟡). Numbers → `right_cols`, K/M notation. `title`/`legend` render outside `<pre>`. Never hand-roll `mono()` grids.

## Key functions
`_oi_signal_light` hedge-aware OI light · `_oi_intent_algo` per-strike intent · `_compute_gex` GEX/flip/walls · `high_prob_signals_engine` 24-model ensemble (weights in `signal_weights`) · `_bb_quote` OpenBB bid/ask/IV/delta for one contract · `_exp_iso` (bot) / `_exp_to_date`+`_gp_norm_date` (dashboard) date normalizers — NEVER positional split('-') parsing · scanners `_spreads_scan_bot/_wheel_scan_bot/_hiprob_scan/_live_momentum_scanner/compute_universe_momentum`.

## Signal logic
- Mean Rev composite: `PCR_z×1.5 − Price_z − NetOI_z`; ≥+3 → LONG; 20d lookback.
- Gamma walls: call+put OI ≥ 2× mean · Max pain: min Σ ITM loss per expiry.
- Put skew: skip expiries where call < $0.50 · VIX/VIX3M >1.05 backwardation, <0.95 contango.
- Spreads score = 0.40·POP + 0.25·R/R + 0.20·cushion + 0.15·liquidity; drop `maxp/maxl≤0.05`, credit `net/width<0.05`, `rr<0.10`. NaN IV is truthy → guard `not (iv>0)`. NaN pnl: `x or 0` does NOT catch NaN — use `pd.isna`.

## Signal validation recipe ("test" = prove it would've been right)
1. Pull historical fires from `options_change`/`stock_daily` per past trade_date (ISO, plain sort).
2. Join forward return: `fwd_ret = close_{t+N}/close_t − 1` (N≈3/5/10).
3. Hit-rate = % where sign matches the call; compare vs unconditional baseline same window.
4. Persist to `signal_accuracy` → adaptive weights flow to `signal_weights`.
5. Report `_pipe_table` (signal·N·hit%·avg fwd·vs base); flag thin N (~6-mo history is weak).

### ⛔ NEVER use a pooled rank-IC t-stat (proven broken here, 2026-07-31)
Stacking every (ticker, date) into one correlation and computing
`t = IC·√(N−2)/√(1−IC²)` is INVALID on this data and will manufacture edge:
- **Overlap** — fwd-5d returns sampled daily share 4 of 5 days with the next observation.
- **Cross-correlation** — 700+ tickers all load on the market; one day is nowhere near
  700 independent draws.
Nominal N (~100k) is therefore ~100x overstated and t inflates by roughly √100 ≈ 10x.

**Measured on this exact DB:** of randomly generated alpha expressions, **68% clear p<0.05**
under the pooled test and **46% clear |t|>4** (best random hit |t|=8.15). A correct test
rejects **0%** of them. This is not theoretical — it already produced one wrong shipped
result (`/debate` Technical weight, reverted).

**Use instead — daily cross-sectional IC:**
1. For each date, rank-correlate the signal against fwd return ACROSS tickers → one IC per day.
2. Sample dates `[::N]` so windows don't overlap.
3. `scipy.stats.ttest_1samp(daily_ics, 0)` — N is now ~days, not ~observations.
4. Sanity-gate any new harness by running random signals through it first; if more than
   ~5% pass p<0.05, the harness is broken, not the signal.

Hit-rate-vs-baseline (steps 1–5 above) is unaffected — it makes no independence claim.
Null results from the pooled method remain valid (inflation can only create false
POSITIVES); positive results from it must be re-tested.

## Dashboard (Streamlit) specifics
- `@st.cache_data(ttl=60)` on yfinance readers (`_cached_history/_cached_price/load_oi_for_date/load_stock_daily`); `ttl=30` `_cached_trades`. Never `st.cache_data.clear()` app-wide — clear per function.
- Nested `st.expander` is forbidden → use `st.toggle` for inner reveals.
- STOCK legs: guard every Black-Scholes call site (`typ=="stock"` / K>0) — shares are linear.

### ⛔ Never tune a parameter on the data you then judge it on (2026-08-02)
The pooled t-stat was one way this project manufactured edge; **in-sample fitting is the
other**. Picking a lookback / threshold / weight over all history and then reporting its
score on that same history is not a backtest, it is a description of the past.

**Anything that CHOOSES a parameter must go through `tools/walkforward.py`.**
Anything that only scores a FIXED signal may call `daily_ic` directly.

```python
from walkforward import walk_forward, daily_ic, sanity_gate
walk_forward(px, fit, signal, horizon=5, n_folds=5)   # fit() sees TRAIN ONLY
```

Rules the harness enforces:
- **Expanding window.** Fold k trains up to d_k, tests on (d_k, d_k+h]. Never trains on
  anything after its own test window.
- **Refit inside every fold.** Choosing one parameter over all history and then "walking
  it forward" is still in-sample.
- The train window stops `horizon` short, or its last labels peek into the test window.
- Test ICs are de-overlapped by the horizon before any t-test (same reason as the ban above).
- **Judge on the pooled TEST folds only.** Train IC is printed alongside on purpose: a large
  positive **train−test gap is the overfitting signal**.

**Self-test on the real DB (120 tickers x 1400 days, 2026-08-02):** cross-sectional momentum
with the lookback refit per fold scored train IC +0.0179 vs test IC +0.0113 — pooled test
t=+0.75, p=0.49, **does not survive**. Note fold 5 alone reads +0.066 (t=+1.89); a single
flattering fold is exactly what an ad-hoc backtest would have reported. Sanity gate on the
same panel: 2.5% of random signals passed (expect ~5%).
