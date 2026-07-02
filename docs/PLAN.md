# PLAN — remaining work (source of truth)

> Cross-model/session handoff. Keep this current; `LOG.md` records what's done, `NEXT.md` holds the one-glance switch-over note.
> Worked by `/task-loop` (loop-engineering): pick top unchecked → implement → verify → commit `loop: …` → tick here.

## Goal
Options-trading edge system: Telegram bot + dashboard + our own capture-forward options DB
(bid/ask/IV/delta), every signal validated against DB history — less API dependence, more provable edge.

## Open tasks
- [ ] (user) Parallel-test OpenBB vs yfinance for 3–5 days — daily `python NYSE_OpenBB.py --universe openbb_universe` then `--compare`; pass = ≥95% agreement on overlapping contracts
- [ ] (gated: parallel test passes) Production migration to OpenBB — wire capture into `run_all_offhours.py`, ALTER `options_daily` +bid/ask/iv/delta +source, per-ticker yfinance fallback, pin `openbb==`, keep `--compare` as daily sanity job, retire 4-hr options leg
- [ ] Profile remaining `NYSE_YFin.py` stages — instrument per-stage timing logs to see where the 4 hrs go beyond the options fetch
- [ ] (gated: ~2 wks of scn_* fires with t+5 outcomes) First scanner backtest read — hit-rate + avg fwd vs baseline for uoa/building/breakout/zrev/revert, persist to `signal_accuracy`, flag thin N
- [ ] (gated: ~1 mo of OpenBB bid/ask captures) Revive `/skew` + dispersion (#14) on real bid/ask instead of lastPrice
- [ ] Action Board daily Telegram digest — reuse `_ab_ideas()` sources bot-side; push top ⭐ consensus ideas each morning like the Earnings Radar job

## Constraints / decisions locked in
- CLAUDE.md rules win: edit `telegram_bot_optimized.py`/`dashboard.py` directly (no patch scripts), single-engine (dashboard imports the bot), dates MM-DD-YYYY sort trick, secrets never committed/printed, `US_data.db` never written by NYSE_OpenBB.py.
- "Tested" = validated vs DB history (hit-rate vs baseline), not "it runs".
- Commit to `main`, one atomic commit per completed task; nothing pushed to remote unless asked.

## Out of scope (for now)
- qlib port (own data-format project) · macro-event positioner (needs econ-calendar feed) · index-rebalance (corp-action feed) · gamma-scalp (tick data) · box-arb (borrow rates) · ETF-NAV (institutional data) · AlphaVantage premium backfill ($50/mo, optional).
