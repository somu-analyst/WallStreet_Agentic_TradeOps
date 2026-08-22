# NEXT — handoff

_Updated 2026-08-21. `docs/IDEA_TRACKER.xlsx` (`python tools/show_pending.py`) is the
authoritative queue; this file is orientation only._

## State

Bot and dashboard running. Working tree clean, **everything pushed** (`origin/main` at
`26674be`). **302 tracker rows — 1 actionable, 1 blocked, nothing open.**

`show_pending.py` now separates ACTIONABLE from ANSWERED/WAITING. The old flat list showed
18 answered questions as "open" and made the queue unreadable.

## The only thing left

| ID | Pri | Item |
|---|---|---|
| 234 | P2 | **DUE 2026-08-26** — remove or promote `_derive_scope_watch()`. Day-7 check was CLEAN (0 issues, 0 missing days across all five downstream tables). It **self-expires** past `_DERIVE_WATCH_UNTIL`, so doing nothing is valid; the only question is whether to delete the dead code or keep it as a permanent audit. |
| 36 | P2 | Cross-strategy allocator — BLOCKED on ~1000 graded fires. Time, not work. |

## Waiting on data, not on us

- **`earnings_implied`** (`/emtest`) — accruing since 2026-08-21. Answers whether selling the
  implied move pays **on this universe**, instead of trusting a generic backtest. Judge it
  when it has a distribution, not before. Same rule as the other accruing tables.
- **`signal_accuracy`** — re-run `tools/measure_signal_base_rates.py` as it grows. Convert a
  writeup only when a model clears the **Bonferroni** column, never the nominal one.

## Landed this session

- **ID 241/243** `_signal_writeup()` house template; measured the whole ensemble against it —
  **nothing qualified**, so nothing was converted. That is the template working.
- **ID 217/270** Position alerts re-send on material change, cover the paper book, and can no
  longer fail silently inside the scheduled job.
- **ID 249** Schedules are **ET-anchored**; India lanes stay `tz="UTC"` (IST has no DST).
- **ID 273** Trend columns were **wrong** — a stale DB series shifted every window. yfinance
  is now primary for `_chg_windows`, anchored to the live mark.
- **ID 301** Spread scanner was recommending **arbitrage that does not exist** (credit ≥ width).
- **ID 296** One glossary (`_GLOSSARY`) behind every acronym, in both surfaces.
- **`us_analytics_daily` retired** — 8 readers were being fed February data as if current.

## Traps that have cost real work here

- **`tools/` is gitignored** (except `show_pending.py`, which predates the rule and IS
  tracked). Record findings in `docs/LOG.md`, not in a tool file.
- **The tracker can have a concurrent writer.** Write through `tools/tracker_io.py`.
- **Reading the pending LIST is not reading the ROW.** `Detail` holds the diagnostics.
- **This machine runs on New York time.** Local == ET. Don't infer IST from working hours.
- **Restarting races the watchdog** (`bot_watchdog.py --loop`, 5-min sweep). Check the
  instance count after a restart.
- **Don't test bot output through `python -c`** — console encoding mangles em-dashes/emoji.
  Write a UTF-8 file and run that.
- **Changing a table's column count?** Grep for positional index use (`r[4]`).
- **Verify numbers, not just that they render.** The trend columns *rendered* perfectly and
  were wrong for every US ticker. Recompute against an independent source.
- **Streamlit grids are CANVAS.** `[role=columnheader]` and `<th>` are the accessibility
  layer only — CSS cannot style what you see, and `--gdg-*` variables are not consumed.

## Recently fixed — do not re-diagnose

- Long Telegram messages are SPLIT in `_send_message_sanitized`, not truncated.
- `<b>` inside `<pre>` is STRIPPED by Telegram — proven by API probe, not assumed.
- Bare NSE symbols resolve through `_yf_alias`; Yahoo 404s on the bare symbol are expected.
- India paper values were never a dashboard bug — BANKIETF and NIFTYIETF were closed 08-20.
