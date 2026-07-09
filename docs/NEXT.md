# NEXT — one-glance switch-over note

> The single most useful thing for whoever picks this up next. Overwrite each handoff.

**Right now:** **OpenBB is the PRIMARY DB and the perf/UX overhaul is shipped.** Everything below is on
`main` (pushed 2026-07-09).

**Live state:**
- **DB cutover done** — bot + dashboard + 5 `_lib` modules default `DB_PATH` → `US_data_OpenBB.db`
  (734 tickers + IV/greeks); reversible via env `NYSE_DB_PATH` → `US_data.db`. State synced (positions intact).
- **Serving layer** `daily_ticker_summary` (built nightly by `NYSE_OpenBB_derive.build_serving_layer`, incl.
  `gex_notional`) → overview/scanner reads ~2–50ms (was ~2s). Accessors in dashboard: `load_ticker_summary`,
  `load_oi_for_ticker_date`, `tickers_for_date`. Speed sweep repointed 8 heavy sites (backtest loops 40s→20ms).
- **Scanners** cover ~453 liquid names — `SCAN_UNIVERSE` is DB-derived (total OI ≥ 10k) + core, at bot import.
- **Sidebar 🎚️ Scan Universe sliders**: OI floor (instant), beta, market cap (fundamentals via
  `fundamentals_cache`; one-time "Load fundamentals" button). Universe in `st.session_state['scan_universe']`;
  wired into the strategy scanner. **TODO:** wire into more scanner pages if wanted.
- **Columns**: option OHLC populated (=lastPrice, matches Yahoo); every DTE table column now shows the expiry
  date; per-leg detail has Earnings + Ex-Div (`_next_events`).

**Deploy:** restart the bot (`python telegram_bot_optimized.py`) + rerun Streamlit.

**Watch out:**
- BB market data depends on the nightly OpenBB derive (`run_all_offhours.py`, non-fatal, no auto-fallback).
  If a capture fails, BB is stale — the derive log shows it; revert with `set NYSE_DB_PATH=...US_data.db`.
- `NYSE_Telegram.py` (EOD report) still reads `US_data.db` — flip to env-aware if you want it on BB too.
- Two DTE-heavy pages (6192/8874 in dashboard) intentionally still full-load — they need `oi_anomalies`
  across all tickers.

**Validated finding (5y):** >1% index-move MAGNITUDE is predictable (VIX rank-IC +0.365; P(>1%) 11%→50%
across VIX quintiles); DIRECTION is not (IC≈0). Build the turbulence/size engine; don't chase index direction.
