[RESUME AFTER] 2026-07-21 04:00  (limit-guard: block at 106643993 tokens >= 80000000)
# NEXT — switch-over note (2026-07-21)

**Single most useful next step: verify the two market-hours-only fixes on a LIVE session** — they
were only testable off-hours this session.
1. During RTH, type a bare ticker (e.g. `AMD`) in the bot → the snapshot must read **`🟢 LIVE HH:MM ET`**
   with a live price + %chg vs last close (not `EOD`). Covered tickers (positions + ~30 leaders)
   serve from the intraday DB; others from yahoo `fast_info`. Logic: `_cur_price`/`_market_is_open`.
2. Run `/spreads`, `/wheel`, `/hiprob` → **POP must be realistic (50–90%), NOT ~100%**. If any POP
   still pins near 100%, the ATM-mid IV back-out (`iv_ref` via `_implied_vol_hp`) failed for that
   ticker — check the ATM mid isn't 0.

Everything is committed (through `d798758`); bot + dashboard both healthy.

## USER-APPROVED build order (2026-07-21, do these next — multi-session, deferred at usage reset)
1. **Portfolio-track: MCP + RAG + Docker/k8s** (PLAN.md #31, job-hunt showcase).
   - ✅ **Phase 1 DONE (07-21, commit 66808f1): `mcp_server.py`** — FastMCP stdio server, 5 read-only
     tools (get_positions/scan_premium/oi_breakdown/capital_flow/backtest_signal) wrapping the engine.
     Verified vs live DB (GOOG spread, AMD capflow -11, POP 70.6%). Register via
     `mcp_client_config.example.json`. Imports bot as library; stdout muted during import.
   - ✅ **Phase 2 DONE (07-21, commit 98db2c3): `search_notes`** — 6th MCP tool, local SQLite FTS5
     RAG over event_writeups + news_feed + event_catalog + journal/bookmarks + docs/*.md (114-doc
     corpus, BM25, snippet highlight, source filter, AND→OR recall). Keyless/offline; index =
     `rag_index.db` (gitignored, rebuilt on demand). Verified vs real corpus.
   - ✅ **Phase 3 DONE (07-21, commit e250c96): Docker** — `Dockerfile` (py3.12-slim, default CMD =
     MCP server), `docker-compose.yml` (bot + dashboard services), `.dockerignore` (ALL secrets +
     *.db excluded), `docs/DOCKER.md` (guide + mermaid arch diagram), docker-run variant in the
     client config; added mcp + matplotlib to requirements.txt. Validated JSON/YAML/dockerignore.
     ⚠️ **NOT built** — no Docker on this box. **One `docker build -t nyse-options:latest .` on a
     Docker host is the only unverified step** (apt/pip resolution); the image installs the exact
     deps the engine already runs mcp_server.py on, so import is correct-by-construction.
   → **Portfolio-track COMPLETE (Phases 1-3).** Optional Phase 4 later = k8s manifest + CI. Next
     build below is #2 OpenBB migration.
2. **OpenBB migration** — re-scoped: yahoo STAYS primary for bars/fundamentals/live; migrate OPTIONS.
   - ✅ **EOD lane: DONE + PROVEN (verified 07-21).** `run_all_offhours.py:362` already runs BB-primary
     and SKIPS the yahoo lane entirely when `bb_capture_ok` (≥300 tickers) passes. Coverage is proven:
     **734 tickers EVERY trading day** for 2+ weeks (`options_change`). The fallback CODE stays on
     purpose — a free safety net; do NOT delete NYSE_YFin.py.
   - ⬜ **Read-side: SCOPED, not started (risky — live-bot core paths; deferred at ~106M tokens).**
     ~15 live `yfinance` option_chain() sites. Keep LIVE ones on yahoo (position marks @11389,
     `_option_chain_snapshot` live views). MIGRATE the EOD-analytics SCANNERS to BB: `_hiprob_scan`
     (23337), `_spreads_scan_bot` (23880), `_wheel_scan_bot` (24021), + the 2 at ~24190/24722 —
     source strikes + real bid/ask/iv/delta from `options_openbb` (already captured, 734 tkrs) via a
     `_bb_chain(tk, exp)` helper; fall back to yfinance ONLY when the ticker/expiry is absent from BB.
     Wins: routes options onto BB + kills per-ticker network latency. **TEST GATE:** POP/score must
     match the current output on AMD/GOOG/NVDA before/after (the ATM-mid IV back-out must be preserved
     — see standing rule on garbage yfinance IV). Do on fresh budget; it touches the live scanners.
3. **AI-system integration**: adapt **TradingAgents** pattern (Claude-compatible, LangGraph multi-
   agent) as a thin layer over OUR engine (OI-flow/`/flow`/`/world`/GEX/`/capflow`) rather than
   importing its stack — vs **Qlib** (ML-alpha, heavier, own data pipeline). User leaned "do both"
   → start TradingAgents-style (smaller, fits existing signals); Qlib later.
4. **Alpaca free live tick** — needs the USER's Alpaca API key first (free tier, real-time IEX).
   Build `_alpaca_price()` with graceful fallback to yahoo `fast_info` when no key.

DONE this session from that list: **`/capflow`** (per-ticker capital-flow score, commit 7cb1257,
labelled NOT-yet-backtested — backtest the composite vs fwd returns before trusting it).

## Smaller contained items (fill-in)
- Accuracy audit R5 (macro/narrative wording, low prio) · VXN sweep (~35 VIX sites → `_vol_for`) ·
  dashboard left-nav → dropdowns (already 2-level `_NAV_GROUPS`@dashboard.py:5288) ·
  NSE India lane (`/india`, endpoints verified) · whale/13F (112 rows).
- DONE 07-21b: `/flow`/`/world`/`/capflow` now have MAIN_MENU_KB buttons (commit 52c015d) —
  MACRO & EVENTS row, mapped to existing capflow_view/flow_view/world_view callbacks.

## Session note 2026-07-21b (near-limit, ~99.6M tokens)
- Bot was DOWN on resume (overnight reset killed pid 122772) → restarted, now **pid 126996**.
- `mcp` package NOT installed — Portfolio-track Phase 1 needs `pip install mcp` first.
- Deliberately did NOT start the multi-week builds (Portfolio-track MCP / OpenBB migration /
  AI-agent) — we're over the 80M guard threshold; starting one risks a half-finished mid-build
  cutoff (same call as last night). Did one contained win (menu buttons) instead. Build order
  below is unchanged and still the plan for a fresh-budget session.

## Standing rules learned this session
- **yfinance per-strike IV is GARBAGE** (~1e-5 for OTM). Any new option-probability code must back
  IV out of the ATM MID (`_implied_vol_hp`) or use HV — never `.impliedVolatility` per strike.
- OpenBB is **slower** than yahoo for OHLCV; it wins ONLY for options (CBOE). Don't route bars/
  fundamentals through it.
- `/flow` = 20d positioning tilt (small real edge). `/world` = co-movement map, NOT a leading signal.
- User's book is a **GOOG bear put spread only** (340P long / 300P short, exp 8/28) — concentrated,
  bearish on a resilient name; the real weakness their own tools flag is semis/memory.
- User actions still pending: BotFather `/setinline` · Anthropic top-up · weekly offsite parquet copy.
