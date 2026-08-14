# NEXT — handoff

_Updated 2026-08-13. `docs/IDEA_TRACKER.xlsx` (`python tools/show_pending.py`) is the
authoritative queue; this file is orientation only._

## State

Bot and dashboard both running the committed code. **242 tracker rows.** Working tree clean
at `a416dd4`. Last three commits: message-truncation fix, trend columns, paper-tile P&L.

## Start here — ID 241 needs one answer before any code

The user pasted this verbatim as the next task and will open a fresh window to continue it:

> Index put-flow is in the TOP 20% of its own history. **What followed, measured on 151
> days:** a >2% Nasdaq week came **62%** of the time, vs **38%** after a normal day. Median
> move 2.26% vs 1.55% (p=0.012). **Direction: 53% up — a coin flip.** This calls SIZE, not
> side. **Do:** favour long premium, widen stops, cut size on short-vol. Do NOT pick a
> direction off this.

This is the Market-Radar finding already validated here (put-flow predicts SIZE, not
direction) written the way the user wants signals surfaced: measured base rates, a p-value,
an explicit coin-flip warning, then a Do list. **Ask first which is wanted** — (a) wire this
block into the brief / radar output, or (b) adopt it as the house template for every signal
writeup. Guessing means a rebuild.

## Genuinely open

| ID | Pri | Item |
|---|---|---|
| 241 | P1 | Put-flow writeup — confirm intent, then implement (above). |
| 237 | P1 | India news lane: daily/weekly/monthly per holding, written as an advisor. Google News RSS per NSE symbol needs no key. |
| 217 | P1 | **Needs a user decision, not work.** Position alerts are not lost — ID 52 consolidated them into ONE status message that is EDITED in place, and Telegram does not notify on an edit, so it scrolls away silently. Offered: re-send on material change (±20%, EXIT/CUT) vs pin the message. |
| 211 | P2 | Country/asset-class picker when adding. Mostly overtaken — country is inferred from the symbol now; asset class is still watchlist-only. |
| 28 | P2 | Drop `options_daily`. **Advice: don't.** Row 27 proved 8 "dead" columns are LIVE, written by `NYSE_YFin.py`; dropping it kills the Yahoo fallback silently, surfacing only the day OpenBB capture fails. |
| 36 | P2 | Cross-strategy allocator — BLOCKED on ~1000 graded fires (~7 months). Time, not work. |
| 234 | P2 | DUE 2026-08-26: remove or promote `_derive_scope_watch()`. |
| 204 | P3 | `/paper` 61 cells, `/watchlist` 41 vs the 28-cell guideline. Aligned, just wide. Waiting on whether they wrap badly on the user's phone. |

## Two traps that cost real work this session

- **The tracker had a concurrent writer.** A second Claude session edited
  `IDEA_TRACKER.xlsx` at the same time; IDs collided and four rows lost their outcome text
  to an ID-keyed update landing on the wrong row. **Write through `tools/tracker_io.py`** —
  `add()` allocates at write time, `update(..., expect=)` refuses a mismatched row. Assume
  another session may be live and re-read before writing.
- **`dashboard.py` also changed under me mid-edit.** Re-read before any edit that depends on
  surrounding lines.

## Recently fixed — do not re-diagnose

- Long Telegram messages are SPLIT in `_send_message_sanitized`, not truncated. If something
  looks cut, check for a NEW pre-send `_tg_cut`, not the wrapper.
- `_world_news_block()` returns EMPTY and always has. `_geo_news()` is the working lane;
  `_move_news_pool()` combines it with the (now repaired) aggregator.
- All four getters in `_lib/market_news_enhanced.py` used to return `None` on a non-200,
  which made `get_aggregated_news` raise and kill all four sources.
- Bare NSE symbols need `_yf_alias`; `_hist_for()` in the dashboard does this. Any new
  price/history lane for a foreign name must go through it or India goes blank again.
