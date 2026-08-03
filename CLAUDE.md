# NYSE_DATA — Claude Code Reference

<!-- Token diet 2026-07-16: this file loads EVERY session — only non-inferable essentials live
     here. Deep detail is path-scoped in .claude/rules/ (bot-conventions.md loads with the bot/
     dashboard files, workflow.md with docs/) and loads only when relevant. -->

## ⚡ Efficiency rules
- **Canonical files:** `telegram_bot_optimized.py` (~23k lines, THE running bot + engine) · `dashboard.py` (Streamlit, imports the bot at runtime). Edit directly — NEVER patch/helper scripts.
- **NEVER read whole big files** — `Grep` to locate, `Read` with offset/limit. Don't re-read after editing.
- Dates: ALL DB date columns are ISO `YYYY-MM-DD` (censused 07-14/16-2026) → plain string sort/`MAX()`. substr tricks + positional `split('-')` parsing are RETIRED; use `_exp_iso` (bot) / `_exp_to_date` (dashboard).
- `datetime.utcnow()` → `datetime.now(timezone.utc).replace(tzinfo=None)` (3.12+).
- Dead/NULL cols: `vol_rank_call/put`, `money_coi_*`. SPY PCR spikes 11+ on expiry (not signal).
- Secrets gitignored, never commit/print: `token.txt`, `us_bot_*.txt`, `api_keys.enc`, `dash_token.txt`; also `*.db`, `logs/`, `tools/`.
- **Keys live in `api_keys.enc`** (encrypted, machine-bound, THE store). Add one by dropping a plaintext `api_keys.env` (`NAME=value` lines) next to the bot — `_load_api_keys()` merges it in, re-encrypts, and DELETES the plaintext, so `api_keys.env` being absent is normal, not a fault. Currently SET: `ANTHROPIC_API_KEY`, `FINNHUB_API_KEY` (verified live), `ALPHAVANTAGE_KEY`. Every Finnhub reader already falls back `FINNHUB_API_KEY or FINNHUB_KEY` — no alias bug. Macro/`/flow`/`/world`/`/capflow`/`/debate`/OI/scanners are all keyless.
- Git: commit to `main` directly, only when asked. Console prints ASCII-only (Windows cp1252 crashes on ✔/σ/–).
- "test" = validate signal vs DB history (hit-rate vs baseline), not "it runs". Recipe in `.claude/rules/bot-conventions.md`.
- **HARD RULE (2026-07-24, after shipping the SAME broken UI fix twice unverified — see LOG.md):** any Streamlit UI/markdown/HTML change must be verified with a live **headless-browser DOM check** (Playwright: load the real URL, read `inner_text()`/query the DOM) before calling it done. `py_compile` only proves syntax; `curl` only proves the server responds (Streamlit is client-rendered — curl never sees the real page). Neither catches a rendering bug. This is mandatory, not optional, for any change where the RESULT is something a user looks at on screen.
- **LOG TO THE SHEET FIRST — every question and every idea, before answering** (user 2026-08-03).
  The order is: (1) write the row into `docs/IDEA_TRACKER.xlsx`, (2) then answer or build.
  Not after, not "if it turns into work" — a question IS an item, because the answer is what
  gets lost. This applies to throwaway-sounding questions too ("why is X zero", "what is this
  column"): those are precisely the ones that vanished.
- **The tracker is the ONLY source of pending work.** Never type a status table from memory —
  READ the sheet (`python tools/show_pending.py`) and print what it says. A memory-written
  summary already went out stale once, omitting a P1 the sheet did contain.
- **Mid-turn messages: log first, finish current task, then work in order** (user 2026-08-03).
  When the user sends a message while a change is in flight: (1) finish the in-flight edit and
  verify it, (2) add EVERY new ask as a row in `docs/IDEA_TRACKER.xlsx` immediately — before
  answering, (3) then work them in the order given. Answering opportunistically caused real
  losses: several asks were half-answered, and `_world_market_map_png` was fully BUILT but never
  wired to a command because attention moved on before it was finished. The tracker is the queue;
  a message that is not in it will be dropped.
- **Every task should be optimized** (user 2026-07-24): prefer the fewest steps/tool calls that actually verify the outcome — don't re-run expensive checks (full app boot, network calls) more than once per change, don't repeat a failed verification method a second time once it's shown it can't catch the bug class in question, and batch independent checks instead of serializing them.

## 🧭 Working method
- Think before coding: restate task, ≤2 approaches, surgical edits, verify, ask when confused. Conventions win.
- Workflow commands: `/standup` orient → `/plan-task` → `/task-loop` → `/self-review` → `/recap`. `docs/PLAN.md` = queue · `docs/LOG.md` = history · `docs/NEXT.md` = handoff. Manual `/compact` near ~50% context.
- Token-aware: usage tracked (ccusage); offload bulk/mechanical work to cheaper lanes.
- **Limit lockouts (automated):** Stop/PostToolUse hook → `limit_guard.ps1` (threshold `.claude/limit_threshold_tokens.txt`) writes `[RESUME AFTER]` to NEXT.md + schedules `ClaudeResume` (`claude --continue /standup`). Manual: `.\resume_after_limit.ps1 -At "HH:mm"`. If throttling appears mid-session: recap to LOG/NEXT + tick PLAN before stopping.

## ▶️ Run
- Bot: `python telegram_bot_optimized.py` (token from `token.txt`). Dashboard: `streamlit run dashboard.py` (bot auto-launches it, port 8502).
- EOD: `run_all_offhours.py` NY-gated scheduler — **BB PRIMARY first** (`NYSE_OpenBB.py`→derive→`skew_snapshot.py`); Yahoo lane (`NYSE_YFin.py`→`US_data.db` + `NYSE_Telegram.py` legacy report) runs ONLY as fallback when `bb_capture_ok()` fails (<300 tickers for target day). Changed from always-both 2026-07-16.
- Intraday: `NYSE_intraday.py` (1m bars + 30-min CBOE chains → `US_intraday.db`) — AUTO-spawned by the bot's `intraday_lane_supervisor` (heartbeat-gated, separate process on purpose). Feeds `/live` `/heat`.
- Old tests/`core/`/migrations + retired builders live in `archive/` (not wired in).

## 🗺️ Repo map (root)
`telegram_bot_optimized.py` · `dashboard.py` · `run_all_offhours.py` · `NYSE_YFin.py` · `NYSE_Telegram.py` · `NYSE_intraday.py` · `NYSE_OpenBB*.py` · `skew_snapshot.py` · `_lib/`: event_writeup_engine+hooks (real, wired), market_news_enhanced (`get_aggregated_news` used; other 5 fns unused). Deleted 2026-07-24 (100% dead, verified zero call sites): options_tracker.py, market_news_aggregator.py, news_and_earnings.py — each was a superseded abstraction layer; the underlying tables (`trades`, `market_snapshots`, `news_feed`) are still alive via separate, direct code in the main files.

## DB Schema (key tables — PRIMARY DB = `US_data_OpenBB.db`, revert env `NYSE_DB_PATH`)
- `options_change`: ticker, strike, expiry_date, trade_date_now, change_OI_Call/Put, openInt_Call/Put_now/prev, pct_change_OI_*, vol_*_now, lastPrice_*_now, R1, S1
- `options_daily`: same shape (raw snapshot) · `options_openbb`: + real bid/ask/iv/delta per side (`_bb_quote` reads it)
- `stock_daily`: ticker, trade_date, close, pcr_oi, high/low/volume (~6mo) · `stock_history`: multi-year OHLCV — read via `_daily_history`/`_history_matrix` (DB-first, self-maintained)
- `trades`: trade_id, ticker, strategy, entry_date, expiry, status, strike, option_type, quantity, entry_price, pnl. **STOCK legs**: option_type='STOCK', strike 0, expiry '' (never auto-close), qty=shares, multiplier 1, entry_date = tax clock. Bot option analytics EXCLUDE stock rows; universes include them; every BS call site must guard `typ=="stock"`/K>0.
- self-managed: `signal_accuracy`, `signal_weights`, `momentum_ranks`, `gamma_wall_trades`, `event_journal`, `bookmarks`, `alert_dedup`, `us_analytics_daily`, `skew_snapshot`
- `hiprob_recs`: rec_date, ticker, strategy, legs, expiry, dte, pop, ror, k1, k2, net, spot0, capital, status, settle_px, pnl, **`src`**. `src='LIVE'` = actually issued that day · `'BACKFILL'` = reconstructed from captured chains by `_hiprob_scan_asof`. **NEVER pool them** — `/recperf` reports them separately or it would show hindsight as performance. Backfill is bounded by `options_openbb` (needs real bid/ask+IV); `options_daily` reaches further back but is lastPrice-only → recs from it would be fiction.
