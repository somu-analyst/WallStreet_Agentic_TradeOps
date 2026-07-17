# NEXT — switch-over note (2026-07-16, late evening)

1. **Everything is LIVE**: bot restarted on latest code (universal _report formats, /premium,
   /add, morphing wizards, inline search, /terminal local-only). Dashboard fresh on 8502.
   Intraday lane supervised. EOD scheduler = BB primary, Yahoo fallback-only.
2. **User actions outstanding**: BotFather `/setinline` (for @bot ticker search) ·
   weekly offsite copy of `openbb_chains\*.parquet` (Google Drive/rclone setup deferred —
   needs user's one-time OAuth at the keyboard).
3. **Queue (user-gated)**: NSE India lane (design in PLAN §2, user said keep queued) ·
   heat/fade + skew backtest RERUNS (~2 wks data accruing; harness = backtests_p2_p3.py
   pattern, results table `backtest_summary`) · Mini App phase 2 (parked).
4. **Positions**: GOOG 100sh@167 (clock FROZEN, LT ≈ 2027-08-23) + GOOGL 375P/420C collar
   (Aug 21, covers Jul 22 ER) + AMD −2× 400P (Jul 31, before Aug 4 ER). UNH closed +$483.
5. Tax income default lives in DB `app_settings` (`/tax set 250k`). Backtest verdicts:
   revert VALIDATED (+2.7% t+5, 54% vs 49%); uoa/building direction FAILED (context only).
