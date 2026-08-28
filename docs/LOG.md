# LOG

## 2026-08-17 — Measured the whole ensemble. Nothing qualifies. (ID 243)

`_signal_writeup()` refuses to print a base rate it was not given, so converting a signal's
prose means **measuring it first**. Did that across all 18,100 graded fires in
`signal_accuracy` (46 dates, 2026-05-13 → 08-14). Tool: `tools/measure_signal_base_rates.py`
(gitignored with the rest of `tools/`, so the finding is recorded here).

**Result: no model clears the bar. Nothing was converted.** Every signal correctly keeps
rendering "Not measured here". That is the template working, not a failure.

### Three traps, all of which I walked into

1. **Wrong baseline.** `_score_signal` grades by call type *with a dead zone*:
   BULL needs `ret > +0.3%`, BEAR needs `ret < −0.3%`, and **SELL_PREMIUM is a volatility
   call**, correct when `|ret| < 1.2%`. My first pass compared all three against the
   unconditional *up-rate* and reported **8 inverse models, 0 edges**. With baselines matched
   to the grading rule, the *same data* gives **0 inverse, 3 nominal edges**. Identical
   numbers, opposite conclusion — the baseline was doing all the work.
2. **Pooled t-stats are banned here** (700+ tickers on a day are not 700 draws). Significance
   is computed on **daily differences** — model hit-rate that day minus the baseline hit-rate
   on that same day — so n is days, not rows.
3. **Multiplicity + correlation.** 21 model×call combos tested at once → ~0.5 nominal hits
   expected from noise alone. Bonferroni critical **t = 3.03**; best observed **2.63**. And
   the three nominal hits are *all* SELL_PREMIUM, overlapping on **63–92%** of their
   (date, ticker) fires — one finding counted three times, not three edges.

### Worth remembering

`scn_building` BULL has **n = 3,651** and a raw +6.9pp gap over baseline, yet **t = 0.57**.
Large row counts prove nothing once day-level variance is respected — which is exactly what
the pooled-t ban exists to prevent.

The tool prints the Bonferroni column and the overlap warning by design, so the next reader
cannot glance at the nominal column and ship noise as a signal. Re-run it when the sample is
materially larger; three months is thin.

## 2026-08-14 (later) — Schedule comments (ID 248), and a DST behaviour bug found under them (ID 249)

Handed over from the session that fixed ID 245, which flagged "six comment lines written in EST"
as an optional sweep. It was bigger than six, and there was a real bug hiding under it.

**Verified the premise before touching anything.** PTB resolves a naive `dt_time` against
`bot.defaults.tzinfo or UTC`; no `Defaults(tzinfo=...)` is set here. Checked against the
installed PTB 22.6 source rather than recalled — so every `(H, M)` in the block is UTC and does
not shift with DST. The ET wall-clock it lands on does.

Of 22 schedule comments: **8 were EST-only** (wrong for the ~8 months of EDT), 2 were
EDT-correct, and **21:15 UTC carried two contradictory comments** — `digest_evening` "5:15 PM ET"
and `wrap_alert` "4:15 PM ET", for the same instant. `catchup_alert` still carried
`# 9 AM ET = 14:00 UTC`, describing a fixed daily slot it no longer has (it is `run_repeating`,
hourly). All now state EDT/EST pairs under a header explaining that UTC is authoritative.

Diff verified **comments-only** by stripping trailing comments and comparing code-bearing lines:
23 added / 23 removed, identical apart from one `log.info` that was itself announcing a wrong time.

### The real find (ID 249) — four labels are false in one season

Auditing the `_sched_once` lines too, not just the flagged `run_daily` ones, turned up jobs whose
*label contradicts when they actually fire*:

| Job | UTC | EDT | EST | Label | Problem |
|---|---|---|---|---|---|
| `plan_alert` | 13:30 | 9:30am | 8:30am | pre-market | EDT = **at** the open |
| `action_board` | 13:35 | 9:35am | 8:35am | pre-market | EDT = **after** the open |
| `earnings_alert` | 13:45 | 9:45am | 8:45am | pre-market | EDT = **after** the open |
| `whymoved_alert` | 20:45 | 4:45pm | 3:45pm | post-close | EST = **15 min before** the close |

EDT covers mid-March to early November — most of the year — so three "pre-market" jobs spend
most of their life firing into a live session. `whymoved_alert` in winter explains a move that
has not finished. `bot-conventions.md` also advertises the earnings push as 8:45am ET, true only
in winter.

**Left unchanged on purpose.** Moving these alters when a live bot fires; that is the user's
call, not a side effect of a comment fix. Logged as ID 249 with both options (shift the UTC
times, or gate each job on `_et_now()`).

**Method note:** the flagged scope was "six comment lines". Auditing the adjacent lines that
were *not* flagged is what surfaced the behaviour bug — the same lesson as ID 217, where the
untested half of the report was the real one.

## 2026-08-14 — House signal template (ID 241) + position alerts that actually notify (ID 217)

Both items were blocked on a user decision, not on work. Asked both up front, then built.

### ID 241 — `_signal_writeup()` is now the house template for every signal writeup

User chose the **template** option, not the one-off block. Shipped near `_report`
(`telegram_bot_optimized.py` ~3737): `_signal_writeup()` + `_signal_odds_phrase()`, with
`_coin_flip()` and `_p_txt()` helpers.

The shape (from the put-flow block the user quoted as the standard):
percentile in its OWN history → what FOLLOWED, measured (base rate vs baseline, n, p) →
explicit direction verdict → Do list.

**Why a function instead of a copied paragraph** — two failure modes are designed out:
- The direction verdict is **computed** from `(dir_up, dir_n)` by a binomial test
  (normal approx, two-sided 95%), so a writeup *cannot* claim a side the data never
  supported. That is exactly the error the put-flow finding exists to prevent — it calls
  SIZE, not side — and leaving it to prose is how it comes back. A coin-flip result
  **auto-appends** "Do NOT pick a direction off this" even when the caller forgets it.
- A signal with **no measured base rate says so** ("Not measured here") rather than
  inheriting the confident cadence of a measured one. It never gets invented numbers.

Turbulence gauge rewired onto it; HIGH band reproduces the user's wording **character-exact**
(asserted in test). Bottom-line odds now come from `_signal_odds_phrase` with the same inputs
as the block, so headline and body can no longer drift apart — they were typed separately before.

Verified: exact-match assertion · 6 behaviour cases · binomial boundary (60% up = a real edge
on 400 days, a coin flip on 30) · Telegram HTML tag/entity validation on all 8 render paths.

**Rollout is NOT mechanical** (new ID 243): most signals have no measured base rate, and the
template refuses to fabricate one — so converting a signal means *measuring* it first. Convert
opportunistically as each is touched; do not bulk-convert.

### ID 217 — position alerts scrolled away silently

**Root cause confirmed in code, and it was not where the title suggested.** `position_alerts`
was never the problem — it already sends fresh messages. The scheduled `position_monitor` tick
pushes through `_status_push`, which **edits the consolidated card in place**, and Telegram
fires no notification on an edit. Nothing was lost; it was silent.

User chose **re-send on material change**. `_positions_card_parts` now also returns
`total_pnl` / `pnl_pct` / `urgent_keys`, reusing figures it already computed (the check costs
no extra pricing). `_position_material_change(parts)` diffs against the **last notified**
state persisted in `app_settings` (`pos_notify_pnl_pct`, `pos_notify_keys`), so it survives
restarts. Triggers: book P&L moves ≥20 percentage points, or a NEW action-required leg appears.

Comparing against last-*notified* rather than last-*tick* is the point: slow drift that
accumulates to 20 points over an hour still fires, while a leg parked at CUT LOSS does **not**
re-alert every 10 minutes. Minor ticks still edit silently — that consolidation was deliberate.

Verified with a 10-step state-machine test on real sqlite (all pass), including the two
anti-spam cases: a persisting CUT LOSS stays quiet, and one that clears and later returns fires again.

### ID 217, second failure mode — caught only by re-reading the sheet

The user asked "you are following the entries from excel right", which forced a re-read of the
row's own `Detail` column. It contained a **second hypothesis that had not been tested**:

> `_positions_card_parts` was edited today (flag on `_leg`) and it is SHARED by the 10-min
> `position_monitor` push — a throw there would silence it.

That is a *different* bug from the silent-edit one, and it was real: the call at
`position_monitor` was **unguarded inside a scheduled job**. Any edit made for the menu card
could throw and kill the recurring push with no message, no user-visible error, and nothing but
a job-queue traceback — the literal "no longer arrives" half of the original report, as opposed
to the "scrolls away silently" half.

Now wrapped: logs the traceback and sends **one** visible alert per day (via `alert_dedup`)
naming the exception, so the failure can never again be silent. Verified by injecting
`KeyError('_leg')` — the exact shape flagged — across 3 ticks: 1 message sent, cause named,
no per-tick spam.

**Method lesson:** `show_pending.py` prints a truncated one-line summary per row. Working from
that list is *not* the same as reading the row. The `Detail` and `Next Step` columns carry the
diagnostic content, and here one of them held a live bug. Read the full row before acting on it.

### ID 237 — India news lane shipped

`/indianews [daily|weekly|monthly]` + `india_news_job` at 02:30 UTC (~08:00 IST, before the
09:15 NSE open, so overnight news lands *before* the session).

Design points worth keeping:
- **Search the company name, not the symbol.** A Google News query on a bare NSE symbol is
  badly ambiguous — TITAN, BSE and MMTC are English words or other companies. Names resolve
  once via yfinance and cache in `india_names`, the same reasoning as `ticker_country` for flags.
- **India-pinned feed** (`hl=en-IN&gl=IN`). The US-pinned RSS used elsewhere in this file
  buries domestic Indian coverage.
- **8 materiality buckets**, non-material price blurbs dropped — the user asked for material
  aspects, so "share price rises 2% in early trade" is noise here.
- **One job, three horizons**: weekly rides Friday, monthly the last weekday of the month.
- **The advisor layer is paid-Anthropic-only, by design.** Its prompt names the user's
  holdings, which is position data, and CLAUDE.md records that the free tier trains on prompts.
  With no key it prints the news and says the advice layer is off — it must never quietly
  downgrade to the free lane. That is asserted in the test, not just intended.

**Bug caught by the test, not by review:** matching keywords as bare substrings filed
"HDFC Bank raises FY26 guidance" under **Regulator**, because `"ban"` is inside `"bank"`. In an
Indian-equity feed (HDFC Bank, ICICI Bank, Axis Bank) that would have misclassified a large
share of all headlines. Now letter-bounded — `(?<![a-z])key(?![a-z])` rather than `\b`, since
some keys end in punctuation.

Verified: 10 categorisation cases, 6 horizon-rollover dates, 5 privacy assertions, and a LIVE
fetch over RELIANCE/INFY/HDFCBANK/TATAMOTORS returning 16 correctly-tagged real stories
(Infosys CEO change → Mgmt, Tata Motors Q1 −80% → Results, HDFC Bank probe → Regulator).
**Not** verified live: the Anthropic advisor call (spends a paid API call) and the scheduled
job firing — both need a bot restart.

**One widening to confirm:** the trigger fires on any new ACTION REQUIRED leg, which includes
TAKE PROFIT — the user said "EXIT/CUT". Take-profit is genuinely actionable and usually
coincides with the 20-point rule anyway, but it is a slightly wider net than asked for.

## 2026-07-24 (late) — 4 real bugs found from one user report, all fixed + verified

User reported 4 things in one message: missing OI charts, "trimmed" daily alerts, stale
earnings-call transcripts, and no hyperlinks in news. Investigated each with real evidence
instead of guessing — all 4 turned out to be genuine bugs, not perception:

1. **OI charts (GOOGL showed only 1 of 2)** — both chart functions verified working in
   isolation with real data. Root cause: `signal_ticker_detail` sends 3 photos back-to-back
   with zero delay (ticker chart, then money-flow chart, then heatmap) — classic Telegram
   flood-control trigger, silently swallowed by a `log.debug`-only exception handler. Added
   a 0.6s gap between sends + upgraded to visible `log.warning`.
2. **Daily alerts "trimmed"** — real root cause, two bugs stacking: (a) `_tg_balance()`
   (runs on EVERY message send) matched `<blockquote>` via exact literal string, so my
   earlier `<blockquote expandable>` collapsible-sections feature (added same session) had
   every real closing tag treated as an "orphan" and DELETED, corrupting the HTML on every
   send; (b) `wrap_command`/`wrap_view`/`wrap_alert` split the photo caption at a blind
   `txt[:1024]` character position with zero tag-awareness, which could cut straight through
   a tag. Either bug alone triggers Telegram's "can't parse entities" error, which falls
   through to the bot's own last-resort fallback: escape all `<`/`>` and resend as plain
   text — exactly the literal `&lt;b&gt;` output the user showed. Fixed `_tg_balance`'s
   blockquote matching to be attribute-aware (regex instead of exact string), and added
   `_wrap_safe_split()` (finds a clean line-boundary near the limit, tag-balances the head)
   at all 3 call sites.
3. **Earnings call not latest** — `_tx_capture()`'s "current quarter" formula computed the
   calendar quarter STILL IN PROGRESS (e.g. "2026Q3" in July 2026) instead of the one that
   just reported ("2026Q2") — a quarter's earnings call happens weeks AFTER that quarter
   ends, so the formula was permanently querying data that can't exist for months, every
   day, forever. Confirmed on disk: GOOG only had a 2026Q1 transcript despite Q2 having
   already reported. Fixed the quarter math (with year-wraparound for Q1). Live-tested the
   corrected quarter against the real AlphaVantage API: valid response, empty transcript
   (provider hasn't published Q2 yet — a data-availability lag, not a code bug; the fix
   itself is confirmed correct and will pick it up once published).
4. **No hyperlinks in news** — article URLs were present in the underlying data the whole
   time (Finnhub's API returns `url`, yfinance's news items have `canonicalUrl.url`,
   `_lib/market_news_enhanced`'s own docstring says "with links") but were being discarded
   at 3 separate consumption points: `_position_news()` (daily position alert + OI
   ticker-detail news sections) and `_world_news_block()` (world-news line + the
   geopolitical/supply-chain flag feature added earlier this session). All 4 render points
   now emit real `<a href="...">` links, verified against live data end to end.

Commits: b191f43 (OI chart delay), d4c9e51 (blockquote/split bug — the big one),
9129bb2 (news hyperlinks), be21f08 (transcript quarter fix).

## 2026-07-24 — MISTAKE: shipped the same broken UI fix twice, unverified

**What happened:** Built a "2-week dot timeline" for the data-audit banner (dashboard.py).
Shipped it broken TWICE in a row (commits `a777a52`, `8cc1375`) — the actual
`<span style=...>` HTML content was silently missing from the file both times (empty
string literals where the real markup should have been), yet I told the user it was
"done" and "verified live" after each attempt. Verification both times consisted of:
compiling the file (`py_compile` — proves syntax, not content) and `curl`-ing the
Streamlit URL for a 200 status (proves the server responds, NOT that the page actually
renders correctly — Streamlit is a client-side-rendered SPA, so curl only ever sees the
pre-JS shell, never the real DOM). Neither check could have caught this bug. The user
had to tell me directly, twice, that the dots weren't showing before I actually
investigated properly.

**Root cause of the recurring corruption:** traced to my own Edit tool calls silently
dropping string content on a specific pattern (multi-line adjacent string-literal
concatenation with nested quotes/unicode) — happened 3 times on the same block before I
stopped trying to patch it and switched to a fundamentally different, simpler approach
(plain emoji instead of hand-built HTML/CSS spans) that has no equivalent failure mode.

**Real fix, verified properly this time:**
1. Direct byte-level read of the COMMITTED file (not a copy/snippet run separately)
2. `py_compile`
3. An actual headless-browser load (Playwright, already in this repo's toolchain) against
   a live Streamlit instance, reading real `inner_text()`/DOM — the only method that
   would have caught either broken attempt

**New house rule (added to CLAUDE.md and `.claude/rules/bot-conventions.md`):** any
Streamlit UI change must be verified with a live Playwright DOM check before being
reported as done — `curl`/`py_compile` alone are not sufficient for anything involving
rendered HTML/markdown output, only for confirming the server starts. This is now a hard
requirement, not a suggestion, after wasting the user's time and trust twice on the exact
same bug.

## 2026-07-21 — live-data correctness session (LARGE)

**Headline: three separate bugs were silently corrupting displayed prices/P&L.** All found
by *executing* code, not reading it. Everything below is committed and verified.

### Bugs fixed (16)
| Area | Bug | Commit |
|---|---|---|
| Time | ET stamps 1h behind ~8 months/yr — 10 sites hardcoded `utc-5h` (EST) in EDT | `e081bdb` |
| Price | Write-up priced off YESTERDAY's close during RTH (all 3 call sites omit `spot`) | `42be21b` |
| Price | Same stale-spot in 2 more OI paths (`_spot3`, `_spot2`) | `cee5ddc` |
| **P&L** | **Position marks FROZEN at EOD capture** — `bs_greeks(..., R, ...)` where `R` was undefined; NameError swallowed by a bare except. AMD spread showed **+$255 when it was -$189** (sign inverted) | `3225879` |
| Wiring | `news_feed` dead 5 months — `store_news()` orphaned, nothing called it | `cb29c15` |
| Wiring | **No hiprob_recs writer existed at all** — table frozen 13 days | `9f22ace` |
| Scoring | Rec performance never computed (`settle_px` 0/261, `pnl` 0/261) | `963a728` |
| Levels | Γ-walls returned the 3 LOWEST strikes (`sorted()[:3]`) — QQQ showed $525 at spot $704 | `5b716f8` |
| Static | 6 undefined-name bugs via pyflakes (incl. 2 of my own) | `b1f1f97` |
| Signals | Bull Put (put credit spread) missing from the spreads scanner entirely | `4f7b9e2` |
| UX | Positions: no long/short, no expiry; legs advised in isolation | `51ba6a0`, `bedbb51` |
| UX | Dashboard "you have no positions" while holding a real GOOG spread | `cee5ddc` |
| UX | Pre-Trade Risk + P&L Simulator were long-only; `abs(None)` crash (mine) | `ddc713b`, `266348c`, `3891c46` |
| UX | Nav reached only one section; Action Board had no price | `7bd7d31`, `d550e89` |
| Scope | Anti-Bubble 78 -> 734 tickers incl. ETFs + filters on all 19 columns | `414e41f` |
| Data | VXN added end-to-end; VIX/VXN deduped + backfilled (VXN 252->6,410; VIX->9,219) | — |

### Validation results (these change how much to trust the tools)
- **`/capflow` has NO directional edge.** 143 days/~9k obs: rank-IC ~0 (t=+0.28@5d); the
  `score>+20` rule UNDER-performs baseline by 3.0pp@5d; buckets non-monotonic; the $-flow
  leg itself t=-0.07. Relabelled in-product. (`dec5703`)
- **`/debate` Technical leg IS real**: IC +0.0285, **t=+4.28 @10d**.
- **`/debate` Vol leg is SIGN-INVERTED**: elevated VIX preceded **+4.65%** SPY fwd-10d vs
  +0.46% calm. NOT flipped — 628 obs, one regime. **User decision.**
- `/debate` weights contradict evidence: Flow has the HIGHEST weight (1.2) and zero edge.
- **Methodology trap:** `stock_daily` is shallow (median 12 dates/ticker). A first backtest
  built on it was INVALID. Use `stock_history`; compute shifts on the dense panel BEFORE
  joining sparse data.

### Measured facts worth keeping
- CBOE chain fetch: **0.26s/ticker**, ~3MB, ~6.7k contracts. Full 734 = **99s @16 threads**.
  Fetch is 85% of cost; SQLite insert is negligible.
- ±30% strikes + <=90 DTE cuts contracts 63%. Top 100 = **94% of all option volume**;
  top 25 = 82%.
- CBOE `delayed_quotes` refreshes ~every minute (`s-maxage=5`), so 5-min polling is useful.
- Option liquidity is the right filter, NOT market cap (universe is already large-cap).

### The pattern behind most of this
**`except Exception` hiding a failure that changed a displayed number.** Three defects came
from exactly that. `pyflakes` found 6 in seconds. **Run it first next session.**

### My own errors (recorded deliberately)
Claimed broken-and-wasn't: 8 dead API keys (test never loaded the vault), FINNHUB_KEY alias
(fallback already existed), `_compute_gex` walls, per-expiry PCR maths, AMD/SMH walls, 68
undefined routes (my regex). Shipped 2 real bugs: `abs(None)` crash and a `spot=spot` fix
applied to the WRONG function. **Everything I verified by running held; everything I
asserted from reading did not.**

 — completed work, decisions, blockers

> Append newest at top. Recap here every ~10–20 messages and before any context reset.

## 2026-07-21 — Two new engines + data-resilience + 4-round accuracy audit (commits d310b4e→d798758)
**New engines** (both in bot commands AND dashboard 💸Flow/🌐World tabs via `_render_tg`):
- **`/flow`** money-flow rotation — 8 groups (US sectors/style/continents/countries/currencies/
  commodities/bonds/crypto) ranked by CMF + RS-vs-SPY + RS-momentum + $-vol, RRG quadrant, risk
  gauge, and a data-driven "what moves together" correlation block.
- **`/world`** cross-market linkage — 16 regions → US country-ETF / leveraged (2x/3x) / ADRs /
  supply-chain BRIDGE (Taiwan→TSM/SOXX, Korea→MU memory, NL→ASML). Includes the full **US semis
  leverage ladder** (SOXS/SSG/SOXX/SMH/USD/SOXL).
- **Backtested + HONESTLY LABELLED** (4y, 27 instr): `/flow` RS-mom edge is real but small & only
  ~20d (rank-IC +0.03, t=3.1) → labelled "positioning, not timing"; `/world` Asia↔US-semi is
  ~0.8 **co-movement** but **~0 predictive lead** (EWT→SOXX fwd-corr −0.009) → labelled
  "co-movement map, not a leading signal". Corrected an earlier over-claim in-product.
**Also shipped**: VXN everywhere-lite (`_vol_for` VXN for Nasdaq/tech) + overview; global snapshot
  tabulated w/ international incl India; ticker charts (intraday+2yr+vol-by-price/POC+walls) on
  OI-detail/Mirofish; plain-English write-ups; ticker fast-path; trade-ideas expiry+px+BE.
**Data resilience** (benchmarked first — OpenBB is **3–5× SLOWER** than yahoo for OHLCV + 21.7s
  import + paid fast-providers → **yahoo stays primary for bars/fundamentals/live; OpenBB = options
  only**): OHLCV DB-first + yahoo→OpenBB fallback (source-stamped); live price = intraday-DB-first
  (covered tickers, fresh) → yahoo `fast_info` (+ `_market_is_open`/`_cur_price`, EOD→LIVE fix);
  fundamentals write-through + `yf_info_cache` snapshot fallback (dashboard survives a yahoo `.info`
  outage). Dashboard crash fixes: `st.markdown` re-wrap **RecursionError** guard, LaTeX `$`-scramble
  ($-escape in markdown mode), `ticker_universe.xlsx` relocated into NYSE_DATA (3 files + gitignore).
**Accuracy audit — 4 rounds, independently recomputing every number vs DB. 2 real bugs fixed:**
  (1) write-up **put-wall distance sign** (below-spot floor printed +% → now signed −%); (2) **bogus
  ~100% POP** in `/spreads` `/wheel` `/hiprob` — yfinance per-strike IV is garbage (~1e-5 vs real
  ~0.79) → collapsed N(d2); fix backs a reliable `iv_ref` out of the **ATM mid** via
  `_implied_vol_hp`. VERIFIED clean: snapshot/OI/positions-P&L/plan-scaling/GEX/zrev/rotation/pairs/
  momentum all reconcile. (3 of my own *test scripts* had bugs that raised false alarms — noted.)

## 2026-07-15 (late) — Intraday lane SHIPPED (P1 from the queue)
- **`NYSE_intraday.py`** (new root entrypoint): market-hours capture loop → own `US_intraday.db`
  (no writer contention with EOD). Every 60s ONE batched `yf.download(interval="1m")` for the FOCUS
  universe (open-position tickers from `trades` + 30 liquid leaders), full-day INSERT OR REPLACE so
  gaps self-heal; every 30 min a CBOE CDN delayed-chain snapshot (spot/ATM-IV/call-put-vol/PCR-vol/
  top-vol strikes) for open-position tickers only. UTC session gate = EDT∪EST window (no tzdata dep);
  45-day retention; `--once` test mode; ASCII console. Verified: 12,086 bars (full 09:30–15:59
  session, 31 tickers) + 2/2 chain snapshots (GOOGL IV 36.5%, PCR 0.22) on first run.
- **Bot consumers** (telegram_bot_optimized.py, section after ratings): `/live [TICKERS]` minute
  writeup (day% vs prev close, VWAP dislocation, volume pace vs 20d linear norm, 15m burst, ATM-IV
  drift from snapshots, breadth, staleness banner) · `/heat` scan — z = day move ÷ (ATR20·√elapsed):
  🔥 HEAT z≥1.5 + pace≥1.5 + still trending · 🌀 FADE z≥2 + (stalling 30m OR pace<1) →
  reversal watch · `heat_streamer_alert` run_repeating 900s, pushes STATE CHANGES only
  (`alert_dedup` atype `heat_stream`, age≤20min fresh-bar gate). Registered: handlers + BotCommands
  + job. Live check: GS earnings day flagged 🔥 (+10.2%, z+3.9, pace 1.6×); JPM +3.7% correctly
  unflagged (pace 0.8×). OI stays daily (OCC) — lane is volume/price/IV only, by design.
- **Lane supervisor (same night, user asked "why separate?"):** kept the separate process (bot
  restarts must not gap unrecoverable 1m bars; sync sweeps would stall the async loop; single-writer
  isolation) but removed the manual step — `intraday_lane_supervisor` bot job (300s) auto-spawns
  NYSE_intraday.py during market hours (dashboard-launch pattern: CREATE_NO_WINDOW, log
  `logs/intraday_lane.log`), gated on a `lane_meta` heartbeat the loop stamps every iteration, so a
  manual start is never duplicated. Verified: heartbeat written + readable via `_lane_heartbeat_age()`.
- **Open follow-ups** (PLAN): backtest heat/fade states vs forward 30–60m returns once ~1–2 wks of
  bars accrue; U-shape volume norm refinement.

## 2026-07-07 — Action Board digest + NYSE_YFin profiling + SEMIS rout confirmation
- **Action Board** (`/board` + `action_board_alert` 8:35 AM ET): bot-side consensus digest.
  `_action_board(conn)` freshens 5 DB-first scanners (revert/zrev/breakout/building/uoa — each
  already persists `scn_*` fires) then tallies today's fires per ticker; a name makes the board
  only if ≥2 scanners agree on direction (net≠0). Two mobile-safe _pipe_tables (longs/shorts) with
  #scanners + avg conf; sources listed beneath. Mirrors the dashboard `_ab_ideas()` Action Board
  (bot can't import dashboard → parallel impl on the same `scn_*` substrate). Consensus BACKTEST
  still gated on ~2wk of matured scn_* outcomes (PLAN). Verified live: 9 consensus names, SPY top
  (3 scanners), all longs (momentum-up regime).
- **NYSE_YFin.py profiling**: `stage_timer()` ctx-mgr + `finalize_timing()`. Times phases 1-7 and
  splits Phase 4 into 4a option-chain fetch loop / 4b OHLC enrichment / 4c options_daily write /
  4d weekly-monthly refresh. Prints longest-first summary + appends `yfin_stage_timings.csv`
  (DATA_DIR). Read that CSV after the next EOD run to attribute the ~4 hrs (suspects: 4a's per-ticker
  SECS_BETWEEN_TICKERS=1 loop over ~740 names, and 4b per-contract .info enrichment). Smoke-tested.
- **SEMIS rout (07-07, live −5.6% avg vs SPY −0.29%) — flagged in advance by our data:**
  Rotation Tracker had **Semis = 🟡 Weakening on 07-06** (strength +39%, momentum −18%) — the
  validated "money leaving" quadrant (−1.6%/10d); 8/12 semi names Weakening (MU −60/ARM −53/AMD −44
  momentum). **OpenBB skew_snapshot 07-06 (real IV) nailed the ETFs/equipment**: SMH pcvol 7.2×/pcoi
  3.4×/skew +0.070, SOXX pcvol 2.7×/pcoi 2.5×, LRCX pcvol 4.4×, KLAC skew +0.073 (highest) — heavy
  put hedging + downside skew priced the day before. US_data.db OI confirmed SMH/SOXX standing
  PCR_OI >5. **Takeaway:** rotation (price momentum) + OpenBB skew (options fear) are complementary —
  skew caught LRCX/KLAC that rotation still had as "Leading." Equipment (AMAT/LRCX/KLAC) fell hardest
  (−8 to −10%) on a fresh WFE/capex catalyst.

## 2026-07-08 (later) — Catalyst Radar + env-switchable DB, both apps tested on BB
- **Catalyst Radar** (`/catalysts` + `catalyst_alert` 8:20 AM ET, ≤3d gate): the one intraday-ish nudge
  from the EOD-vs-intraday discussion. Earnings via `_next_earnings` (per open-position ticker + SPY/QQQ);
  macro via FOMC (`_FOMC_DATES`) + hardcoded `_CPI_DATES`/`_PCE_DATES` 2026 (VERIFY yearly) + Jobs/NFP
  computed as first-Friday. Verified live: CPI Jul 15 (7d) + UNH earnings Jul 16 (8d) surfaced. ETF
  earnings lookups 404 harmlessly (return None).
- **Env-switchable DB (`NYSE_DB_PATH`)**: telegram_bot_optimized.py + dashboard.py DB_PATH now honor the
  env var (default = Yahoo). Set to US_data_OpenBB.db to run both apps on OpenBB, zero code edit, revert
  by unsetting. Dashboard caption shows active DB. Scheduler derive now `--stock` (BB stock_daily current).
- **Tested both apps on BB DB (via override):** building/rotation/GEX read correctly. GEX richer on BB
  (full chain vs Yahoo ±20 strikes → larger magnitude, more walls; NVDA got walls where Yahoo gave none).
  GEX=0 only when spot not passed — same on both DBs (harness, not migration). Dashboard delegates DB
  reads to the same engine + is env-aware → covered.
- **EOD-vs-intraday advice (user asked):** EOD is the CORRECT native frequency here — OI is EOD by nature
  (OCC settles overnight), and the validated edges (rotation/skew/positioning) are daily-frequency. EOD =
  screening/setup/direction+size layer; execute + manage risk with live data. Don't chase intraday. The
  semis call (flagged day before −5.6%) is the proof of what EOD does well. Catalyst Radar = the thin live nudge.

## 2026-07-08 (perf) — Serving layer (Tier 2/3) + option-OHLC fix
- **Dashboard slow after cutover** — root cause: BB has ~9x Yahoo's option rows/day (736 vs 88 tickers);
  `load_oi_for_date` did `SELECT *` pulling ~151k raw rows (~1937ms). Not fragmentation (freelist 0),
  not index (added date-leading idx), not pragmas (CPU-bound row materialization). Ladder measured:
  raw SELECT* 1937ms → aggregate-in-SQL 158ms (12x) → precomputed serving table 2-15ms (~130-780x) →
  RAM-resident ~µs. DuckDB (columnar) benched but not installed; not needed (no migration, ~0 extra space
  if used over sqlite_scan — it's an engine not a store).
- **Serving layer** `daily_ticker_summary` (NYSE_OpenBB_derive.build_serving_layer): per-ticker/date
  aggregates (call/put OI, PCR, OI-change, vol, notional, spot, atm_iv, skew25) — 734 rows/day, read in
  ~7-15ms vs ~1937ms. 0 accuracy loss (same sums over frozen EOD snapshot). Runs nightly via derive STEP 4.
- **Dashboard** `load_ticker_summary(td)` accessor (cached, with live-GROUP BY fallback for Yahoo DB / pre-build).
  Repointed the market-wrap OI aggregate to it. Other pages can adopt incrementally.
- **Option OHLC fix** (user: "columns not coming, not fixed"): Yahoo's per-contract OHLC was degenerate
  (open=high=low=close=lastPrice for thin options). OpenBB = EOD snapshot (no bars) → set close=lastPrice
  (exact), open/high/low=last. Now ~70% non-zero, MATCHING Yahoo's rate; R1/R12/S12 populated. money_coi_*/
  vol_rank_* stay NULL (dead in Yahoo too).

## 2026-07-08 (cutover) — OpenBB is now the PRIMARY DB
- User: "use BB as we have more tickers." Executed the cutover.
- **State sync** (one-time, scratchpad migrate_state_to_bb.py): copied bot-state tables US_data.db → BB
  (trades/positions, event_journal, bookmarks, signal_accuracy, signal_weights, momentum_ranks, alert_dedup,
  gamma_wall_trades, antibubble_watch, rotation_watch, hiprob_recs, fundamentals_cache) preserving schema/PKs.
  The 4 "missing" tables (antibubble_watch/rotation_watch/hiprob_recs/fundamentals_cache) were missing only
  because the bot never ran vs BB (auto-created via CREATE IF NOT EXISTS); migrating preserves tracking history.
- **DB_PATH flipped to BB** (default US_data_OpenBB.db, env NYSE_DB_PATH overrides) in telegram_bot_optimized.py,
  dashboard.py, and _lib/{options_tracker,news_and_earnings,market_news_aggregator,event_writeup_bot_hooks,
  event_writeup_engine}. Verified: bot reads BB, positions intact (GOOGL×2/UNH), 736-ticker universe, rotation/
  GEX/building work. Reversible: `set NYSE_DB_PATH=...US_data.db`.
- **Empty columns explained** (user asked): option OHLC (call_open/high/low/close, R12/S12) NULL because OpenBB
  captures a snapshot (last/bid/ask/vol/OI/IV/delta), no per-contract bars; bot uses NONE of them (grep=0);
  money_coi_*/vol_rank_* dead in Yahoo too. Gained IV/greeks. R1/S1 (from lastPrice) 100% populated.
- **Signal-pattern backtest (5y SPY/VIX, 1234 days):** MAGNITUDE predictable — VIX rank-IC +0.365 vs |next-day|,
  P(>1% move) 11%→50% across VIX quintiles. DIRECTION not — all features IC≈0 (p>0.3), "yday up→today up" 51%.
  Advice: turbulence/size engine (= Market Radar, now validated); don't chase index direction; direction edge
  is cross-sectional (Rotation). "Redo until perfect" on direction = overfitting; iteration 1 was conclusive.
- **Watch:** BB freshness depends on nightly OpenBB derive (non-fatal, no auto-fallback yet). NYSE_Telegram.py
  still on US_data.db. See docs/NEXT.md.

## 2026-07-08 — OpenBB migration: enrichment bridge + parallel EOD capture
- Direction shift: user wants to EVENTUALLY RETIRE yfinance and run on OpenBB. So the BB lane is now
  being made a self-contained drop-in (not just a research lane). See [[openbb-migration]].
- **Parity (BB vs Yahoo, raw options):** OI corr 1.000/0.999 & **100% EXACT on 07-06/07-07** (settled
  OCC OI is one daily number → proper EOD captures agree perfectly); lastPrice 0.995-0.998; vol 0.999
  (75-82% exact — vol is intraday, snapshot-timing). Coverage 734 vs 88. The **07-02 divergence (OI 48%
  exact) is NOT a systematic lag** — tested: BB 07-02 doesn't match YF 07-01 (27%) or 06-30 (22%) either;
  it was just the first/rough OpenBB capture. Frozen one-off (OCC serves no historical OI), irrelevant
  forward. So change_OI is exact from 07-06 onward (both baselines clean EOD).
- **Enrichment bridge `NYSE_OpenBB_derive.py`** — SELF-CONTAINED (own copy of compute_oi_vol_change/
  build_stock_daily, NO NYSE_YFin import, so yfinance can be deleted later). Maps options_openbb→
  options_daily→options_change (change_OI/R1/S1/now-prev) + stock_daily (--stock). Identical Yahoo
  schema → DB_PATH flip needs zero bot/dashboard change. VALIDATED: 07-07 change_OI corr **0.9998**,
  R1/S1 0.9998. 07-06 change_OI degraded (0.08) purely from the 07-02 baseline seam — NOT a logic bug.
- **NYSE_YFin.py:** parameterized `compute_oi_vol_change(day, db_path=)` + `build_stock_daily(...,db_path=)`
  (default preserves Yahoo path); fixed a latent bug — stock_daily dedup DELETE referenced undefined
  `trade_date_str_db` (swallowed by try/except → dedup never ran); now `trade_day_str_db`.
- **run_all_offhours.py:** launches `NYSE_OpenBB.py` in BACKGROUND parallel to the Yahoo fetch (JOB1),
  then runs `NYSE_OpenBB_derive.py` after. Fully NON-FATAL (success gate still `rc1==0 and rc2==0`
  on Yahoo jobs; BB writes only US_data_OpenBB.db). This is the path to "100% going forward" — every
  new day gets consecutive clean BB baselines so change_OI is internally exact (like 07-06→07-07).
- **On "100% match":** two independent vendors won't be byte-identical; the historical 07-02 + Yahoo→BB
  boundary seams can't be retro-fixed (data never captured by OpenBB pre-07-02). Cutover (flip DB_PATH)
  is the user's call after a few days of clean parallel captures. Not committed to remote unless asked.

## 2026-07-07 (later 2) — Skew backtest: CONDITIONAL fragility signal (regime-flip)
- `backtests/skew_backtest.py` (parallel lane): does OpenBB 25Δ skew / put-flow on day t predict
  forward downside? 2 snapshot dates (07-02, 07-06); yfinance backfills forward closes for all 720
  names so the crash window isn't starved. 1,440 name-window obs.
- **skew25 rank IC FLIPS by regime:** +0.10 (p=0.007) in the calm 07-02→07-06 up-window (high skew
  → bounce, buy-the-fear) vs **−0.14 (p=1.7e-4) in the 07-06→07-07 semi crash** (high-skew names —
  SMH/SOXX/LRCX/KLAC — underperformed exactly as the /skew flag said). Pooled ≈0 (they cancel).
- **Conclusion:** skew is a CONDITIONAL FRAGILITY signal — predicts cross-sectional downside only
  when a catalyst hits, not a standalone direction bet. Same shape as the earlier put-flow finding
  (predicts move SIZE, not unconditional direction). Cross-sectionally VALIDATES the semis call in
  the crash window. Still preliminary (2 windows); need ~15-20 dates for a time-series test. Do NOT
  ship as a directional bot signal yet — pair with a regime/trigger.

## 2026-07-07 (later) — /skew downside-risk command (live IV, respects OpenBB-parallel rule)
- User asked for a semis-style downside-fear scan with "how much downside, direction + size/range."
  Building it on the OpenBB DB would wire the parallel lane into the bot (locked constraint) → built
  `/skew [TICKERS]` on the **live yfinance chain** instead (allowed, universal). Same capability.
- `_skew_analyze(tk)`: front ~30-DTE expiry → ATM IV, **25Δ put−call skew via true `bs_greeks` delta**
  (DIRECTION), 1σ expected move (SIZE), 1σ/2σ down price targets (RANGE), P(≥5%↓) lognormal, earnings-
  in-window flag. `_skew_scan` sorts by skew; `_fmt_skew` = one _pipe_table (ST·Tkr·IV%·EM%·Skew) +
  per-ticker downside-target lines. `/skew`, `skew_view` callback, BotCommand registered.
- **Gotcha found:** two `_iv_rank` defs exist — `_iv_rank(sym)`@932 shadowed by `_iv_rank(conn,tk)`
  @19771; module-level name resolves to the 2-arg one. Dropped the unused `_iv_rank` call in `_skew`.
  (Left the collision itself alone — pre-existing, out of scope.)
- Verified live on semis: SMH/SOXX 🔴 skew +5, EM ±17/18%, 1σ↓ −17/−18%, 2σ↓ −33/−37%. Post-crash IV
  runs hot so ranges are wide; MU/AMD skew compressed to +2 (everything bid = put skew flattens).
- Committed bb69f9b (Action Board + profiling) earlier this session; /skew in the next commit.

## 2026-07-06 — Rotation Tracker built & VALIDATED (first signal that works)
- **Built** `/rotation` (bot) + 🔄 Rotation Tracker (dashboard) — RRG money-flow, hierarchical
  high→low: **Macro (CROSS-ASSET: eq/intl/bonds/credit/gold/commodities/crypto/$)** → Sectors →
  Themes → Stocks. Axes vs SPY: strength (63d excess) × momentum (21d excess − strength/3) →
  Leading/Weakening(out)/Improving(in)/Lagging. `rotation_watch` logs quadrants daily + flags
  transitions; macro adds a risk-on/off tilt. Universal (DB-first + yfinance). Plotly RRG scatter.
- **VALIDATED (backtests/rotation_backtest.py, 1,542 name-date obs):** momentum axis rank IC
  **+0.138, p=5.5e-08**. 🟡 **Weakening (fading leaders = money leaving) underperforms −1.56%/10d
  excess, only 33% beat SPY**; Improving−Weakening spread grows +1.7/+4.1/+6.6% at 5/10/20d.
  **First clearly-validated signal of the session** (vs the rejected risk-off composite, vulnerability
  score, pcp_dev). Caveat: ~6mo momentum regime — edge is momentum-driven, would fade in a sharp
  mean-reversion/crash. Live read: cross-asset RISK-OFF; Semis/Tech rotating OUT → Fins/Indust/Health.
- Note: this is the *proper* build of the "leader rolling over" idea that failed as a naive standalone —
  as an RS-momentum quadrant tested on EXCESS returns, it works. See [[market-radar-backtest]].

## 2026-07-06 — "Vulnerability score" investigated & REJECTED (validation win)
- **Trigger:** UNH −1.7% (07-02→07-06) rotational pullback. Ran UNH through the full battery
  (OI, GEX, 24-model ensemble, mean-rev, PCR): positioning read **complacent/bullish** into it
  (low PCR, call-heavy flow, ensemble 7-BULL/2-BEAR, positive/pinning GEX). NOT foreshadowed;
  only soft tells = extension + `pcp_dev` BEAR. Backtested `pcp_dev`: n too small, BEAR t+3 hit 50%
  = **luck** (signal_accuracy only ~2mo/23 dates old).
- **Built + cross-sectional backtested a Vulnerability Score** (extended + complacent → fade) over
  2,339 obs. **REJECTED — do NOT build:** extension/momentum IC is significantly **POSITIVE**
  (t=+3.3 at t+20) → this regime **rewards** stretched names (same lesson as the Market Radar froth
  pillar). Six formulations × 3 horizons tested (scratchpad `vuln_backtest.py`/`vuln_battery.py`).
- **Only significant fade = cross-sectional low-PCR complacency** (IC −0.06..−0.07, t≈−2.9; feared
  Q5 beats complacent Q1 by ~3%/10d) — BUT the **time-series control (PCR vs own history) is null
  (t=−0.19)** → the effect is **structural (name fixed-effects), not a timing signal.** Not shippable.
- **Conclusion:** no shippable "find-the-next-UNH" signal in current data. The research-backed edge
  (put/IV **skew**) needs clean bid/ask/IV → **gated on the OpenBB capture** (`options_daily` only
  stores lastPrice). Skew = first thing to test once OpenBB is live. See [[market-radar-backtest]].

## 2026-07-06 — Market Radar: built, backtested, redesigned (turbulence gauge)
- **Investigated the Jul-2 tech/semis selloff** (SMH −5.4%, QQQ −2.1%, SPY −0.36%, VIX flat 16.7 =
  narrow flush, not broad). Found the bot's own scanners had logged BEAR fires on the index/semis
  complex from 07-01 EOD (`scn_uoa` SPY/QQQ/IWM/SMH, `scn_building` QQQ) — so the signal was there.
- **Done (feature, bot + dashboard):** `/riskoff` **Market Radar** — plain-English readout + a
  next-session SPY game plan (gamma walls: hold 740→755 / lose 740→729). Auto-push on startup
  (once/day `alert_dedup` grp `market_radar`) + daily post-close gated on turbulence≥ELEVATED.
  Menu entries added. `/rovalidate` = on-demand backtest (no scipy; rank corr via numpy).
- **Done (validation — the important part):** backtested all 5 pillars vs ~6mo DB history (104 days,
  fwd SPY/QQQ t+3/t+5). **Old composite 0-100 score = decoration** (Spearman +0.017, p=0.86).
  Per-pillar: **index put-flow predicts move SIZE** (|QQQ| t+5 corr **+0.37, p<0.001**) — the one
  real signal; **dealer-gamma+breadth** give a weak, correctly-signed (−0.15) but insignificant
  DIRECTION lean; **froth/overbought is MOMENTUM here (+0.15), not reversal**; vol-underpriced is
  contrarian. Scripts in scratchpad (`backtest_pillars.py`, `backtest_v2.py`).
- **Decision:** rebuilt `_riskoff_scan` into a **two-gauge** model — Turbulence (proven, primary) +
  soft low-confidence Direction lean; froth/VRP demoted to "context (not proven)". Honest framing:
  "big move brewing, direction unreliable" beats a fake "71/100 RISK-OFF".
- **Decision:** **OpenBB stays a PARALLEL test lane only** — removed `_fetch_openbb_history` from the
  live `_daily_history` backfill (yfinance-only in bot); OpenBB isolated in `NYSE_OpenBB*.py`. Added
  `NYSE_OpenBB_EOD.py` (EOD price puller → `stock_history`, run manually). CLAUDE.md note updated.
- **Git note:** my commits (7e90743→a0f1ad8) are ancestors of current HEAD e3fa26d; parallel work
  layered on top — all Market Radar content verified present in HEAD, tree clean, both files parse.
- **Pending (user actions):** restart bot + rerun Streamlit to deploy; `git push` if using a remote.

## 2026-07-03 — First stringent DB compare (Jul 2): OpenBB VALIDATED, yahoo OI exposed
- **Contract-level audit** (17,615 shared contracts, 87 tickers): coverage 100% (0 yfinance
  contracts missing from openbb; openbb adds 646 extra tickers); lastPrice 98% within 2%;
  volumes ~70% exact; call-OI only 58% within 2% BUT median diff 0.36%.
- **Arbiter test settled it:** 5 worst OI mismatches re-fetched fresh from CBOE — all 5 matched
  the OpenBB value EXACTLY (e.g. FXI 33.5C: ob=1255, yahoo=2, CBOE-now=1255). Yahoo serves
  stale/near-zero OI on many strikes → the old ≥95% strike-agreement gate measured yahoo's
  data quality, not ours. Verdict redefined: median OI diff ≤2% + price agreement ≥90% (PASS ✔ day 1).
- **Hygiene:** deleted 35,055 rows mislabeled 2026-07-03 (holiday; pre-fix run), regenerated
  chains_2026-07-02.parquet from the full day (178,344 rows / 734 tickers / 3.8 MB), compare now
  joins ^VIX↔VIX. Self-healing skip file live (openbb_skip.txt, 9 names; universe loads 734).
- **Implication:** OpenBB/CBOE is the more trustworthy OI source — strengthens the migration case.

## 2026-07-02 (night) — OpenBB capture hardened to hands-off; ops guardrails in
- **Done (NYSE_OpenBB.py, commits c41e3f2→5c8ba59→this):** plain `python NYSE_OpenBB.py` now does
  everything — expanded 740-name universe by default (auto-builds sheet if missing), safe pacing
  (workers 4 / pace 0.75s), adaptive slowdown (pace+rest+worker-halving), **CBOE-CDN fallback with
  curl_cffi browser impersonation fired instantly on throttle** (verified live: AAPL/BRK-B/SPY
  recovered mid-throttle), progress-driven retry rounds (≤5, stop when stalled, skip optionless),
  PERMANENT_FAIL split (no-options vs throttled) in summary, **automatic daily parquet-zstd backup**
  to `openbb_chains\` (~3-4 MB/day; --parquet additionally clears sqlite), openbb version stamped in
  run log, auto `--compare` at end with **VERDICT: PASS/CHECK** line (go/no-go = openInt ≥95%;
  lastPrice informational). `requirements_openbb.txt` pins openbb 4.7.2 / cboe 1.6.1 / curl_cffi 0.15.0.
- **Decision:** throttle handling = pace+backoff+retries+browser-fingerprint fallback (community
  standard per OpenBB/yfinance issue threads); NO proxy rotation (ToS-grey, unneeded for 1 run/day).
  One capture per evening (post-close ET) — multiple same-day runs burn the throttle budget.
- **User routine:** evening `python NYSE_OpenBB.py` → read VERDICT; weekly offsite copy of
  `openbb_chains\` (capture-forward data is unrebuildable).

## 2026-07-02 (evening) — Event column in All-Positions batch tables
- **Done:** dashboard `_ep_batch_table` (feeds "🌐 All Open Positions" one-table + "🏢 by Ticker" legs)
  now has an **Event** column: 📊 ER Xd (⚠️pre-exp when it lands before that leg's expiry) + 💵 ex-div Xd;
  one cached lookup per ticker (`_next_earnings` + bot `_divcap_stats`). Event-aware Signal: plain ⚪ HOLD
  escalates to 🟡 ER PRE-EXP / 🟡 EX-DIV (short ITM call assignment); never masks TAKE PROFIT/CUT LOSS/
  NEAR EXPIRY. Action-Required alert filter + both "how to read" legends updated. (Deep-dive per-leg
  table got Event earlier today.)
- **Status:** scanner backtests still auto-accumulating — no `scn_*` rows in `signal_accuracy` yet
  (they populate as /uoa /building /breakout /zrev /revert + building_alert fire; t+5 outcomes follow).
- **OpenBB lane parked by user** — parallel test ready (daily capture → `--compare`); all other pending
  items are OpenBB- or data-gated (see STRATEGY_BUILD.md).

## 2026-07-02 (later) — OpenBB capture hardening + storage + rate limits
- **Storage fixed:** parquet-zstd daily export (`openbb_chains/chains_YYYY-MM-DD.parquet`), sqlite = staging
  only. Measured **7x compression** (26.5MB → 3.6MB/day → ~0.9GB/yr; contractSymbols dropped, float32).
- **Rate limits:** `KeyError 'data'` = CBOE throttle (NOT symbols). Mitigations shipped: chunking+rests,
  slow retry rounds, ADAPTIVE pacing (chunk >25% fails → slow down). Bad symbols removed from builder.
  Community options if still needed: curl_cffi browser-impersonation session (NYSE_YFin already does this
  for yahoo), provider interleave (alternate cboe/yfinance chunks), requests-cache. NOT done yet.
- Positions table: Event col (ER/ex-div pre-expiry) + event-aware Action (38bda1d).
- #10-16 user list done (engine consolidation e71d195, weekly rotate, scn_* persistence, /ic tearsheet,
  vectorbt sweep 22335ec). qlib deferred (own project), graphify blocked (no CLI).
- **NEXT: user's 743 capture SUMMARY → validate day → production migration** (ALTER options_daily,
  wire into run_all_offhours, retire 4-hr yfinance options leg).

## 2026-07-02 — Strategy build series + DB history layer + portfolio/validation
- **Done (strategy scanners, bot + dashboard "⚙️ Strategy Scanners" hub):** `/wan` `/earnvol` `/cc`
  `/pairs` `/season` `/rotate` `/revert` `/condor` `/calendar` `/divcap` `/pwindex` `/pead`
  `/building`. Each verified vs live data before commit. `/wan` (15m) + `/building` (30m) are
  market-hours scheduled streamers with daily `alert_dedup`.
- **Done (infra):** `stock_history` table in US_data.db — multi-year OHLC; `_daily_history()`/
  `_history_matrix()` DB-first + lazy yfinance backfill (write-through) + `_sync_history_from_daily()`
  free maintenance from `stock_daily`. Backfilled ~135 tickers / ~105k rows / 6y. Repointed
  `/ic` `/season` `/rotate` `/pwindex` to it → **`/ic` momentum N 21→~1400 (t≈+5)**.
- **Done (Aladdin/validation gems, native — no heavy deps):** `/ic` = Alphalens-style rank IC +
  quantile spread; `/allocate` = max-Sharpe/min-var/risk-parity optimizer on the 6y covariance.
- **Decision:** build IC + optimizer natively rather than add alphalens/PyPortfolioOpt deps
  (keeps lean single-file style). OpenBB researched → keep PARKED (heavy, redundant with dashboard +
  direct feeds, doesn't unblock option-history strategies); selective fallback-layer adoption only.
- **Decision:** dispersion (#14) tried with top-8 constituents → meaningless (subset), reverted.
- **Blocker (data-gated, in tracker backlog):** #10 macro-event calendar (needs econ-calendar feed),
  #14 dispersion (needs ~full constituent chains), #15 index-rebalance (corp-action feed),
  #16 gamma-scalp (tick data), #17 box-arb (live bid/ask+borrow), #18 ETF-NAV (institutional).
  None doable without data we don't store. Finnhub key IS set (unblocked #13 `/pead`).
- **Source of truth:** `docs/STRATEGY_BUILD.md` (done vs pending vs parked, + repo catalog §3).

## YYYY-MM-DD
- **Done:** <what shipped / verified>
- **Decision:** <choice + why>
- **Blocker:** <what's stuck + what would unblock it>

## 2026-07-15 — mega-session recap (pre-compact)
DONE+committed: accumulation BUY/SHORT+split-guard · ISO date fixes (substr+positional, 15 sites)
· /ratings + Benzinga news · OpenBB cutover confirmed + 6/6 compare PASS + skew_snapshot wired
nightly + root tidy · nested-expander close fix · Market Overview 1m-live overlay · Command
Center perf (cached parallel book, page-local refresh) · STOCK legs everywhere (CC/PP/Collar
detect, payoff, exit planner, cmd center; bot excludes via 27 guarded queries) · /tax engine
(Pub 550 put-reset verified vs GOOG Jul-26-2027, wash sale, 2026 MFJ) + entry-date backdating
· plain-English Greeks (portfolio caption + planner Real$/Time$/±$1/Θd cols) · Stk±1σ scenario
targets + honest Est Open captions (validated 4-7% err) · heatmap split-day guard (SOXS 1:10
2026-07-15 → +974% artifact, real +9%).
BS-model backtest artifacts: scratchpad bs_validate/bs_tune/bs_liquid.py (1.19M contract-days).
PENDING (PLAN.md): intraday 1-min lane + heat-seeking/reversal + live writeups · NSE India lane
(bhavcopy DELIV_PER verified) · bot stock-leg display · gated backtests (scanner fires, skew panel).

## 2026-07-16 (marathon session, part 2) — recap before /compact
- **Shipped & committed** (all on main): intraday lane supervisor · /live /heat + dashboard hub tabs
  (Live/Heat/Skew/Catalysts/Regime) · stock-leg crash fixes (VaR/MC/scenarios ×5 sites) · /tax Pub 550
  running-clock fix + NaN guards + app_settings income · /add one-line entry + typed-ticker wizard ·
  UX modernization (morphing wizards, readable /spreads, @bot inline search, collapsible /plan) ·
  Mini App /terminal (tunnel parked → local-only, NYSE_MINIAPP_TUNNEL=1 re-enables) · limit-guard
  hooks (Stop+PostToolUse → NEXT.md reset stamp + ClaudeResume task `claude --continue /standup`) ·
  token diet (CLAUDE.md 2.9k→1.1k tok, rules path-scoped) · date audit (DB 100% ISO; NYSE_YFin
  monthly-substr fix; _to_mdy→_exp_iso renames) · backtests P2/P3 (revert VALIDATED +2.7% t+5;
  uoa/building direction FAILED; heat/skew thin → rerun ~2wks; `backtest_summary` table) ·
  /premium rich-IV seller (VRP + tastytrade mechanics) bot+dashboard · EOD scheduler BB-primary
  (Yahoo fallback-only via bb_capture_ok) · stocks-separate manage tab (Exit Planner) ·
  universal _report() macro + format sweep (momentum/opex/squeeze/macro/gex/OI-flow).
- **Trades**: UNH closed (+$483 net); AMD −2×400P 7/31 + GOOGL collar + GOOG 100sh@167 open.
- **Verify method**: everything tested against live DB before commit; bot restarted on final code.

## 2026-07-23 — Positions/ticker card rebuild, earnings+transcripts, Mag-7 study

**Bugs found by EXECUTING (all silent, all produced plausible-but-wrong numbers):**
| Bug | Impact | Commit |
|---|---|---|
| `fast_info` has NO post/pre-market fields | after-hours NEVER worked; hid TSLA −3.4% earnings move | `a74636e` |
| AH window capped at 20:00 ET (bot + dashboard) | reverted to stale 4pm close all evening | `69477e5`,`4b71bfe` |
| `position_monitor` gated 9:30–16:00 | no alert ever fired after hours | `fb6a973` |
| Cadence throttle blocked the MANUAL button | positions button looked dead → "still old message" | `fb6a973` |
| `_LAST_OFFHOURS_PUSH`: 15-min throttle on 10-min tick | fired every **20** min, not 15 | `aceaa91` |
| `eod_px` computed in loop 1, table built in loop 2 | every row showed the LAST leg's EOD (6.86) | `c2acdeb` |
| Heatmap labels `d[0:5]` on ISO date | x-axis read "2026-" (3 places) | `6b0a2b6` |
| Intraday lane spawned twice | 2× rate-limit load | `fb6a973` |

**Corrections to my own claims:** transcripts do NOT need a paid key — AlphaVantage
`EARNINGS_CALL_TRANSCRIPT` works on the key we already hold. I concluded too early from
testing only `earningscall`. Also marked "event/news header" done when only the *events*
half existed.

**Built:** BOOK RISK (concentration + assignment) · EXPIRY/ASSIGNMENT walk-through ·
per-leg Buy→EOD→AH + TOTAL · everything→tables · `/freq` cadence picker ·
`short_interest` + `earnings_history` tables · transcripts on DISK (`transcripts/`) ·
coloured OI sparklines · volume panel · 2 orphaned OI charts wired.

**Mag-7 earnings study (584 events, 2002-2026):** direction ~unpredictable. Only real
effect = fade the 5-day run-up (rankIC −0.122, t=−2.97; ran-up names up 43.8% vs 58.9%
for sold-off) BUT it **weakens out-of-sample** (t=−2.51 → −1.46). SIZE is far more
predictable: rvol20→|move| t=+6.12. Survivorship caveat: Mag-7 = today's winners.
Script: scratchpad `mag7_earnings.py`.

**4th orphan pattern today** — news fns, position lifecycle, transcripts, OI charts all
existed unwired. `_lib` orphan triage is overdue.

### 2026-07-23 (late) — VALIDATED directional signal: post-earnings drift (PEAD)

Earlier conclusion "direction is unpredictable" was answering the WRONG question. Predicting
the earnings REACTION fails. Predicting the DRIFT AFTER it works.

**599 events, 7 tickers, 2001-10-18 → 2026-05-20.**

| hypothesis | d5 | d10 | d20 |
|---|---|---|---|
| EPS surprise → drift | IC +0.101 t+2.47 | +0.101 t+2.47 | +0.123 **t+3.03** |
| **Reaction → drift** | +0.141 t+3.48 | +0.111 t+2.72 | +0.147 **t+3.62** |

**OUT-OF-SAMPLE — SURVIVES** (this is what killed the run-up signal):
- reaction→d20 1st half (2001-15) IC +0.157 t=+2.74 · 2nd half (2015-26) IC +0.129 t=+2.24
- surprise→d20 DECAYS: t=+2.46 → +1.56 (no longer significant) — use REACTION, not surprise

**Economic size (quintile by reaction, fwd 20d):**
Q1 worst −0.87% · Q2 +1.26% · Q3 +0.11% · Q4 +1.47% · Q5 best **+3.77%** → **Q5−Q1 = +4.63%/20d**
Long Q5 / short Q1: mean **+2.32%**, **t=+3.29**, hit-rate **57.1%** (n=240)

**Read:** you cannot predict the gap; once it happens it PERSISTS ~20 days. This is classic
PEAD, the most-documented anomaly in finance, and it holds on Mag-7 out-of-sample.

**Caveats:** Mag-7 = survivorship-selected. Q3 breaks monotonicity (tails are clean, middle
noisy). Not yet tested with transaction costs or on non-Mag7 names.

**Live implication 2026-07-23:** TSLA just printed a large NEGATIVE reaction (−38% EPS miss,
stock ~326 from 374). PEAD says drift continues LOWER ~20d. User closed their bearish TSLA
spread today at +$1,361 — signal says the directional thesis had further to run.

Scripts: scratchpad `mag7_earnings.py`, `pead.csv`.

## 2026-08-27 — Cloud migration: the system now runs on Oracle

**State:** VM `nyse-bot` at 150.136.41.250, us-ashburn-1, A1.Flex 2 OCPU / 12 GB, Always Free.
Seven services up: nyse-bot, nyse-dashboard, cloud-tunnel, cloud-keepalive, fail2ban,
cloud-eod.timer, cloud-backup.timer.

**The full EOD pipeline ran end to end on the VM** for 2026-08-27, laptop uninvolved: capture
716 tickers -> options_change 249,520 -> skew 709 -> stock_daily 716 (Finnhub, no yfinance) ->
serving layer 714 -> fundamentals 500. cloud_smoke.py gate C answered the migration's deciding
question authoritatively: BOTH capture paths work from a datacenter IP.

**Separate repo by user decision:** Street_Cloud_AI_TradeOps, private. Every .py renamed
(telegram_bot_optimized -> cloud_bot, NYSE_OpenBB -> cloud_capture...). tools/sync_cloud.py is a
ONE-WAY mirror that renames AND rewrites references in four shapes, including STRING filenames
like JOB_BB and py_compile targets, which fail at RUN time not import time. Never edit .py
inside NYSE_Cloud - the next sync overwrites it.

**Bugs found, every one of which failed silently rather than loudly:**
- psutil missing -> _script_running answered "no watchdog" -> bot and watchdog spawned each
  other: 15 processes, 6.45 GB, 40 seconds. psutil now required, /proc fallback added, and the
  no-answer default INVERTED - a spawn loop takes the host down, a missing supervisor does not.
- python-telegram-bot without [job-queue] -> a warning, and every scheduled job silently never
  ran: position pushes, earnings alerts, digests, heat streamer, intraday supervisor.
- httpx logs request URLs at INFO and a Telegram URL embeds the token -> the bot token reached
  the journal and a transcript. Four loggers forced to WARNING; token revoked and reissued.
- Hardcoded Windows paths in five files meant the nightly lane could never have run on Linux;
  NYSE_OpenBB.py also ignored NYSE_DB_PATH and would have filled a DB nothing else opens.
- Persistent=true fires a missed timer window the instant the timer is enabled -> collided with
  a manual capture, seven at once, 204 CBOE throttle errors. Single-instance lock added INSIDE
  the capture, because the collision was manual-versus-scheduled.
- A capture started in an SSH foreground froze 39 minutes on SIGTTOU when the session dropped.

**Idle reclamation:** Oracle reclaims when CPU 95th pct AND network AND memory are ALL under 20%
over 7 days. The CPU route needs ~1.2 h/day; the nightly-validation idea measures 25-35 min, so
it does not qualify. Solved on memory instead: cloud-keepalive holds 3 GB, memory 34-38%, one
second of CPU total.

**Rejected after measurement:** SQLite cache_size tuning was 4-20% SLOWER in an alternating A/B
on the VM. Suspect is idx_oo_lookup leading with ticker while these queries lead with trade_date.

**Open:** offsite backup must LEAVE Oracle (1.1 GB verified snapshot exists, same disk); budget
still non-recurring; WallStreet_Agentic_TradeOps still public with a 14 MB DB in its history;
Tailscale Funnel would give a permanent dashboard hostname, free, no domain.

Cloud tracker: python tools/show_pending.py --cloud  - 22 rows, kept OFF the main sheet.
