# NEXT — handoff

_Updated 2026-08-25. `docs/IDEA_TRACKER.xlsx` (`python tools/show_pending.py`) is the
authoritative queue; this file is orientation only._

## State

Bot and dashboard running. **333 tracker rows · 11 actionable · 1 blocked.** Everything
committed and pushed. The open work is now dominated by ONE theme: moving the system off
this laptop (ID 306 and its dependants).

## Landed since the last refresh

- **`/sankey` + Money Flow page** — company income statement as a flow diagram, figures
  pulled from the company's own SEC filing rather than typed. Refuses to render numbers that
  do not balance. Revenue splits by **geography** or **customer segment** (Palantir:
  Government +79% vs Commercial +110%), each carrying its own Y/Y so you can see which part
  of the business is actually growing.
- **Legendary Investors (13F)** — 185,043 holdings; what the investors did quarter over
  quarter, refreshed weekly.
- **Datacenter-safe price lane** — `NYSE_PRICE_SOURCE=finnhub` matches real closes at
  **0.000%**. This is what makes cloud hosting possible at all; yfinance is blocked from
  datacenter IPs.
- **Market Radar printed its own HTML tags** on the dashboard — engine emits Telegram HTML,
  Streamlit renders Markdown. `_tg_md()` converts at the boundary.
- **Watchlist takes any market** with `country=` / `cc=` to disambiguate.

## Start here — the cloud migration

Everything below hangs off ID 306. The order matters: each gate can kill the next.

| ID | Pri | Item |
|---|---|---|
| 306 | P1 | **HOST EVERYTHING FREE.** Gates 1 (datacenter data) and 2 (ARM wheels) PASSED. Gate 3 (vault) solved via `KEYVAULT_PASSPHRASE`. **Gate 4 needs the user's Oracle account** — nothing proceeds without it. |
| 314 | P1 | Parallel repo exists at `../WallStreet_TradingOps` — scaffolded, isolated, 4 commits, **no GitHub remote yet** (no `gh` CLI on this machine; user must create the repo). |
| 316 | P1 | Unattended operation + per-change validation + zero-cost guarantee. Written up as an artifact; needs the runbook in the repo. |
| 317 | P1 | **US licensing exposure.** Showing market data to other people is redistribution — CBOE/Finnhub/Yahoo are all personal-use licensed. Keep it private and invite-only. This is the biggest non-technical risk. |
| 308 / 312 / 313 | P2 | Frontend, database and security questions — all downstream of the read-only-vs-own-book decision, which is **ANSWERED: read-only now, `user_id` in the schema so own-book is a later upgrade, not a retrofit.** |
| 330 | P2 | Money-flow chart enrichment: mix shift, operating leverage. |

## Conventions worth not re-learning

- **Canonical files only.** `sankey_income.py` started standalone and was folded into
  `telegram_bot_optimized.py` / `dashboard.py` (commit `35015c0`). Analysis tools in `tools/`
  are fine; a second copy of engine LOGIC is not.
- **Never copy a constant out of the engine.** `measure_signal_base_rates.py` hardcoded the
  grading thresholds with a comment saying "must mirror `_score_signal`" — a promise a comment
  cannot keep. It now imports them, and refuses to run rather than guess.
- **Verify numbers, not that they render.** The trend columns rendered perfectly and were
  wrong for every US ticker.
- **A silent `except` around a fallback hides a dead fallback.** The CBOE throttle-buster
  returned `None` for every ticker for weeks — a `date > datetime` TypeError swallowed whole.
- **Test the path the product uses.** A gate that exercised the CDN fallback said nothing
  about the primary OpenBB pull.
- **Streamlit grids are canvas.** `<th>` and `[role=columnheader]` are the accessibility
  layer only; CSS cannot style what you see.
- **Changing a cached function's return SHAPE requires bumping the cache key**, or
  `@st.cache_data` serves the old shape and the page dies with a type error.
- **Don't test bot output through `python -c`** — the console is cp1252 and mangles em-dashes
  and emoji. Write a UTF-8 file and run that.
- **The engine speaks Telegram HTML.** Anything rendering it in Streamlit markdown must go
  through `_tg_md()`.

## Self-improvement status — read before adding an agent

The predict → grade → reweight loop runs (28,164 graded fires). The fourth step, an agent
rewriting its own logic, is **deliberately absent**: nothing has cleared the multiplicity
bar. Bonferroni critical **t = 3.03**, best observed **2.63**, and the three nominal hits
overlap on 63–92% of their fires — one finding counted three times.

Adding a self-edit loop now would fit noise faster. Re-run
`tools/measure_signal_base_rates.py` as the sample grows; judge on the Bonferroni column,
never the nominal one.
