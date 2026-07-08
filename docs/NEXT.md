# NEXT — one-glance switch-over note

> The single most useful thing for whoever (or whatever model) picks this up next. Overwrite each handoff.

**Right now:** OpenBB migration is in **parallel-validation**. The BB lane is self-contained and wired:
`NYSE_OpenBB.py` (capture) + `NYSE_OpenBB_derive.py` (self-contained bridge → options_daily/options_change/
stock_daily, same Yahoo schema) run each EOD via `run_all_offhours.py` **parallel to the Yahoo fetch,
non-fatal**. Bot + dashboard read `DB_PATH` which honors **env `NYSE_DB_PATH`** (default = Yahoo). Parity:
OI matches Yahoo **100% exact on clean EOD days** (07-06/07-07); derived change_OI/R1/S1 corr 0.9998.
Only 07-02 (first rough capture) diverges — one-off, rolls off.

**Do next (in order):**
1. Let the scheduler run BB in parallel a few nights (accrue clean consecutive captures).
2. Trial the bot on BB: `set NYSE_DB_PATH=C:\Users\srini\Options_chain_data\US_data_OpenBB.db` then launch;
   eyeball GEX/scanners/rotation. Unset to revert.
3. When confident → make BB primary (leave the env var set, or hardcode later).

**⚠️ Pending at cutover — the `_lib` split (DON'T forget):** bot + dashboard are fully BB-switchable, but
these still hardcode `US_data.db` and must be handled when BB becomes primary:
- `_lib/options_tracker.py`, `_lib/news_and_earnings.py`, `_lib/market_news_aggregator.py`,
  `_lib/event_writeup_bot_hooks.py` (+ `event_writeup_engine.py` uses a different env `US_DATA_DB`),
  and `NYSE_Telegram.py`.
- **Split rule:** MARKET-DATA reads (options_change/stock_daily) → follow `NYSE_DB_PATH`; but pin
  **USER STATE** (`trades`/positions, `event_journal`, `bookmarks`, news cache) to `US_data.db` — the BB
  DB holds STALE mirror copies of those, so a blanket flip would read stale positions/P&L. NOT a blanket
  find-replace.

**Watch out for:** `stock_daily` in BB needs the derive's `--stock` step (now in the scheduler) — without it,
spot/GEX read stale. Two vendors won't be byte-identical (vol differs on snapshot timing); don't chase
literal 100%. Cutover is the USER'S call — don't flip autonomously.
