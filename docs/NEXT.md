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

## Then, from the queue (pick by value)
- **Accuracy audit R5** (low prio): macro tables + momentum/rotate narrative wording.
- VXN sweep (~35 remaining VIX sites) · full yahoo→BB read sweep · dashboard left-nav → dropdowns.
- **NSE India lane** (`/india`, PLAN.md — endpoints verified: bhavcopy DELIV_PER + F&O ΔOI).
- **Portfolio-track MCP+RAG+Docker/k8s** (PLAN.md, biggest — job-hunt showcase).
- Whale/13F coverage (edgar_13f only 112 rows).

## Standing rules learned this session
- **yfinance per-strike IV is GARBAGE** (~1e-5 for OTM). Any new option-probability code must back
  IV out of the ATM MID (`_implied_vol_hp`) or use HV — never `.impliedVolatility` per strike.
- OpenBB is **slower** than yahoo for OHLCV; it wins ONLY for options (CBOE). Don't route bars/
  fundamentals through it.
- `/flow` = 20d positioning tilt (small real edge). `/world` = co-movement map, NOT a leading signal.
- User's book is a **GOOG bear put spread only** (340P long / 300P short, exp 8/28) — concentrated,
  bearish on a resilient name; the real weakness their own tools flag is semis/memory.
- User actions still pending: BotFather `/setinline` · Anthropic top-up · weekly offsite parquet copy.
