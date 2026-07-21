# AUDIT — 2026-07-21 (full session findings)

Scope note up front: this was **symptom-driven spot-checking plus one systematic wiring pass**,
NOT a minute-level audit of the whole system. Measured coverage: ~6/61 commands, 2/34 dashboard
pages, 0/7 ETL scripts executed, 1/22 jobs exercised. Treat "not listed" as "not checked".

---

## A. BUGS FIXED (each verified against live data before commit)

| # | Bug | Root cause | Commit |
|---|-----|-----------|--------|
| A1 | **ET timestamps 1 hour behind** ~8 months/yr | 10 sites hardcoded `utc - timedelta(hours=5)` (EST) while Mar–Nov is EDT (UTC-4). 2 of them computed the ET *date*, so they could roll the day boundary | `e081bdb` |
| A2 | **Write-up priced off yesterday's close during RTH** | `_ticker_writeup(spot=0.0)` — ALL 3 call sites omit `spot`, and the fallback read `stock_daily` close without ever checking live. Fed narrative, wall distances, BS prices AND trade ideas | `42be21b` |
| A3 | Same stale-spot in 2 more OI paths | `_spot3` (9121), `_spot2` (10430) read `stock_daily` close | `cee5ddc` |
| A4 | **"You have no open positions"** while holding a real GOOG spread | `_pos_df` is scoped to the SELECTED ticker; page defaulted to `A` (Agilent) | `cee5ddc` |
| A5 | **`news_feed` frozen since 2026-02-20** | `_lib/news_and_earnings.store_news()` existed but **NOTHING CALLED IT** — orphaned, never scheduled. Not a key problem | `cb29c15` |
| A6 | **Γ-walls showed `$525/$530/$555`** for QQQ at $704 | `sorted(qualifying_strikes)` + caller `[:3]` → the three NUMERICALLY LOWEST strikes (deepest OTM puts) | `5b716f8` |
| A7 | **`capflow` `vol_ratio` silently dead** for most of the 734 universe | Read `stock_daily` (median 12 dates/ticker) with a `len>=20` gate → pinned at 1.0. It was the only leg with any signal | `54acbc6` |
| A8 | **`abs(None)` crash** (self-inflicted) | I made `max_loss=None` for unbounded short calls, fixed the metrics row, missed a 2nd consumer | `3891c46` |
| A9 | Per-expiry `PCR` label ambiguous | Value is PCR(open interest) but sat beside CdOI/PdOI (change) columns | `acd68e8` |
| A10 | `CLAUDE.md` secrets model wrong | Said `api_keys.env/.enc`; real vault is `api_keys.enc` — misled me into two false "keys are dead" claims | `c2fc9b0` |
| A11 | Pre-Trade Risk was **long-only** | No direction input; `max_loss` hardcoded to `-premium` | `ddc713b` |
| A12 | P&L Simulator was **long-only** | 4 separate P&L sites all assumed the buyer's side | `266348c` |
| A13 | Dashboard nav only reached pages in the selected section | Section→radio; 34 pages, no global picker | `7bd7d31` |

## B. SIGNAL-QUALITY FINDINGS (validation, not bugs)

- **B1. `/capflow` has NO directional edge.** 143 days / ~9k obs: rank-IC ≈ 0 (t=+0.28 @5d);
  the `score>+20` rule **UNDER-performs** baseline by 3.0pp @5d; buckets non-monotonic; the
  `$`-flow leg itself t=-0.07. Relabelled in-product. (`dec5703`)
- **B2. `/debate` Technical leg HAS real edge**, strengthening with horizon:
  IC +0.0131 (t=+1.83) @3d → +0.0166 (t=+2.43) @5d → **+0.0285 (t=+4.28) @10d**.
- **B3. `/debate` Vol leg is SIGN-INVERTED.** Elevated VIX preceded **+4.65%** SPY fwd-10d vs
  **+0.46%** when calm (rank-IC -0.194; VXN agrees -0.132). `_agent_vol` scores it bearish.
  NOT flipped unilaterally — 628 obs span one recovering regime; buy-fear is what breaks in 2008.
- **B4. `/debate` weights contradict the evidence.** Flow carries the HIGHEST weight (1.2) with
  ZERO edge; Technical (t=+4.28) sits at 1.0.
- **B5. `_agent_macro` adds no cross-sectional information** — it is SPY flow, identical for
  every ticker on a given day.
- **B6. METHODOLOGY TRAP:** `stock_daily` is SPARSE (median 12 dates/ticker). A first backtest
  built on it was INVALID — 20d/forward shifts silently spanned multi-month gaps. Use
  `stock_history` and compute shifts on the dense panel BEFORE joining sparse data.

## C. NON-RELATIONS / ORPHANED WIRING (~31 dead public functions)

`store_news` was not an isolated oversight — it is the norm in `_lib/`:

| Module | Orphaned / total public fns | Notable |
|---|---|---|
| `options_tracker` | **8 / 9** | `enter_trade`, `exit_trade`, `check_exit_conditions`, `update_position_snapshots` — an entire position lifecycle that is NOT running |
| `news_and_earnings` | **8 / 12** | `get_company_news`, `sync_ticker_news`, `get_upcoming_events`, `store_earnings_event` |
| `market_news_aggregator` | **10 / 13** | `get_market_snapshot`, `get_forex_news`, `get_crypto_news` |
| `market_news_enhanced` | **4 / 6** | `get_benzinga_rss`, `get_yahoo_finance_news` |
| `event_writeup_engine` | **1 / 1** | `get_recent_economic_releases` |

`CLAUDE.md` calls these "7 loaded" — they import, but most of their surface is dead.
**ACTION NEEDED: triage each — wire up or delete.** Exit-condition monitoring you may believe
is running is not.

## D. DATA ISSUES

- **D1.** `stock_daily` sparse (median 12 dates/ticker) vs `stock_history` (median 1507).
  **Any code reading `stock_daily` for HISTORY is suspect** — A7 was one instance; there may be more.
- **D2.** ✅ `VIX`/`^VIX` + `VXN`/`^VXN` duplicates merged losslessly, then backfilled:
  **VXN 252 → 6,410 rows (2001→)**, **VIX 515 → 9,219 (1990→)**.
- **D3.** AMD returns `zero_gamma=None` — `/debate`'s Position analyst silently loses that input.
- **D4. INVARIANT: never mix a live spot with captured option prices.** Both `lastPrice` and BB
  bid/ask are EOD-captured; comparing either to a live spot manufactures below-intrinsic quotes.
  Correct combination = **live spot + BB captured IV** (BB IV 23.2% vs a 4.7% ATM back-out at 1 DTE).

## E. FALSE ALARMS — things I claimed were broken that were NOT

Recording these because the pattern matters: **every one came from asserting before executing.**

1. "8 API keys dead / `/pead` silently broken" — my test never imported the bot, so
   `_load_api_keys()` never ran. `ANTHROPIC_API_KEY`, `FINNHUB_API_KEY`, `ALPHAVANTAGE_KEY` are
   all SET; Finnhub verified live (128 fresh AMD items, 717 earnings rows).
2. "`FINNHUB_KEY` alias bug" — every reader already does
   `os.environ.get("FINNHUB_API_KEY") or os.environ.get("FINNHUB_KEY")`.
3. "Gamma walls are broken in `_compute_gex`" — those were sane (within 6.4% of spot); a
   different code path (A6) was at fault.
4. "Per-expiry PCR is wrong" — maths CORRECT (verified 1.28→1.3, 2.05→2.1, 4.12→4.1); label only.
5. "AMD/SMH walls >15% from spot are a bug" — real OI concentrations (SMH put wall 475 = 45,378
   OI). My ±15% heuristic was too tight for names that rallied 7–13% in a session.
6. "68 undefined callback routes" — artifact of my own regex capturing variable names.
7. "Option prices are EOD-captured, needs a rewrite" — already resolved by the A2 spot fix;
   verified 8/8 trade ideas above intrinsic, 0 violations. **No code change needed.**

## F. NOT AUDITED (explicit gaps — do not assume healthy)

- **34 dashboard pages** — 2 checked.
- **7 ETL / lane scripts** — 0 executed (`NYSE_OpenBB`, `NYSE_YFin`, `NYSE_intraday`,
  `run_all_offhours`, `skew_snapshot`, `NYSE_Telegram`).
- **196 callback routes** — 0 smoke-tested (my detector was broken).
- **22 scheduled jobs** — verified only that callbacks are DEFINED, not that they FIRE without
  silently excepting. A5 proves "registered" ≠ "working".
- `/debate` **Position/GEX leg** — unbacktested (needs historical chain rebuild).
- `/heat`, `/live` — unbacktested. **Now possible**: yfinance gives ~3yr of 1h bars free.
- Docker image — **never built** (no Docker on this box).
- MCP server + RAG — smoke-tested only.

## G. PENDING BUILDS

- **India NSE lane** (`PLAN #37`) — endpoints verified; `NSE_EOD.py` → `NSE_data.db`
  (`nse_stock_daily` w/ **DELIV_PER** delivery %, `nse_options_daily` ΔOI) → `/india` + dashboard,
  ₹ FX-normalised P&L, Indian tax profile. Nifty50 (`^NSEI`) IS already in the global snapshot.
- OpenBB scanner read-side migration (scoped; touches live scanners — POP test gate required).
- BS next-day insights → dashboard (`PLAN #40`; scripts were in a lost scratchpad).
- Dispersion + skew backtest (`PLAN #55`) — **gated** on ~1mo of OpenBB captures.

## H. DECISIONS FOR THE USER (not mine to make)

1. Vol analyst: flip the sign, neutralise it, or leave it (regime risk both ways).
2. `/debate` weights: rebalance toward Technical, or hold (one backtest = overfit risk).
3. `_lib` orphans: wire up or delete ~31 functions.

## I. USER ACTIONS

- `docker build -t nyse-options:latest .` on a Docker host (only unverified Portfolio-track step).
- BotFather `/setinline` — placeholder: `Type a ticker — e.g. AMD, SPY, NVDA`.
- Weekly offsite copy of `openbb_chains\*.parquet` (`PLAN #42`) — capture-forward data is
  unrebuildable.
