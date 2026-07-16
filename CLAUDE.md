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
- Secrets gitignored, never commit/print: `token.txt`, `us_bot_*.txt`, `api_keys.env/.enc`, `dash_token.txt`; also `*.db`, `logs/`, `tools/`.
- Git: commit to `main` directly, only when asked. Console prints ASCII-only (Windows cp1252 crashes on ✔/σ/–).
- "test" = validate signal vs DB history (hit-rate vs baseline), not "it runs". Recipe in `.claude/rules/bot-conventions.md`.

## 🧭 Working method
- Think before coding: restate task, ≤2 approaches, surgical edits, verify, ask when confused. Conventions win.
- Workflow commands: `/standup` orient → `/plan-task` → `/task-loop` → `/self-review` → `/recap`. `docs/PLAN.md` = queue · `docs/LOG.md` = history · `docs/NEXT.md` = handoff. Manual `/compact` near ~50% context.
- Token-aware: usage tracked (ccusage); offload bulk/mechanical work to cheaper lanes.
- **Limit lockouts (automated):** Stop/PostToolUse hook → `limit_guard.ps1` (threshold `.claude/limit_threshold_tokens.txt`) writes `[RESUME AFTER]` to NEXT.md + schedules `ClaudeResume` (`claude --continue /standup`). Manual: `.\resume_after_limit.ps1 -At "HH:mm"`. If throttling appears mid-session: recap to LOG/NEXT + tick PLAN before stopping.

## ▶️ Run
- Bot: `python telegram_bot_optimized.py` (token from `token.txt`). Dashboard: `streamlit run dashboard.py` (bot auto-launches it, port 8502).
- EOD: `run_all_offhours.py` NY-gated scheduler → Yahoo lane (`NYSE_YFin.py`→`US_data.db`, backup) ∥ BB lane (`NYSE_OpenBB.py`→`NYSE_OpenBB_derive.py`→`skew_snapshot.py`).
- Intraday: `NYSE_intraday.py` (1m bars + 30-min CBOE chains → `US_intraday.db`) — AUTO-spawned by the bot's `intraday_lane_supervisor` (heartbeat-gated, separate process on purpose). Feeds `/live` `/heat`.
- Old tests/`core/`/migrations + retired builders live in `archive/` (not wired in).

## 🗺️ Repo map (root)
`telegram_bot_optimized.py` · `dashboard.py` · `run_all_offhours.py` · `NYSE_YFin.py` · `NYSE_Telegram.py` · `NYSE_intraday.py` · `NYSE_OpenBB*.py` · `skew_snapshot.py` · `_lib/` (7 loaded: event_writeup_engine+hooks, news_and_earnings, market_news_aggregator, market_news_enhanced, options_tracker).

## DB Schema (key tables — PRIMARY DB = `US_data_OpenBB.db`, revert env `NYSE_DB_PATH`)
- `options_change`: ticker, strike, expiry_date, trade_date_now, change_OI_Call/Put, openInt_Call/Put_now/prev, pct_change_OI_*, vol_*_now, lastPrice_*_now, R1, S1
- `options_daily`: same shape (raw snapshot) · `options_openbb`: + real bid/ask/iv/delta per side (`_bb_quote` reads it)
- `stock_daily`: ticker, trade_date, close, pcr_oi, high/low/volume (~6mo) · `stock_history`: multi-year OHLCV — read via `_daily_history`/`_history_matrix` (DB-first, self-maintained)
- `trades`: trade_id, ticker, strategy, entry_date, expiry, status, strike, option_type, quantity, entry_price, pnl. **STOCK legs**: option_type='STOCK', strike 0, expiry '' (never auto-close), qty=shares, multiplier 1, entry_date = tax clock. Bot option analytics EXCLUDE stock rows; universes include them; every BS call site must guard `typ=="stock"`/K>0.
- self-managed: `signal_accuracy`, `signal_weights`, `momentum_ranks`, `gamma_wall_trades`, `event_journal`, `bookmarks`, `alert_dedup`, `us_analytics_daily`, `skew_snapshot`
