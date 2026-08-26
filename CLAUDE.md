# NYSE_DATA — Claude Code Reference

<!-- Token diet 2026-07-16: this file loads EVERY session — only non-inferable essentials live
     here. Deep detail is path-scoped in .claude/rules/ (bot-conventions.md loads with the bot/
     dashboard files, workflow.md with docs/) and loads only when relevant. -->

## ⚡ Efficiency rules
- **Canonical files:** `telegram_bot_optimized.py` (~43k lines, THE running bot + engine) · `dashboard.py` (Streamlit, imports the bot at runtime). Edit directly — NEVER patch/helper scripts. A new feature starts IN these files; `sankey_income.py` began standalone and had to be folded back in (`35015c0`). Analysis scripts in `tools/` are fine — a second copy of engine LOGIC is not.
- **NEVER copy a constant out of the engine.** `tools/measure_signal_base_rates.py` hardcoded the grading thresholds under a comment saying "must mirror `_score_signal`" — a promise a comment cannot keep, and a silent wrong-verdict generator the day the engine changed. It now imports them and refuses to run rather than guess. Same rule anywhere else.
- **The engine speaks TELEGRAM HTML** (`<b>…</b>`). Streamlit renders Markdown and `st.warning/error/success` cannot take `unsafe_allow_html` at all — engine text dropped into a markdown call prints its tags on screen (Market Radar, 2026-08-23). Route it through **`_tg_md()`**.
- **Changing a cached function's return SHAPE? Bump the cache key.** `@st.cache_data` keeps serving the old shape and the page dies with a type error that looks like a data bug.
- **NEVER read whole big files** — `Grep` to locate, `Read` with offset/limit. Don't re-read after editing.
- Dates: ALL DB date columns are ISO `YYYY-MM-DD` (censused 07-14/16-2026) → plain string sort/`MAX()`. substr tricks + positional `split('-')` parsing are RETIRED; use `_exp_iso` (bot) / `_exp_to_date` (dashboard).
- `datetime.utcnow()` → `datetime.now(timezone.utc).replace(tzinfo=None)` (3.12+).
- `vol_rank_*` / `money_*` / `chg_oi_*` are GONE — dropped from `options_daily` 2026-08-08 (10 cols, 216MB). SPY PCR spikes 11+ on expiry (not signal).
- Secrets gitignored, never commit/print: `token.txt`, `us_bot_*.txt`, `api_keys.enc`, `dash_token.txt`; also `*.db`, `logs/`, `tools/`.
- **NEVER rewrite a source file from PowerShell** (`Set-Content`/`Out-File`). PS 5.1 reads UTF-8 through the ANSI codepage and writes it back double-encoded — it silently destroyed **1,914 emoji + 5,537 box chars** across the 1.9MB bot on 2026-08-08, and the file still compiled and ran, so nothing failed loudly. Use the Edit tool. Same reason heredocs are banned for code containing `\n`.
- **NEVER wrap a ticker column in `UPPER()` in a WHERE clause.** It defeats `idx_oo_lookup`: `SCAN` 1,685ms vs `SEARCH` 5.1ms on options_openbb — **330x**. All 47 ticker tables are verified all-uppercase and every call site already `.upper()`s its parameter, so it is pure waste. Fixed at 33 sites 2026-08-08; a dispersion snapshot went ~10min → 0.28s.
- **2-decimal cap**: `_pipe_table` truncates any purely-numeric cell with 3+ decimals (user 2026-08-08). Dates/tickers untouched. Result columns only — the fractional-share qty INPUT stays 4dp on purpose. **The dashboard needs its own cap**: a bare pandas `Styler` falls back to `display.precision=6`, so a Streamlit grid shows `101.000000` even when the value was `round(x, 2)` at source — always `.format(precision=2, thousands=",")` (found 2026-08-10, ID 203).
- **Keys live in `api_keys.enc`** (encrypted, machine-bound, THE store). Add one by dropping a plaintext `api_keys.env` (`NAME=value` lines) next to the bot — `_load_api_keys()` merges it in, re-encrypts, and DELETES the plaintext, so `api_keys.env` being absent is normal, not a fault. Currently SET: `ANTHROPIC_API_KEY`, `FINNHUB_API_KEY` (verified live), `ALPHAVANTAGE_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GOOGLE_API_KEY`.
- **Free-LLM lane (2026-08-08)**: ONE OpenAI-compatible client `_llm_chat()` → providers in `_LLM_PROVIDERS` (Groq primary, then Google AI Studio, then OpenRouter). Swapping provider = base_url + model, never a rewrite. `/llm` shows status + live round-trip. Groq free tier 14,400 req/day, no-training. **Google's free tier DOES train on prompts** — public news only, never position data (use the paid Anthropic key for that). OpenRouter `:free` slugs CHURN (4 died on 2026-08-08); if one 404s, list `/api/v1/models` and pick a live one. Every Finnhub reader already falls back `FINNHUB_API_KEY or FINNHUB_KEY` — no alias bug. Macro/`/flow`/`/world`/`/capflow`/`/debate`/OI/scanners are all keyless.
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
- **Reading the pending LIST is not reading the ROW.** `show_pending.py` truncates each item to
  one line; the `Detail` / `Next Step` columns hold the diagnostic content. Before ACTING on an
  item, dump its full row. On 2026-08-14 ID 217's `Detail` named a second, untested failure
  hypothesis ("`_positions_card_parts` is SHARED by the 10-min push — a throw there would
  silence it") which turned out to be a real unguarded crash path in a scheduled job; it was
  found only because the user asked whether the sheet was being followed.
- **Write the tracker through `tools/tracker_io.py` — never hardcode an ID.** Two sessions
  edited the workbook at once on 2026-08-12, both computed "next ID" from a stale copy, and
  the second save won: 5 rows collided and 4 lost their outcome text to an ID-keyed update
  landing on the wrong row. `add()` allocates max(ID)+1 at write time; `update(..., expect=)`
  refuses to write unless the question text matches.
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
- Bot: `python telegram_bot_optimized.py` (token from `token.txt`). Dashboard: `streamlit run dashboard.py` (port 8502). The two are INDEPENDENT — the bot does not auto-launch the dashboard at startup; `ensure_streamlit_running()` only fires on the terminal tap and no-ops if the port is up. Full run/rebuild/recovery steps: `docs/RUNBOOK.md`.
- **`NYSE_PRICE_SOURCE`** picks where `_build_stock_daily` gets its closes: `yfinance` (default, unchanged) · `finnhub` · `capture`. yfinance is SCRAPED and Yahoo flags a datacenter IP within ~50 requests while this step makes ~730 a night — so a cloud host MUST set `finnhub`, which matched real closes at **0.000%** mean and max. `capture` reuses the spot already in `options_openbb` (zero API calls) but is the price at capture time, 0.21% mean / 0.97% max off the settled close — last resort only.
- EOD: `run_all_offhours.py` NY-gated scheduler — **BB PRIMARY first** (`NYSE_OpenBB.py --full` = capture→**skew**→derive); Yahoo lane (`NYSE_YFin.py`→`US_data.db` + `NYSE_Telegram.py` legacy report) runs ONLY as fallback when `bb_capture_ok()` fails (<300 tickers for target day). Changed from always-both 2026-07-16.
- **Derive is SCOPED to the captured day (2026-08-12).** `--full` used to re-derive every capture date nightly — 29 identical days, ~50 of the 57 min, growing ~2 min per night. `_derive_scope()` now returns the captured day **plus any date genuinely missing downstream** (self-heal after a failed night); `--rebuild` still does the whole history. **Skew runs BEFORE the serving layer** — `_build_serving_layer` merges `skew_snapshot` for the same date, so the old order wrote `atm_iv/skew25/pcvol` NULL and relied on the next night's rebuild to fill them (08-11 was 0/734). Steps 1/2/4 are pure functions of captured data — re-running a past date reproduces identical rows, so there is nothing to gain from it. Watched by `_derive_scope_watch()` (bot) until **2026-08-26**, then it self-expires.
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
- **ACCRUING tables (2026-08-08)** — snapshot-only sources with NO history API, so they are worthless until they accumulate and CANNOT be backfilled: `macro_vintages` (BLS print revisions), `reddit_mentions` (ApeWisdom crowding), `dispersion_daily` (index-vs-member IV ratio), `narrative_checks` (headline claim → verdict from our own prices). Judge each when it has a distribution, not before.
- **`options_daily` is now 31 cols** (was 41): 10 verified-dead dropped 2026-08-08, 216MB reclaimed. The 8 `*_info` cols LOOK dead but are WRITTEN by `NYSE_YFin.py` (which can target this DB) — dropping them breaks the Yahoo fallback on insert.
- **SEPARATE DB: `India_data.db`** (`_india_conn()`) holds `india_daily`. Same front end, own store — different calendar, currency, and ~2,400 symbols/day that would dilute US universe queries.
- `hiprob_recs`: rec_date, ticker, strategy, legs, expiry, dte, pop, ror, k1, k2, net, spot0, capital, status, settle_px, pnl, **`src`**. `src='LIVE'` = actually issued that day · `'BACKFILL'` = reconstructed from captured chains by `_hiprob_scan_asof`. **NEVER pool them** — `/recperf` reports them separately or it would show hindsight as performance. Backfill is bounded by `options_openbb` (needs real bid/ask+IV); `options_daily` reaches further back but is lastPrice-only → recs from it would be fiction.
