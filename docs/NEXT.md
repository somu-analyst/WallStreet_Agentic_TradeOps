# NEXT — one-glance switch-over note

> The single most useful thing for whoever (or whatever model) picks this up next. Overwrite each handoff.

**Right now:** Market Radar (`/riskoff`) shipped + backtested + redesigned into a two-gauge model
(Turbulence = index put-flow, the only proven signal at QQQ t+5 corr +0.37 p<0.001; Direction =
weak low-confidence lean). All committed in HEAD; both files parse. See `docs/LOG.md` 2026-07-06.

**Do next:** Deploy — restart the bot (`python telegram_bot_optimized.py`) + rerun Streamlit to load
it; `git push` if using a remote. Then optionally re-run `backtests/backtest_pillars.py` as more
history accrues to confirm turbulence stays ✅ and direction hasn't flipped.

**Watch out for:** OpenBB is a PARALLEL test lane only — do NOT wire `NYSE_OpenBB*.py` or
`_fetch_openbb_history` into the live bot/dashboard (yfinance-only in the live path). Backtest window
is ~6mo of a single uptrend regime = low power; don't fit pillar weights to it (overfit risk).
