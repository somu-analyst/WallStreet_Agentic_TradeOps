# NEXT — handoff

_Updated 2026-08-18. `docs/IDEA_TRACKER.xlsx` (`python tools/show_pending.py`) is the
authoritative queue; this file is orientation only._

## State

Bot running (restarted 2026-08-18 08:34 ET, 85 commands). Working tree clean, everything
committed. **259 tracker rows, no P1 open.**

## Landed recently

- **ID 241** `_signal_writeup()` — the house signal template. Direction verdict is *computed*
  by a binomial test, so no writeup can claim a side the data never supported; unmeasured
  signals render "Not measured here" rather than borrowing confident language.
- **ID 243** Measured the whole ensemble against it — **nothing qualifies**, so nothing was
  converted. See `docs/LOG.md` 2026-08-17; the reusable tool is
  `tools/measure_signal_base_rates.py` (gitignored with the rest of `tools/`).
- **ID 217** Position alerts re-send on material change (≥20 P&L points or a new EXIT/CUT),
  and the shared card builder can no longer fail silently inside the scheduled job.
- **ID 237 / 250** `/indianews`, then fixed to actually read the real book — the India
  holdings live in `paper_trades`, and two of three are index ETFs needing an index query.
- **ID 249** Schedules are now **ET-anchored** (`_sched_once(..., tz="ET")` default) so
  market-relative labels stay true across DST. India lanes stay `tz="UTC"` — IST has no DST.
- **ID 257** `/paper` US book pushes at 16:30 ET, mirroring the India card.
- **ID 258** Startup catch-up is a **full replay** of everything due today; the hourly sweep
  still dedups. Throttled to one replay per 30 min.
- **ID 204** `/paper` grid 61 → 29 display cells.

## Start here

1. **Anthropic account is out of credit** (ID 259). The `/indianews` advisor 400 was *not* a
   code bug — the message was `"Your credit balance is too low"`, hidden behind a
   `str(e)[:80]` truncation that has since been fixed (`_llm_err_msg`). Every paid-Anthropic
   feature (`/insight`, `/desk`, `/why`, the advisor) stays degraded until credits are added.
2. **ID 211** — country + asset-class pickers on `/add` and `/paper`. User approved BOTH.
   Not started.

## Genuinely open

| ID | Pri | Item |
|---|---|---|
| 211 | P2 | Country + asset-class pickers on `/add`/`/paper` — user said add both. |
| 243 | P2 | Re-run the base-rate tool as `signal_accuracy` accrues; convert a writeup only when a model clears the **Bonferroni** column, never the nominal one. |
| 28 | P2 | Drop `options_daily`. **Advice: don't** — 8 "dead" columns are written by `NYSE_YFin.py`; dropping it kills the Yahoo fallback silently. |
| 36 | P2 | Cross-strategy allocator — BLOCKED on ~1000 graded fires. Time, not work. |
| 234 | P2 | DUE 2026-08-26: remove or promote `_derive_scope_watch()`. |
| 256 | P2 | Optional `/retail` command — answered, not built (no macro history table). |

## Traps that have cost real work here

- **`tools/` is gitignored.** `tracker_io.py`, `show_pending.py` and the measurement tool all
  live there and cannot be committed — record findings in `docs/LOG.md` instead.
- **The tracker can have a concurrent writer.** Write through `tools/tracker_io.py`; `add()`
  allocates the ID at write time and `update(..., expect=)` refuses a mismatched row.
- **Reading the pending LIST is not reading the ROW.** `show_pending.py` truncates to one
  line; `Detail` holds the diagnostics. ID 217's `Detail` named a second failure hypothesis
  that turned out to be a live unguarded crash path. Dump the full row before acting.
- **This machine runs on New York time.** Local == ET. Don't assume IST from the user's
  working hours — I misread a correct catch-up as a bug on that assumption.
- **Restarting races the watchdog.** `bot_watchdog.py --loop` restarts the bot within 5 min
  of finding it down, so a manual kill+start can briefly produce two instances. PTB's polling
  conflict kills the loser, but check the instance count after a restart.
- **Don't test bot output through `python -c`.** Console encoding mangles em-dashes and emoji
  and `%` doubling corrupts comparisons — it looks like a code bug when it is a harness bug.
  Write a UTF-8 file and run that.
- **Changing a table's column count?** Grep for positional index use (`r[4]`) — the ID 204
  trim left `_sub` summing a column that no longer existed and crashed `/paper`.

## Recently fixed — do not re-diagnose

- Long Telegram messages are SPLIT in `_send_message_sanitized`, not truncated.
- `_world_news_block()` returns EMPTY and always has; `_geo_news()` is the working lane.
- Bare NSE symbols need `_yf_alias` (`_hist_for` in the dashboard does this) or India goes
  blank. Yahoo 404s for BANKIETF/MOTHERSON/NIFTYIETF are expected on the bare symbol; prices
  resolve through the alias path.
