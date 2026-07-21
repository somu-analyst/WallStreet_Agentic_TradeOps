[RESUME AFTER] 2026-07-21 04:00  (limit-guard: block at 96340206 tokens >= 80000000)
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
1. **Portfolio-track: MCP + RAG + Docker/k8s** (PLAN.md #31, job-hunt showcase). Phase 1 = MCP
   server exposing engine tools (get_positions/scan_premium/oi_breakdown/backtest_signal) over
   stdio — the ~1-session headline. Then RAG over event_journal+news+LOG, then Dockerfile+compose,
   then README+diagram. Secrets stay OUT of images (env mounts).
2. **OpenBB migration** — but re-scoped this session: yahoo STAYS primary for bars/fundamentals/
   live (it's faster + fundamentals are free); "migration" = finish routing OPTIONS fully onto BB
   + retire the yahoo EOD fallback lane where BB coverage is proven. Do NOT move bars to BB.
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
  dashboard left-nav → dropdowns (already 2-level `_NAV_GROUPS`@dashboard.py:5288) · `/flow`/`/world`/
  `/capflow` menu buttons · NSE India lane (`/india`, endpoints verified) · whale/13F (112 rows).

## Standing rules learned this session
- **yfinance per-strike IV is GARBAGE** (~1e-5 for OTM). Any new option-probability code must back
  IV out of the ATM MID (`_implied_vol_hp`) or use HV — never `.impliedVolatility` per strike.
- OpenBB is **slower** than yahoo for OHLCV; it wins ONLY for options (CBOE). Don't route bars/
  fundamentals through it.
- `/flow` = 20d positioning tilt (small real edge). `/world` = co-movement map, NOT a leading signal.
- User's book is a **GOOG bear put spread only** (340P long / 300P short, exp 8/28) — concentrated,
  bearish on a resilient name; the real weakness their own tools flag is semis/memory.
- User actions still pending: BotFather `/setinline` · Anthropic top-up · weekly offsite parquet copy.
