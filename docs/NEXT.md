# NEXT — one-glance switch-over note

> The single most useful thing for whoever (or whatever model) picks this up next. Overwrite each handoff.

**Right now:** **CUTOVER DONE — OpenBB is the PRIMARY DB.** `telegram_bot_optimized.py`, `dashboard.py`,
and the 5 `_lib` modules all default `DB_PATH` → `US_data_OpenBB.db` (734 tickers + real IV/greeks),
overridable via env `NYSE_DB_PATH` (point to `US_data.db` to revert to Yahoo). Bot-state tables
(trades/positions, journals, bookmarks, signal_accuracy, momentum_ranks, watch tables, fundamentals_cache)
were **synced US_data.db → BB** so positions/history are correct. Verified: bot reads BB, positions intact
(GOOGL×2, UNH), 736-ticker universe, rotation/GEX/building all work.

**Operational dependency (important):** BB market data (options_change/stock_daily) is refreshed nightly by
`NYSE_OpenBB.py` + `NYSE_OpenBB_derive.py --stock` in `run_all_offhours.py` (parallel to Yahoo, non-fatal).
If the OpenBB capture fails a night, BB market data is stale with **no auto-fallback** — Yahoo's US_data.db
still updates but isn't read. Watch the derive log; if BB goes stale, revert with `set NYSE_DB_PATH=...US_data.db`.

**Known/benign:** option OHLC columns (call_open/high/low/close, R12/S12, money_coi_*, vol_rank_*) are NULL in
BB — OpenBB has no per-contract OHLC bars; the bot uses NONE of them (R1/S1 from lastPrice are 100% populated).

**Do next (optional):**
- Restart the bot + rerun Streamlit to load the cutover.
- `NYSE_Telegram.py` (EOD report) still reads US_data.db — flip to env-aware if you want the daily report on BB too.
- Consider a freshness auto-fallback (if BB's latest options_change < Yahoo's, use Yahoo) for robustness.

**Signal research finding (5y backtest):** MAGNITUDE of >1% index moves is predictable (VIX rank-IC +0.365;
P(>1% move) 11%→50% across VIX quintiles); DIRECTION is not (all IC≈0, 51% coin-flip). Build/keep the
turbulence(size) engine; don't chase index direction. Directional edge is cross-sectional (Rotation, validated).
