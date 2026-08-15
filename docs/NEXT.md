# NEXT — handoff

_Updated 2026-08-14. `docs/IDEA_TRACKER.xlsx` (`python tools/show_pending.py`) is the
authoritative queue; this file is orientation only._

## State

Bot and dashboard both running. **243 tracker rows.** Last session closed the two P1s that
were blocked on a user decision (241, 217) — see `docs/LOG.md` 2026-08-14 for the full write-up.
Changes are in the working tree at `telegram_bot_optimized.py`, compiled and tested,
**not yet committed** (user commits on request only).

## Landed this session

- **ID 241 — `_signal_writeup()` is the house signal template** (bot ~line 3737). Percentile →
  measured base rate vs baseline (n, p) → direction verdict → Do list. The direction verdict is
  **computed** by a binomial test, so no writeup can claim a side the data never supported, and a
  coin flip auto-appends the "Do NOT pick a direction off this" guard. Unmeasured signals render
  "Not measured here" instead of borrowing confident language. Turbulence gauge rewired onto it,
  reproducing the user's wording character-exact.
- **ID 217 — position alerts now notify, and can no longer fail silently.** Two distinct bugs:
  (1) the recurring push edits the card in place and Telegram doesn't notify on edits — fixed
  with a material-change re-send (book P&L ≥20 points, or a new action-required leg), diffed
  against the last *notified* state in `app_settings`; (2) the shared `_positions_card_parts`
  call inside the scheduled job was **unguarded**, so a throw killed the push with no message
  at all — now logged and surfaced as one visible alert per day.

- **ID 237 — India news lane.** `/indianews [daily|weekly|monthly]` + `india_news_job` at 02:30
  UTC (pre-NSE-open). India-pinned Google News RSS, searched by **company name** (bare NSE
  symbols are ambiguous), 8 materiality buckets, one job covering all three horizons. The
  advisor layer is **paid-Anthropic-only by design** — its prompt names holdings, and the free
  tier trains on prompts. Needs a bot restart to load.

## Start here — two decisions, no blocked work

1. **ID 249 (P2) — four jobs have a label that is false in one DST season.** Schedule times are
   UTC and don't shift; the ET wall-clock does. `plan_alert` / `action_board` / `earnings_alert`
   are labelled "pre-market" but fire at or after the 9:30 open under **EDT** (most of the year);
   `whymoved_alert` is "(post-close)" but fires 3:45pm **EST**, 15 min before the close. Fix is
   either to move the UTC times or gate each job on `_et_now()`. Not changed unilaterally — it
   alters when a live bot fires. Note `bot-conventions.md` still advertises the 8:45am ET
   earnings push, which is only true in winter.
2. **ID 217 widening** — the re-send fires on any new ACTION REQUIRED leg, which includes
   TAKE PROFIT; the user said "EXIT/CUT". One line to narrow (drop `"profit"` from
   `urgent_keys` in `_positions_card_parts`) if unwanted.

## Restart needed

The running bot and dashboard both hold pre-fix modules. Nothing landed this session is live yet:
`/indianews` + its 02:30 UTC job, the material-change position re-send, the card-build guard,
and the ID 245 cutoff all need a restart. Harmless meanwhile — old and new paths agree on
today's audit row.

## Genuinely open

| ID | Pri | Item |
|---|---|---|
| 245 | P1 | **Owned by the other session** — DATA VALIDATED shows 2026-08-13 not 08-14 though capture succeeded. Check with them before touching it. |
| 211 | P2 | Country/asset-class picker when adding. Mostly overtaken — country is inferred from the symbol now; asset class is still watchlist-only. |
| 243 | P2 | Roll the signal template out to remaining writeups. **Not mechanical** — most signals have no measured base rate and the template refuses to invent one, so converting means measuring first. Do it opportunistically, never as a sweep. |
| 28 | P2 | Drop `options_daily`. **Advice: don't.** Row 27 proved 8 "dead" columns are LIVE, written by `NYSE_YFin.py`; dropping it kills the Yahoo fallback silently, surfacing only the day OpenBB capture fails. |
| 36 | P2 | Cross-strategy allocator — BLOCKED on ~1000 graded fires (~7 months). Time, not work. |
| 234 | P2 | DUE 2026-08-26: remove or promote `_derive_scope_watch()`. |
| 204 | P3 | `/paper` 61 cells, `/watchlist` 41 vs the 28-cell guideline. Aligned, just wide. Waiting on whether they wrap badly on the user's phone. |

## Traps that have cost real work here

- **The tracker can have a concurrent writer.** A second Claude session edited
  `IDEA_TRACKER.xlsx` at the same time on 2026-08-12; IDs collided and four rows lost their
  outcome text. **Write through `tools/tracker_io.py`** — `add()` allocates at write time,
  `update(..., expect=)` refuses a mismatched row. Assume another session may be live.
- **`dashboard.py` has changed under an in-flight edit before.** Re-read before any edit that
  depends on surrounding lines.
- **Reading the pending LIST is not reading the ROW.** `show_pending.py` truncates to one line;
  `Detail` / `Next Step` hold the diagnostics. ID 217's `Detail` named a second failure
  hypothesis that turned out to be a live unguarded crash path in a scheduled job — found only
  because the user asked whether the sheet was being followed. Dump the full row before acting.
- **Don't test bot HTML through a `python -c` one-liner.** The Windows console is cp1252 and
  mangles `—`/emoji, and `%` doubling in shell strings corrupts the comparison — it looks like a
  code bug when it is a harness bug. Write a UTF-8 test file to the scratchpad instead.

## Recently fixed — do not re-diagnose

- Long Telegram messages are SPLIT in `_send_message_sanitized`, not truncated. If something
  looks cut, check for a NEW pre-send `_tg_cut`, not the wrapper.
- `_world_news_block()` returns EMPTY and always has. `_geo_news()` is the working lane;
  `_move_news_pool()` combines it with the (now repaired) aggregator.
- All four getters in `_lib/market_news_enhanced.py` used to return `None` on a non-200,
  which made `get_aggregated_news` raise and kill all four sources.
- Bare NSE symbols need `_yf_alias`; `_hist_for()` in the dashboard does this. Any new
  price/history lane for a foreign name must go through it or India goes blank again.
