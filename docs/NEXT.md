[RESUME AFTER] 2026-07-23 11:00  (limit-guard: block at 126024956 tokens >= 80000000)
# NEXT — handoff (written 2026-07-21, end of a very large session)

## START HERE (2 minutes, before anything else)

    python -m pyflakes telegram_bot_optimized.py dashboard.py | grep -i "undefined name"

It found **6 real bugs in seconds** last session — including two of mine — that no amount of
symptom-chasing had surfaced. It is currently **clean**; keep it that way.

Bot last ran as pid 10508. Everything committed through `9f22ace` + LOG/AUDIT commits.

---

## THE ONE THING THAT MATTERS MOST

**Three separate bugs were silently corrupting displayed prices and P&L**, all hidden by
`except Exception`. The worst: position marks were frozen at the EOD capture because
`bs_greeks(..., R, ...)` referenced an **undefined `R`**. The AMD spread displayed
**+$255 profit when it was actually -$189** — sign inverted, on live money.

**Standing rule:** any `except` around code producing a PRICE or P&L must log at WARNING,
never `debug`/`pass`. A silent failure there is worse than a crash.

---

## USER DECISIONS PENDING (do not decide these unilaterally)

1. **`/debate` Vol analyst is SIGN-INVERTED.** Elevated VIX preceded **+4.65%** SPY fwd-10d
   vs **+0.46%** when calm (rank-IC -0.194; VXN agrees -0.132). `_agent_vol` scores it
   bearish. Flip / neutralise / leave? 628 obs span ONE recovering regime — buy-fear is
   exactly the rule that breaks in a 2008.
2. **`/debate` weights contradict the evidence.** Flow carries the HIGHEST weight (1.2) with
   ZERO edge (t=-0.07); Technical has **t=+4.28** at weight 1.0. Rebalancing on one backtest
   risks overfitting.
3. **`_lib` orphan triage** — ~31 dead public functions. Wire up or delete?

## OPEN WORK (ranked)

1. **`_lib` orphans (~31 public fns never referenced).** `options_tracker` **8/9 dead**,
   incl. `enter_trade`/`exit_trade`/`check_exit_conditions` — an entire position lifecycle
   NOT running. Also `news_and_earnings` 8/12, `market_news_aggregator` 10/13,
   `market_news_enhanced` 4/6, `event_writeup_engine` 1/1. TWO production bugs last session
   were exactly this pattern (`store_news`, and no hiprob_recs writer at all).
2. **Surface `/recperf` in the dashboard** — engine exists (`_recs_perf_report`), only the
   Telegram command is wired; the HiProb page still shows OPEN-only.
3. **Intraday per-strike quotes table** (costed, not built). New `intraday_quotes` in
   `US_intraday.db`, **2-day retention** — every existing intraday reader uses
   `MAX(trade_date)`, so nothing needs history. Tiered: **positions + top-25 @5min,
   next 75 @30min** ~2,900 req/day, **~4.6-8.8 GB/day**. Full 734 @5min = 23 GB/day and
   ~9,500 requests/day = real rate-limit risk to a lane you depend on. Keep `intraday_bars`
   at 45d (only possible source of 1-min history; yfinance caps at 7 days).
4. **Backtest `/heat` + `/live`** — now possible: yfinance gives **~3yr of 1h bars** free
   (5,070 rows verified). Never validated.
5. **`/debate` Position/GEX leg** — unbacktested (needs historical chain rebuild).
6. **India NSE lane** (`PLAN #37`) — endpoints verified, nothing built. Nifty50 (`^NSEI`) IS
   already in the global snapshot. `NSE_EOD.py` -> `NSE_data.db` (DELIV_PER delivery % beats
   the US volume proxy) -> `/india` + dashboard, INR FX, Indian tax profile.
7. AMD returns `zero_gamma=None` — `/debate` Position leg silently loses that input.
8. `stock_daily` vs `stock_history` = same quantity from **different vendors** (OpenBB vs
   yfinance) with **nothing reconciling them**. A daily tolerance check would catch capture
   corruption early.

## NOT AUDITED — do not assume healthy
34 dashboard pages (2 checked) · **7 ETL scripts (0 ever executed)** · 196 callback routes
(0 smoke-tested) · 22 jobs verified only as *defined*, not *firing* — `store_news` proves
registered != working · Docker image **never built**
(`docker build -t nyse-options:latest .` is the only unverified Portfolio-track step).

Full detail: **`docs/AUDIT.md`**.

## STANDING RULES (learned the hard way)
- **Never mix a live spot with captured option prices** — `lastPrice` and BB bid/ask are both
  EOD; comparing either to a live spot manufactures below-intrinsic quotes. Correct pairing =
  **live spot + BB captured IV**.
- **History -> `stock_history`, never `stock_daily`** (median 12 vs 1507 dates/ticker).
- yfinance per-strike IV is garbage — back it out of the ATM mid, or use BB's.
- `/capflow` has **NO directional edge** — positioning description, not a signal.
- Option **liquidity** is the right universe filter, not market cap (universe is already
  large-cap; top 100 = 94% of option volume, top 25 = 82%).
- Test by EXECUTING. Every claim verified by running held up; several asserted from reading
  were wrong.

## USER ACTIONS
`docker build` on a Docker host · weekly offsite copy of `openbb_chains\*.parquet`
(`PLAN #42`, unrebuildable) · BotFather `/setinline` placeholder:
`Type a ticker — e.g. AMD, SPY, NVDA`

---
## 2026-07-23 late — EVENTS table: ATTEMPTED, REVERTED, still TODO

**Ask:** merge the prose `EVENTS:` line + `LAST EARNINGS` table into ONE table:
`Tkr | Event | Date | In | Est/Act` — `In` signed (−d passed / +d upcoming, T−2…T+2),
Est/Act only shown once the value is actually held (never claim "released" on a
scheduled-but-unconfirmed event).

**Status: REVERTED.** Two attempts blanked the whole EVENTS section. Table logic
VERIFIED GOOD in isolation (43 chars, rows build fine):
```
Tkr  | Event | Date  |   In |   Est/Act
GOOG | Earn  | 07-22 |  -1d | 2.91/9.11
AMD  | Earn  | 05-05 | -79d | 1.29/1.37
```
so the bug is in the FOMC/`_ev_bits` loop, not the earnings rows. Reverted to
`1a7cecc` (working prose EVENTS + LAST EARNINGS table) rather than ship a blank
section.

**Next session — do this first, it is nearly done:**
1. `_ev_bits` was changed from strings to 5-tuples in the same edit; confirm EVERY
   producer/consumer agrees. A leftover string entry unpacking into 5 names is the
   most likely killer.
2. Build the table from EARNINGS ROWS ONLY first (proven to work), commit that,
   THEN add calendar events as a second pass.
3. `event_date_str` is NOT ISO — `[5:10]` on it yielded "9" for FOMC. Derive the
   date from `today + timedelta(days=event_days)`.
4. Target ≤40 chars. `Est/Act` merged into one cell is what got it from 46 → 43.

**Lesson:** I patched two things at once (row shape + width) and could not tell
which broke it. Change ONE and render each time.
