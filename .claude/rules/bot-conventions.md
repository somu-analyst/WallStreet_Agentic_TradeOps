---
paths:
  - "telegram_bot_optimized.py"
  - "dashboard.py"
---

# Bot & engine conventions (loads only when touching the bot/dashboard)

## Bot commands (registered in telegram_bot_optimized.py)
- `/start` `/menu` entry · `/gex` signed GEX (walls, zero-gamma flip) · `/vanna` · `/opex` max pain · `/regime` risk-on/off read · `/squeeze`.
- Scanners: `/spreads` · `/wheel` (CSP) · `/cc` covered-call income · `/hiprob` ensemble · `/momentum` · `/earnvol` pre-earnings IV-crush · `/pead` post-earnings drift (needs FINNHUB_API_KEY; 8:45am ET `earnings_alert` pushes both) · `/pairs` sector stat mean-reversion · `/season` seasonality · `/rotate` sector RS · `/revert` 5d reversal z · `/condor` iron condor · `/calendar` ATM calendars · `/divcap` dividend calendar · `/pwindex` put-write backtest (BS approx, educational).
- Narratives: `/wrap` · `/briefing` · `/macro` (BLS+yields, keyless) · `/earnings` · `/event` · `/logevent`.
- DB-first singles: `/rs` (vs SPY) · `/breakout` 52wk · `/zrev` price z · `/vrp` (ATM IV vs MAD realized vol; high→sell premium).
- `/ratings [TICKERS]` — analyst up/downgrades + PT moves 45d (keyless yf `upgrades_downgrades`, Benzinga-via-Yahoo). Net = ups−dns + ½·(PT±). Benzinga RSS also feeds briefing + News page.
- Intraday: `/live` minute writeup · `/heat` heat/reversal scan (z = day move ÷ ATR20·√elapsed; 🔥 z≥1.5+pace≥1.5 trending · 🌀 z≥2 stalling) · `heat_streamer_alert` pushes state CHANGES only. Read `US_intraday.db`; OI is daily → volume/price/IV edge only.
- Flow/positioning: `/uoa` vol/OI ≥2, DTE≥7 · `/building` new OI staged S/I/C.
- `/tax [INCOME]` — lots, ST→LT flip, Pub 550 protective-put clock (chronological vs RUNNING restarted clock; GOOG↔GOOGL class match = first 4 chars & len ±1), QCC, wash sale. Engine `_tax_scan/_fmt_tax`; same panel dashboard Portfolio → P&L. NOT advice.
- `/allocate [sharpe|minvar|rp]` covariance optimizer · `/ic` factor rank-IC validation.
- Tools: `/plan` game plan · `/add` one-line add (order-free: `TICKER 375P YYYY-MM-DD ±QTY @PX [entry-date]` | `TICKER stock QTY @PX [date]`; wizard step 1 accepts typed ticker, 10-min gate in `ai_chat_handler`) · `/journal` · `/bookmarks` · `/tv` · `/terminal` (dashboard; tunnel parked — env `NYSE_MINIAPP_TUNNEL=1` re-enables).
- `/wan` 24-model ensemble stream (15-min job, daily dedup); cached snapshot feeds `ai_chat_handler` plain-text answers.
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

## Dashboard (Streamlit) specifics
- `@st.cache_data(ttl=60)` on yfinance readers (`_cached_history/_cached_price/load_oi_for_date/load_stock_daily`); `ttl=30` `_cached_trades`. Never `st.cache_data.clear()` app-wide — clear per function.
- Nested `st.expander` is forbidden → use `st.toggle` for inner reveals.
- STOCK legs: guard every Black-Scholes call site (`typ=="stock"` / K>0) — shares are linear.
