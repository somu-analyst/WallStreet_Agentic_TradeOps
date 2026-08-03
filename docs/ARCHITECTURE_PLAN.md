# Architecture Plan — one backend, two front-ends

> Written 2026-08-02 as an audit + migration plan. **Nothing here has been executed.**
> Sections 1–2 were delivered in conversation; this file is the full record so the work can
> be analysed before any code moves.

**Measured baseline (2026-08-02)**

| | |
|---|---|
| `telegram_bot_optimized.py` | 34,969 lines · 440 logic fns · 282 handlers · **82 `st.` refs** |
| `dashboard.py` | 24,061 lines · 36 pages · 2,080 `st.*` calls · **0 telegram refs** |
| Bot functions the dashboard already calls | **81** |
| Telegram commands | **69** |
| Commands with a dashboard twin | **19** |
| Scheduled jobs (all inside the bot process) | **25** |
| Tests | **0** |

---

## 1. Current-state assessment

### Working
- **The data spine.** 734-ticker daily capture with real bid/ask/IV/delta, self-healing
  retries, verified parquet backup, offsite sync, `stock_history` to 1990. The expensive
  part is solid.
- **Engine shared between surfaces.** `dashboard.py` imports the bot and calls its scanners
  — 81 functions, no reimplementation. The instinct is right and already load-bearing.
- **Validation discipline.** Banned pooled t-stat, enforced walk-forward, mandatory random-
  signal sanity gate. On 2026-08-02 alone this withdrew two claims, killed one strategy idea
  before it was built, and caught a harness emitting 15% false positives.
- **Honest UI labelling.** POP marked model-output, UOA marked descriptive-not-predictive,
  GEX carrying its own p-value.

### Messy / duplicated
- **The bot file is four programs in one namespace** — data access, indicators, scanners,
  handlers, scheduler. The dashboard importing it for *logic* drags in handlers and startup
  paths it never uses. No seam to cut along.
- **The dashboard is a 24k-line top-down script.** 36 `if page ==` branches in one module
  flow. `_ab_ideas` was called 13k lines before definition — that panel had **never** worked
  on Command Center. Structural, not accidental: nothing enforces definition order.
- **Trading logic inside UI handlers.** The basket sizer (selection rule, EV ranking,
  concentration cap, lot scaling) is ~150 lines inside a Streamlit `if` branch. It decides
  position sizing and cannot be called from Telegram, tested, or backtested — verifying the
  2026-08-02 fix required reimplementing it in a scratch script. That is the tell.
- **Multiple surfaces per subject.** GEX had two dedicated pages + sections inside two other
  pages + `/gex` + the new co-pilot. Merged 2026-08-02, but it was one instance of a pattern.
- **Scanner output recomputed per render.** Nothing materialises it; `st.cache_data(ttl=300)`
  is the only thing between the operator and a full rescan.
- **Recommendation state split across 4 tables** — `hiprob_recs` (LIVE vs BACKFILL, never to
  be pooled), `signal_accuracy` (450 fires/day, mostly noise), `rec_basket(_legs)`, `trades`.
  No single "what am I in and why" view.

### Risky
- **No tests.** Verification is `py_compile` plus a house rule forcing a headless-browser DOM
  check. That rule exists *because* the system can't be tested otherwise — it is a workaround
  for missing architecture, costing minutes per change.
- **A UI reload can kill data collection.** Already happened: a write connection collided
  with the capture at 18:32:15, `database is locked`, capture died at 11%. `busy_timeout`
  patched it; the condition stands — **4 writers, one SQLite file, no coordination layer.**
- **The bot process owns too much** — it launches the dashboard, supervises the intraday lane,
  runs 25 jobs, and serves commands. Bot dies → collection supervision dies.
- **Silent failure is the idiom.** `except Exception: pass` / `return []` throughout. A broken
  feed is indistinguishable from a quiet news day. No health surface beyond `data_audit`.

**Bottom line:** not bad choices — a **containment** problem. Correct ideas implemented as
two enormous scripts, so nothing can be tested, reused, or safely changed.

---

## 2. Responsibility split

**The rule: duration and posture.**

| Surface | Owns | Test |
|---|---|---|
| **Telegram** | Alerts, go/no-go checks, approvals, quick lookups, EOD digest | <30s, one-way, mobile, standing up |
| **Streamlit** | Charts, basket sizing, backtests, portfolio review, research | Exploratory, multi-step, seated |
| **services/** | EOD pipeline, materialisation, archival, health | No human in the loop |
| **core/** | All maths, all strategy, all risk | Never imports a UI |

Applied to GEX: `/gexcheck` in Telegram (go/no-go at the desk), full blueprint + chart in
Streamlit, `_compute_gex` in `core/indicators/gex.py` called by both.

### Target layout

```
core/                       ← no `streamlit`, no `telegram` imports. CI-enforced.
  data/       db.py chains.py history.py      one connection policy: WAL, busy_timeout, RO handles
  indicators/ gex.py skew.py vol.py oi.py
  scanners/   uoa.py building.py breakout.py revert.py rs.py vrp.py
  strategy/   hiprob.py basket.py fills.py hedges.py     ← sizing lives HERE
  research/   walkforward.py ic.py backtest.py           ← already exists in tools/
  ops/        audit.py health.py archive.py
services/
  scheduler.py     EOD capture → derive → skew → digest, own process
  materialize.py   scanners run ONCE/day → scanner_results table
apps/
  streamlit_app/   pages/*.py — thin, reads core + scanner_results
  telegram_bot/    handlers/*.py — thin, same calls, different formatting
  formatters/      pipe_table / markdown / metrics — shared render layer
```

**The one constraint that makes it work:** `core/` may not import `streamlit` or `telegram`.
A single CI `grep` enforces it. That is what is missing today.

### What this fixes (observed bugs, not hypotheticals)

| Bug seen | Why it disappears |
|---|---|
| `_ab_ideas` NameError | `from core.scanners import ideas` — import order is the language's job |
| 20.9s Command Center | Scanners materialise once/day; page becomes a `SELECT` (~0.3s) |
| `database is locked` killing capture | One `core/data/db.py` owns WAL + timeouts + RO handles |
| Basket sizer untestable | `core/strategy/basket.py` callable from pytest, Streamlit, Telegram |
| Mandatory Playwright rule | Test `core/` directly; browser check only for visual changes |

---

## 3. Redundancy cleanup

### 3.1 Duplicate surfaces — 19 of 69 commands have a dashboard twin

Twins are **fine when the split is duration-based** and **waste when both are full features**.

| Command | Page twin | Verdict |
|---|---|---|
| `/gex` `/gexplan` `/gexcheck` | GEX Command | **Keep both** — `/gexcheck` is a 30s go/no-go; the page is exploration |
| `/wrap` | Market Wrap | **Keep both** — push vs read |
| `/plan` | Next-Day Exit Planner | **Keep both** — morning push vs seated review |
| `/board` | Action Board | **Telegram = summary only.** Full list is a page |
| `/spreads` `/wheel` `/momentum` `/rs` `/flow` `/rotation` | Scanner pages | **Telegram = top-3 + link.** Never the full table on mobile |
| `/paper` | Paper Trading | **Delete the Telegram side** — multi-step entry belongs on a page |
| `/watchlist` | Watchlist | **Delete the Telegram side** — editing on mobile is worse |
| `/live` | Live Position Predictor | **Different things sharing a name.** Rename one |
| `/cc` | (matched Signal Accuracy in error) | Name collision — audit |
| `/ic` `/rovalidate` `/pwindex` | — | **Move to `tools/`** — research, not ops |

**Rule to adopt:** Telegram never renders a table wider than a phone. It sends the top 3 and
a link. If an operator needs the full table, that is a Streamlit job.

### 3.2 Overlapping workflows
- **Recommendation state in 4 tables.** Collapse to one view: `core/strategy/book.py`
  exposing `open_positions()`, `recommendations(src)`, `basket(id)`. The LIVE/BACKFILL
  separation must survive — it is a correctness rule, not a preference.
- **Two backup paths.** `openbb_chains/` (capture writes) vs `archive_parquet/` (built
  2026-08-02, deleted same day as redundant). Keep `openbb_chains` + `--verify-existing`.
  **Already resolved.**
- **Fires vs Ideas vs Recs.** Three panels, escalating filtration, no stated relationship.
  Document as one funnel: 450 fires → 30 ideas → 9 consensus → N sized positions.

### 3.3 Repeated code paths
- **82 `st.` references inside the bot** — the actual layering violation. Small, mechanical.
- **`_exp_iso` (bot) vs `_exp_to_date` (dashboard)** — two date normalisers, one job.
- **Per-surface formatting** — `_pipe_table` for Telegram, `st.dataframe` for Streamlit,
  reimplemented per page. Belongs in `apps/formatters/`.
- **`_gex_spot` / `_last_price` / `_opex_spot`** — overlapping spot resolution.

### 3.4 Delete outright
- `tools/archive_parquet.py` export mode (keep `--verify-existing`) — duplicates the capture's
  own backup.
- Telegram-side `/paper` and `/watchlist` mutation flows.
- Any scanner with no measured edge that is presented as a *signal* rather than as context —
  currently `scn_revert`, `scn_zrev`, `gex` (directional), `left_skew`. Keep computing them;
  stop implying they predict.

---

## 4. Workflow redesign

### Operator day
```
pre-market   Telegram push: digest + FOMC/catalysts + "3 setups qualify"
             -> tap through to Streamlit only if something needs sizing
intraday     Telegram: /gexcheck TICKER call  -> GREEN/RED, one screen
             alerts only on STATE CHANGE, never on a timer
EOD          scheduler: capture -> derive -> skew -> materialize -> digest
             Telegram push: what filled, what expired, what needs action tomorrow
weekly       Streamlit: recperf, walk-forward re-tests, basket review
```

### Alert flow
Today ~25 jobs push independently. Target: **one edited status message per day** (already
proven in `1563870`) + genuine state-change alerts only. Every alert carries: what changed,
what it implies, what action is available.

### Manual approval flow
The gap worth closing. Today a recommendation appears on a page and the operator acts
elsewhere with no record. Target:

```
core/strategy -> proposal (structure, POP, capital, EV verdict, fill assumption)
              -> Telegram: [Approve] [Skip] [Size...]
              -> approval written to `decisions` with WHO/WHEN/WHY
              -> Streamlit shows the decision log next to outcomes
```
This produces the audit trail the system currently lacks, and makes "did I follow my own
rules?" answerable.

---

## 5. Refactoring priorities

### Refactor now (low risk, high leverage)
1. **Extract `core/`** — move the 81 dashboard-called functions behind their existing names,
   leave re-export shims in the bot. Zero behaviour change, fully reversible.
2. **CI guard** — `grep -r "import streamlit\|import telegram" core/` fails the build.
3. **`services/materialize.py`** — scanners once/day into `scanner_results`. Biggest
   operator-visible win; removes the remaining 7.8s from Command Center.
4. **One DB policy** in `core/data/db.py` — WAL, busy_timeout, read-only handles for UI.
   Directly prevents the incident that killed a capture.

### Refactor later
5. Remove the 82 `st.` refs from the bot.
6. Split `apps/streamlit_app/pages/` — one file per page, kills the definition-order bug class.
7. Collapse the 4 state tables behind `core/strategy/book.py`.
8. Approval flow + `decisions` table.
9. Move the scheduler out of the bot process.

### Remove entirely
10. Duplicate Telegram mutation flows (`/paper`, `/watchlist`).
11. Full-table Telegram output — top-3 + link.
12. `archive_parquet` export mode.

### Explicitly NOT now
- **Do not switch UI framework.** See §6.
- **Do not big-bang rewrite.** 45k untested lines making money decisions; a large refactor is
  how you lose a month.

---

## 6. Streamlit — keep it

The pain (22k-line reruns, NameError bugs, no testability) is caused by **logic living in the
UI**, not by Streamlit. Extract `core/` and a page becomes ~200 lines that query a table.

| Option | Verdict |
|---|---|
| **Streamlit** (current) | **Stay** — 2,080 widget calls is a large sunk cost |
| **Marimo** | Closest upgrade — reactive, no rerun model, git-friendly. Trial *after* `core/` |
| **Reflex / NiceGUI** | Real component model; weeks of work |
| **Dash / Panel** | Sideways move, more boilerplate |
| **FastAPI + React** | Correct at scale, wrong for a solo operator — you'd write TypeScript instead of trading logic |
| **Gradio** | No |

Reassess only once the UI is thin. The immediate win is **materialisation**, not a framework.

---

## 7. Final blueprint

```
                    ┌──────────────────────────────────────┐
   OpenBB / Yahoo ──▶│  services/scheduler.py               │
   CBOE intraday     │  capture → derive → skew →           │
                     │  materialize → digest                │
                     └───────────────┬──────────────────────┘
                                     │ writes
                     ┌───────────────▼──────────────────────┐
                     │  SQLite (WAL) + parquet archive      │
                     │  chains · history · recs · decisions │
                     │  scanner_results · audit             │
                     └───────────────┬──────────────────────┘
                                     │ reads (RO handles)
                     ┌───────────────▼──────────────────────┐
                     │  core/   data · indicators · scanners │
                     │          strategy · research · ops    │
                     │  NO streamlit. NO telegram.           │
                     └───────┬───────────────────┬───────────┘
                             │                   │
                ┌────────────▼──────┐   ┌────────▼─────────────┐
                │ apps/telegram_bot │   │ apps/streamlit_app   │
                │ alerts, go/no-go, │   │ charts, sizing,      │
                │ approvals, digest │   │ backtests, review    │
                │ <30s, mobile      │   │ exploratory, seated  │
                └───────────────────┘   └──────────────────────┘
                         both use apps/formatters/
```

**Invariants**
1. `core/` never imports a UI framework. CI-enforced.
2. One writer policy for the DB; UI gets read-only handles.
3. Scanners materialise on a schedule; surfaces read results.
4. Every strategy decision is recorded in `decisions` with who/when/why.
5. Telegram never renders a full table.
6. Anything choosing a parameter goes through `core/research/walkforward.py`.

---

## Open questions for the operator
1. **Approval flow** — do you want trade approval in Telegram, or is the dashboard enough?
2. **`/paper` and `/watchlist`** — confirm the Telegram sides can go.
3. **Scheduler process** — split out of the bot now, or after `core/` lands?
4. **Marimo trial** — worth an afternoon after extraction, or not interested?
5. **Scanner honesty** — demote the no-edge scanners (`scn_revert`, `scn_zrev`, directional
   `gex`, `left_skew`) from "signal" to "context" in the UI?
