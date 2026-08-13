# NEXT — handoff

_Updated 2026-08-08. Read `docs/IDEA_TRACKER.xlsx` (or `python tools/show_pending.py`) for
the authoritative queue; this file is orientation only._

## State

Bot, dashboard and watchdog all running. **197 tracker rows, 182 done, 1 queued, 1 blocked.**

## Only 2 items open

| ID | Status | Note |
|---|---|---|
| 36 | BLOCKED | Cross-strategy allocator — needs ~1000 graded fires (~7 months). Time, not work. |
| 28 | QUEUED | Drop `options_daily` entirely. **Advice: don't.** Row 27 proved 8 of its "dead" columns are LIVE, written by `NYSE_YFin.py` (which can target this DB). Dropping the table kills the Yahoo fallback silently — surfacing only the day OpenBB capture fails, i.e. exactly when it is needed. |

## Built 2026-08-08 (all on BOTH surfaces)

`/dealer` CFTC dealer futures · `/whatif` Entropy-Pooling scenario · `/insight` cross-lane LLM ·
`/desk` research-desk report · `/why` narrative-vs-data · `/feed` channel ingest · `/llm` provider
status · `/xirr` annualised returns · `/india` NSE EOD + delivery %

## Tested and REJECTED (do not rebuild — see ADOPTED.md)

- **Investment Clock** (Part 12) — 1 of 4 quadrants correct; the aggregate was the equity risk
  premium leaking through the one quadrant that picks stocks.
- **Inflation-direction rule** (Part 12.4b) — the FINDING survives (+4.37%/yr equity gap on total
  returns) but the RULE dies: −1.71%/yr vs always-stocks. The whole apparent edge was the
  missing dividend, exactly as the caveat predicted.
- **Alpha Zoo, 10 pre-registered factors** (Part 14) — 0 of 10 clear raw p<0.05, 5 of 10 carry the
  WRONG sign. Underpowered (37–72 independent dates), and said so.
- **Kronos** — pretrained through an unpublished cutoff; permanently untestable here.

## Accruing — worthless until they have history, and CANNOT be backfilled

`macro_vintages` (BLS revisions) · `reddit_mentions` (crowding) · `dispersion_daily` (index-vs-member
IV ratio, 7 days so far, sd 0.012 — no distribution yet) · `narrative_checks` (per-source hit-rate)

## Watch-outs earned the hard way today

1. **Never rewrite source from PowerShell** — double-encoded 1,914 emoji, still compiled.
2. **Never `UPPER(ticker)` in a WHERE** — 330× slower; killed at 33 sites.
3. **A silently-empty lane makes the LLM invent data** — it fabricated positions when the book
   query failed. Every lane block must emit something, even "unavailable".
4. Groq/OpenRouter don't train on prompts; **Google's free tier does** — public news only.

## Housekeeping

- `US_data_OpenBB.db.pre27.bak` (3.39 GB) — safe to delete after ~1 week if nothing breaks.
- If `Options_chain_data` syncs to Google Drive, exclude `*.db` / `*.bak` (6.7 GB).
- `docs/PLAN.md` (10d) and `docs/LOG.md` (13d) are stale; the tracker superseded them in practice.
